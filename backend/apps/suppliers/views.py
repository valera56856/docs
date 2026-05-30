"""Views for the suppliers app.

Implements ``GET /api/suppliers/`` — the list of active suppliers shown in the
receipt-create picker. Read-only: supplier management lives in Django admin in
the skeleton.
"""

from __future__ import annotations

from drf_spectacular.utils import extend_schema
from rest_framework.generics import ListAPIView
from rest_framework.permissions import IsAuthenticated

from .models import Supplier
from .serializers import SupplierSerializer


@extend_schema(
    summary="Список активних постачальників",
    description="Повертає постачальників із is_active=True, відсортованих за назвою.",
    tags=["suppliers"],
)
class SupplierListView(ListAPIView):
    """List active suppliers (``GET /api/suppliers/``).

    Only ``is_active=True`` rows are returned, ordered by name, so the picker
    never offers a retired supplier. Requires authentication like every non-auth
    endpoint.
    """

    serializer_class = SupplierSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """Return active suppliers ordered by name.

        Returns:
            QuerySet[Supplier]: Active suppliers, alphabetical by ``name``.
        """

        return Supplier.objects.filter(is_active=True).order_by("name")
