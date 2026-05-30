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


class IntegrationSettings(models.Model):
    """Singleton row holding admin-editable integration configuration.

    The Settings PWA lets an admin store the SalesDrive YML export URL in the
    database instead of relying solely on the ``SALESDRIVE_YML_URL`` env var. To
    keep that configuration unambiguous there is exactly **one** config row,
    enforced by pinning the primary key to ``1`` (see :meth:`save`). Reads always
    go through :meth:`load`, which lazily creates that single row.

    WHY a DB singleton instead of just the env var:
        The env var stays as a deploy-time fallback, but operators need to change
        the YML URL through the designed admin UI (not a redeploy or Django
        admin). A one-row table is the simplest durable place to hold that
        without inventing a key/value store.

    Attributes:
        salesdrive_yml_url: The SalesDrive YML export URL. Blank means "fall back
            to ``settings.SALESDRIVE_YML_URL``" (see
            ``apps.catalog.services.sync_catalog``).
        updated_at: Auto-updated timestamp of the last save, so the UI can show
            when the configuration was last changed.
    """

    salesdrive_yml_url = models.URLField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Налаштування інтеграцій"
        verbose_name_plural = "Налаштування інтеграцій"

    def __str__(self) -> str:
        """Return a label for the (single) settings row in admin/logs.

        Returns:
            A constant human-readable label — there is only ever one row.
        """

        return "Налаштування інтеграцій"

    def save(self, *args: object, **kwargs: object) -> None:
        """Persist the row, forcing it to be the one-and-only singleton (pk=1).

        Pinning the primary key guarantees a second ``IntegrationSettings()`` can
        never create a competing config row: a save just overwrites pk=1.

        Args:
            *args: Positional arguments forwarded to ``Model.save``.
            **kwargs: Keyword arguments forwarded to ``Model.save``.
        """

        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls) -> "IntegrationSettings":
        """Return the singleton settings row, creating it lazily if absent.

        Returns:
            The single :class:`IntegrationSettings` instance (pk=1). On first
            access it is created with blank defaults.
        """

        obj, _ = cls.objects.get_or_create(pk=1)
        return obj
