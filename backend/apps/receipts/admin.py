"""Django admin registration for the receipts app.

Registers :class:`~apps.receipts.models.Receipt` (with inline photos and lines)
plus :class:`~apps.receipts.models.ReceiptPhoto` and
:class:`~apps.receipts.models.ReceiptLine`. Inlines let staff inspect a full
receipt — its photos and recognized lines — from one admin page, which is the
fastest way to debug an OCR/mapping run.
"""

from __future__ import annotations

from django.contrib import admin

from apps.receipts.models import Receipt, ReceiptLine, ReceiptPhoto


class ReceiptPhotoInline(admin.TabularInline):
    """Inline editor for a receipt's photographed pages.

    Shows both the uploaded ``image`` file and the derived ``image_url`` so staff
    can confirm a page reached storage and inspect what OCR will read.
    """

    model = ReceiptPhoto
    extra = 0
    fields = ("image", "image_url")


class ReceiptLineInline(admin.TabularInline):
    """Inline editor for a receipt's recognized line items.

    ``raw_ocr_json`` is read-only because it is the immutable OCR audit record;
    editing it would corrupt the audit trail.
    """

    model = ReceiptLine
    extra = 0
    readonly_fields = ("raw_ocr_json",)


@admin.register(Receipt)
class ReceiptAdmin(admin.ModelAdmin):
    """Admin configuration for :class:`Receipt`.

    Shows the workflow status in the changelist, allows filtering by status and
    supplier, and embeds photos and lines as inlines for one-page inspection.
    ``recognized_supplier`` (the raw OCR supplier dict) is read-only because it is
    the immutable detection audit record — editing it would corrupt the audit
    trail of why a supplier was auto-detected.
    """

    list_display = ("id", "supplier", "status", "created_by", "created_at")
    list_filter = ("status", "supplier")
    search_fields = ("supplier__name", "created_by")
    readonly_fields = ("recognized_supplier",)
    inlines = (ReceiptPhotoInline, ReceiptLineInline)


@admin.register(ReceiptPhoto)
class ReceiptPhotoAdmin(admin.ModelAdmin):
    """Admin configuration for :class:`ReceiptPhoto` (standalone view)."""

    list_display = ("id", "receipt", "image", "image_url")


@admin.register(ReceiptLine)
class ReceiptLineAdmin(admin.ModelAdmin):
    """Admin configuration for :class:`ReceiptLine` (standalone view).

    Useful for cross-receipt queries (for example, finding all still-unmapped
    lines). ``raw_ocr_json`` is read-only to preserve the OCR audit record.
    """

    list_display = (
        "id",
        "receipt",
        "recognized_sku",
        "recognized_name",
        "quantity",
        "price",
        "match_status",
        "matched_product",
    )
    list_filter = ("match_status",)
    search_fields = ("recognized_sku", "recognized_name")
    readonly_fields = ("raw_ocr_json",)
