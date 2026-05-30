"""Serializers for the receipts app.

These cover the full receipt lifecycle surface:

* :class:`ReceiptCreateSerializer` — create a draft receipt (supplier optional —
  the scan-first flow detects it) + attach photo URLs.
* :class:`ReceiptPhotoSerializer` — a single photographed page.
* :class:`SupplierMiniSerializer` — the nested ``{id, name, edrpou}`` supplier.
* :class:`ReceiptLineSerializer` — one recognized line (read), with the resolved
  product embedded.
* :class:`ReceiptLinePatchSerializer` — partial edit of quantity / price / sku.
* :class:`ReceiptSerializer` — full receipt with nested supplier, photos, lines.
* :class:`ReceiptUpdateSerializer` — set/change the receipt's supplier (PATCH).
* :class:`GenerateXlsxResultSerializer` — response for the Excel-generation step.

Why ``Decimal`` quantity/price flow through unchanged:
    The models store money/quantity as ``DecimalField`` for exactness; DRF's
    ``DecimalField`` preserves that precision end-to-end (no float coercion).
"""

from __future__ import annotations

from rest_framework import serializers

from apps.catalog.serializers import OurProductSerializer
from apps.suppliers.models import Supplier

from .models import Receipt, ReceiptLine, ReceiptPhoto


class SupplierMiniSerializer(serializers.ModelSerializer):
    """Compact nested supplier for receipt reads (``{id, name, edrpou}``).

    The receipt screen renders an auto-detected supplier header card, so it needs
    the supplier's display name and ЄДРПОУ inline rather than just the FK id. We
    expose a *minimal* projection (not the full :class:`SupplierSerializer`) to
    keep the receipt payload lean — the receipt does not need ``note`` /
    ``is_active`` / ``created_at`` to draw that card.
    """

    class Meta:
        model = Supplier
        fields = ["id", "name", "edrpou"]
        read_only_fields = fields


class ReceiptPhotoSerializer(serializers.ModelSerializer):
    """Serialize a :class:`~apps.receipts.models.ReceiptPhoto` for reads.

    Exposes the stable ``image_url`` the frontend renders. The underlying
    ``image`` file field is intentionally not serialized out — the URL is the one
    field clients need, and it is populated from ``image.url`` on upload.
    """

    class Meta:
        model = ReceiptPhoto
        fields = ["id", "image_url"]
        read_only_fields = ["id", "image_url"]


# Upload limits (H4). A phone photo of an invoice page is comfortably under
# 10 MB and well under 40 megapixels; anything larger is either a mistake or an
# attempt to exhaust memory/storage (a decompression bomb decodes to a huge
# bitmap). Bytes: 10 * 1024 * 1024.
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_UPLOAD_PIXELS = 40_000_000


class ReceiptPhotoUploadSerializer(serializers.Serializer):
    """Validate a multipart photo upload (``POST .../photos/``).

    The client sends the captured invoice page as a multipart ``image`` file.
    DRF's :class:`~rest_framework.serializers.ImageField` validates it is a real,
    Pillow-decodable image (rejecting non-image junk) before we save it, and
    :meth:`validate_image` additionally bounds its byte size and pixel area (H4).

    Attributes:
        image: The uploaded invoice-page image file (required).
    """

    image = serializers.ImageField(
        write_only=True,
        help_text="Файл фотографії сторінки накладної (multipart).",
    )

    def validate_image(self, image):
        """Reject uploads that are too large in bytes or pixel area (H4).

        Two independent caps, because they defend different attacks:

        * **Byte size** (``> 10 MB``) — bounds raw upload/storage cost.
        * **Pixel area** (``width * height > 40M``) — bounds *decoded* memory, so
          a small, highly-compressed "decompression bomb" that would balloon to
          gigabytes of bitmap when Pillow decodes it is refused. ``image.width`` /
          ``image.height`` come from DRF's already-completed Pillow validation, so
          reading them does not re-decode the file. (Pillow's process-wide
          ``MAX_IMAGE_PIXELS`` guard set in settings is the backstop.)

        Args:
            image: The uploaded image file (validated as a real image by
                :class:`~rest_framework.serializers.ImageField` first).

        Returns:
            The same ``image`` when it is within both limits.

        Raises:
            rest_framework.serializers.ValidationError: If the file exceeds the
                byte-size or pixel-area cap.
        """

        size = getattr(image, "size", None)
        if size is not None and size > MAX_UPLOAD_BYTES:
            raise serializers.ValidationError(
                "Файл завеликий (максимум 10 МБ)."
            )

        width = getattr(image, "width", None) or 0
        height = getattr(image, "height", None) or 0
        if width * height > MAX_UPLOAD_PIXELS:
            raise serializers.ValidationError(
                "Зображення завелике за роздільною здатністю."
            )

        return image


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
    """Full read serializer for a receipt with its supplier, photos and lines.

    Returned by ``GET /api/receipts/{id}/`` and on create. The nested
    ``supplier`` (``{id, name, edrpou}`` or ``null``) lets the receipt screen draw
    the auto-detected supplier header card without a second request;
    ``recognized_supplier`` exposes the raw OCR supplier dict for the
    "auto-detected" provenance. Nested ``photos`` and ``lines`` give the client
    everything it needs to render the receipt screen in a single round-trip.

    WHY ``supplier`` is nullable here:
        The scan-first flow creates a draft with no supplier and detects it on
        recognition, so a receipt may legitimately be ``supplier: null`` (the UI
        then prompts the operator to pick one).
    """

    supplier = SupplierMiniSerializer(read_only=True)
    photos = ReceiptPhotoSerializer(many=True, read_only=True)
    lines = ReceiptLineSerializer(many=True, read_only=True)

    class Meta:
        model = Receipt
        fields = [
            "id",
            "supplier",
            "recognized_supplier",
            "status",
            "xlsx_url",
            "created_by",
            "created_at",
            "photos",
            "lines",
        ]
        read_only_fields = [
            "id",
            "supplier",
            "recognized_supplier",
            "status",
            "xlsx_url",
            "created_by",
            "created_at",
            "photos",
            "lines",
        ]


