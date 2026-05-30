"""Security-hardening behavior tests (the audit fixes).

Each test pins one fix from the security audit so a regression fails loudly:

* **H1 throttling** — the PIN and email-login endpoints start returning ``429``
  once their per-scope rate is exceeded.
* **H2 IDOR** — operator A cannot read or mutate operator B's receipt by id
  (``404``, not ``403`` — id enumeration is denied), while an admin can.
* **H3 SSRF** — :func:`integrations.salesdrive.fetch_catalog_yml` rejects the
  cloud-metadata IP, loopback, and a private IP with ``ValueError`` *before* any
  request goes out; the SalesDrive test view returns a generic error (never the
  internal exception string).
* **H4 upload limit** — the photo-upload serializer rejects an oversized file.
* **M5 logout** — logging out blacklists the refresh token so it can no longer
  be exchanged for a new access token.

The network boundary is never hit: SSRF tests stub DNS resolution / ``requests``,
and the SalesDrive test-view test stubs ``probe_catalog_yml``. DB tests use
``@pytest.mark.django_db``.
"""

from __future__ import annotations

import io

import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache
from PIL import Image
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import Profile
from apps.receipts.models import Receipt

User = get_user_model()

PIN_LOGIN_PATH = "/api/auth/pin/"
LOGIN_PATH = "/api/auth/login/"
LOGOUT_PATH = "/api/auth/logout/"
REFRESH_PATH = "/api/auth/refresh/"
SALESDRIVE_TEST_PATH = "/api/settings/salesdrive/test/"


@pytest.fixture(autouse=True)
def _clear_throttle_cache():
    """Reset the throttle cache around every test.

    DRF's throttle classes persist their hit history in Django's cache (the
    in-process ``LocMemCache`` under test), which would otherwise leak request
    counts between tests and make rate-limit assertions order-dependent. Clearing
    before *and* after keeps each test hermetic.
    """

    cache.clear()
    yield
    cache.clear()


def _client():
    """Return a fresh unauthenticated DRF ``APIClient``."""

    from rest_framework.test import APIClient

    return APIClient()


def _auth_client(user):
    """Return an ``APIClient`` authenticated as ``user`` via a JWT access token.

    Args:
        user: The user to mint an access token for.

    Returns:
        rest_framework.test.APIClient: Client with the ``Authorization`` header.
    """

    client = _client()
    token = RefreshToken.for_user(user)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token.access_token}")
    return client


def _make_user(username: str, email: str, *, role: str = Profile.ROLE_OPERATOR):
    """Create a user and set its (auto-created) profile role.

    Args:
        username: Login username.
        email: Email (the ``created_by`` stamp and login identifier).
        role: Profile role to set (defaults to operator).

    Returns:
        The created user.
    """

    user = User.objects.create_user(
        username=username, email=email, password="pass1234"
    )
    profile, _ = Profile.objects.get_or_create(user=user)
    if profile.role != role:
        profile.role = role
        profile.save(update_fields=["role"])
    return user


# ---------------------------------------------------------------------------
# H1 — throttling returns 429 after the per-scope limit
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_pin_login_throttled_after_limit() -> None:
    """The PIN endpoint returns 429 once the ``pin`` rate (5/min) is exceeded.

    The first five wrong-PIN attempts get the normal 401; the sixth is rejected
    by ScopedRateThrottle with 429, which is what makes online PIN guessing
    (a 4-digit, 10k-space credential) infeasible.
    """

    client = _client()
    body = {"email": "nobody@example.com", "pin": "0000"}

    statuses = [
        client.post(PIN_LOGIN_PATH, body).status_code for _ in range(6)
    ]

    # First five within the limit (401 invalid creds), the sixth throttled.
    assert statuses[:5] == [401, 401, 401, 401, 401]
    assert statuses[5] == 429


@pytest.mark.django_db
def test_email_login_throttled_after_limit() -> None:
    """The email-login endpoint returns 429 once the ``login`` rate is exceeded.

    The ``login`` scope is 10/min; the 11th attempt in the window is throttled,
    blunting password brute force.
    """

    client = _client()
    body = {"email": "nobody@example.com", "password": "wrong-password"}

    statuses = [
        client.post(LOGIN_PATH, body).status_code for _ in range(11)
    ]

    # The first ten are processed (401 bad creds); the eleventh is throttled.
    assert 429 not in statuses[:10]
    assert statuses[10] == 429


# ---------------------------------------------------------------------------
# H2 — IDOR: receipts are scoped to their creator for non-admins
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_operator_cannot_get_another_operators_receipt() -> None:
    """Operator A gets 404 (not 403) for operator B's receipt by id."""

    owner = _make_user("owner", "owner@example.com")
    other = _make_user("other", "other@example.com")

    receipt = Receipt.objects.create(created_by="owner@example.com", status="draft")

    # Owner can read it...
    assert _auth_client(owner).get(f"/api/receipts/{receipt.pk}/").status_code == 200
    # ...but a different operator gets a 404 (id existence not confirmed).
    assert _auth_client(other).get(f"/api/receipts/{receipt.pk}/").status_code == 404


