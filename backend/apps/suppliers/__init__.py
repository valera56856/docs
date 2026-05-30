"""Suppliers domain app for Valeraup.

This app owns the :class:`~apps.suppliers.models.Supplier` directory — the
vendors whose printed invoices managers photograph. A supplier is the scope key
for SKU mappings: the same supplier SKU may map to different catalog products
across different suppliers, so every :class:`~apps.mapping.models.ArticleMapping`
is keyed by ``(supplier, normalized_sku)``.
"""

from __future__ import annotations
