"""Behavior tests for the supplier directory API (``/api/suppliers/``).

The supplier directory is exposed as a DRF ``ModelViewSet`` so the designed PWA
can manage vendors without a Django-admin round-trip. These tests pin the
contract every parallel agent depends on:

* **Reads** (``list``/``retrieve``) are open to any authenticated user — the
  operator must keep picking a vendor on the receipt-create screen.
* **Writes** (``create``/``update``/``partial_update``/``destroy``) are
  admin-only via :class:`~apps.accounts.permissions.IsAdmin`; an operator gets
  403.
* ``GET /api/suppliers/`` returns **active suppliers only** by default; the admin
  screen opts into the full set with ``?include_inactive=true``.
* ``DELETE`` of a supplier that has protected related receipts
  (``Receipt.supplier=PROTECT``) returns ``409`` with an actionable message —
  "deactivate instead" — rather than 500ing.

The 409 path is exercised with a real :class:`~apps.receipts.models.Receipt` row
so the ``ProtectedError`` is genuinely raised by the DB, not mocked.

All DB-touching tests use ``@pytest.mark.django_db``.
"""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model

from apps.accounts.models import Profile
from apps.suppliers.models import Supplier

User = get_user_model()

# Endpoint paths under test. Constants keep a path change to a one-line edit.
LIST_PATH = "/api/suppliers/"


def _detail_path(pk: int) -> str:
    """Return the detail URL for a supplier primary key.

    Args:
        pk: The supplier primary key.

    Returns:
        The ``/api/suppliers/{pk}/`` path string.
    """

    return f"/api/suppliers/{pk}/"


@pytest.fixture
def admin_client(api_client):
    """Return an API client authenticated as an admin-role user.

    The conftest ``auth_client`` is an *operator*; supplier mutations are
    admin-only, so this mints a dedicated admin and attaches a JWT.

    Args:
        api_client: The unauthenticated client fixture from conftest.

    Returns:
        rest_framework.test.APIClient: A client bearing an admin JWT.
    """
    from rest_framework_simplejwt.tokens import RefreshToken

    admin_user = User.objects.create_user(
        username="suppliers-admin",
        email="suppliers-admin@example.com",
        password="pass1234",
    )
    profile = Profile.objects.get(user=admin_user)
    profile.role = Profile.ROLE_ADMIN
    profile.save(update_fields=["role"])

    token = RefreshToken.for_user(admin_user)
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {token.access_token}")
    return api_client


def _names(payload) -> list[str]:
    """Extract supplier names from a (possibly paginated) list response.

    The viewset returns a plain list, but this helper tolerates a paginated
    ``{"results": [...]}`` shape too so the assertions stay robust to global
    pagination defaults.

    Args:
        payload: The DRF response ``.data`` from the list endpoint.

    Returns:
        The ``name`` of each returned supplier, in response order.
    """

    rows = payload["results"] if isinstance(payload, dict) else payload
    return [row["name"] for row in rows]


# ---------------------------------------------------------------------------
# create
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_admin_can_create_supplier(admin_client) -> None:
    """An admin creates a supplier with a minimal ``{name}`` payload.

    ``note`` defaults blank and ``is_active`` defaults ``True``, so the smallest
    valid create is just a name; the server stamps ``id`` and ``created_at``.
    """
    response = admin_client.post(
        LIST_PATH, {"name": "ACME Постачання"}, format="json"
    )

    assert response.status_code == 201
    assert response.data["name"] == "ACME Постачання"
    assert response.data["is_active"] is True
    assert response.data["note"] == ""
    assert "id" in response.data
    assert "created_at" in response.data

    created = Supplier.objects.get(pk=response.data["id"])
    assert created.name == "ACME Постачання"


@pytest.mark.django_db
def test_operator_cannot_create_supplier(auth_client) -> None:
    """An operator is forbidden from creating suppliers (403, nothing written).

    Listing is open to operators, but the directory is curated by admins only.
    """
    response = auth_client.post(LIST_PATH, {"name": "Заборонено"}, format="json")

    assert response.status_code == 403
    assert Supplier.objects.count() == 0


@pytest.mark.django_db
def test_create_requires_authentication(api_client) -> None:
    """Anonymous create is rejected with 401."""
    response = api_client.post(LIST_PATH, {"name": "Аноним"}, format="json")
    assert response.status_code == 401
    assert Supplier.objects.count() == 0


