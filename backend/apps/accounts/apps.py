"""Django application configuration for the accounts app."""

from __future__ import annotations

from django.apps import AppConfig


class AccountsConfig(AppConfig):
    """App config for the accounts domain.

    Attributes:
        default_auto_field: Use 64-bit ``BigAutoField`` primary keys so the
            schema does not need a painful migration if row counts ever grow
            past the 32-bit ``AutoField`` ceiling.
        name: Dotted path of the app. It is ``"apps.accounts"`` (not bare
            ``"accounts"``) because every Valeraup app lives under the
            ``apps`` namespace package and is imported that way in
            ``INSTALLED_APPS``.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.accounts"
