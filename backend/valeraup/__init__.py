"""Valeraup Django project package.

Importing the Celery application here guarantees that the shared ``app`` object
is created and registered as soon as Django starts. This is required so that the
``@shared_task`` decorator used across the apps binds to *this* Celery app, and
so beat/worker processes pick up the autodiscovered tasks.
"""
from __future__ import annotations

from .celery import app as celery_app

__all__ = ("celery_app",)
