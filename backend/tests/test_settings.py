"""Behavior tests for the admin SalesDrive settings API + the DB singleton.

These tests pin the contract of the DB-configurable SalesDrive integration that
the Settings PWA edits (instead of Django admin):

* ``GET  /api/settings/salesdrive/`` returns the stored YML URL plus derived
  catalog status (``last_synced``, ``product_count``).
* ``PUT  /api/settings/salesdrive/`` persists the URL onto the
  :class:`~apps.catalog.models.IntegrationSettings` singleton (always pk=1) and
  returns the same read shape.
* ``POST /api/settings/salesdrive/test/`` probes a URL (provided or stored)
  without writing, always answering HTTP 200 with ``{ok, product_count, error}``
  so a bad URL is a *result*, never a 500.

Authorization: every settings endpoint is admin-only (``IsAuthenticated`` +
``IsAdmin``) — an operator must get 403 and an anonymous caller 401.

Two singleton-level invariants are covered because the rest of the system relies
on them: :meth:`IntegrationSettings.save` always pins ``pk=1`` (one config row),
and :func:`apps.catalog.services.sync_catalog` resolves the **DB** URL ahead of
the env fallback.

The SalesDrive HTTP boundary is always mocked (``monkeypatch`` on
``integrations.salesdrive.fetch_catalog_yml``); no test hits a live export.

All DB-touching tests use ``@pytest.mark.django_db``.
"""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model

from apps.accounts.models import Profile
from apps.catalog import services
from apps.catalog.models import IntegrationSettings, OurProduct
from integrations import salesdrive

User = get_user_model()

# Endpoint paths under test. Constants keep a path change to a one-line edit.
SETTINGS_PATH = "/api/settings/salesdrive/"
TEST_PATH = "/api/settings/salesdrive/test/"

# A minimal valid YML with two offers, used to exercise the probe/sync boundary
# without a network call. Mirrors the shape in ``test_catalog.py``.
SAMPLE_YML = """<?xml version="1.0" encoding="UTF-8"?>
<yml_catalog date="2024-01-01 00:00">
  <shop>
    <offers>
      <offer id="9001">
        <name>Товар A</name>
        <vendorCode>VC-A</vendorCode>
      </offer>
      <offer id="9002">
        <name>Товар B</name>
        <vendorCode>VC-B</vendorCode>
      </offer>
    </offers>
  </shop>
</yml_catalog>
"""


@pytest.fixture
def admin_client(api_client):
    """Return an API client authenticated as an admin-role user.

    The ``user``/``auth_client`` conftest fixtures default to an *operator*, but
    the settings endpoints are admin-only, so this fixture mints a dedicated
    admin and attaches a JWT (the same path the PWA uses).

    Args:
        api_client: The unauthenticated client fixture from conftest.

    Returns:
        rest_framework.test.APIClient: A client bearing an admin JWT.
    """
    from rest_framework_simplejwt.tokens import RefreshToken

    admin_user = User.objects.create_user(
        username="settings-admin",
        email="settings-admin@example.com",
        password="pass1234",
    )
    profile = Profile.objects.get(user=admin_user)
    profile.role = Profile.ROLE_ADMIN
    profile.save(update_fields=["role"])

    token = RefreshToken.for_user(admin_user)
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {token.access_token}")
    return api_client


# ---------------------------------------------------------------------------
# IntegrationSettings singleton invariants (no HTTP)
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_integration_settings_is_a_pk1_singleton() -> None:
    """Every save pins ``pk=1`` so there is exactly one config row.

    ``load`` and any direct ``save`` must converge on the same row; saving a
    fresh, unsaved instance must overwrite pk=1 rather than insert a second row.
    This is what lets the rest of the code treat the config as a true singleton.
    """
    first = IntegrationSettings.load()
    assert first.pk == 1

    # A separately constructed instance still lands on pk=1 on save.
    second = IntegrationSettings(salesdrive_yml_url="https://example.com/a.yml")
    second.save()
    assert second.pk == 1

    assert IntegrationSettings.objects.count() == 1
    # ``load`` reflects the latest write (same row).
    assert IntegrationSettings.load().salesdrive_yml_url == "https://example.com/a.yml"


