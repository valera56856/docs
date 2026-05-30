"""Django application configuration for the receipts app."""

from __future__ import annotations

from django.apps import AppConfig


class ReceiptsConfig(AppConfig):
    """App config for the receipts domain.

    Attributes:
        default_auto_field: Use ``BigAutoField`` primary keys (project-wide
            convention).
        name: Dotted path ``"apps.receipts"`` matching the ``apps`` namespace
            package used across the project.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.receipts"
