"""Behavior tests for the receipt workflow endpoints and status machine.

Covers the round-2 receipts delta:

* Creating a draft receipt from ``{supplier: id}`` (no photos needed up front).
* :func:`recompute_receipt_status` transitions (no lines / unmapped → needs
  mapping; all mapped → ready; never downgrading a terminal state).
* :func:`set_receipt_status` legal/illegal explicit transitions.
* ``PATCH`` editing a line (and the status recompute it triggers).
* The map flow setting ``manual`` and flipping the receipt to ``ready``.

The network boundary (Gemini) is never touched here — these tests exercise the
synchronous API + service layer only. Auth flows through the shared
``auth_client`` fixture (real SimpleJWT), matching the PWA's auth path.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from apps.catalog.models import OurProduct
from apps.mapping.models import ArticleMapping
from apps.receipts.models import Receipt, ReceiptLine
from apps.receipts.services.status import (
    recompute_receipt_status,
    set_receipt_status,
)
from apps.suppliers.models import Supplier


@pytest.fixture
def supplier(db) -> Supplier:
    """Create and return a persisted active supplier."""
    return Supplier.objects.create(name="ACME Постачання")


@pytest.fixture
def product(db) -> OurProduct:
    """Create and return a persisted catalog product."""
    return OurProduct.objects.create(
        salesdrive_id="SD-1", sku="OUR-1", name="Сорочка біла"
    )


@pytest.fixture
def media_root(settings, tmp_path):
    """Redirect file storage to a temp dir so generated files are cleaned up.

    Forces the local FileSystemStorage fallback regardless of the ambient
    environment, keeping the generate-xlsx test hermetic (no real bucket, no
    leftover files under ``backend/media``).
    """
    settings.MEDIA_ROOT = str(tmp_path)
    settings.STORAGES = {
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
        },
    }
    return tmp_path


# ---------------------------------------------------------------------------
# Create draft
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_create_draft_receipt_from_supplier(auth_client, supplier) -> None:
    """``POST /api/receipts/`` with just a supplier creates a ``draft``.

    The new camera-first flow creates the receipt before any photos exist, so
    ``photo_urls`` must be optional and the receipt must start in ``draft``.
    """
    response = auth_client.post(
        "/api/receipts/", {"supplier": supplier.pk}, format="json"
    )

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "draft"
    assert body["supplier"] == supplier.pk
    assert body["photos"] == []
    assert body["lines"] == []


@pytest.mark.django_db
def test_create_draft_requires_auth(api_client, supplier) -> None:
    """Anonymous receipt creation is rejected (global ``IsAuthenticated``)."""
    response = api_client.post(
        "/api/receipts/", {"supplier": supplier.pk}, format="json"
    )
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# recompute_receipt_status
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_recompute_no_lines_is_needs_mapping(supplier) -> None:
    """A receipt with no lines cannot be exported → ``needs_mapping``."""
    receipt = Receipt.objects.create(supplier=supplier, status="recognizing")

    assert recompute_receipt_status(receipt) == "needs_mapping"
    receipt.refresh_from_db()
    assert receipt.status == "needs_mapping"


@pytest.mark.django_db
def test_recompute_unmapped_line_is_needs_mapping(supplier) -> None:
    """Any unmapped line keeps the receipt at ``needs_mapping``."""
    receipt = Receipt.objects.create(supplier=supplier, status="recognizing")
    ReceiptLine.objects.create(
        receipt=receipt,
        recognized_sku="SUP-A",
        quantity=Decimal("1.000"),
        matched_product=None,
        match_status="unmapped",
    )

    assert recompute_receipt_status(receipt) == "needs_mapping"


@pytest.mark.django_db
def test_recompute_all_mapped_is_ready(supplier, product) -> None:
    """When every line has a product the receipt becomes ``ready``."""
    receipt = Receipt.objects.create(supplier=supplier, status="needs_mapping")
    ReceiptLine.objects.create(
        receipt=receipt,
        recognized_sku="SUP-A",
        quantity=Decimal("2.000"),
        matched_product=product,
        match_status="auto",
    )

    assert recompute_receipt_status(receipt) == "ready"
    receipt.refresh_from_db()
    assert receipt.status == "ready"


@pytest.mark.django_db
@pytest.mark.parametrize("terminal", ["xlsx_ready", "error"])
def test_recompute_never_downgrades_terminal(supplier, product, terminal) -> None:
    """``xlsx_ready`` / ``error`` are protected from auto-downgrade.

    A late line edit must not silently un-generate an exported receipt or clear a
    recorded failure.
    """
    receipt = Receipt.objects.create(supplier=supplier, status=terminal)
    # Even with no lines (which would otherwise force needs_mapping), the terminal
    # state is preserved.
    assert recompute_receipt_status(receipt) == terminal
    receipt.refresh_from_db()
    assert receipt.status == terminal


# ---------------------------------------------------------------------------
# set_receipt_status
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_set_status_legal_transition(supplier) -> None:
    """A legal explicit transition is applied and persisted."""
    receipt = Receipt.objects.create(supplier=supplier, status="draft")
    assert set_receipt_status(receipt, "recognizing") == "recognizing"
    receipt.refresh_from_db()
    assert receipt.status == "recognizing"


@pytest.mark.django_db
def test_set_status_error_from_anywhere(supplier) -> None:
    """``error`` is reachable from any state (any step may fail)."""
    receipt = Receipt.objects.create(supplier=supplier, status="draft")
    assert set_receipt_status(receipt, "error") == "error"


@pytest.mark.django_db
def test_set_status_illegal_transition_raises(supplier) -> None:
    """An obviously-wrong jump is rejected with ``ValueError``."""
    receipt = Receipt.objects.create(supplier=supplier, status="draft")
    with pytest.raises(ValueError):
        set_receipt_status(receipt, "xlsx_ready")


@pytest.mark.django_db
def test_set_status_unknown_status_raises(supplier) -> None:
    """An unrecognised status value is rejected."""
    receipt = Receipt.objects.create(supplier=supplier, status="draft")
    with pytest.raises(ValueError):
        set_receipt_status(receipt, "bogus")


# ---------------------------------------------------------------------------
# Line PATCH
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_patch_line_updates_quantity_and_price(auth_client, supplier, product) -> None:
    """``PATCH .../lines/{id}/`` edits qty/price and returns the line."""
    receipt = Receipt.objects.create(supplier=supplier, status="ready")
    line = ReceiptLine.objects.create(
        receipt=receipt,
        recognized_sku="SUP-A",
        quantity=Decimal("1.000"),
        price=Decimal("10.00"),
        matched_product=product,
        match_status="auto",
    )

    response = auth_client.patch(
        f"/api/receipts/{receipt.pk}/lines/{line.pk}/",
        {"quantity": "5.000", "price": "12.50"},
        format="json",
    )

    assert response.status_code == 200
    line.refresh_from_db()
    assert line.quantity == Decimal("5.000")
    assert line.price == Decimal("12.50")


@pytest.mark.django_db
def test_patch_line_recomputes_status(auth_client, supplier, product) -> None:
    """Editing a line keeps a fully-mapped receipt ``ready`` (recompute runs)."""
    receipt = Receipt.objects.create(supplier=supplier, status="needs_mapping")
    line = ReceiptLine.objects.create(
        receipt=receipt,
        recognized_sku="SUP-A",
        quantity=Decimal("1.000"),
        matched_product=product,
        match_status="auto",
    )

    auth_client.patch(
        f"/api/receipts/{receipt.pk}/lines/{line.pk}/",
        {"quantity": "3.000"},
        format="json",
    )

    receipt.refresh_from_db()
    # The single line is mapped, so the recompute on edit promotes to ready.
    assert receipt.status == "ready"


# ---------------------------------------------------------------------------
# Map flow
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_map_line_sets_manual_and_remembers(auth_client, supplier, product) -> None:
    """Mapping a line marks it ``manual``, records a mapping, and recomputes.

    The single (previously unmapped) line becoming mapped flips the receipt to
    ``ready``, and a remembered :class:`ArticleMapping` is created for next time.
    """
    receipt = Receipt.objects.create(supplier=supplier, status="needs_mapping")
    line = ReceiptLine.objects.create(
        receipt=receipt,
        recognized_sku="SUP-A",
        quantity=Decimal("1.000"),
        matched_product=None,
        match_status="unmapped",
    )

    response = auth_client.post(
        f"/api/receipts/{receipt.pk}/lines/{line.pk}/map/",
        {"our_product_id": product.pk},
        format="json",
    )

    assert response.status_code == 200
    line.refresh_from_db()
    assert line.matched_product_id == product.pk
    assert line.match_status == "manual"

    receipt.refresh_from_db()
    assert receipt.status == "ready"

    mapping = ArticleMapping.objects.get(
        supplier=supplier, supplier_sku_normalized="SUP-A"
    )
    assert mapping.our_product_id == product.pk
    assert mapping.times_used == 1


@pytest.mark.django_db
def test_generate_xlsx_sets_xlsx_ready(
    auth_client, supplier, product, media_root
) -> None:
    """Generating the Excel stores a URL and flips status to ``xlsx_ready``."""
    receipt = Receipt.objects.create(supplier=supplier, status="ready")
    ReceiptLine.objects.create(
        receipt=receipt,
        recognized_sku="SUP-A",
        quantity=Decimal("2.000"),
        price=Decimal("10.00"),
        matched_product=product,
        match_status="auto",
    )

    response = auth_client.post(f"/api/receipts/{receipt.pk}/generate-xlsx/")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "xlsx_ready"
    assert body["xlsx_url"]
    receipt.refresh_from_db()
    assert receipt.status == "xlsx_ready"
    assert receipt.xlsx_url
