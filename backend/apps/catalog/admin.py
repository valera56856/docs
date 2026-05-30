"""Django admin registration for the catalog app.

Registers :class:`~apps.catalog.models.OurProduct` so staff can inspect the
cached SalesDrive catalog and verify sync results. Sync timestamps are
read-only because they are maintained automatically by the sync job.
"""

from __future__ import annotations

from django.contrib import admin

from apps.catalog.models import OurProduct


@admin.register(OurProduct)
class OurProductAdmin(admin.ModelAdmin):
    """Admin configuration for :class:`OurProduct`.

    Surfaces SKU, name, SalesDrive id and last-sync time, with search across the
    identifying fields so admins can confirm a product made it into the cache.
    """

    list_display = ("sku", "name", "salesdrive_id", "last_synced")
    search_fields = ("sku", "name", "salesdrive_id")
    readonly_fields = ("last_synced",)
