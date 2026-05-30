"""Django application configuration for the suppliers app."""

from __future__ import annotations

from django.apps import AppConfig


class SuppliersConfig(AppConfig):
    """App config for the suppliers domain.

    Attributes:
        default_auto_field: Use ``BigAutoField`` primary keys (see project-wide
            convention) to avoid a future 32-bit ID exhaustion migration.
        name: Dotted path ``"apps.suppliers"`` matching the ``apps`` namespace
            package used across the project.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.suppliers"
