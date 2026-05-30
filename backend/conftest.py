"""Project-wide pytest fixtures for the Valeraup backend.

These fixtures are shared across the ``backend/tests`` suite. They provide:

* ``api_client`` — an unauthenticated DRF ``APIClient``.
* ``user`` — a persisted Django user with an attached operator ``Profile``.
* ``auth_client`` — an ``APIClient`` pre-authenticated as ``user`` via a
  SimpleJWT access token.

Why JWT-forced auth rather than session login: the API authenticates exclusively
with SimpleJWT, so tests must exercise the same path the PWA uses.
"""
from __future__ import annotations

import pytest


@pytest.fixture
def api_client():
    """Return a fresh, unauthenticated DRF API client.

    Returns:
        rest_framework.test.APIClient: A client with no credentials attached.
            Useful for asserting that protected endpoints reject anonymous
            requests (HTTP 401).
    """
    from rest_framework.test import APIClient

    return APIClient()


@pytest.fixture
def user(db):
    """Create and return a persisted user with an operator profile.

    The ``apps.accounts`` ``Profile`` is created explicitly so tests do not
    depend on signal wiring that may not exist yet in the skeleton.

    Args:
        db: pytest-django database fixture (enables DB access).

    Returns:
        django.contrib.auth.models.User: The created user, email
            ``operator@example.com``.
    """
    from django.contrib.auth import get_user_model

    user_model = get_user_model()
    created = user_model.objects.create_user(
        username="operator",
        email="operator@example.com",
        password="pass1234",
    )

    # Attach a Profile if the accounts app is migrated/available. Guarded so the
    # fixture stays usable even before the accounts models exist.
    try:
        from apps.accounts.models import Profile

        Profile.objects.get_or_create(
            user=created, defaults={"role": Profile.ROLE_OPERATOR}
        )
    except Exception:  # pragma: no cover - profile is optional for some tests
        pass

    return created


@pytest.fixture
def auth_client(api_client, user):
    """Return an API client authenticated as ``user`` via a JWT access token.

    Args:
        api_client: The unauthenticated client fixture.
        user: The persisted user fixture to authenticate as.

    Returns:
        rest_framework.test.APIClient: The same client with an
            ``Authorization: Bearer <token>`` header set.
    """
    from rest_framework_simplejwt.tokens import RefreshToken

    token = RefreshToken.for_user(user)
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {token.access_token}")
    return api_client
