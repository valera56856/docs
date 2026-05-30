"""Business logic for syncing the SalesDrive catalog into the local cache.

This module owns the ORM side of catalog synchronization: it pulls the SalesDrive
YML (via :mod:`integrations.salesdrive`), parses it, and upserts the rows into
:class:`~apps.catalog.models.OurProduct` keyed by ``salesdrive_id``.

WHY a separate service (not in the view or task):
    Keeping the sync logic here makes it callable from three places — the manual
    ``POST /api/sync/catalog/`` endpoint, the daily Celery beat task, and tests —
    without duplicating the upsert. Views/tasks stay thin wrappers.

WHY ``update_or_create`` keyed on ``salesdrive_id``:
    ``salesdrive_id`` is SalesDrive's stable identifier and is ``unique`` on the
    model. Upserting on it means a re-sync updates names/SKUs in place instead of
    creating duplicates, which is the whole point of an idempotent cache refresh.
"""

from __future__ import annotations

import logging

from django.conf import settings
from django.db import transaction

from apps.catalog.models import IntegrationSettings, OurProduct
from integrations import salesdrive

logger = logging.getLogger(__name__)


def sync_catalog(yml_url: str | None = None) -> int:
    """Fetch, parse and upsert the SalesDrive catalog into ``OurProduct``.

    Idempotent: running it repeatedly converges the local cache to whatever the
    YML currently contains. Each offer is upserted by ``salesdrive_id`` so
    existing rows are updated rather than duplicated.

    The YML URL is resolved in priority order so the admin-editable DB value wins
    over the deploy-time env fallback:

    1. The explicit ``yml_url`` argument (e.g. a one-off override).
    2. :attr:`IntegrationSettings.salesdrive_yml_url` (set via the Settings UI).
    3. ``settings.SALESDRIVE_YML_URL`` (env fallback).

    Args:
        yml_url: Optional URL of the SalesDrive YML export. If falsy, falls back
            to the DB-configured value and then ``settings.SALESDRIVE_YML_URL``.

    Returns:
        The number of products synced (created or updated) in this run.

    Raises:
        ValueError: If no YML URL is available (argument, DB config and setting
            are all blank), or if the downloaded YML is not parseable.
        requests.RequestException: On network errors while fetching the YML.
    """

    resolved_url = (
        yml_url
        or IntegrationSettings.load().salesdrive_yml_url
        or settings.SALESDRIVE_YML_URL
    )
    if not resolved_url:
        raise ValueError(
            "No SalesDrive YML URL provided, IntegrationSettings is blank, and "
            "SALESDRIVE_YML_URL is unset"
        )

    logger.info("catalog_sync_start", extra={"url": resolved_url})

    raw = salesdrive.fetch_catalog_yml(resolved_url)
    products = salesdrive.parse_catalog_yml(raw)

    synced = 0
    created = 0
    # Wrap the upserts in one transaction: a partial sync that fails halfway
    # should not leave the cache in a torn, half-updated state.
    with transaction.atomic():
        for product in products:
            _, was_created = OurProduct.objects.update_or_create(
                salesdrive_id=product["salesdrive_id"],
                defaults={
                    "sku": product.get("sku", ""),
                    "name": product.get("name", ""),
                },
            )
            synced += 1
            if was_created:
                created += 1

    logger.info(
        "catalog_sync_done",
        extra={
            "url": resolved_url,
            "synced": synced,
            "created_count": created,
            "updated": synced - created,
        },
    )
    return synced


def probe_catalog_yml(yml_url: str) -> dict[str, int]:
    """Fetch and parse a SalesDrive YML URL without writing anything.

    This is the read-only "test connection" path: it downloads the export and
    parses it (the same boundary calls :func:`sync_catalog` uses) but performs no
    database upsert. It exists so the Settings UI can validate a URL before the
    admin commits to saving/syncing it.

    Exceptions are intentionally **not** caught here — the caller (the
    test-connection view) converts any fetch/parse error into a friendly
    ``{"ok": false, "error": ...}`` payload, keeping HTTP-vs-domain concerns in
    the view layer.

    Args:
        yml_url: The SalesDrive YML export URL to probe.

    Returns:
        A dict ``{"product_count": int}`` with the number of offers the YML
        currently contains.

    Raises:
        ValueError: If the URL is empty or the downloaded YML is not parseable.
        requests.RequestException: On network errors while fetching the YML.
    """

    logger.info("catalog_probe_start", extra={"url": yml_url})
    raw = salesdrive.fetch_catalog_yml(yml_url)
    products = salesdrive.parse_catalog_yml(raw)
    logger.info(
        "catalog_probe_done",
        extra={"url": yml_url, "product_count": len(products)},
    )
    return {"product_count": len(products)}