@pytest.mark.django_db
def test_sync_catalog_uses_db_url_over_env(monkeypatch, settings) -> None:
    """``sync_catalog()`` (no arg) resolves the DB URL ahead of the env var.

    Stores a URL on the singleton and sets a *different* ``SALESDRIVE_YML_URL``
    env value; the fetch boundary must be called with the DB URL, proving the
    documented resolution priority (arg > DB > env).
    """
    settings.SALESDRIVE_YML_URL = "https://env.example.com/env.yml"
    config = IntegrationSettings.load()
    config.salesdrive_yml_url = "https://db.example.com/db.yml"
    config.save()

    seen: dict[str, str] = {}

    def _fake_fetch(url: str) -> bytes:
        seen["url"] = url
        return SAMPLE_YML.encode("utf-8")

    monkeypatch.setattr(salesdrive, "fetch_catalog_yml", _fake_fetch)

    count = services.sync_catalog()

    assert seen["url"] == "https://db.example.com/db.yml"
    assert count == 2
    assert OurProduct.objects.count() == 2


# ---------------------------------------------------------------------------
# GET /api/settings/salesdrive/
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_get_settings_returns_url_and_catalog_status(admin_client) -> None:
    """GET returns the stored URL plus ``last_synced``/``product_count``.

    With one cached product and a stored URL, the read shape must surface all
    three fields so the UI renders the status line in a single round-trip.
    """
    config = IntegrationSettings.load()
    config.salesdrive_yml_url = "https://example.com/feed.yml"
    config.save()
    OurProduct.objects.create(salesdrive_id="SD-1", sku="ABC-1", name="Сорочка")

    response = admin_client.get(SETTINGS_PATH)

    assert response.status_code == 200
    assert response.data["salesdrive_yml_url"] == "https://example.com/feed.yml"
    assert response.data["product_count"] == 1
    # ``last_synced`` is the Max(OurProduct.last_synced); with one cached row it
    # is present (not null). It serializes as an ISO datetime string, so we only
    # assert presence rather than equating a str against a datetime.
    assert response.data["last_synced"] is not None


@pytest.mark.django_db
def test_get_settings_empty_when_unconfigured(admin_client) -> None:
    """A fresh install returns blank URL, null last_synced, zero products.

    The Settings page must render cleanly before any sync has ever run, so the
    derived figures degrade to ``""`` / ``None`` / ``0`` rather than erroring.
    """
    response = admin_client.get(SETTINGS_PATH)

    assert response.status_code == 200
    assert response.data["salesdrive_yml_url"] == ""
    assert response.data["last_synced"] is None
    assert response.data["product_count"] == 0


# ---------------------------------------------------------------------------
# PUT /api/settings/salesdrive/
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_put_settings_persists_url_on_singleton(admin_client) -> None:
    """PUT writes the URL onto the pk=1 singleton and echoes the read shape.

    The response must be the same shape as GET (so the UI re-renders from the
    PUT reply), and the value must actually land on ``IntegrationSettings``.
    """
    response = admin_client.put(
        SETTINGS_PATH,
        {"salesdrive_yml_url": "https://example.com/new.yml"},
        format="json",
    )

    assert response.status_code == 200
    assert response.data["salesdrive_yml_url"] == "https://example.com/new.yml"
    assert "product_count" in response.data
    assert "last_synced" in response.data

    # Persisted on the singleton (still exactly one row, still pk=1).
    assert IntegrationSettings.objects.count() == 1
    assert (
        IntegrationSettings.load().salesdrive_yml_url
        == "https://example.com/new.yml"
    )


@pytest.mark.django_db
def test_put_settings_blank_url_clears_value(admin_client) -> None:
    """A blank URL is accepted and clears the stored value (env fallback).

    Clearing is a valid action meaning "fall back to ``SALESDRIVE_YML_URL``", so
    PUT with an empty string must succeed (200) and leave the singleton blank.
    """
    config = IntegrationSettings.load()
    config.salesdrive_yml_url = "https://example.com/old.yml"
    config.save()

    response = admin_client.put(
        SETTINGS_PATH, {"salesdrive_yml_url": ""}, format="json"
    )

    assert response.status_code == 200
    assert response.data["salesdrive_yml_url"] == ""
    assert IntegrationSettings.load().salesdrive_yml_url == ""


# ---------------------------------------------------------------------------
# Authorization: admin-only
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_settings_get_forbidden_for_operator(auth_client) -> None:
    """An operator (the default ``auth_client`` user) is forbidden (403).

    Reading integration config is an admin action: the operator JWT is valid but
    ``IsAdmin`` rejects it, so DRF answers 403 rather than 401/200.
    """
    response = auth_client.get(SETTINGS_PATH)
    assert response.status_code == 403


