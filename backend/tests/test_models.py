"""Behavior tests for the Valeraup ORM models.

These tests lock in the model contract shared with every other agent:

* Object creation succeeds with the documented fields.
* ``ArticleMapping`` enforces ``unique_together(supplier, supplier_sku_normalized)``.
* ``Receipt.status`` defaults to ``"draft"`` and ``ReceiptLine.match_status``
  defaults to ``"unmapped"``.
* ``Receipt.supplier`` is ``PROTECT`` (deleting a supplier with receipts must
  raise rather than silently orphan financial records).
* ``Profile`` stores a *hashed* PIN that verifies with Django's ``check_password``.

Every test uses ``@pytest.mark.django_db`` because they all touch the database.
"""
from __future__ import annotations

from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import check_password, make_password
from django.db import IntegrityError
from django.db.models import ProtectedError

from apps.accounts.models import Profile
from apps.catalog.models import OurProduct
from apps.mapping.models import ArticleMapping
from apps.receipts.models import Receipt, ReceiptLine, ReceiptPhoto
from apps.suppliers.models import Supplier


# ---------------------------------------------------------------------------
# Suppliers
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_supplier_creation_defaults() -> None:
    """A supplier is active by default and stringifies to its name."""
    supplier = Supplier.objects.create(name="ACME Постачання")

    assert supplier.pk is not None
    assert supplier.is_active is True
    assert supplier.note == ""
    # ``edrpou`` is optional and defaults to blank (most rows are auto-created).
    assert supplier.edrpou == ""
    assert supplier.created_at is not None
    assert str(supplier) == "ACME Постачання"


@pytest.mark.django_db
def test_supplier_stores_edrpou() -> None:
    """``Supplier.edrpou`` persists the Ukrainian tax code key."""
    supplier = Supplier.objects.create(name="ТОВ Демо", edrpou="12345678")

    supplier.refresh_from_db()
    assert supplier.edrpou == "12345678"


# ---------------------------------------------------------------------------
# Catalog
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_our_product_salesdrive_id_unique() -> None:
    """``OurProduct.salesdrive_id`` is unique (the upsert key for sync).

    Two products may share a SKU, but never a SalesDrive id — that id is how
    ``sync_catalog`` decides update-vs-insert.
    """
    OurProduct.objects.create(salesdrive_id="SD-1", sku="A", name="Товар А")

    with pytest.raises(IntegrityError):
        OurProduct.objects.create(salesdrive_id="SD-1", sku="B", name="Товар Б")


# ---------------------------------------------------------------------------
# Mapping
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_article_mapping_unique_together() -> None:
    """Duplicate ``(supplier, supplier_sku_normalized)`` is rejected.

    This constraint guarantees one canonical mapping per supplier SKU. The raw
    ``supplier_sku`` may differ between attempts, but the *normalized* value plus
    supplier must be unique.
    """
    supplier = Supplier.objects.create(name="ACME")
    product = OurProduct.objects.create(
        salesdrive_id="SD-1", sku="OUR-1", name="Товар"
    )

    ArticleMapping.objects.create(
        supplier=supplier,
        supplier_sku="sku-7",
        supplier_sku_normalized="SKU-7",
        our_product=product,
    )

    with pytest.raises(IntegrityError):
        ArticleMapping.objects.create(
            supplier=supplier,
            supplier_sku="SKU 7",  # different raw spelling …
            supplier_sku_normalized="SKU-7",  # … but same normalized key
            our_product=product,
        )


@pytest.mark.django_db
def test_article_mapping_same_sku_different_supplier_allowed() -> None:
    """The same normalized SKU is allowed for two different suppliers.

    SKU namespaces are per-supplier, so the unique constraint only bites within
    one supplier.
    """
    product = OurProduct.objects.create(
        salesdrive_id="SD-1", sku="OUR-1", name="Товар"
    )
    supplier_a = Supplier.objects.create(name="A")
    supplier_b = Supplier.objects.create(name="B")

    ArticleMapping.objects.create(
        supplier=supplier_a,
        supplier_sku="SKU-7",
        supplier_sku_normalized="SKU-7",
        our_product=product,
    )
    # Must NOT raise — different supplier.
    mapping_b = ArticleMapping.objects.create(
        supplier=supplier_b,
        supplier_sku="SKU-7",
        supplier_sku_normalized="SKU-7",
        our_product=product,
    )

    assert mapping_b.pk is not None
    assert mapping_b.times_used == 0  # default


# ---------------------------------------------------------------------------
# Receipts
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_receipt_status_defaults_to_draft() -> None:
    """A freshly created receipt starts in the ``"draft"`` status.

    ``draft`` is the entry point of the status state machine the frontend
    renders and the Celery tasks advance.
    """
    supplier = Supplier.objects.create(name="ACME")
    receipt = Receipt.objects.create(supplier=supplier)

    assert receipt.status == "draft"
    assert receipt.xlsx_url == ""
    assert receipt.created_at is not None


