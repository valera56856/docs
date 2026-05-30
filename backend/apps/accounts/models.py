"""Database models for the accounts app.

This module defines the :class:`Profile` model, a one-to-one extension of the
built-in Django user that stores Valeraup-specific authentication metadata:
the user's role and a hashed PIN for the fast PIN/biometric login flow.

Why store a *hashed* PIN rather than the raw value:
    The PIN is a credential. We never persist it in plaintext. Use Django's
    ``django.contrib.auth.hashers.make_password`` to write ``pin_hash`` and
    ``check_password`` to verify it during the ``/api/auth/pin/`` flow, exactly
    as Django hashes regular passwords. This keeps the PIN safe at rest and lets
    us benefit from Django's configured password hashers.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models


class Profile(models.Model):
    """Per-user Valeraup profile holding role and PIN credential.

    Each Django user has exactly one :class:`Profile` (one-to-one). The profile
    carries the access role (admin vs operator) used for permission checks, and
    a hashed PIN that powers the convenient fast-login endpoint.

    Attributes:
        user: One-to-one link to the project's auth user. Deleting the user
            cascades to (and removes) the profile.
        role: Access role, one of :attr:`ROLE_ADMIN` or :attr:`ROLE_OPERATOR`.
            Defaults to operator (least privilege).
        pin_hash: Django-hashed 4-digit PIN. Blank when no PIN is set. Written
            with ``make_password`` and verified with ``check_password``; it is
            never stored or compared in plaintext.
    """

    ROLE_ADMIN = "admin"
    ROLE_OPERATOR = "operator"
    ROLE_CHOICES = [
        (ROLE_ADMIN, "Адмін"),
        (ROLE_OPERATOR, "Оператор"),
    ]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile",
    )
    role = models.CharField(
        max_length=10,
        choices=ROLE_CHOICES,
        default=ROLE_OPERATOR,
    )
    # Django-hashed PIN (use make_password / check_password). Blank = no PIN set.
    pin_hash = models.CharField(max_length=255, blank=True)

    def __str__(self) -> str:
        """Return a readable label for admin lists and logs.

        Returns:
            The associated username followed by the role, e.g. ``"valera (admin)"``.
        """

        return f"{self.user} ({self.role})"
