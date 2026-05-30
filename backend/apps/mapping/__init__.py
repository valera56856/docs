"""Mapping domain app for Valeraup — the SKU translation core.

This app remembers how a given supplier's SKU corresponds to one of our
SalesDrive catalog products. The :class:`~apps.mapping.models.ArticleMapping`
table is the learning store: once an operator maps a supplier SKU manually, the
mapping is saved (keyed by supplier + normalized SKU) and future recognitions of
the same SKU auto-match without human input.

Why normalization matters here:
    Suppliers print the same SKU inconsistently (extra spaces, different case).
    We persist a normalized form (``supplier_sku_normalized``) and key lookups on
    it so cosmetically different spellings of one SKU collapse to a single
    mapping. The normalization rules live in ``apps.mapping.services.normalize_sku``.
"""

from __future__ import annotations
