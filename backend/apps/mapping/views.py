"""Views for the mapping app.

Two distinct mapping mutation surfaces exist, by design:

* The receipt-line map action — ``POST /api/receipts/{id}/lines/{line_id}/map/``
  — is implemented in the receipts app because its URL is nested under a receipt
  line (see ``apps.receipts.views.ReceiptLineMapView``); it calls
  ``apps.mapping.services.remember_mapping``.
* The **admin mappings-management API** — ``/api/mappings/`` — lives here. It
  lets an admin audit, search, re-target and delete the remembered
  :class:`~apps.mapping.models.ArticleMapping` rows directly (the "memory" of the
  system), independent of any receipt.

:class:`ArticleMappingViewSet` provides list / create / partial-update / destroy
for ``/api/mappings/``. Every action is admin-only (``IsAuthenticated`` +
``IsAdmin``) because editing remembered mappings changes how *future* invoices
auto-match — an operator must not silently rewrite that memory.

WHY normalize on write here rather than rely on ``remember_mapping``:
    ``remember_mapping`` bumps ``times_used`` on every call (it models a *use* of
    the mapping during the receipt flow). Admin edits are curation, not uses, so
    they must NOT inflate the usage counter. The viewset therefore writes the
    normalized SKU via ``update_or_create`` directly and leaves ``times_used``
    alone (preserving it across re-targets).
"""

from __future__ import annotations

import logging

from django.db.models import Q, QuerySet
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from apps.accounts.permissions import IsAdmin

from .models import ArticleMapping
from .serializers import (
    ArticleMappingReadSerializer,
    ArticleMappingWriteSerializer,
)
from .services import normalize_sku

logger = logging.getLogger(__name__)

# Cap the list size: the admin table browses recent/high-value mappings, not the
# entire (potentially large) memory. The most-used mappings surface first via the
# ``-times_used`` ordering, so a cap keeps the mobile payload bounded without
# hiding what matters. Combine with ``?q``/``?supplier`` to narrow further.
LIST_LIMIT = 200


def _actor(request: Request) -> str:
    """Return a stable string identifier for the requesting admin.

    Used to stamp ``created_by`` on freshly created mappings for audit (matches
    the receipts app's convention: email first, then username).

    Args:
        request: The authenticated DRF request.

    Returns:
        The user's email if set, otherwise the username, otherwise ``""``.
    """

    user = getattr(request, "user", None)
    if user is None:
        return ""
    return getattr(user, "email", "") or getattr(user, "username", "") or ""


