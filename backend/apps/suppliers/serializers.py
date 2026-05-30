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
    remaining fields (``name``, ``edrpou``, ``note``, ``is_active``) are writable
    so admins can create, rename, annotate, tag with a tax code, and
    (de)activate suppliers from the PWA rather than the Django admin. ``edrpou``,
    ``note`` and ``is_active`` carry sensible defaults (blank / ``True``) so a
    minimal create payload is just ``{"name": "…"}``.

    WHY ``edrpou`` is writable but optional:
        It is the Ukrainian tax code (ЄДРПОУ) — the reliable key the
        auto-supplier detection matches on. Admins may set or correct it for a
        manually-created vendor, but most rows are created automatically from a
        recognized invoice (see ``apps.suppliers.services.match_or_create_supplier``),
        so the field must not be required on a hand-typed create.
    """

    class Meta:
        model = Supplier
        fields = ["id", "name", "edrpou", "note", "is_active", "created_at"]
        read_only_fields = ["id", "created_at"]
        extra_kwargs = {
            # Optional on writes: a code-less vendor is valid, and the field is
            # usually populated by auto-detection rather than typed by an admin.
            "edrpou": {"required": False},
        }
