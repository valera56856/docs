"""Catalog domain app for Valeraup.

This app holds a local cache of our SalesDrive product catalog, mirrored from
the SalesDrive YML export. The cache (:class:`~apps.catalog.models.OurProduct`)
is what mapping searches and dropdowns query, so the UI never has to hit
SalesDrive live.

Why cache rather than query SalesDrive on demand:
    SalesDrive exposes the catalog only as a YML export (no convenient search
    API). Syncing it into PostgreSQL lets us index ``sku``/``name`` for fast,
    typo-tolerant lookups during manual SKU mapping. A daily Celery task keeps
    the cache fresh; see ``apps.catalog.tasks.sync_catalog_task``.
"""

from __future__ import annotations
