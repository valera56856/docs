"""Serializers for the mapping app.

The mapping *action* endpoint (mapping a receipt line to a product) lives in the
receipts app because its URL is nested under a receipt line. This module provides
the read serializer for :class:`~apps.mapping.models.ArticleMapping` plus the
input serializer reused by that action so the request shape is documented and
validated in one place.
"""

from __future__ import annotations

from rest_framework import serializers

from apps.catalog.serializers import OurProductSerializer

from .models import ArticleMapping


class ArticleMappingSerializer(serializers.ModelSerializer):
    """Read serializer for a remembered supplier-SKU to product mapping.

    Embeds the resolved product so clients can render the mapping without a
    second lookup.
    """

    our_product = OurProductSerializer(read_only=True)

    class Meta:
        model = ArticleMapping
        fields = [
            "id",
            "supplier",
            "supplier_sku",
            "supplier_sku_normalized",
            "our_product",
            "times_used",
            "created_by",
            "created_at",
        ]
        read_only_fields = fields


class MapLineRequestSerializer(serializers.Serializer):
    """Input for mapping a receipt line to one of our products.

    Attributes:
        our_product_id: Primary key of the :class:`~apps.catalog.models.OurProduct`
            the operator selected from the search dropdown.
    """

    our_product_id = serializers.IntegerField(min_value=1)