# ---------------------------------------------------------------------------
# update / partial_update (rename, annotate, deactivate)
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_admin_can_update_supplier(admin_client) -> None:
    """An admin can rename and annotate an existing supplier via PATCH."""
    supplier = Supplier.objects.create(name="Стара назва")

    response = admin_client.patch(
        _detail_path(supplier.pk),
        {"name": "Нова назва", "note": "Доставка вівторок"},
        format="json",
    )

    assert response.status_code == 200
    assert response.data["name"] == "Нова назва"
    assert response.data["note"] == "Доставка вівторок"

    supplier.refresh_from_db()
    assert supplier.name == "Нова назва"
    assert supplier.note == "Доставка вівторок"


@pytest.mark.django_db
def test_admin_can_deactivate_supplier(admin_client) -> None:
    """Deactivation is a PATCH ``is_active=False`` — the supplier is retained.

    Deactivating (rather than deleting) is the preferred way to retire a vendor
    while preserving historical receipts/mappings.
    """
    supplier = Supplier.objects.create(name="Вибуває", is_active=True)

    response = admin_client.patch(
        _detail_path(supplier.pk), {"is_active": False}, format="json"
    )

    assert response.status_code == 200
    assert response.data["is_active"] is False

    supplier.refresh_from_db()
    assert supplier.is_active is False


@pytest.mark.django_db
def test_operator_cannot_update_supplier(auth_client) -> None:
    """An operator cannot mutate a supplier (403, value unchanged)."""
    supplier = Supplier.objects.create(name="Лише читання")

    response = auth_client.patch(
        _detail_path(supplier.pk), {"name": "Зламано"}, format="json"
    )

    assert response.status_code == 403
    supplier.refresh_from_db()
    assert supplier.name == "Лише читання"


# ---------------------------------------------------------------------------
# list: active-only by default vs include_inactive
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_list_returns_active_only_by_default(auth_client) -> None:
    """The default list hides inactive suppliers (operator picker contract).

    The receipt-create picker must never offer a retired vendor, so a plain
    ``GET /api/suppliers/`` returns only ``is_active=True`` rows, ordered by name.
    """
    Supplier.objects.create(name="Активний А", is_active=True)
    Supplier.objects.create(name="Активний Б", is_active=True)
    Supplier.objects.create(name="Неактивний", is_active=False)

    response = auth_client.get(LIST_PATH)

    assert response.status_code == 200
    names = _names(response.data)
    assert names == ["Активний А", "Активний Б"]  # ordered by name, no inactive


@pytest.mark.django_db
def test_list_include_inactive_returns_all(admin_client) -> None:
    """``?include_inactive=true`` returns active *and* inactive suppliers.

    The admin management screen needs to see (and reactivate) deactivated
    vendors, so the opt-in flag widens the list to the full directory.
    """
    Supplier.objects.create(name="Активний", is_active=True)
    Supplier.objects.create(name="Неактивний", is_active=False)

    response = admin_client.get(LIST_PATH, {"include_inactive": "true"})

    assert response.status_code == 200
    names = _names(response.data)
    assert names == ["Активний", "Неактивний"]


@pytest.mark.django_db
def test_list_requires_authentication(api_client) -> None:
    """Anonymous listing is rejected with 401."""
    response = api_client.get(LIST_PATH)
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# destroy: plain delete vs PROTECT → 409
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_admin_can_delete_supplier_without_receipts(admin_client) -> None:
    """An admin can hard-delete a supplier that has no related receipts (204)."""
    supplier = Supplier.objects.create(name="Без накладних")

    response = admin_client.delete(_detail_path(supplier.pk))

    assert response.status_code == 204
    assert not Supplier.objects.filter(pk=supplier.pk).exists()


@pytest.mark.django_db
def test_delete_supplier_with_receipts_returns_409(admin_client) -> None:
    """Deleting a supplier referenced by a receipt returns 409, not 500.

    ``Receipt.supplier`` is ``on_delete=PROTECT``; the viewset must translate the
    raised :class:`~django.db.models.ProtectedError` into a friendly 409 with an
    actionable Ukrainian message and leave the supplier in place.
    """
    from apps.receipts.models import Receipt

    supplier = Supplier.objects.create(name="Має накладні")
    Receipt.objects.create(supplier=supplier)

    response = admin_client.delete(_detail_path(supplier.pk))

    assert response.status_code == 409
    assert "detail" in response.data
    assert "Деактивуйте" in response.data["detail"]
    # The protected supplier is NOT deleted.
    assert Supplier.objects.filter(pk=supplier.pk).exists()


@pytest.mark.django_db
def test_operator_cannot_delete_supplier(auth_client) -> None:
    """An operator cannot delete a supplier (403, row retained)."""
    supplier = Supplier.objects.create(name="Захищено від оператора")

    response = auth_client.delete(_detail_path(supplier.pk))

    assert response.status_code == 403
    assert Supplier.objects.filter(pk=supplier.pk).exists()
