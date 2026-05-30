"""Serializers for the receipts app.

These cover the full receipt lifecycle surface:

* :class:`ReceiptCreateSerializer` — create a draft receipt + attach photo URLs.
* :class:`ReceiptPhotoSerializer` — a single photographed page.
* :class:`ReceiptLineSerializer` — one recognized line (read), with the resolved
  product embedded.
* :class:`ReceiptLinePatchSerializer` — partial edit of quantity / price / sku.
* :class:`ReceiptSerializer` — full receipt with nested photos and lines.
* :class:`GenerateXlsxResultSerializer` — response for the Excel-generation step.

Why ``Decimal`` quantity/price flow through unchanged:
    The models store money/quantity as ``DecimalField`` for exactness; DRF's
    ``DecimalField`` preserves that precision end-to-end (no float coercion).
"""

from __future__ import annotations

from rest_framework import serializers

from apps.catalog.serializers import OurProductSerializer

from .models import Receipt, ReceiptLine, ReceiptPhoto


class ReceiptPhotoSerializer(serializers.ModelSerializer):
    """Serialize a :class:`~apps.receipts.models.ReceiptPhoto`."""

    class Meta:
        model = ReceiptPhoto
        fields = ["id", "image_url"]
        read_only_fields = ["id"]


class ReceiptLineSerializer(serializers.ModelSerializer):
    """Read serializer for a recognized receipt line.

    Embeds the resolved catalog product (``matched_product``) so the receipt
    table can render the mapping target without an extra request. ``raw_ocr_json``
    is included for audit/debugging in the skeleton.
    """

    matched_product = OurProductSerializer(read_only=True)

    class Meta:
        model = ReceiptLine
        fields = [
            "id",
            "recognized_sku",
            "recognized_name",
            "quantity",
            "price",
            "matched_product",
            "match_status",
            "raw_ocr_json",
        ]
        read_only_fields = ["id", "matched_product", "match_status", "raw_ocr_json"]


class ReceiptLinePatchSerializer(serializers.ModelSerializer):
    """Partial-update serializer for a receipt line.

    Allows the operator to correct OCR mistakes before Excel generation:
    ``quantity``, ``price`` and the recognized SKU/name. Mapping is changed via
    the dedicated map endpoint, not here, so ``matched_product`` /
    ``match_status`` are not writable.
    """

    class Meta:
        model = ReceiptLine
        fields = ["recognized_sku", "recognized_name", "quantity", "price"]
        extra_kwargs = {
            "recognized_sku": {"required": False},
            "recognized_name": {"required": False},
            "quantity": {"required": False},
            "price": {"required": False},
        }


class ReceiptSerializer(serializers.ModelSerializer):
    """Full read serializer for a receipt with its photos and lines.

    Returned by ``GET /api/receipts/{id}/`` and on create. Nested ``photos`` and
    ``lines`` give the client everything it needs to render the receipt screen in
    a single round-trip.
    """

    photos = ReceiptPhotoSerializer(many=True, read_only=True)
    lines = ReceiptLineSerializer(many=True, read_only=True)

    class Meta:
        model = Receipt
        fields = [
            "id",
            "supplier",
            "status",
            "xlsx_url",
            "created_by",
            "created_at",
            "photos",
            "lines",
        ]
        read_only_fields = [
            "id",
            "status",
            "xlsx_url",
            "created_by",
            "created_at",
            "photos",
            "lines",
        ]


class ReceiptCreateSerializer(serializers.ModelSerializer):
    """Create a draft receipt and attach photo URLs.

    The client uploads the photos to storage (R2) directly and posts their URLs
    here together with the chosen supplier. Each URL becomes a
    :class:`~apps.receipts.models.ReceiptPhoto`. The receipt is created in
    ``draft`` status; recognition is triggered separately.

    Attributes:
        photo_urls: List of stored image URLs for the invoice pages. Optional —
            a receipt may be created first and photos attached on recognize.
    """

    photo_urls = serializers.ListField(
        child=serializers.URLField(),
        write_only=True,
        required=False,
        default=list,
        help_text="URLs зображень сторінок накладної у сховищі (R2).",
    )

    class Meta:
        model = Receipt
        fields = ["id", "supplier", "photo_urls"]
        read_only_fields = ["id"]

    def create(self, validated_data: dict) -> Receipt:
        """Create the receipt and its photo rows atomically.

        Args:
            validated_data: Validated fields, including the popped
                ``photo_urls`` list and the ``created_by`` injected by the view.

        Returns:
            Receipt: The newly created draft receipt with photos attached.
        """

        from django.db import transaction

        photo_urls = validated_data.pop("photo_urls", []) or []
        with transaction.atomic():
            receipt = Receipt.objects.create(**validated_data)
            ReceiptPhoto.objects.bulk_create(
                [
                    ReceiptPhoto(receipt=receipt, image_url=url)
                    for url in photo_urls
                ]
            )
        return receipt

    def to_representation(self, instance: Receipt) -> dict:
        """Return the full receipt representation after create.

        Args:
            instance: The created receipt.

        Returns:
            The :class:`ReceiptSerializer` output so the client immediately has
            the full object (id, status, nested photos/lines).
        """

        return ReceiptSerializer(instance, context=self.context).data


class GenerateXlsxResultSerializer(serializers.Serializer):
    """Response schema for the Excel-generation endpoint.

    Attributes:
        xlsx_url: URL of the generated ``.xlsx`` receipt in storage.
        status: The receipt's status after generation (``xlsx_ready``).
    """

    xlsx_url = serializers.URLField(read_only=True)
    status = serializers.CharField(read_only=True)


class RecognizeResultSerializer(serializers.Serializer):
    """Response schema for the recognize trigger.

    Attributes:
        task_id: Celery task id for the enqueued OCR job.
        status: The receipt status after enqueue (``recognizing``).
    """

    task_id = serializers.CharField(read_only=True)
    status = serializers.CharField(read_only=True)