@pytest.mark.django_db
def test_operator_cannot_patch_another_operators_receipt() -> None:
    """Operator A cannot change the supplier of operator B's receipt (404)."""

    other = _make_user("other2", "other2@example.com")
    receipt = Receipt.objects.create(created_by="owner@example.com", status="draft")

    response = _auth_client(other).patch(
        f"/api/receipts/{receipt.pk}/", {"supplier": None}, format="json"
    )
    assert response.status_code == 404


@pytest.mark.django_db
def test_admin_can_get_another_operators_receipt() -> None:
    """An admin sees every receipt regardless of creator (full access)."""

    admin = _make_user("adminx", "adminx@example.com", role=Profile.ROLE_ADMIN)
    receipt = Receipt.objects.create(created_by="owner@example.com", status="draft")

    response = _auth_client(admin).get(f"/api/receipts/{receipt.pk}/")
    assert response.status_code == 200
    assert response.json()["id"] == receipt.pk


@pytest.mark.django_db
def test_receipt_create_stamps_created_by() -> None:
    """Creating a receipt stamps ``created_by`` with the caller's email.

    This is the anchor the IDOR scope filters on: a receipt created by an
    operator becomes visible only to that operator (and admins).
    """

    owner = _make_user("creator", "creator@example.com")
    response = _auth_client(owner).post("/api/receipts/", {}, format="json")
    assert response.status_code == 201

    receipt = Receipt.objects.get(pk=response.json()["id"])
    assert receipt.created_by == "creator@example.com"


# ---------------------------------------------------------------------------
# H3 — SSRF: fetch_catalog_yml rejects internal targets
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "url",
    [
        "http://169.254.169.254/latest/meta-data/",  # cloud metadata
        "http://127.0.0.1/export.yml",  # loopback
        "http://10.0.0.5/export.yml",  # private (RFC1918)
        "ftp://example.com/export.yml",  # non-http(s) scheme
    ],
)
def test_fetch_catalog_yml_rejects_ssrf_targets(monkeypatch, url) -> None:
    """Internal / non-http(s) URLs raise ``ValueError`` before any request.

    ``requests.get`` is patched to explode if it is ever called, proving the
    rejection happens in the pre-flight guard and no outbound request is made.
    Literal-IP URLs resolve to themselves via ``getaddrinfo`` and are caught by
    the private/loopback/link-local checks.
    """

    from integrations import salesdrive

    def _boom(*args, **kwargs):  # pragma: no cover - must never run
        raise AssertionError("requests.get must not be called for a blocked URL")

    monkeypatch.setattr(salesdrive.requests, "get", _boom)

    with pytest.raises(ValueError, match="Недозволена адреса"):
        salesdrive.fetch_catalog_yml(url)


def test_fetch_catalog_yml_rejects_hostname_resolving_to_private(monkeypatch) -> None:
    """A public-looking hostname that resolves to a private IP is rejected.

    Guards against DNS-rebinding-style attacks: the literal URL looks external,
    but its A record points inside the network. ``getaddrinfo`` is stubbed to
    return a private address, which the guard must reject.
    """

    from integrations import salesdrive

    def _fake_getaddrinfo(host, port, *args, **kwargs):
        return [(2, 1, 6, "", ("192.168.1.10", port or 80))]

    monkeypatch.setattr(salesdrive.socket, "getaddrinfo", _fake_getaddrinfo)
    monkeypatch.setattr(
        salesdrive.requests,
        "get",
        lambda *a, **k: (_ for _ in ()).throw(
            AssertionError("must not fetch a host resolving to a private IP")
        ),
    )

    with pytest.raises(ValueError, match="Недозволена адреса"):
        salesdrive.fetch_catalog_yml("http://internal.example.com/export.yml")


def test_fetch_catalog_yml_allows_public_host(monkeypatch) -> None:
    """A public host (resolving to a public IP) is allowed through to fetch.

    Confirms the guard does not regress legitimate use: a real export URL whose
    host resolves to a public address proceeds to ``requests.get`` (stubbed) and
    returns the body, with ``allow_redirects=False`` passed through.
    """

    from integrations import salesdrive

    monkeypatch.setattr(
        salesdrive.socket,
        "getaddrinfo",
        lambda host, port, *a, **k: [(2, 1, 6, "", ("93.184.216.34", port or 80))],
    )

    captured: dict = {}

    class _Resp:
        content = b"<yml_catalog></yml_catalog>"

        def raise_for_status(self) -> None:
            return None

    def _fake_get(url, timeout=None, allow_redirects=None):
        captured["allow_redirects"] = allow_redirects
        return _Resp()

    monkeypatch.setattr(salesdrive.requests, "get", _fake_get)

    body = salesdrive.fetch_catalog_yml("https://shop.example.com/export.yml")
    assert body == b"<yml_catalog></yml_catalog>"
    # Redirects must be disabled so a 3xx cannot bounce to an internal target.
    assert captured["allow_redirects"] is False


