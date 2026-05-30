"""Database models for the suppliers app.

Defines :class:`Supplier`, the vendor directory. Suppliers are referenced by
receipts (which vendor an invoice came from) and by article mappings (the SKU
namespace is per-supplier).
"""

from __future__ import annotations

from django.db import models


class Supplier(models.Model):
    """A vendor whose printed invoices are processed by Valeraup.

    Attributes:
        name: Human-readable supplier name shown in the UI.
        note: Free-form internal note (delivery terms, contacts, etc.).
        is_active: Whether the supplier appears in active-supplier pickers.
            Inactive suppliers are retained for historical receipts/mappings but
            hidden from the ``GET /api/suppliers/`` list.
        created_at: Timestamp set once when the supplier is created.
    """

    name = models.CharField(max_length=255)
    note = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        """Return the supplier name for admin lists, dropdowns and logs.

        Returns:
            The supplier's ``name``.
        """

        return self.name
