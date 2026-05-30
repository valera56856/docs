"""Behavior tests for the admin mappings-management API (``/api/mappings/``).

This API lets an admin audit, search, re-target and delete the remembered
:class:`~apps.mapping.models.ArticleMapping` rows — the "memory" of the system —
directly, independent of any receipt. (The receipt-line *map* action is a
separate, nested endpoint owned by the receipts app.) These tests pin the
contract:

* ``GET    /api/mappings/`` lists mappings most-used first, with optional
  ``?supplier=<id>`` and ``?q=<text>`` filters (q matches supplier SKU, product
  SKU, or product name), capped and join-optimized.
* ``POST   /api/mappings/`` creates / re-targets a mapping, normalizing the SKU
  and keying on the unique ``(supplier, supplier_sku_normalized)`` pair. Admin
  curation must **not** inflate ``times_used``.
* ``PATCH  /api/mappings/{id}/`` re-targets the product (and/or re-normalizes the
  SKU) without touching ``times_used``/``created_by``.
* ``DELETE /api/mappings/{id}/`` forgets the mapping (204).

Authorization: **every** action is admin-only (``IsAuthenticated`` +
``IsAdmin``) because editing remembered mappings changes how future invoices
auto-match — an operator gets 403.

All DB-touching tests use ``@pytest.mark.django_db``.
"""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model

from apps.accounts.models import Profile
from apps.catalog.models import OurProduct
from apps.mapping.models import ArticleMapping
from apps.mapping.services import normalize_sku
from apps.suppliers.models import Supplier

User = get_user_model()

# Endpoint paths under test. Constants keep a path change to a one-line edit.
LIST_PATH = "/api/mappings/"


def _detail_path(pk: int) -> str:
    """Return the detail URL for a mapping primary key.

    Args:
        pk: The mapping primary key.

    Returns:
        The ``/api/mappings/{pk}/`` path string.
    """

    return f"/api/mappings/{pk}/"


@pytest.fixture
def admin_client(api_client):
    """Return an API client authenticated as an admin-role user.

    Mappings management is admin-only; the conftest ``auth_client`` is an
    operator, so this fixture mints a dedicated admin and attaches a JWT.

    Args:
        api_client: The unauthenticated client fixture from conftest.

    Returns:
        rest_framework.test.APIClient: A client bearing an admin JWT.
    """
    from rest_framework_simplejwt.tokens import RefreshToken

    admin_user = User.objects.create_user(
        username="mappings-admin",
        email="mappings-admin@example.com",
        password="pass1234",
    )
    profile = Profile.objects.get(user=admin_user)
    profile.role = Profile.ROLE_ADMIN
    profile.save(update_fields=["role"])

    token = RefreshToken.for_user(admin_user)
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {token.access_token}")
    return api_client


@pytest.fixture
def supplier(db) -> Supplier:
    """Return a persisted active supplier to own mappings."""
    return Supplier.objects.create(name="ACME Постачання", is_active=True)


@pytest.fixture
def other_supplier(db) -> Supplier:
    """Return a second supplier to prove the ``?supplier`` filter scopes rows."""
    return Supplier.objects.create(name="Інший Постачальник", is_active=True)


@pytest.fixture
def product(db) -> OurProduct:
    """Return a persisted catalog product to map supplier SKUs to."""
    return OurProduct.objects.create(
        salesdrive_id="SD-1001", sku="OUR-1001", name="Сорочка біла"
    )


@pytest.fixture
def other_product(db) -> OurProduct:
    """Return a second catalog product (used to test re-targeting)."""
    return OurProduct.objects.create(
        salesdrive_id="SD-2002", sku="OUR-2002", name="Штани сині"
    )


def _rows(payload) -> list:
    """Return the row list from a (possibly paginated) list response.

    Args:
        payload: The DRF response ``.data`` from the list endpoint.

    Returns:
        The list of mapping dicts, unwrapping a ``{"results": [...]}`` envelope
        if global pagination is active.
    """

    return payload["results"] if isinstance(payload, dict) else payload


# ---------------------------------------------------------------------------
# list + filtering
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_list_returns_mappings_most_used_first(
    admin_client, supplier, product, other_product
) -> None:
    """The list orders by descending ``times_used`` (most valuable memory first).

    Each row carries the nested supplier ``{id,name}`` and product
    ``{id,sku,name}`` plus ``times_used`` so the admin table renders without a
    second round-trip.
    """
    ArticleMapping.objects.create(
        supplier=supplier,
        supplier_sku="LOW-1",
        supplier_sku_normalized=normalize_sku("LOW-1"),
        our_product=product,
        times_used=2,
    )
    ArticleMapping.objects.create(
        supplier=supplier,
        supplier_sku="HIGH-1",
        supplier_sku_normalized=normalize_sku("HIGH-1"),
        our_product=other_product,
        times_used=9,
    )

    response = admin_client.get(LIST_PATH)

    assert response.status_code == 200
    rows = _rows(response.data)
    assert [r["supplier_sku"] for r in rows] == ["HIGH-1", "LOW-1"]
    # Nested shapes the frontend ``MappingAdmin`` type expects.
    top = rows[0]
    assert top["supplier"] == {"id": supplier.id, "name": supplier.name}
    assert top["our_product"] == {
        "id": other_product.id,
        "sku": other_product.sku,
        "name": other_product.name,
    }
    assert top["times_used"] == 9


