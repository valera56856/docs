"""Views for the catalog app.

Implements:

* ``GET  /api/products/search/?q=`` — search :class:`OurProduct` by SKU or name
  for the manual-mapping dropdown (:class:`ProductSearchView`).
* ``POST /api/sync/catalog/`` — admin-only trigger that enqueues the Celery
  catalog-sync task (:class:`CatalogSyncView`).
* ``GET/PUT /api/settings/salesdrive/`` — admin-only read/update of the
  DB-configured SalesDrive YML URL plus catalog status
  (:class:`SalesDriveSettingsView`).
* ``POST /api/settings/salesdrive/test/`` — admin-only "test connection" that
  probes a YML URL without writing (:class:`SalesDriveTestView`).
"""

from __future__ import annotations

import logging

from django.db.models import Max, Q
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.generics import ListAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsAdmin

from .models import IntegrationSettings, OurProduct
from .serializers import (
    CatalogSyncResultSerializer,
    OurProductSerializer,
    SalesDriveSettingsReadSerializer,
    SalesDriveSettingsSerializer,
    SalesDriveTestResultSerializer,
)
from .services import probe_catalog_yml

logger = logging.getLogger(__name__)

# Cap result size: the dropdown only needs a handful of candidates, and an
# unbounded LIKE scan over the whole catalog would be wasteful on mobile.
SEARCH_LIMIT = 20


def _salesdrive_settings_payload() -> dict:
    """Build the SalesDrive settings read shape (config + catalog status).

    Combines the stored YML URL with two derived figures so the Settings UI can
    render everything it needs in one response:

    * ``last_synced`` — the most recent :attr:`OurProduct.last_synced` across the
      whole cache (``None`` if the catalog has never been synced).
    * ``product_count`` — how many products are cached right now.

    Returns:
        A dict ``{"salesdrive_yml_url", "last_synced", "product_count"}`` matching
        :class:`SalesDriveSettingsReadSerializer`.
    """

    config = IntegrationSettings.load()
    last_synced = OurProduct.objects.aggregate(value=Max("last_synced"))["value"]
    product_count = OurProduct.objects.count()
    return {
        "salesdrive_yml_url": config.salesdrive_yml_url,
        "last_synced": last_synced,
        "product_count": product_count,
    }


@extend_schema(
    summary="Пошук товарів каталогу",
    description=(
        "Пошук OurProduct за артикулом (sku) або назвою для випадаючого "
        "списку маппінгу. Порожній запит повертає порожній список."
    ),
    parameters=[
        OpenApiParameter(
            name="q",
            description="Підрядок для пошуку за sku або name.",
            required=False,
            type=str,
        ),
    ],
    tags=["catalog"],
)
class ProductSearchView(ListAPIView):
    """Search catalog products by SKU or name (``GET /api/products/search/``).

    The ``q`` query parameter is matched case-insensitively against both ``sku``
    and ``name``. Results are capped at :data:`SEARCH_LIMIT`. An empty/blank query
    returns an empty list (so the dropdown shows nothing until the user types).
    """

    serializer_class = OurProductSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None

    def get_queryset(self):
        """Return up to :data:`SEARCH_LIMIT` products matching ``q``.

        Returns:
            QuerySet[OurProduct]: Matching products ordered by SKU. Empty when no
                ``q`` is supplied.
        """

        q = self.request.query_params.get("q", "").strip()
        if not q:
            return OurProduct.objects.none()
        return (
            OurProduct.objects.filter(Q(sku__icontains=q) | Q(name__icontains=q))
            .order_by("sku")[:SEARCH_LIMIT]
        )


class CatalogSyncView(APIView):
    """Trigger a SalesDrive catalog sync (``POST /api/sync/catalog/``).

    Admin-only. Enqueues the Celery task that fetches and parses the SalesDrive
    YML export and upserts :class:`OurProduct` rows, then returns the task id so
    the caller can poll progress. The actual sync runs out-of-band on a worker.

    ``admin`` here is the Valeraup product role on the user's
    :class:`~apps.accounts.models.Profile` (see :class:`IsAdmin`), *not* Django's
    ``is_staff`` flag — catalog sync is a product-admin action.
    """

    permission_classes = [IsAuthenticated, IsAdmin]

    @extend_schema(
        request=None,
        responses={202: CatalogSyncResultSerializer},
        summary="Запустити синхронізацію каталогу (адмін)",
        tags=["catalog"],
    )
    def post(self, request: Request) -> Response:
        """Enqueue the catalog-sync Celery task.

        Args:
            request: Authenticated admin request. Body is ignored — the YML URL
                comes from ``settings.SALESDRIVE_YML_URL`` inside the task.

        Returns:
            ``202 Accepted`` with ``{"task_id", "detail"}``.

        Notes:
            The task is imported lazily so this module stays importable even
            before the catalog ``tasks.py`` (written by another agent) lands.
            ``.delay()`` returns immediately; the sync itself happens on a worker.
        """

        from .tasks import sync_catalog_task

        async_result = sync_catalog_task.delay()
        logger.info(
            "catalog_sync_enqueued",
            extra={"task_id": async_result.id, "user_id": request.user.pk},
        )
        return Response(
            {
                "task_id": async_result.id,
                "detail": "Синхронізацію каталогу поставлено в чергу.",
            },
            status=status.HTTP_202_ACCEPTED,
        )


