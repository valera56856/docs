"""Serializers for the suppliers app."""

from __future__ import annotations

from rest_framework import serializers

from .models import Supplier


class SupplierSerializer(serializers.ModelSerializer):
    """Serialize a :class:`~apps.suppliers.models.Supplier` for the API.

    Used by ``GET /api/suppliers/`` (the supplier picker on the receipt-create
    screen). All fields are read-only in the skeleton — supplier CRUD is managed
    through Django admin for now.
    """

    class Meta:
        model = Supplier
        fields = ["id", "name", "note", "is_active", "created_at"]
        read_only_fields = fields
