"""Database models for the mapping app.

Defines :class:`ArticleMapping`, the persistent supplier-SKU to our-product
translation. This is the heart of the "map once, remember forever" behavior:
the unique constraint on ``(supplier, supplier_sku_normalized)`` guarantees one
canonical mapping per supplier SKU, and ``times_used`` records how often it has
helped auto-match a line.
"""

from __future__ import annotations

from django.db import models


class ArticleMapping(models.Model):
    """Remembered mapping from a supplier's SKU to one of our products.

    A mapping is created the first time an operator manually links a supplier SKU
    to an :class:`~apps.catalog.models.OurProduct`. Thereafter, recognizing the
    same SKU for the same supplier auto-matches via this row (see
    ``apps.mapping.services.match_line``).

    Attributes:
        supplier: The vendor whose SKU namespace this mapping belongs to.
            Deleting the supplier cascades to its mappings.
        supplier_sku: The SKU exactly as recognized/printed (kept for audit and
            display).
        supplier_sku_normalized: The normalized SKU (trim/UPPER/collapse spaces)
            used for lookups. Indexed because every auto-match query filters on
            it together with the supplier.
        our_product: The catalog product this SKU resolves to. Cascades on
            product deletion (a mapping to a removed product is meaningless).
        times_used: How many times this mapping produced an auto-match.
            Incremented on use; surfaces the most valuable mappings.
        created_by: Identifier (username/email) of whoever first created the
            manual mapping. Blank for system-created entries.
        created_at: Timestamp set once when the mapping is first stored.

    Meta:
        unique_together: ``(supplier, supplier_sku_normalized)`` enforces a
            single canonical mapping per supplier SKU so cosmetic spelling
            variants cannot create duplicate, conflicting mappings.
    """

    MATCH_AUTO = "auto"
    MATCH_MANUAL = "manual"

    supplier = models.ForeignKey(
        "suppliers.Supplier",
        on_delete=models.CASCADE,
        related_name="mappings",
    )
    supplier_sku = models.CharField(max_length=255)
    supplier_sku_normalized = models.CharField(max_length=255, db_index=True)
    our_product = models.ForeignKey(
        "catalog.OurProduct",
        on_delete=models.CASCADE,
        related_name="mappings",
    )
    times_used = models.PositiveIntegerField(default=0)
    created_by = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("supplier", "supplier_sku_normalized")

    def __str__(self) -> str:
        """Return a readable label for admin lists and logs.

        Returns:
            The supplier SKU and the product it maps to, e.g.
            ``"SKU-7 → ABC-123 — Сорочка біла"``.
        """

        return f"{self.supplier_sku} → {self.our_product}"
