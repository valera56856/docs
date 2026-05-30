"""Django admin registration for the suppliers app.

Registers :class:`~apps.suppliers.models.Supplier` so staff can manage the
vendor directory (add suppliers, toggle ``is_active``) from the Django admin.
"""

from __future__ import annotations

from django.contrib import admin

from apps.suppliers.models import Supplier


@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    """Admin configuration for :class:`Supplier`.

    Provides quick filtering by active state, name search, and an inline
    ``is_active`` toggle in the changelist for fast activation/deactivation.
    """

    list_display = ("name", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("name", "note")
    list_editable = ("is_active",)
