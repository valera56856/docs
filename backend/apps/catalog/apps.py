"""Django application configuration for the catalog app."""

from __future__ import annotations

from django.apps import AppConfig


class CatalogConfig(AppConfig):
    """App config for the catalog domain.

    Attributes:
        default_auto_field: Use ``BigAutoField`` primary keys (project-wide
            convention).
        name: Dotted path ``"apps.catalog"`` matching the ``apps`` namespace
            package used across the project.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.catalog"