@pytest.mark.django_db
def test_settings_put_forbidden_for_operator(auth_client) -> None:
    """An operator cannot mutate the SalesDrive settings (403)."""
    response = auth_client.put(
        SETTINGS_PATH,
        {"salesdrive_yml_url": "https://example.com/x.yml"},
        format="json",
    )
    assert response.status_code == 403
    # Nothing was written.
    assert IntegrationSettings.objects.count() == 0


@pytest.mark.django_db
def test_settings_get_requires_authentication(api_client) -> None:
    """Anonymous callers are rejected with 401 (no auth at all)."""
    response = api_client.get(SETTINGS_PATH)
    assert response.status_code == 401


@pytest.mark.django_db
def test_settings_test_forbidden_for_operator(auth_client) -> None:
    """The test-connection endpoint is admin-only too (operator → 403)."""
    response = auth_client.post(
        TEST_PATH,
        {"salesdrive_yml_url": "https://example.com/x.yml"},
        format="json",
    )
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# POST /api/settings/salesdrive/test/
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_test_connection_ok_reports_product_count(admin_client, monkeypatch) -> None:
    """A reachable, parseable URL returns ``{ok: true, product_count: N}``.

    The fetch boundary is stubbed to return the sample YML; the probe parses it
    and reports the offer count without writing any ``OurProduct`` rows.
    """
    monkeypatch.setattr(
        salesdrive, "fetch_catalog_yml", lambda url: SAMPLE_YML.encode("utf-8")
    )

    response = admin_client.post(
        TEST_PATH,
        {"salesdrive_yml_url": "https://example.com/good.yml"},
        format="json",
    )

    assert response.status_code == 200
    assert response.data["ok"] is True
    assert response.data["product_count"] == 2
    assert response.data["error"] is None
    # Probe must NOT write to the catalog cache.
    assert OurProduct.objects.count() == 0


@pytest.mark.django_db
def test_test_connection_failure_returns_200_with_error(
    admin_client, monkeypatch
) -> None:
    """A failing fetch is a *result*: HTTP 200, ``ok=false``, ``error`` set.

    A bad URL / unreachable host is an expected outcome of a connectivity test,
    never a 5xx. The view must catch the raised exception and report it inline.
    """

    def _boom(url: str) -> bytes:
        raise ValueError("boom: host unreachable")

    monkeypatch.setattr(salesdrive, "fetch_catalog_yml", _boom)

    response = admin_client.post(
        TEST_PATH,
        {"salesdrive_yml_url": "https://example.com/bad.yml"},
        format="json",
    )

    assert response.status_code == 200
    assert response.data["ok"] is False
    assert response.data["product_count"] is None
    # H3: the client-facing error is GENERIC — the internal exception text must
    # not leak (it would act as an SSRF / network oracle). Server logs keep the
    # real cause; the response carries only the fixed friendly message.
    assert response.data["error"] == "Не вдалося підключитися до SalesDrive"
    assert "boom" not in response.data["error"]


@pytest.mark.django_db
def test_test_connection_uses_stored_url_when_body_omits_it(
    admin_client, monkeypatch
) -> None:
    """With no URL in the body, the test probes the stored singleton URL.

    The Settings UI offers "Перевірити підключення" against the saved config
    without re-sending the URL, so an empty body must fall back to the stored
    value (here proven by the boundary being called with that URL).
    """
    config = IntegrationSettings.load()
    config.salesdrive_yml_url = "https://stored.example.com/feed.yml"
    config.save()

    seen: dict[str, str] = {}

    def _fake_fetch(url: str) -> bytes:
        seen["url"] = url
        return SAMPLE_YML.encode("utf-8")

    monkeypatch.setattr(salesdrive, "fetch_catalog_yml", _fake_fetch)

    response = admin_client.post(TEST_PATH, {}, format="json")

    assert response.status_code == 200
    assert response.data["ok"] is True
    assert seen["url"] == "https://stored.example.com/feed.yml"


@pytest.mark.django_db
def test_test_connection_no_url_anywhere_is_a_failed_result(admin_client) -> None:
    """No URL in body or storage yields a friendly failed result (not 400/500).

    The endpoint surfaces "no URL" as ``ok=false`` with an error string so the UI
    shows one uniform inline message, rather than a validation error.
    """
    response = admin_client.post(TEST_PATH, {}, format="json")

    assert response.status_code == 200
    assert response.data["ok"] is False
    assert response.data["product_count"] is None
    assert response.data["error"]
