"""Django application configuration for the mapping app."""

from __future__ import annotations

from django.apps import AppConfig


class MappingConfig(AppConfig):
    """App config for the mapping domain.

    Attributes:
        default_auto_field: Use ``BigAutoField`` primary keys (project-wide
            convention).
        name: Dotted path ``"apps.mapping"`` matching the ``apps`` namespace
            package used across the project.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.mapping"
