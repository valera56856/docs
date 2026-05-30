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

from apps.catalog.models import OurProduct
from integrations import salesdrive

logger = logging.getLogger(__name__)


def sync_catalog(yml_url: str) -> int:
    """Fetch, parse and upsert the SalesDrive catalog into ``OurProduct``.

    Idempotent: running it repeatedly converges the local cache to whatever the
    YML currently contains. Each offer is upserted by ``salesdrive_id`` so
    existing rows are updated rather than duplicated.

    Args:
        yml_url: URL of the SalesDrive YML export. If falsy, falls back to
            ``settings.SALESDRIVE_YML_URL``.

    Returns:
        The number of products synced (created or updated) in this run.

    Raises:
        ValueError: If no YML URL is available (neither argument nor setting),
            or if the downloaded YML is not parseable.
        requests.RequestException: On network errors while fetching the YML.
    """

    resolved_url = yml_url or settings.SALESDRIVE_YML_URL
    if not resolved_url:
        raise ValueError(
            "No SalesDrive YML URL provided and SALESDRIVE_YML_URL is unset"
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
