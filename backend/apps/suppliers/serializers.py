"""Serializers for the suppliers app."""

from __future__ import annotations

from rest_framework import serializers

from .models import Supplier


class SupplierSerializer(serializers.ModelSerializer):
    """Serialize and validate a :class:`~apps.suppliers.models.Supplier`.

    Drives the full supplier CRUD surface exposed by
    :class:`~apps.suppliers.views.SupplierViewSet`:

    * ``GET /api/suppliers/`` — the supplier picker on the receipt-create screen
      (operators) and the admin management list.
    * ``POST/PUT/PATCH/DELETE /api/suppliers/{id}/`` — admin-only mutations.

    ``id`` and ``created_at`` are server-owned and therefore read-only; the
    remaining fields (``name``, ``note``, ``is_active``) are writable so admins
    can create, rename, annotate and (de)activate suppliers from the PWA rather
    than the Django admin. ``note`` and ``is_active`` carry sensible defaults
    (blank / ``True``) so a minimal create payload is just ``{"name": "…"}``.
    """

    class Meta:
        model = Supplier
        fields = ["id", "name", "note", "is_active", "created_at"]
        read_only_fields = ["id", "created_at"]
