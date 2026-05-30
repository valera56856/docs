"""Database models for the receipts app.

Defines the three models that make up the receipt workflow:

* :class:`Receipt` — one supplier invoice being processed, with a status that
  drives the UI state machine.
* :class:`ReceiptPhoto` — a photographed page of the invoice (image URL in
  storage, typically Cloudflare R2).
* :class:`ReceiptLine` — a single recognized line item, carrying the OCR result,
  editable quantity/price, and the resolved catalog product.

Why ``DecimalField`` for quantity and price:
    Quantities and money must be represented exactly. Floating point would
    introduce rounding errors in cost math and Excel output, so both use
    ``DecimalField``. Quantity allows 3 decimals (weighted / fractional goods);
    price allows 2 decimals (currency).
"""

from __future__ import annotations

from django.db import models


class Receipt(models.Model):
    """A single supplier invoice being processed through the pipeline.

    The :attr:`status` field is the workflow state machine the frontend renders
    and the Celery tasks advance:
    ``draft → recognizing → needs_mapping/ready → xlsx_ready``, with ``error`` as
    a terminal failure state.

    Attributes:
        supplier: The vendor this invoice is from. ``PROTECT`` on delete because
            a supplier with historical receipts must not be silently removable —
            doing so would orphan financial records.
        status: Current workflow stage; one of the values in :attr:`STATUS`.
            Defaults to ``"draft"``.
        xlsx_url: URL of the generated ``.xlsx`` receipt once available; blank
            until ``generate-xlsx`` runs.
        created_by: Identifier (username/email) of the manager who created it.
        created_at: Timestamp set once when the receipt is created.
    """

    STATUS = [
        ("draft", "Чернетка"),
        ("recognizing", "Розпізнається"),
        ("needs_mapping", "Потрібен маппінг"),
        ("ready", "Готовий до генерації"),
        ("xlsx_ready", "Excel згенеровано"),
        ("error", "Помилка"),
    ]

    supplier = models.ForeignKey(
        "suppliers.Supplier",
        on_delete=models.PROTECT,
        related_name="receipts",
    )
    status = models.CharField(max_length=20, choices=STATUS, default="draft")
    xlsx_url = models.URLField(blank=True)
    created_by = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        """Return a readable label for admin lists and logs.

        Returns:
            The receipt id, supplier and status, e.g.
            ``"Receipt #12 — Постачальник (ready)"``.
        """

        return f"Receipt #{self.pk} — {self.supplier} ({self.status})"


class ReceiptPhoto(models.Model):
    """A single photographed page of a receipt's invoice.

    Attributes:
        receipt: The receipt this photo belongs to. Cascades on receipt delete.
        image_url: URL of the stored image (typically Cloudflare R2); this is
            what OCR fetches and the UI displays.
    """

    receipt = models.ForeignKey(
        Receipt,
        related_name="photos",
        on_delete=models.CASCADE,
    )
    image_url = models.URLField()

    def __str__(self) -> str:
        """Return a readable label for admin lists and logs.

        Returns:
            A label tying the photo to its receipt, e.g. ``"Photo of Receipt #12"``.
        """

        return f"Photo of Receipt #{self.receipt_id}"


class ReceiptLine(models.Model):
    """One recognized line item on a receipt.

    Each line starts from the OCR output (``recognized_*`` fields plus
    :attr:`raw_ocr_json` for audit), is resolved to a catalog product by the
    mapping step, and may be edited by the operator before Excel generation.

    Attributes:
        receipt: The owning receipt. Cascades on receipt delete.
        recognized_sku: Supplier SKU as recognized from the invoice.
        recognized_name: Product name as recognized; blank if OCR omitted it.
        quantity: Quantity, exact to 3 decimals (supports fractional/weighted
            goods). Defaults to 0.
        price: Purchase price / cost, exact to 2 decimals. Nullable because OCR
            may fail to read a price; the operator can fill it in.
        matched_product: The catalog product this line resolved to, or ``None``
            when unmapped. ``SET_NULL`` on product delete so the line survives if
            a catalog product is removed (it simply becomes unmatched again).
        match_status: How the line was matched — one of :attr:`MATCH`
            (``auto`` / ``manual`` / ``unmapped``). Defaults to ``"unmapped"``.
        raw_ocr_json: The raw per-line OCR JSON from Gemini, kept for audit and
            for re-running mapping without re-OCR.
    """

    MATCH = [
        ("auto", "Авто"),
        ("manual", "Вручну"),
        ("unmapped", "Не знайдено"),
    ]

    receipt = models.ForeignKey(
        Receipt,
        related_name="lines",
        on_delete=models.CASCADE,
    )
    recognized_sku = models.CharField(max_length=255)
    recognized_name = models.CharField(max_length=500, blank=True)
    quantity = models.DecimalField(max_digits=12, decimal_places=3, default=0)
    price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
    )
    matched_product = models.ForeignKey(
        "catalog.OurProduct",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="receipt_lines",
    )
    match_status = models.CharField(max_length=10, choices=MATCH, default="unmapped")
    raw_ocr_json = models.JSONField(null=True, blank=True)

    def __str__(self) -> str:
        """Return a readable label for admin lists and logs.

        Returns:
            The recognized SKU, quantity and match status, e.g.
            ``"SKU-7 x 3.000 (auto)"``.
        """

        return f"{self.recognized_sku} x {self.quantity} ({self.match_status})"