@pytest.mark.django_db
def test_list_filters_by_supplier(
    admin_client, supplier, other_supplier, product
) -> None:
    """``?supplier=<id>`` restricts the list to one supplier's namespace."""
    ArticleMapping.objects.create(
        supplier=supplier,
        supplier_sku="A-1",
        supplier_sku_normalized=normalize_sku("A-1"),
        our_product=product,
    )
    ArticleMapping.objects.create(
        supplier=other_supplier,
        supplier_sku="B-1",
        supplier_sku_normalized=normalize_sku("B-1"),
        our_product=product,
    )

    response = admin_client.get(LIST_PATH, {"supplier": supplier.id})

    assert response.status_code == 200
    rows = _rows(response.data)
    assert [r["supplier_sku"] for r in rows] == ["A-1"]
    assert all(r["supplier"]["id"] == supplier.id for r in rows)


@pytest.mark.django_db
def test_list_q_matches_sku_and_product_name(
    admin_client, supplier, product, other_product
) -> None:
    """``?q`` matches the supplier SKU, product SKU, or product name (icontains).

    Three mappings are created; a query that only appears in one product's name
    must surface exactly that row, proving the cross-field OR search.
    """
    ArticleMapping.objects.create(
        supplier=supplier,
        supplier_sku="ZZZ-1",
        supplier_sku_normalized=normalize_sku("ZZZ-1"),
        our_product=product,  # name "Сорочка біла"
    )
    ArticleMapping.objects.create(
        supplier=supplier,
        supplier_sku="ZZZ-2",
        supplier_sku_normalized=normalize_sku("ZZZ-2"),
        our_product=other_product,  # name "Штани сині"
    )

    # Matches the product name of the second mapping only.
    by_name = admin_client.get(LIST_PATH, {"q": "штани"})
    assert by_name.status_code == 200
    rows = _rows(by_name.data)
    assert [r["supplier_sku"] for r in rows] == ["ZZZ-2"]

    # Matches a supplier SKU substring shared by both mappings.
    by_sku = admin_client.get(LIST_PATH, {"q": "zzz"})
    assert {r["supplier_sku"] for r in _rows(by_sku.data)} == {"ZZZ-1", "ZZZ-2"}


@pytest.mark.django_db
def test_list_forbidden_for_operator(auth_client) -> None:
    """An operator cannot browse the mappings memory (403)."""
    response = auth_client.get(LIST_PATH)
    assert response.status_code == 403


@pytest.mark.django_db
def test_list_requires_authentication(api_client) -> None:
    """Anonymous mapping listing is rejected with 401."""
    response = api_client.get(LIST_PATH)
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# create
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_admin_create_mapping_normalizes_and_returns_read_shape(
    admin_client, supplier, product
) -> None:
    """POST stores the normalized SKU and returns the nested read shape (201).

    The raw SKU is stored trimmed (DRF trims surrounding whitespace on input)
    while the lookup key is fully normalized (trim/UPPER/collapse). Admin
    curation does **not** count as a use, so
    ``times_used`` stays 0.
    """
    response = admin_client.post(
        LIST_PATH,
        {
            "supplier": supplier.id,
            "supplier_sku": "  sku-7 ",
            "our_product_id": product.id,
        },
        format="json",
    )

    assert response.status_code == 201
    # DRF trims surrounding whitespace on input; whitespace is never a
    # meaningful part of a SKU. The stored raw is the trimmed value, while the
    # normalized lookup key (asserted below) is UPPER + collapsed.
    assert response.data["supplier_sku"] == "sku-7"
    assert response.data["our_product"]["id"] == product.id
    assert response.data["supplier"]["id"] == supplier.id
    assert response.data["times_used"] == 0  # curation is not a "use"

    stored = ArticleMapping.objects.get(pk=response.data["id"])
    assert stored.supplier_sku_normalized == normalize_sku("  sku-7 ") == "SKU-7"


@pytest.mark.django_db
def test_create_mapping_is_upsert_on_normalized_sku(
    admin_client, supplier, product, other_product
) -> None:
    """POSTing the same normalized SKU twice re-targets in place (no duplicate).

    The model is unique on ``(supplier, supplier_sku_normalized)``; a second
    create with a formatting-variant SKU must update the existing row's product
    rather than raise an integrity error or create a second row.
    """
    first = admin_client.post(
        LIST_PATH,
        {
            "supplier": supplier.id,
            "supplier_sku": "sku-9",
            "our_product_id": product.id,
        },
        format="json",
    )
    assert first.status_code == 201

    second = admin_client.post(
        LIST_PATH,
        {
            "supplier": supplier.id,
            "supplier_sku": "  SKU-9  ",  # same normalized key
            "our_product_id": other_product.id,
        },
        format="json",
    )
    assert second.status_code == 201

    assert ArticleMapping.objects.count() == 1
    row = ArticleMapping.objects.get()
    assert row.our_product_id == other_product.id  # re-targeted