class ReceiptCreateSerializer(serializers.ModelSerializer):
    """Create a draft receipt; supplier optional (scan-first flow).

    The camera-first PWA posts an empty body (or ``{"supplier": null}``) to open a
    ``draft`` receipt with **no** supplier — the vendor is auto-detected from the
    photographed invoice header on recognition (see
    ``apps.receipts.tasks.recognize_receipt_task``). A supplier may still be sent
    explicitly (legacy "pick first" flow). The legacy ``photo_urls`` field remains
    optional for the pre-upload-then-POST path; each URL becomes a
    :class:`~apps.receipts.models.ReceiptPhoto`.

    Attributes:
        supplier: Optional supplier id. ``required=False`` and ``allow_null=True``
            so a scan-first draft can be created without one.
        photo_urls: List of stored image URLs for the invoice pages. Optional —
            a receipt may be created first and photos attached on recognize.
    """

    # Supplier is optional for the scan-first flow: a draft can exist before the
    # vendor is known. ``allow_null=True`` lets the client send ``null`` explicitly.
    supplier = serializers.PrimaryKeyRelatedField(
        queryset=Supplier.objects.all(),
        required=False,
        allow_null=True,
    )
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


class ReceiptUpdateSerializer(serializers.ModelSerializer):
    """Set or change the receipt's supplier (``PATCH /api/receipts/{id}/``).

    The auto-supplier flow may leave a receipt with no supplier (OCR found none),
    or the operator may correct a mis-detected one. This serializer validates the
    single writable field — ``supplier`` (a supplier id) — and ``allow_null=True``
    lets a caller deliberately clear it. The view re-runs per-supplier mapping and
    recomputes status after the change.

    WHY only ``supplier`` is writable here:
        Status, photos, lines, and the audit ``recognized_supplier`` are advanced
        by their own dedicated endpoints / the OCR task — exposing them here would
        let a PATCH bypass the status machine. Keeping the surface to ``supplier``
        keeps this a focused "set the vendor" mutation.
    """

    supplier = serializers.PrimaryKeyRelatedField(
        queryset=Supplier.objects.all(),
        required=False,
        allow_null=True,
    )

    class Meta:
        model = Receipt
        fields = ["supplier"]

    def to_representation(self, instance: Receipt) -> dict:
        """Return the full receipt after the supplier change.

        Args:
            instance: The updated receipt.

        Returns:
            The :class:`ReceiptSerializer` output so the client gets the receipt
            with its nested supplier, refreshed line mappings and recomputed
            status in one round-trip.
        """

        return ReceiptSerializer(instance, context=self.context).data


class ReceiptPhotoUploadResultSerializer(serializers.Serializer):
    """Response schema for the photo-upload endpoint.

    Attributes:
        id: Primary key of the created :class:`ReceiptPhoto`.
        image_url: URL of the stored image (from ``image.url``), for the UI to
            render a thumbnail immediately.
    """

    id = serializers.IntegerField(read_only=True)
    image_url = serializers.CharField(read_only=True)


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
