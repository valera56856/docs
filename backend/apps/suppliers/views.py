"""Views for the suppliers app.

Exposes the supplier directory as a DRF ``ModelViewSet`` so the designed PWA can
manage vendors directly (no Django admin round-trip):

* ``GET    /api/suppliers/``        list suppliers (active-only by default).
* ``POST   /api/suppliers/``        create a supplier.
* ``GET    /api/suppliers/{id}/``   retrieve one supplier.
* ``PUT/PATCH /api/suppliers/{id}/`` update a supplier.
* ``DELETE /api/suppliers/{id}/``   delete a supplier (guarded — see below).

WHY a split permission model: operators must keep *reading* the active-supplier
list to pick a vendor when photographing an invoice, but only admins may mutate
the directory. The viewset therefore grants list/retrieve to any authenticated
user and gates create/update/destroy behind :class:`IsAdmin`.

WHY ``include_inactive`` defaults off: the receipt-create picker must never offer
a retired supplier, so ``GET /api/suppliers/`` returns ``is_active=True`` rows
only. The admin management screen opts in with ``?include_inactive=true`` to also
see (and reactivate) deactivated suppliers.

WHY ``destroy`` may answer 409: ``Receipt.supplier`` is ``on_delete=PROTECT``, so
deleting a supplier that has historical receipts raises
:class:`~django.db.models.ProtectedError`. We translate that into a friendly 409
telling the admin to deactivate instead of hard-deleting — preserving the audit
trail rather than letting the request 500.
"""

from __future__ import annotations

from django.db.models import ProtectedError, QuerySet
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import status, viewsets
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from apps.accounts.permissions import IsAdmin

from .models import Supplier
from .serializers import SupplierSerializer

# Query-param values treated as "yes" for the ``include_inactive`` toggle. We
# accept the common truthy spellings a client might send so the contract is
# forgiving (``?include_inactive=true`` / ``1`` / ``yes`` all work).
_TRUTHY = frozenset({"1", "true", "t", "yes", "y", "on"})


@extend_schema_view(
    list=extend_schema(
        summary="Список постачальників",
        description=(
            "Повертає постачальників, відсортованих за назвою. За замовчуванням "
            "лише активні (is_active=True). Передайте ?include_inactive=true, щоб "
            "побачити також деактивованих (екран керування для адміністратора)."
        ),
        tags=["suppliers"],
    ),
    retrieve=extend_schema(summary="Постачальник", tags=["suppliers"]),
    create=extend_schema(summary="Створити постачальника", tags=["suppliers"]),
    update=extend_schema(summary="Оновити постачальника", tags=["suppliers"]),
    partial_update=extend_schema(
        summary="Частково оновити постачальника", tags=["suppliers"]
    ),
    destroy=extend_schema(
        summary="Видалити постачальника",
        description=(
            "Видаляє постачальника. Якщо існують повʼязані накладні "
            "(Receipt.supplier=PROTECT), повертає 409 — деактивуйте замість "
            "видалення, щоб зберегти історію."
        ),
        tags=["suppliers"],
    ),
)
class SupplierViewSet(viewsets.ModelViewSet):
    """Full CRUD for :class:`~apps.suppliers.models.Supplier`.

    Reads (``list``/``retrieve``) are open to any authenticated user so operators
    can pick a supplier; writes (``create``/``update``/``partial_update``/
    ``destroy``) require the ``admin`` role via :class:`IsAdmin`.
    """

    queryset = Supplier.objects.all()
    serializer_class = SupplierSerializer

    def get_permissions(self) -> list[BasePermission]:
        """Return the permission instances for the current action.

        List and retrieve only require authentication (operators read the active
        picker); all mutating actions additionally require the ``admin`` role.

        Returns:
            The permission instances DRF should enforce for ``self.action``.
        """

        if self.action in {"list", "retrieve"}:
            permission_classes: list[type[BasePermission]] = [IsAuthenticated]
        else:
            permission_classes = [IsAuthenticated, IsAdmin]
        return [permission() for permission in permission_classes]

    def get_queryset(self) -> QuerySet[Supplier]:
        """Return suppliers ordered by name, filtered for the ``list`` action.

        For ``list`` we hide inactive suppliers unless the caller opts in with a
        truthy ``include_inactive`` query param, so the operator picker only ever
        sees active vendors while the admin screen can request the full set.
        Detail/mutating actions operate over the unfiltered base queryset so an
        admin can still retrieve, update or delete an inactive supplier by id.

        Returns:
            QuerySet[Supplier]: Suppliers ordered alphabetically by ``name``,
            optionally filtered to active-only for the list action.
        """

        queryset = Supplier.objects.all()
        if self.action == "list":
            include_inactive = self.request.query_params.get("include_inactive", "")
            if include_inactive.strip().lower() not in _TRUTHY:
                queryset = queryset.filter(is_active=True)
        return queryset.order_by("name")

    def destroy(self, request: Request, *args: object, **kwargs: object) -> Response:
        """Delete a supplier, converting FK protection into a friendly 409.

        ``Receipt.supplier`` is ``on_delete=PROTECT``: a supplier referenced by
        any receipt cannot be hard-deleted (this preserves the audit trail).
        Rather than surfacing the resulting :class:`ProtectedError` as a 500, we
        catch it and return ``409 Conflict`` with an actionable Ukrainian
        message steering the admin toward deactivation instead.

        Args:
            request: The incoming DRF request.
            *args: Positional args forwarded from the router (unused).
            **kwargs: URL kwargs forwarded from the router (carries ``pk``).

        Returns:
            ``204 No Content`` on success, or ``409 Conflict`` with a ``detail``
            message when the supplier has protected related receipts.
        """

        try:
            return super().destroy(request, *args, **kwargs)
        except ProtectedError:
            return Response(
                {
                    "detail": (
                        "Постачальник має повʼязані накладні. "
                        "Деактивуйте замість видалення."
                    )
                },
                status=status.HTTP_409_CONFLICT,
            )
