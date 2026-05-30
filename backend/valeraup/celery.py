"""Celery application factory and beat schedule for Valeraup.

Defines the project-wide Celery app, wires it to Django settings (all broker /
result backend / serialization options are read from the ``CELERY_*`` namespace
in ``valeraup.settings``), and autodiscovers ``tasks.py`` modules across the
installed apps.

A daily beat schedule is registered for the SalesDrive catalog sync so that the
local cache of ``OurProduct`` rows is refreshed without manual intervention.

Why the indirection: Django and Celery both want to "own" configuration. We let
Django own everything (via ``config_from_object`` with the ``CELERY`` namespace)
so there is a single source of truth, and Celery merely consumes it.
"""
from __future__ import annotations

import os

from celery import Celery
from celery.schedules import crontab

# Ensure the settings module is configured before the app reads from it. This
# mirrors ``manage.py`` / ``wsgi.py`` so the worker process can boot standalone.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "valeraup.settings")

app = Celery("valeraup")

# Pull every ``CELERY_*`` setting from Django settings. Using a namespace keeps
# Celery config grouped and discoverable in ``settings.py``.
app.config_from_object("django.conf:settings", namespace="CELERY")

# Discover ``tasks.py`` in each app listed in INSTALLED_APPS.
app.autodiscover_tasks()

# ---------------------------------------------------------------------------
# Beat schedule
# ---------------------------------------------------------------------------
# Refresh the SalesDrive catalog cache once per day at 03:00 server time. The
# task accepts an optional YML URL; when omitted it falls back to the
# ``SALESDRIVE_YML_URL`` setting, so no argument is needed here.
app.conf.beat_schedule = {
    "sync-salesdrive-catalog-daily": {
        "task": "apps.catalog.tasks.sync_catalog_task",
        "schedule": crontab(hour=3, minute=0),
    },
}


@app.task(bind=True, ignore_result=True)
def debug_task(self) -> None:  # pragma: no cover - diagnostic helper only
    """Print this task's request for connectivity debugging.

    Useful for verifying that the worker is reachable and able to execute tasks.

    Args:
        self: The bound task instance (provided by ``bind=True``).
    """
    print(f"Request: {self.request!r}")