# ---------------------------------------------------------------------------
# H3 — SalesDriveTestView returns a generic error (no str(exc) leak)
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_salesdrive_test_view_returns_generic_error(monkeypatch) -> None:
    """A probe failure surfaces a GENERIC error, never the internal exception.

    The internal exception text (which could reveal a resolved IP / blocked
    range and act as an SSRF oracle) must not appear in the response; the client
    gets the fixed friendly message, and the endpoint still returns HTTP 200.
    """

    admin = _make_user("sdadmin", "sdadmin@example.com", role=Profile.ROLE_ADMIN)

    from apps.catalog import views as catalog_views

    secret_detail = "blocked 169.254.169.254 internal metadata leak"

    def _boom(url):
        raise ValueError(secret_detail)

    monkeypatch.setattr(catalog_views, "probe_catalog_yml", _boom)

    response = _auth_client(admin).post(
        SALESDRIVE_TEST_PATH,
        {"salesdrive_yml_url": "http://169.254.169.254/"},
        format="json",
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False
    assert body["error"] == "Не вдалося підключитися до SalesDrive"
    # The internal detail must NOT leak to the client.
    assert secret_detail not in body["error"]


# ---------------------------------------------------------------------------
# H4 — upload validation rejects an oversized file
# ---------------------------------------------------------------------------
def test_upload_serializer_rejects_oversized_file() -> None:
    """The photo-upload serializer rejects a file larger than the byte cap.

    A real (small) PNG is wrapped so its reported ``size`` exceeds 10 MB; the
    ``validate_image`` hook must reject it with a validation error. Using a real
    decodable image isolates the *size* check from the image-format check.
    """

    from apps.receipts.serializers import (
        MAX_UPLOAD_BYTES,
        ReceiptPhotoUploadSerializer,
    )

    buffer = io.BytesIO()
    Image.new("RGB", (8, 8), color=(10, 26, 63)).save(buffer, format="PNG")
    png = buffer.getvalue()

    from django.core.files.uploadedfile import SimpleUploadedFile

    upload = SimpleUploadedFile("page.png", png, content_type="image/png")
    # Force the reported size over the cap without allocating 10 MB of bytes.
    upload.size = MAX_UPLOAD_BYTES + 1

    serializer = ReceiptPhotoUploadSerializer(data={"image": upload})
    assert not serializer.is_valid()
    assert "image" in serializer.errors


def test_upload_serializer_accepts_normal_file() -> None:
    """A normal small invoice photo passes validation (no false positives)."""

    from apps.receipts.serializers import ReceiptPhotoUploadSerializer

    buffer = io.BytesIO()
    Image.new("RGB", (640, 480), color=(10, 26, 63)).save(buffer, format="PNG")
    png = buffer.getvalue()

    from django.core.files.uploadedfile import SimpleUploadedFile

    upload = SimpleUploadedFile("page.png", png, content_type="image/png")
    serializer = ReceiptPhotoUploadSerializer(data={"image": upload})
    assert serializer.is_valid(), serializer.errors


# ---------------------------------------------------------------------------
# M5 — logout blacklists the refresh token
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_logout_blacklists_refresh_token() -> None:
    """After logout, the revoked refresh token can no longer be refreshed.

    Exercises the full revocation path: mint a refresh token, log out (which
    blacklists it), then assert a subsequent refresh with that SAME token is
    rejected (401). Requires the ``token_blacklist`` app + rotation settings.

    Note: we do NOT refresh before logging out — with ``ROTATE_REFRESH_TOKENS``
    a refresh would itself blacklist the original token (rotation), which would
    confuse the assertion. Logout is the single revocation under test here.
    """

    user = _make_user("logoutuser", "logoutuser@example.com")
    refresh = RefreshToken.for_user(user)
    refresh_str = str(refresh)

    client = _auth_client(user)

    # Log out → blacklist this refresh token (first use, so a real 205).
    logout = client.post(LOGOUT_PATH, {"refresh": refresh_str}, format="json")
    assert logout.status_code == 205

    # The now-blacklisted refresh token is rejected on a refresh attempt.
    after = client.post(REFRESH_PATH, {"refresh": refresh_str}, format="json")
    assert after.status_code == 401


@pytest.mark.django_db
def test_logout_tolerates_missing_or_invalid_token() -> None:
    """Logout never blocks a client clearing local state (tolerant of junk).

    A missing refresh field returns 200; an unparseable token also returns 200
    (not a 4xx that would leave the client unable to "log out").
    """

    user = _make_user("logout2", "logout2@example.com")
    client = _auth_client(user)

    assert client.post(LOGOUT_PATH, {}, format="json").status_code == 200
    assert (
        client.post(
            LOGOUT_PATH, {"refresh": "not-a-real-token"}, format="json"
        ).status_code
        == 200
    )
