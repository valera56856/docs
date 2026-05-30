"""Django admin registration for the accounts app.

Registers :class:`~apps.accounts.models.Profile` so administrators can inspect
and adjust user roles from the Django admin. The hashed PIN is intentionally not
exposed for editing here; PINs are set through the dedicated auth flow.
"""

from __future__ import annotations

from django.contrib import admin

from apps.accounts.models import Profile


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    """Admin configuration for :class:`Profile`.

    Shows the linked user and role in the changelist and lets staff filter by
    role and search by username/email. ``pin_hash`` is read-only so it cannot be
    accidentally edited or pasted in plaintext.
    """

    list_display = ("user", "role")
    list_filter = ("role",)
    search_fields = ("user__username", "user__email")
    readonly_fields = ("pin_hash",)
