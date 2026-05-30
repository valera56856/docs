"""Celery tasks for the catalog app.

Wraps :func:`apps.catalog.services.sync_catalog` as a Celery task so catalog
refreshes run off the request/response cycle. Two entry points use it:

* The manual ``POST /api/sync/catalog/`` endpoint (admin-triggered).
* The daily beat schedule registered in :mod:`valeraup.celery`
  (``sync-salesdrive-catalog-daily``), which calls this task with no argument so
  it falls back to ``settings.SALESDRIVE_YML_URL``.

WHY a thin task: all real work lives in the service. The task only adapts the
call to Celery (serialization-friendly arguments, structured logging of the
outcome) and is the unit Celery beat references by its dotted path.
"""

from __future__ import annotations

import logging

from celery import shared_task

from apps.catalog.services import sync_catalog

logger = logging.getLogger(__name__)


@shared_task(name="apps.catalog.tasks.sync_catalog_task")
def sync_catalog_task(yml_url: str | None = None) -> int:
    """Sync the SalesDrive catalog into the local cache (Celery task).

    Registered in the Celery beat schedule for a daily refresh and also enqueued
    on demand by the admin sync endpoint. Delegates entirely to
    :func:`apps.catalog.services.sync_catalog`.

    Args:
        yml_url: Optional YML export URL. When ``None`` (the beat-schedule case),
            the service falls back to ``settings.SALESDRIVE_YML_URL``.

    Returns:
        The number of products synced in this run.
    """

    logger.info("catalog_sync_task_received", extra={"url": yml_url})
    # Pass an empty string when None so the service applies its settings
    # fallback; ``sync_catalog`` treats falsy values identically.
    count = sync_catalog(yml_url or "")
    logger.info("catalog_sync_task_done", extra={"synced": count})
    return count
