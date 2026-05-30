"""Serializers for the mapping app.

The mapping *action* endpoint (mapping a receipt line to a product) lives in the
receipts app because its URL is nested under a receipt line. This module provides
the read/write serializers for :class:`~apps.mapping.models.ArticleMapping` used
by the admin mappings-management API (``/api/mappings/``) plus the input
serializer (:class:`MapLineRequestSerializer`) reused by the receipt-line map
action so the request shape is documented and validated in one place.

Two distinct mapping serializers exist on purpose:

* :class:`ArticleMappingReadSerializer` — nests the supplier and product objects
  so the admin UI can render a row (``{supplier_sku} → {our_product.sku} …``)
  without a second round-trip. It is the response shape for list/create/patch.
* :class:`ArticleMappingWriteSerializer` — flat, accepts a supplier PK, the raw
  ``supplier_sku``, and ``our_product_id``. The view normalizes the SKU and runs
  ``update_or_create`` on ``(supplier, supplier_sku_normalized)``; the model's
  derived fields (the normalized SKU, ``times_used``, ``created_*``) are managed
  by the mapping services, not set directly through this serializer.
"""

from __future__ import annotations

from rest_framework import serializers

from apps.catalog.models import OurProduct
from apps.catalog.serializers import OurProductSerializer
from apps.suppliers.models import Supplier

from .models import ArticleMapping


class ArticleMappingSerializer(serializers.ModelSerializer):
    """Read serializer for a remembered supplier-SKU to product mapping.

    Embeds the resolved product so clients can render the mapping without a
    second lookup. Retained for backward compatibility; the admin mappings API
    uses :class:`ArticleMappingReadSerializer` (a leaner, supplier-nested shape).
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


class _SupplierBriefSerializer(serializers.ModelSerializer):
    """Minimal supplier projection (``{id, name}``) for embedding in a mapping.

    The mappings list only needs to label each row with its supplier; embedding
    the full :class:`~apps.suppliers.serializers.SupplierSerializer` (with note,
    is_active, created_at) would be wasteful, so this trims to the two fields the
    admin UI renders.
    """

    class Meta:
        model = Supplier
        fields = ["id", "name"]
        read_only_fields = fields


class _OurProductBriefSerializer(serializers.ModelSerializer):
    """Minimal product projection (``{id, sku, name}``) for a mapping row.

    Matches the ``MappingAdmin.our_product`` shape the frontend expects; omits
    ``salesdrive_id`` / ``last_synced`` which the mappings table does not show.
    """

    class Meta:
        model = OurProduct
        fields = ["id", "sku", "name"]
        read_only_fields = fields


class ArticleMappingReadSerializer(serializers.ModelSerializer):
    """Read serializer for the admin mappings-management list.

    Nests the supplier as ``{id, name}`` and the product as ``{id, sku, name}``
    so a single ``GET /api/mappings/`` response renders each row
    (``{supplier_sku} → {our_product.sku} · {our_product.name} · {times_used}×``)
    without follow-up requests. Every field is read-only — mutations go through
    :class:`ArticleMappingWriteSerializer` and the mapping services.
    """

    supplier = _SupplierBriefSerializer(read_only=True)
    our_product = _OurProductBriefSerializer(read_only=True)

    class Meta:
        model = ArticleMapping
        fields = [
            "id",
            "supplier",
            "supplier_sku",
            "our_product",
            "times_used",
            "created_by",
            "created_at",
        ]
        read_only_fields = fields


class ArticleMappingWriteSerializer(serializers.Serializer):
    """Input serializer for creating / re-targeting an admin mapping.

    Flat by design: the admin client submits the supplier, the raw SKU, and the
    target product id. The view is responsible for normalizing ``supplier_sku``
    (via :func:`apps.mapping.services.normalize_sku`) and persisting through
    ``update_or_create`` on the unique ``(supplier, supplier_sku_normalized)``
    pair — this serializer only validates the incoming shape.

    On **create** all three fields are required. On **PATCH** the view passes
    ``partial=True`` so an operator can re-target the product (``our_product_id``)
    and/or re-normalize the stored SKU (``supplier_sku``) independently, leaving
    the rest untouched.

    Attributes:
        supplier: Primary key of the :class:`~apps.suppliers.models.Supplier`
            whose SKU namespace owns this mapping. Validated against existing
            suppliers (a stale/unknown id is rejected with 400, not 500).
        supplier_sku: The SKU exactly as printed/recognized; the view derives the
            normalized lookup key from it.
        our_product_id: Primary key of the target
            :class:`~apps.catalog.models.OurProduct`.
    """

    supplier = serializers.PrimaryKeyRelatedField(
        queryset=Supplier.objects.all()
    )
    supplier_sku = serializers.CharField(max_length=255)
    our_product_id = serializers.IntegerField(min_value=1)

    def validate_our_product_id(self, value: int) -> int:
        """Ensure the target product exists before the view tries to map to it.

        Validating here turns a dangling ``our_product_id`` into a clean 400
        (``"Такого товару не існує."``) instead of an integrity error deeper in
        the ``update_or_create`` call.

        Args:
            value: The submitted product primary key.

        Returns:
            The same id, once confirmed to reference a real product.

        Raises:
            serializers.ValidationError: If no :class:`OurProduct` has that pk.
        """

        if not OurProduct.objects.filter(pk=value).exists():
            raise serializers.ValidationError("Такого товару не існує.")
        return value

    def validate_supplier_sku(self, value: str) -> str:
        """Reject a SKU that normalizes to nothing (only whitespace).

        A blank normalized SKU could not be matched against a recognized line, so
        it is never a valid mapping key; surface that as a 400 here rather than
        silently storing an unusable row.

        Args:
            value: The raw supplier SKU string.

        Returns:
            The original (un-normalized) SKU, preserved for storage/display.

        Raises:
            serializers.ValidationError: If the SKU is blank after normalization.
        """

        # Local import to avoid a module-level cycle (services imports models,
        # which is fine, but keeping the import here mirrors the view's usage and
        # documents that normalization is the canonical rule).
        from .services import normalize_sku

        if not normalize_sku(value):
            raise serializers.ValidationError("Артикул не може бути порожнім.")
        return value


class MapLineRequestSerializer(serializers.Serializer):
    """Input for mapping a receipt line to one of our products.

    Attributes:
        our_product_id: Primary key of the :class:`~apps.catalog.models.OurProduct`
            the operator selected from the search dropdown.
    """

    our_product_id = serializers.IntegerField(min_value=1)
