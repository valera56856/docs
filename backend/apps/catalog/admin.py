"""Django admin registration for the catalog app.

Registers :class:`~apps.catalog.models.OurProduct` so staff can inspect the
cached SalesDrive catalog and verify sync results, and
:class:`~apps.catalog.models.IntegrationSettings` so the (single) integration
config row is visible from Django admin too. Sync timestamps are read-only
because they are maintained automatically by the sync job.

The primary editing surface for integration settings is the designed Settings
PWA (``GET/PUT /api/settings/salesdrive/``); Django admin is a secondary,
inspection-oriented view.
"""

from __future__ import annotations

from django.contrib import admin
from django.http import HttpRequest

from apps.catalog.models import IntegrationSettings, OurProduct


@admin.register(OurProduct)
class OurProductAdmin(admin.ModelAdmin):
    """Admin configuration for :class:`OurProduct`.

    Surfaces SKU, name, SalesDrive id and last-sync time, with search across the
    identifying fields so admins can confirm a product made it into the cache.
    """

    list_display = ("sku", "name", "salesdrive_id", "last_synced")
    search_fields = ("sku", "name", "salesdrive_id")
    readonly_fields = ("last_synced",)


@admin.register(IntegrationSettings)
class IntegrationSettingsAdmin(admin.ModelAdmin):
    """Admin configuration for the :class:`IntegrationSettings` singleton.

    There is only ever one row (pk=1), so creating additional rows is disabled —
    the YML URL is edited in place. ``updated_at`` is auto-maintained and shown
    read-only.
    """

    list_display = ("__str__", "salesdrive_yml_url", "updated_at")
    readonly_fields = ("updated_at",)

    def has_add_permission(self, request: HttpRequest) -> bool:
        """Disallow adding a second config row once the singleton exists.

        Args:
            request: The current admin request.

        Returns:
            ``True`` only while no :class:`IntegrationSettings` row exists yet.
        """

        return not IntegrationSettings.objects.exists()

    def has_delete_permission(
        self, request: HttpRequest, obj: object | None = None
    ) -> bool:
        """Disallow deleting the singleton config row.

        Args:
            request: The current admin request.
            obj: The object being acted on (unused).

        Returns:
            ``False`` — the config row is permanent; clear the URL instead.
        """

        return False