@extend_schema(tags=["mappings"])
class ArticleMappingViewSet(viewsets.ViewSet):
    """Admin CRUD over remembered article mappings (``/api/mappings/``).

    A thin :class:`~rest_framework.viewsets.ViewSet` (not ``ModelViewSet``)
    because create and update have bespoke logic — SKU normalization plus an
    ``update_or_create`` keyed on the unique ``(supplier, normalized sku)`` pair —
    that does not map cleanly onto the generic mixins. Listing this explicitly
    keeps each action's behavior obvious.

    Routes produced by the DRF ``DefaultRouter`` (basename ``mapping``):

    * ``GET    /api/mappings/``        — :meth:`list` (filters: ``?supplier``, ``?q``)
    * ``POST   /api/mappings/``        — :meth:`create`
    * ``PATCH  /api/mappings/{pk}/``   — :meth:`partial_update`
    * ``DELETE /api/mappings/{pk}/``   — :meth:`destroy`

    All actions require an authenticated **admin** (the Valeraup product role on
    the profile, via :class:`IsAdmin`) — not Django's ``is_staff``.
    """

    permission_classes = [IsAuthenticated, IsAdmin]

    def _base_queryset(self) -> QuerySet[ArticleMapping]:
        """Return the join-optimized base queryset for mapping reads.

        ``select_related`` pulls the supplier and product in one query so
        serializing a page of rows (each nesting both) does not issue N+1
        lookups.

        Returns:
            A :class:`~django.db.models.QuerySet` of all mappings with supplier
            and product pre-joined.
        """

        return ArticleMapping.objects.select_related("supplier", "our_product")

    @extend_schema(
        summary="Список збережених маппінгів (адмін)",
        parameters=[
            OpenApiParameter(
                name="supplier",
                description="Фільтр за id постачальника.",
                required=False,
                type=int,
            ),
            OpenApiParameter(
                name="q",
                description=(
                    "Пошук за артикулом постачальника, sku або назвою товару."
                ),
                required=False,
                type=str,
            ),
        ],
        responses={200: ArticleMappingReadSerializer(many=True)},
    )
    def list(self, request: Request) -> Response:
        """List remembered mappings, most-used first, capped and filterable.

        Query params:
            supplier: Optional supplier id to restrict the namespace.
            q: Optional case-insensitive text matched against the supplier SKU,
                the product SKU, and the product name.

        Args:
            request: Authenticated admin request.

        Returns:
            ``200`` with up to :data:`LIST_LIMIT` serialized mappings ordered by
            descending ``times_used`` (the most valuable memory first).
        """

        queryset = self._base_queryset()

        supplier_id = request.query_params.get("supplier")
        if supplier_id:
            # Tolerate a non-numeric value gracefully: treat it as "no match"
            # rather than 500ing on a bad query string.
            try:
                queryset = queryset.filter(supplier_id=int(supplier_id))
            except (TypeError, ValueError):
                queryset = queryset.none()

        q = (request.query_params.get("q") or "").strip()
        if q:
            queryset = queryset.filter(
                Q(supplier_sku__icontains=q)
                | Q(our_product__sku__icontains=q)
                | Q(our_product__name__icontains=q)
            )

        queryset = queryset.order_by("-times_used", "supplier_sku")[:LIST_LIMIT]
        serializer = ArticleMappingReadSerializer(queryset, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Створити/перепризначити маппінг (адмін)",
        request=ArticleMappingWriteSerializer,
        responses={201: ArticleMappingReadSerializer},
    )
    def create(self, request: Request) -> Response:
        """Create or re-target a mapping for ``(supplier, normalized sku)``.

        Validates the flat write payload, normalizes the SKU, then runs
        ``update_or_create`` on the unique ``(supplier, supplier_sku_normalized)``
        pair so submitting the same SKU twice repoints the existing row instead of
        raising an integrity error. Unlike the receipt-flow
        ``remember_mapping``, this does **not** touch ``times_used`` — admin
        curation is not a "use".

        Args:
            request: Authenticated admin request with
                ``{supplier, supplier_sku, our_product_id}``.

        Returns:
            ``201`` with the created/updated mapping in the nested read shape.
        """

        serializer = ArticleMappingWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        supplier = serializer.validated_data["supplier"]
        supplier_sku = serializer.validated_data["supplier_sku"]
        our_product_id = serializer.validated_data["our_product_id"]

        normalized = normalize_sku(supplier_sku)

        # Build the ``defaults`` up front so the ``created_by`` decision is clear:
        # stamp the author ONLY when no row yet exists for this
        # (supplier, normalized sku) — an admin re-targeting an existing mapping
        # must never overwrite its original author. Check existence before the
        # upsert so ``update_or_create`` can't have created the row first.
        is_new = not ArticleMapping.objects.filter(
            supplier=supplier, supplier_sku_normalized=normalized
        ).exists()
        defaults = {
            "supplier_sku": supplier_sku,
            "our_product_id": our_product_id,
        }
        if is_new:
            defaults["created_by"] = _actor(request)

        mapping, created = ArticleMapping.objects.update_or_create(
            supplier=supplier,
            supplier_sku_normalized=normalized,
            defaults=defaults,
        )

        logger.info(
            "mapping_admin_upserted",
            extra={
                "supplier_id": supplier.pk,
                "normalized_sku": normalized,
                "our_product_id": our_product_id,
                "mapping_id": mapping.pk,
                "was_created": created,
            },
        )
        read = ArticleMappingReadSerializer(
            self._base_queryset().get(pk=mapping.pk)
        )
        return Response(read.data, status=status.HTTP_201_CREATED)

    @extend_schema(
        summary="Оновити маппінг (перепривʼязати товар / змінити sku) (адмін)",
        request=ArticleMappingWriteSerializer,
        responses={200: ArticleMappingReadSerializer},
    )
    def partial_update(self, request: Request, pk: int) -> Response:
        """Patch a mapping: re-target the product and/or re-normalize its SKU.

        Partial by design — an admin may send only ``our_product_id`` (the common
        "re-bind" case) or only ``supplier_sku`` (correct a typo, which re-derives
        ``supplier_sku_normalized``), or both. ``times_used``, ``created_by`` and
        ``created_at`` are immutable here.

        WHY guard the re-normalized SKU against collisions:
            The model is unique on ``(supplier, supplier_sku_normalized)``. If a
            new SKU normalizes onto another existing mapping for the same
            supplier, saving would raise an IntegrityError; we surface that as a
            clean ``409`` instead.

        Args:
            request: Authenticated admin request with a subset of the write
                fields. ``supplier`` is ignored if present — a mapping cannot
                change which supplier namespace it belongs to.
            pk: Primary key of the mapping to update.

        Returns:
            ``200`` with the updated mapping (nested read shape). ``404`` if the
            mapping is absent, ``409`` if the new SKU collides.
        """

        from django.db import IntegrityError
        from django.shortcuts import get_object_or_404

        mapping = get_object_or_404(self._base_queryset(), pk=pk)

        # Re-target product (validated to exist).
        if "our_product_id" in request.data:
            product_id = request.data.get("our_product_id")
            serializer = ArticleMappingWriteSerializer(
                data={
                    "supplier": mapping.supplier_id,
                    "supplier_sku": mapping.supplier_sku,
                    "our_product_id": product_id,
                },
                partial=True,
            )
            serializer.is_valid(raise_exception=True)
            mapping.our_product_id = serializer.validated_data["our_product_id"]

        # Re-normalize SKU.
        update_fields = ["our_product"]
        if "supplier_sku" in request.data:
            new_sku = (request.data.get("supplier_sku") or "")
            normalized = normalize_sku(new_sku)
            if not normalized:
                return Response(
                    {"detail": "Артикул не може бути порожнім."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            mapping.supplier_sku = new_sku
            mapping.supplier_sku_normalized = normalized
            update_fields += ["supplier_sku", "supplier_sku_normalized"]

        try:
            mapping.save(update_fields=update_fields)
        except IntegrityError:
            return Response(
                {
                    "detail": (
                        "Такий артикул уже зіставлено для цього постачальника."
                    )
                },
                status=status.HTTP_409_CONFLICT,
            )

        logger.info(
            "mapping_admin_updated",
            extra={
                "mapping_id": mapping.pk,
                "supplier_id": mapping.supplier_id,
                "our_product_id": mapping.our_product_id,
                "fields": update_fields,
            },
        )
        read = ArticleMappingReadSerializer(
            self._base_queryset().get(pk=mapping.pk)
        )
        return Response(read.data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Видалити маппінг (адмін)",
        responses={204: None},
    )
    def destroy(self, request: Request, pk: int) -> Response:
        """Delete a remembered mapping.

        Removing the row forgets the auto-match for ``(supplier, sku)``: future
        invoices with that SKU fall back to ``unmapped`` until re-mapped. Safe to
        call — it never cascades into receipts (lines reference the product
        directly, not the mapping).

        Args:
            request: Authenticated admin request.
            pk: Primary key of the mapping to delete.

        Returns:
            ``204 No Content``. ``404`` if the mapping does not exist.
        """

        from django.shortcuts import get_object_or_404

        mapping = get_object_or_404(ArticleMapping, pk=pk)
        supplier_id = mapping.supplier_id
        mapping.delete()

        logger.info(
            "mapping_admin_deleted",
            extra={"mapping_id": int(pk), "supplier_id": supplier_id},
        )
        return Response(status=status.HTTP_204_NO_CONTENT)
