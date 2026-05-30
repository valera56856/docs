"""Management command: synchronously refresh the SalesDrive catalog cache.

Provides ``python manage.py sync_catalog`` so the catalog can be refreshed from
the CLI (a freshly provisioned environment, a cron entry, or a quick manual
re-sync during debugging) without going through Celery or the HTTP endpoint.

WHY a management command in addition to the Celery task and the API endpoint:
    The same :func:`apps.catalog.services.sync_catalog` powers all three, but
    each entry point suits a different operator: the API for an admin in the PWA,
    the Celery beat for the daily refresh, and this command for shell/CI use where
    you want the result printed and a non-zero exit on failure.

The command reads the YML URL from ``--url`` if given, otherwise from
``settings.SALESDRIVE_YML_URL`` (sourced from the ``SALESDRIVE_YML_URL`` env var).
It runs synchronously and prints the number of products synced.
"""

from __future__ import annotations

from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError, CommandParser

from apps.catalog.services import sync_catalog


class Command(BaseCommand):
    """Refresh the local ``OurProduct`` cache from the SalesDrive YML export."""

    help = "Синхронізувати каталог OurProduct із SalesDrive YML (синхронно)."

    def add_arguments(self, parser: CommandParser) -> None:
        """Register the optional ``--url`` override.

        Args:
            parser: The argument parser Django passes in.

        Returns:
            None.
        """

        parser.add_argument(
            "--url",
            dest="url",
            default="",
            help=(
                "URL експорту SalesDrive YML. Якщо не вказано, береться "
                "settings.SALESDRIVE_YML_URL (env SALESDRIVE_YML_URL)."
            ),
        )

    def handle(self, *args: Any, **options: Any) -> None:
        """Run the catalog sync and print the resulting count.

        Args:
            *args: Unused positional arguments.
            **options: Parsed options; ``url`` may override the configured YML URL.

        Returns:
            None.

        Raises:
            CommandError: If no YML URL is available, or the sync fails (network
                error, unparseable YML). Raising ``CommandError`` makes the
                command exit non-zero so CI/cron can detect the failure.
        """

        url = options.get("url") or settings.SALESDRIVE_YML_URL
        if not url:
            raise CommandError(
                "Не задано URL: передайте --url або встановіть SALESDRIVE_YML_URL."
            )

        self.stdout.write(f"Синхронізація каталогу з {url} ...")
        try:
            count = sync_catalog(url)
        except Exception as exc:  # noqa: BLE001 - surface any failure as CommandError
            # Re-raise as CommandError so manage.py exits non-zero with a clean
            # message instead of a traceback in routine ops use.
            raise CommandError(f"Синхронізація не вдалася: {exc}") from exc

        self.stdout.write(
            self.style.SUCCESS(f"Синхронізовано товарів: {count}")
        )
