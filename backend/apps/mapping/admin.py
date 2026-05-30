"""Django admin registration for the mapping app.

Registers :class:`~apps.mapping.models.ArticleMapping` so staff can audit and,
if needed, correct remembered SKU mappings. The normalized SKU, usage counter,
and creation metadata are read-only because they are maintained automatically by
the mapping services.
"""

from __future__ import annotations

from django.contrib import admin

from apps.mapping.models import ArticleMapping


@admin.register(ArticleMapping)
class ArticleMappingAdmin(admin.ModelAdmin):
    """Admin configuration for :class:`ArticleMapping`.

    Lets staff filter by supplier, search by SKU/product, and review how often a
    mapping has been used — without being able to corrupt the derived fields
    (``supplier_sku_normalized``, ``times_used``, ``created_*``), which are
    managed by ``apps.mapping.services``.
    """

    list_display = (
        "supplier",
        "supplier_sku",
        "our_product",
        "times_used",
        "created_by",
        "created_at",
    )
    list_filter = ("supplier",)
    search_fields = (
        "supplier_sku",
        "supplier_sku_normalized",
        "our_product__sku",
        "our_product__name",
    )
    readonly_fields = ("supplier_sku_normalized", "times_used", "created_at")