@pytest.mark.django_db
def test_receipt_supplier_is_nullable_for_scan_first() -> None:
    """A draft may be created with no supplier (scan-first flow).

    The vendor is auto-detected from the photographed invoice on recognition, so
    the FK must accept ``None`` and ``recognized_supplier`` starts unset.
    """
    receipt = Receipt.objects.create(supplier=None)

    assert receipt.pk is not None
    assert receipt.supplier_id is None
    assert receipt.recognized_supplier is None
    assert receipt.status == "draft"


@pytest.mark.django_db
def test_receipt_stores_recognized_supplier_dict() -> None:
    """``recognized_supplier`` round-trips the raw OCR supplier dict for audit."""
    receipt = Receipt.objects.create(
        supplier=None,
        recognized_supplier={"name": "ТОВ Демо", "edrpou": "12345678"},
    )

    receipt.refresh_from_db()
    assert receipt.recognized_supplier == {
        "name": "ТОВ Демо",
        "edrpou": "12345678",
    }


@pytest.mark.django_db
def test_receipt_supplier_is_protected_on_delete() -> None:
    """Deleting a supplier that has receipts raises ``ProtectedError``.

    Receipts are financial records; the ``PROTECT`` on the FK prevents a
    supplier deletion from silently orphaning them.
    """
    supplier = Supplier.objects.create(name="ACME")
    Receipt.objects.create(supplier=supplier)

    with pytest.raises(ProtectedError):
        supplier.delete()


@pytest.mark.django_db
def test_receipt_line_defaults_and_relations() -> None:
    """A receipt line defaults to ``unmapped`` with quantity 0 and null price.

    Also verifies the ``ReceiptPhoto``/``ReceiptLine`` reverse relations
    (``receipt.photos`` / ``receipt.lines``) wire up as named in the contract.
    """
    supplier = Supplier.objects.create(name="ACME")
    receipt = Receipt.objects.create(supplier=supplier)
    ReceiptPhoto.objects.create(
        receipt=receipt, image_url="https://r2.example/img.jpg"
    )
    line = ReceiptLine.objects.create(receipt=receipt, recognized_sku="SUP-1")

    assert line.match_status == "unmapped"
    assert line.quantity == Decimal("0")
    assert line.price is None
    assert line.matched_product is None
    assert line.recognized_name == ""
    assert receipt.photos.count() == 1
    assert receipt.lines.count() == 1


@pytest.mark.django_db
def test_receipt_line_matched_product_set_null_on_delete() -> None:
    """Deleting a matched product nulls the line's FK rather than the line.

    ``SET_NULL`` means a removed catalog product leaves the receipt line intact;
    the line simply reverts to having no matched product.
    """
    supplier = Supplier.objects.create(name="ACME")
    receipt = Receipt.objects.create(supplier=supplier)
    product = OurProduct.objects.create(
        salesdrive_id="SD-1", sku="OUR-1", name="Товар"
    )
    line = ReceiptLine.objects.create(
        receipt=receipt,
        recognized_sku="SUP-1",
        matched_product=product,
        match_status="auto",
    )

    product.delete()
    line.refresh_from_db()

    assert line.matched_product is None
    assert ReceiptLine.objects.filter(pk=line.pk).exists()


# ---------------------------------------------------------------------------
# Accounts / Profile
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_profile_defaults_to_operator_role() -> None:
    """The post_save signal auto-creates exactly one operator Profile per user."""
    user = get_user_model().objects.create_user(
        username="op", email="op@example.com", password="pass1234"
    )

    # apps.accounts.signals.ensure_profile creates the Profile on user creation,
    # so we read it back rather than creating a second one (OneToOne is unique).
    profile = user.profile

    assert Profile.objects.filter(user=user).count() == 1
    assert profile.role == Profile.ROLE_OPERATOR
    assert profile.pin_hash == ""


@pytest.mark.django_db
def test_profile_pin_is_stored_hashed() -> None:
    """A PIN written via ``make_password`` verifies with ``check_password``.

    The PIN is a credential and must never be stored in plaintext. This proves
    the ``pin_hash`` field round-trips through Django's password hashers — the
    exact mechanism the ``/api/auth/pin/`` endpoint relies on.
    """
    user = get_user_model().objects.create_user(
        username="admin", email="admin@example.com", password="pass1234"
    )

    # Use the signal-created profile and set the PIN on it (the endpoint does the
    # same: hash the PIN into the existing Profile, never create a duplicate).
    profile = user.profile
    profile.role = Profile.ROLE_ADMIN
    profile.pin_hash = make_password("1234")
    profile.save(update_fields=["role", "pin_hash"])

    assert profile.pin_hash != "1234"  # not plaintext
    assert check_password("1234", profile.pin_hash) is True
    assert check_password("0000", profile.pin_hash) is False
