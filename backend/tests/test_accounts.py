"""Behavior tests for the accounts app (profiles, PIN, role permissions).

These tests pin down the auth/identity contract that the rest of the system
relies on:

* A :class:`~apps.accounts.models.Profile` is **auto-created** for every new user
  via the ``post_save`` signal connected in ``AccountsConfig.ready`` — no code
  path may leave a user profile-less.
* ``POST /api/auth/set-pin/`` hashes the caller's PIN, after which the
  email + PIN login at ``POST /api/auth/pin/`` round-trips and returns a JWT pair.
* ``GET /api/auth/me/`` reports ``email``, ``role`` and ``has_pin``.
* :class:`~apps.accounts.permissions.IsAdmin` blocks an operator and admits an
  admin on a protected endpoint.

The PIN is never asserted in plaintext anywhere — only its observable effect (a
successful login) is checked, matching the "never store/log a raw PIN" rule.

All DB-touching tests use ``@pytest.mark.django_db``.
"""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model

from apps.accounts.models import Profile

User = get_user_model()

# Endpoint paths under test. Constants keep a path change to a one-line edit.
SET_PIN_PATH = "/api/auth/set-pin/"
PIN_LOGIN_PATH = "/api/auth/pin/"
ME_PATH = "/api/auth/me/"
SYNC_CATALOG_PATH = "/api/sync/catalog/"


# ---------------------------------------------------------------------------
# Profile auto-creation via signal
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_profile_auto_created_on_user_create() -> None:
    """Creating a user auto-creates exactly one operator profile.

    The ``post_save`` signal (wired in ``AccountsConfig.ready``) must attach a
    profile to *every* new user, defaulting to the least-privileged operator role.
    This is the invariant that lets every permission/role check assume a profile
    exists.
    """
    user = User.objects.create_user(
        username="auto", email="auto@example.com", password="pass1234"
    )

    profiles = Profile.objects.filter(user=user)
    assert profiles.count() == 1
    assert profiles.first().role == Profile.ROLE_OPERATOR
    assert profiles.first().pin_hash == ""


@pytest.mark.django_db
def test_profile_signal_is_idempotent_on_resave() -> None:
    """Re-saving a user does not create a second profile.

    ``get_or_create`` in the signal makes the update path a no-op, preserving the
    one-to-one invariant even when the user row is saved repeatedly.
    """
    user = User.objects.create_user(
        username="resave", email="resave@example.com", password="pass1234"
    )
    user.first_name = "Updated"
    user.save()

    assert Profile.objects.filter(user=user).count() == 1


# ---------------------------------------------------------------------------
# set-pin → PIN login round-trip
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_set_pin_then_pin_login_round_trips(auth_client, user) -> None:
    """Setting a PIN enables the email + PIN login to mint a JWT pair.

    Proves the full credential round-trip: ``set-pin`` hashes the PIN onto the
    caller's profile (204), and a subsequent ``pin`` login with the correct
    email + PIN returns 200 with ``access`` and ``refresh`` tokens.
    """
    set_response = auth_client.post(SET_PIN_PATH, {"pin": "4321"}, format="json")
    assert set_response.status_code == 204

    # The hash is stored (not the plaintext); we only assert a hash is present.
    profile = Profile.objects.get(user=user)
    assert profile.pin_hash
    assert profile.pin_hash != "4321"

    login_response = auth_client.post(
        PIN_LOGIN_PATH,
        {"email": user.email, "pin": "4321"},
        format="json",
    )
    assert login_response.status_code == 200
    assert "access" in login_response.data
    assert "refresh" in login_response.data


@pytest.mark.django_db
def test_pin_login_rejects_wrong_pin(auth_client, user) -> None:
    """A wrong PIN is rejected with 401 after a PIN is set.

    Confirms ``check_password`` actually gates the login rather than the endpoint
    accepting any 4-digit string.
    """
    auth_client.post(SET_PIN_PATH, {"pin": "4321"}, format="json")

    response = auth_client.post(
        PIN_LOGIN_PATH,
        {"email": user.email, "pin": "0000"},
        format="json",
    )
    assert response.status_code == 401


@pytest.mark.django_db
def test_set_pin_validates_four_digits(auth_client) -> None:
    """A non-4-digit PIN is rejected with a 400 validation error."""
    response = auth_client.post(SET_PIN_PATH, {"pin": "12"}, format="json")
    assert response.status_code == 400


@pytest.mark.django_db
def test_set_pin_requires_authentication(api_client) -> None:
    """Anonymous callers cannot set a PIN (401).

    You must already have proven you own the account before you can attach a PIN
    to it.
    """
    response = api_client.post(SET_PIN_PATH, {"pin": "1234"}, format="json")
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# me endpoint
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_me_reports_email_role_and_has_pin(auth_client, user) -> None:
    """``/api/auth/me/`` returns ``email``, ``role`` and ``has_pin``.

    ``has_pin`` starts ``False`` and flips to ``True`` once a PIN is set, which is
    how the PWA decides whether to offer the PIN-login affordance.
    """
    before = auth_client.get(ME_PATH)
    assert before.status_code == 200
    assert before.data["email"] == user.email
    assert before.data["role"] == Profile.ROLE_OPERATOR
    assert before.data["has_pin"] is False

    auth_client.post(SET_PIN_PATH, {"pin": "1357"}, format="json")

    after = auth_client.get(ME_PATH)
    assert after.data["has_pin"] is True


# ---------------------------------------------------------------------------
# IsAdmin permission
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_isadmin_blocks_operator_on_protected_view(auth_client) -> None:
    """An operator is forbidden from the admin-only catalog-sync endpoint.

    ``IsAdmin`` keys on the profile role, so the default operator user (from the
    ``auth_client`` fixture) gets 403 — the role check, not Django ``is_staff``,
    governs access.
    """
    response = auth_client.post(SYNC_CATALOG_PATH)
    assert response.status_code == 403


@pytest.mark.django_db
def test_isadmin_allows_admin_on_protected_view(api_client, monkeypatch) -> None:
    """An admin-role user may enqueue a catalog sync (202).

    The Celery ``.delay`` is monkeypatched so the test never touches a broker:
    we only verify the permission gate opens and the endpoint accepts the request.
    """
    from rest_framework_simplejwt.tokens import RefreshToken

    admin_user = User.objects.create_user(
        username="adminuser", email="admin@example.com", password="pass1234"
    )
    # Promote the auto-created profile to admin.
    profile = Profile.objects.get(user=admin_user)
    profile.role = Profile.ROLE_ADMIN
    profile.save(update_fields=["role"])

    # Avoid hitting Celery/broker: stub out the task's ``delay``.
    class _FakeAsyncResult:
        id = "fake-task-id"

    from apps.catalog import tasks

    monkeypatch.setattr(
        tasks.sync_catalog_task, "delay", lambda *a, **k: _FakeAsyncResult()
    )

    token = RefreshToken.for_user(admin_user)
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {token.access_token}")

    response = api_client.post(SYNC_CATALOG_PATH)
    assert response.status_code == 202
    assert response.data["task_id"] == "fake-task-id"
