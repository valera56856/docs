"""Database models for the catalog app.

Defines :class:`OurProduct`, a local cache of our SalesDrive catalog populated
from the SalesDrive YML export. Mapping search (``GET /api/products/search/``)
and the manual-mapping dropdown read from this table.
"""

from __future__ import annotations

from django.db import models


class OurProduct(models.Model):
    """A single product mirrored from the SalesDrive catalog.

    Rows are upserted from the SalesDrive YML export keyed by
    :attr:`salesdrive_id` (see ``apps.catalog.services.sync_catalog``). This is a
    read-mostly cache: it is the canonical target a supplier SKU gets mapped to.

    Attributes:
        salesdrive_id: SalesDrive's stable offer/product identifier. Unique —
            used as the upsert key so re-syncing updates rather than duplicates.
        sku: Our internal article/SKU. Indexed because it is the primary search
            and exact-match field during mapping.
        name: Product display name from SalesDrive. Indexed-by-search via the
            API serializer, stored up to 500 chars to fit long titles.
        last_synced: Auto-updated timestamp of the most recent sync that touched
            this row; useful to spot stale entries.
    """

    salesdrive_id = models.CharField(max_length=255, unique=True)
    sku = models.CharField(max_length=255, db_index=True)
    name = models.CharField(max_length=500)
    last_synced = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        """Return a readable label for admin lists, dropdowns and logs.

        Returns:
            The SKU and name, e.g. ``"ABC-123 — Сорочка біла"``.
        """

        return f"{self.sku} — {self.name}"
