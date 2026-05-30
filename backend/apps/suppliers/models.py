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
        edrpou: The supplier's Ukrainian tax code (ЄДРПОУ) as printed in the
            invoice header. This is the *reliable* supplier key: names vary by
            spelling and OCR noise, but the 8-digit (legal entity) / 10-digit
            (sole proprietor) ЄДРПОУ code uniquely identifies a vendor. It is the
            primary key the auto-supplier detection matches on (see
            ``apps.suppliers.services.match_or_create_supplier``). Indexed because
            every detection lookup filters on it. Blank when an invoice omits it.
        note: Free-form internal note (delivery terms, contacts, etc.).
        is_active: Whether the supplier appears in active-supplier pickers.
            Inactive suppliers are retained for historical receipts/mappings but
            hidden from the ``GET /api/suppliers/`` list.
        created_at: Timestamp set once when the supplier is created.
    """

    name = models.CharField(max_length=255)
    # ``edrpou`` is the Ukrainian tax code (ЄДРПОУ). It is ``blank`` (and *not*
    # ``unique``) deliberately: an invoice may omit it, and we cannot enforce
    # uniqueness over a column that legitimately stores empty strings for
    # code-less vendors. The matching service treats only a *non-empty* code as
    # an exact key. Indexed so the auto-detect lookup is cheap.
    edrpou = models.CharField(max_length=20, blank=True, db_index=True)
    note = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        """Return the supplier name for admin lists, dropdowns and logs.

        Returns:
            The supplier's ``name``.
        """

        return self.name