class SalesDriveSettingsView(APIView):
    """Read/update the SalesDrive integration settings (admin-only).

    Backs ``GET/PUT /api/settings/salesdrive/``. The response shape is the same
    for both verbs (config + derived catalog status), so the UI can re-render
    from the ``PUT`` reply without a follow-up ``GET``.

    ``admin`` here is the Valeraup product role on the user's profile (see
    :class:`IsAdmin`), not Django's ``is_staff`` — managing integrations is a
    product-admin action.
    """

    permission_classes = [IsAuthenticated, IsAdmin]

    @extend_schema(
        responses={200: SalesDriveSettingsReadSerializer},
        summary="Отримати налаштування SalesDrive (адмін)",
        tags=["catalog"],
    )
    def get(self, request: Request) -> Response:
        """Return the stored YML URL plus catalog status.

        Args:
            request: Authenticated admin request.

        Returns:
            ``200 OK`` with ``{salesdrive_yml_url, last_synced, product_count}``.
        """

        payload = _salesdrive_settings_payload()
        serializer = SalesDriveSettingsReadSerializer(payload)
        return Response(serializer.data)

    @extend_schema(
        request=SalesDriveSettingsSerializer,
        responses={200: SalesDriveSettingsReadSerializer},
        summary="Зберегти URL YML SalesDrive (адмін)",
        tags=["catalog"],
    )
    def put(self, request: Request) -> Response:
        """Persist the YML URL onto the :class:`IntegrationSettings` singleton.

        A blank URL is accepted and clears the stored value (the sync then falls
        back to ``settings.SALESDRIVE_YML_URL``).

        Args:
            request: Authenticated admin request with body
                ``{"salesdrive_yml_url": str}``.

        Returns:
            ``200 OK`` with the same read shape as :meth:`get`.
        """

        serializer = SalesDriveSettingsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        config = IntegrationSettings.load()
        config.salesdrive_yml_url = serializer.validated_data.get(
            "salesdrive_yml_url", ""
        )
        config.save()
        logger.info(
            "salesdrive_settings_saved",
            extra={
                "user_id": request.user.pk,
                "has_url": bool(config.salesdrive_yml_url),
            },
        )

        payload = _salesdrive_settings_payload()
        return Response(SalesDriveSettingsReadSerializer(payload).data)


class SalesDriveTestView(APIView):
    """Test a SalesDrive YML URL without saving (admin-only).

    Backs ``POST /api/settings/salesdrive/test/``. Probes the provided URL (or
    the stored one if the body omits it) by fetching and parsing the export, then
    reports how many products it contains.

    WHY this always returns HTTP 200:
        A bad URL / unreachable host / malformed YML is an expected *result* of a
        connectivity test, not a server fault. Returning 200 with
        ``{"ok": false, "error": ...}`` lets the UI show a friendly inline message
        instead of a generic network/500 error — so failures never propagate as
        5xx from this endpoint.
    """

    permission_classes = [IsAuthenticated, IsAdmin]
    # Rate-limit the connectivity probe (H1): it triggers an outbound fetch, so
    # cap it at the ``salesdrive_test`` rate to blunt its use as an SSRF probe.
    throttle_scope = "salesdrive_test"

    @extend_schema(
        request=SalesDriveSettingsSerializer,
        responses={200: SalesDriveTestResultSerializer},
        summary="Перевірити підключення SalesDrive (адмін)",
        tags=["catalog"],
    )
    def post(self, request: Request) -> Response:
        """Probe a YML URL and report success/failure.

        Uses ``salesdrive_yml_url`` from the body when present and non-blank,
        otherwise the stored :class:`IntegrationSettings` value. A missing URL is
        reported as a failed test (not a validation error) for a uniform UI.

        Args:
            request: Authenticated admin request with optional body
                ``{"salesdrive_yml_url": str}``.

        Returns:
            ``200 OK`` with ``{ok, product_count, error}``. ``ok`` is ``False`` and
            ``error`` carries a GENERIC message on any fetch/parse failure.

        Notes:
            The client-facing ``error`` is intentionally generic (H3). Echoing
            ``str(exc)`` would leak internal detail (resolved hosts, redirect
            targets, parser internals) and turn this admin endpoint into an SSRF
            oracle — distinguishing "blocked private IP" from "connection
            refused" from "bad XML" probes the internal network. The full
            exception is logged server-side for operators instead.
        """

        serializer = SalesDriveSettingsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        provided = serializer.validated_data.get("salesdrive_yml_url") or ""
        yml_url = provided or IntegrationSettings.load().salesdrive_yml_url

        # Generic, non-leaky message returned to the client on ANY failure.
        generic_error = "Не вдалося підключитися до SalesDrive"

        try:
            if not yml_url:
                # No URL anywhere → surface a friendly "result" rather than 400.
                raise ValueError("URL YML не вказано")
            result = probe_catalog_yml(yml_url)
        except Exception as exc:  # noqa: BLE001 - any failure is a test result
            # Log the real cause server-side (operators need it to debug); the
            # response stays generic so it cannot be used as an SSRF/network
            # oracle. Keep HTTP 200 — a failed test is a result, not a 5xx.
            logger.info(
                "salesdrive_settings_test_failed",
                extra={"user_id": request.user.pk, "error": str(exc)},
            )
            return Response(
                {"ok": False, "product_count": None, "error": generic_error}
            )

        logger.info(
            "salesdrive_settings_test_ok",
            extra={
                "user_id": request.user.pk,
                "product_count": result["product_count"],
            },
        )
        return Response(
            {"ok": True, "product_count": result["product_count"], "error": None}
        )
