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
