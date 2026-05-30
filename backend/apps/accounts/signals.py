"""Signal handlers for the accounts app.

This module guarantees the one-to-one invariant between an auth user and a
:class:`~apps.accounts.models.Profile`: every user must have exactly one profile
so role checks and the PIN-login flow never hit a missing-profile branch.

WHY a ``post_save`` signal rather than overriding ``create_user``:
    Users are created through several paths — the Django admin, ``createsuperuser``,
    ``create_user`` in tests, and any future REST signup. A signal on
    ``AUTH_USER_MODEL`` is the single place that fires for *all* of them, so we
    cannot forget to attach a profile in one code path. Using ``get_or_create``
    keeps it idempotent: re-saving a user (or a fixture that already created the
    profile explicitly) never raises a duplicate-row error.

WHY ``get_or_create`` (not ``create``):
    The shared pytest ``user`` fixture and some seed scripts create a profile
    explicitly. If this handler unconditionally created one it would clash with
    the ``OneToOneField`` uniqueness. ``get_or_create`` converges to "exactly one
    profile" regardless of who got there first.
"""

from __future__ import annotations

import logging
from typing import Any

from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)


@receiver(post_save, sender=settings.AUTH_USER_MODEL, dispatch_uid="accounts.ensure_profile")
def ensure_profile(sender: type, instance: Any, created: bool, **kwargs: Any) -> None:
    """Ensure every saved user has exactly one operator :class:`Profile`.

    Connected to ``post_save`` on ``AUTH_USER_MODEL`` in
    :meth:`apps.accounts.apps.AccountsConfig.ready`. Runs on every user save but
    only ever creates a profile when one is missing, so it is safe to fire on
    updates and idempotent across redundant saves.

    Args:
        sender: The user model class that emitted the signal.
        instance: The user instance that was just saved.
        created: ``True`` when the user row was newly inserted. We act on every
            save (not just creation) so a user that somehow lost its profile gets
            one back, but ``get_or_create`` makes the common update path a no-op.
        **kwargs: Remaining signal keyword arguments (``raw``, ``using``,
            ``update_fields``); ignored here.

    Returns:
        None.

    Notes:
        Imported lazily to avoid touching the model at app-loading time. Defaults
        the role to ``operator`` (least privilege); promotion to ``admin`` is a
        deliberate admin action, never automatic.
    """

    # Skip loaddata/fixtures: ``raw`` saves bypass normal model state and related
    # tables may not be populated yet, so creating a profile then is unsafe.
    if kwargs.get("raw", False):
        return

    from .models import Profile

    _, was_created = Profile.objects.get_or_create(
        user=instance,
        defaults={"role": Profile.ROLE_OPERATOR},
    )
    if was_created:
        logger.info(
            "profile_auto_created",
            extra={"user_id": instance.pk, "role": Profile.ROLE_OPERATOR},
        )
