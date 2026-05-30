"""Serializers for the catalog app."""

from __future__ import annotations

from rest_framework import serializers

from .models import OurProduct


class OurProductSerializer(serializers.ModelSerializer):
    """Serialize an :class:`~apps.catalog.models.OurProduct`.

    Used by the mapping dropdown search (``GET /api/products/search/``) and
    embedded inside receipt-line responses to show what a line resolved to.
    """

    class Meta:
        model = OurProduct
        fields = ["id", "salesdrive_id", "sku", "name", "last_synced"]
        read_only_fields = fields


class CatalogSyncResultSerializer(serializers.Serializer):
    """Response schema for the catalog sync trigger.

    Attributes:
        task_id: Celery task id of the enqueued sync (for status polling).
        detail: Human-readable confirmation message.
    """

    task_id = serializers.CharField(read_only=True)
    detail = serializers.CharField(read_only=True)


class SalesDriveSettingsSerializer(serializers.Serializer):
    """Validate the SalesDrive settings write payload (``PUT``).

    Only the YML URL is admin-editable; ``last_synced`` and ``product_count`` are
    derived/read-only and live on :class:`SalesDriveSettingsReadSerializer`.

    ``allow_blank=True`` is deliberate: clearing the field is a valid action that
    means "fall back to the ``SALESDRIVE_YML_URL`` env var" (see
    ``apps.catalog.services.sync_catalog``).

    Attributes:
        salesdrive_yml_url: The SalesDrive YML export URL (may be blank to clear).
    """

    salesdrive_yml_url = serializers.URLField(allow_blank=True, required=False)


class SalesDriveSettingsReadSerializer(serializers.Serializer):
    """Response schema for the SalesDrive settings resource (``GET``/``PUT``).

    Bundles the stored configuration with derived catalog status so the Settings
    UI can render the URL field plus a "last synced / N products cached" line in
    a single round-trip.

    Attributes:
        salesdrive_yml_url: The currently stored YML URL (may be blank).
        last_synced: The most recent ``OurProduct.last_synced`` across the cache,
            or ``None`` when the catalog has never been synced.
        product_count: How many products are currently cached locally.
    """

    salesdrive_yml_url = serializers.URLField(allow_blank=True)
    last_synced = serializers.DateTimeField(allow_null=True)
    product_count = serializers.IntegerField()


class SalesDriveTestResultSerializer(serializers.Serializer):
    """Response schema for the SalesDrive test-connection endpoint.

    Always returned with HTTP 200 — a failed probe is a *result*, not a server
    error — so the UI can show a friendly message either way.

    Attributes:
        ok: ``True`` when the YML was fetched and parsed successfully.
        product_count: Number of offers found on success, ``None`` on failure.
        error: ``None`` on success, otherwise the failure reason string.
    """

    ok = serializers.BooleanField()
    product_count = serializers.IntegerField(allow_null=True)
    error = serializers.CharField(allow_null=True)