@pytest.mark.django_db
def test_create_mapping_rejects_unknown_product(admin_client, supplier) -> None:
    """A dangling ``our_product_id`` is a clean 400, not an integrity 500."""
    response = admin_client.post(
        LIST_PATH,
        {
            "supplier": supplier.id,
            "supplier_sku": "SKU-1",
            "our_product_id": 999999,
        },
        format="json",
    )
    assert response.status_code == 400
    assert ArticleMapping.objects.count() == 0


@pytest.mark.django_db
def test_operator_cannot_create_mapping(auth_client, supplier, product) -> None:
    """An operator cannot create a mapping via the admin API (403)."""
    response = auth_client.post(
        LIST_PATH,
        {
            "supplier": supplier.id,
            "supplier_sku": "SKU-1",
            "our_product_id": product.id,
        },
        format="json",
    )
    assert response.status_code == 403
    assert ArticleMapping.objects.count() == 0


# ---------------------------------------------------------------------------
# partial_update (re-target product / re-normalize sku)
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_admin_patch_retargets_product(
    admin_client, supplier, product, other_product
) -> None:
    """PATCH ``our_product_id`` re-binds the mapping without touching counters.

    Re-targeting is the common "I mapped the wrong product" fix. ``times_used``
    and ``created_by`` are immutable through this path.
    """
    mapping = ArticleMapping.objects.create(
        supplier=supplier,
        supplier_sku="SKU-RE",
        supplier_sku_normalized=normalize_sku("SKU-RE"),
        our_product=product,
        times_used=5,
        created_by="original-op",
    )

    response = admin_client.patch(
        _detail_path(mapping.pk),
        {"our_product_id": other_product.id},
        format="json",
    )

    assert response.status_code == 200
    assert response.data["our_product"]["id"] == other_product.id

    mapping.refresh_from_db()
    assert mapping.our_product_id == other_product.id
    assert mapping.times_used == 5  # untouched by curation
    assert mapping.created_by == "original-op"  # never overwritten


@pytest.mark.django_db
def test_admin_patch_renormalizes_sku(admin_client, supplier, product) -> None:
    """PATCH ``supplier_sku`` re-derives the normalized lookup key.

    Correcting a typo in the printed SKU must update both the raw value and the
    normalized field so future auto-matches key off the corrected code.
    """
    mapping = ArticleMapping.objects.create(
        supplier=supplier,
        supplier_sku="OLD-SKU",
        supplier_sku_normalized=normalize_sku("OLD-SKU"),
        our_product=product,
    )

    response = admin_client.patch(
        _detail_path(mapping.pk),
        {"supplier_sku": "  new-sku "},
        format="json",
    )

    assert response.status_code == 200
    mapping.refresh_from_db()
    assert mapping.supplier_sku == "  new-sku "
    assert mapping.supplier_sku_normalized == normalize_sku("  new-sku ") == "NEW-SKU"


@pytest.mark.django_db
def test_operator_cannot_patch_mapping(
    auth_client, supplier, product, other_product
) -> None:
    """An operator cannot re-target a mapping (403, target unchanged)."""
    mapping = ArticleMapping.objects.create(
        supplier=supplier,
        supplier_sku="SKU-X",
        supplier_sku_normalized=normalize_sku("SKU-X"),
        our_product=product,
    )

    response = auth_client.patch(
        _detail_path(mapping.pk),
        {"our_product_id": other_product.id},
        format="json",
    )

    assert response.status_code == 403
    mapping.refresh_from_db()
    assert mapping.our_product_id == product.id


# ---------------------------------------------------------------------------
# destroy
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_admin_delete_mapping(admin_client, supplier, product) -> None:
    """DELETE forgets a remembered mapping (204, row gone)."""
    mapping = ArticleMapping.objects.create(
        supplier=supplier,
        supplier_sku="SKU-DEL",
        supplier_sku_normalized=normalize_sku("SKU-DEL"),
        our_product=product,
    )

    response = admin_client.delete(_detail_path(mapping.pk))

    assert response.status_code == 204
    assert not ArticleMapping.objects.filter(pk=mapping.pk).exists()


@pytest.mark.django_db
def test_operator_cannot_delete_mapping(auth_client, supplier, product) -> None:
    """An operator cannot delete a mapping (403, row retained)."""
    mapping = ArticleMapping.objects.create(
        supplier=supplier,
        supplier_sku="SKU-KEEP",
        supplier_sku_normalized=normalize_sku("SKU-KEEP"),
        our_product=product,
    )

    response = auth_client.delete(_detail_path(mapping.pk))

    assert response.status_code == 403
    assert ArticleMapping.objects.filter(pk=mapping.pk).exists()
