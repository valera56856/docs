"""End-to-end tests for auto-supplier detection in the recognize task.

These exercise :func:`apps.receipts.tasks.recognize_receipt_task` with the Gemini
network boundary mocked to return the new ``{"supplier": {...}, "lines": [...]}``
object, asserting the task:

* auto-creates / matches the supplier from the recognized header and attaches it
  to a previously supplier-less draft;
* stores the raw OCR supplier dict on ``receipt.recognized_supplier`` for audit;
* leaves an existing (operator-chosen) supplier untouched;
* runs per-supplier mapping for the lines once a supplier is known, and leaves
  lines unmapped (status ``needs_mapping``) when OCR found no supplier;
* stays idempotent on re-run (no duplicate suppliers / lines).

The boundary is mocked at ``integrations.gemini.recognize_invoice`` (the function
the task calls) so no SDK / HTTP is ever invoked — per CLAUDE.md §10. All tests
use ``@pytest.mark.django_db``.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from apps.catalog.models import OurProduct
from apps.mapping.services import remember_mapping
from apps.receipts import tasks as receipt_tasks
from apps.receipts.models import Receipt
from apps.suppliers.models import Supplier


@pytest.fixture
def product(db) -> OurProduct:
    """Create and return a persisted catalog product."""
    return OurProduct.objects.create(
        salesdrive_id="SD-1", sku="OUR-1", name="Сорочка біла"
    )


def _patch_recognize(monkeypatch, payload: dict) -> None:
    """Patch the Gemini boundary the task calls to return ``payload``.

    Args:
        monkeypatch: pytest monkeypatch fixture.
        payload: The ``{"supplier", "lines"}`` dict the mocked OCR returns.
    """

    monkeypatch.setattr(
        receipt_tasks.gemini, "recognize_invoice", lambda images: payload
    )


@pytest.mark.django_db
def test_task_creates_and_attaches_supplier(monkeypatch) -> None:
    """A supplier-less draft gets a supplier auto-created from the OCR header."""
    _patch_recognize(
        monkeypatch,
        {
            "supplier": {"name": "ТОВ Демо Постач", "edrpou": "12345678"},
            "lines": [
                {
                    "supplier_sku": "ABC-1",
                    "name": "Гель-лак",
                    "quantity": 3,
                    "price": 50,
                }
            ],
        },
    )

    receipt = Receipt.objects.create(supplier=None, status="recognizing")

    receipt_tasks.recognize_receipt_task(receipt.pk)

    receipt.refresh_from_db()
    assert receipt.supplier is not None
    assert receipt.supplier.name == "ТОВ Демо Постач"
    assert receipt.supplier.edrpou == "12345678"
    # The raw OCR supplier dict is recorded for audit.
    assert receipt.recognized_supplier == {
        "name": "ТОВ Демо Постач",
        "edrpou": "12345678",
    }
    # One line was created; no remembered mapping yet → unmapped → needs_mapping.
    assert receipt.lines.count() == 1
    assert receipt.status == "needs_mapping"


@pytest.mark.django_db
def test_task_matches_existing_supplier_by_edrpou(monkeypatch) -> None:
    """Detection reuses an existing supplier by ЄДРПОУ (no duplicate row)."""
    existing = Supplier.objects.create(name="ТОВ Демо", edrpou="12345678")
    _patch_recognize(
        monkeypatch,
        {
            "supplier": {"name": "інша назва", "edrpou": "12345678"},
            "lines": [],
        },
    )

    receipt = Receipt.objects.create(supplier=None, status="recognizing")

    receipt_tasks.recognize_receipt_task(receipt.pk)

    receipt.refresh_from_db()
    assert receipt.supplier_id == existing.pk
    assert Supplier.objects.filter(edrpou="12345678").count() == 1


@pytest.mark.django_db
def test_task_auto_maps_lines_under_detected_supplier(
    monkeypatch, product
) -> None:
    """A remembered mapping auto-resolves a line once the supplier is detected.

    The supplier already exists with a learned ``(supplier, ABC-1) → product``
    mapping, so detecting it on the invoice auto-matches the line → ``ready``.
    """
    supplier = Supplier.objects.create(name="ТОВ Демо", edrpou="12345678")
    remember_mapping(
        supplier_id=supplier.pk, supplier_sku="ABC-1", our_product_id=product.pk
    )
    _patch_recognize(
        monkeypatch,
        {
            "supplier": {"name": "ТОВ Демо", "edrpou": "12345678"},
            "lines": [
                {
                    "supplier_sku": "ABC-1",
                    "name": "Гель-лак",
                    "quantity": 2,
                    "price": 30,
                }
            ],
        },
    )

    receipt = Receipt.objects.create(supplier=None, status="recognizing")

    receipt_tasks.recognize_receipt_task(receipt.pk)

    receipt.refresh_from_db()
    assert receipt.supplier_id == supplier.pk
    assert receipt.status == "ready"
    line = receipt.lines.get()
    assert line.matched_product_id == product.pk
    assert line.match_status == "auto"


@pytest.mark.django_db
def test_task_does_not_clobber_existing_supplier(monkeypatch) -> None:
    """An operator-chosen supplier is preserved even if OCR reads a different one."""
    chosen = Supplier.objects.create(name="Обраний", edrpou="87654321")
    _patch_recognize(
        monkeypatch,
        {
            "supplier": {"name": "ТОВ Демо", "edrpou": "12345678"},
            "lines": [],
        },
    )

    receipt = Receipt.objects.create(supplier=chosen, status="recognizing")

    receipt_tasks.recognize_receipt_task(receipt.pk)

    receipt.refresh_from_db()
    # Supplier unchanged...
    assert receipt.supplier_id == chosen.pk
    # ...but the raw detection is still recorded for audit.
    assert receipt.recognized_supplier == {
        "name": "ТОВ Демо",
        "edrpou": "12345678",
    }
    # The OCR-read supplier was NOT created as a side effect.
    assert not Supplier.objects.filter(edrpou="12345678").exists()


@pytest.mark.django_db
def test_task_no_supplier_leaves_lines_unmapped(monkeypatch) -> None:
    """OCR found no supplier → lines stay unmapped and status ``needs_mapping``.

    With no supplier there is no SKU namespace, so even a line whose SKU *would*
    match some supplier's mapping cannot resolve. ``recognized_supplier`` records
    the (null) detection.
    """
    _patch_recognize(
        monkeypatch,
        {
            "supplier": None,
            "lines": [
                {
                    "supplier_sku": "ABC-1",
                    "name": "Гель-лак",
                    "quantity": 1,
                    "price": 10,
                }
            ],
        },
    )

    receipt = Receipt.objects.create(supplier=None, status="recognizing")

    receipt_tasks.recognize_receipt_task(receipt.pk)

    receipt.refresh_from_db()
    assert receipt.supplier_id is None
    assert receipt.recognized_supplier is None
    assert receipt.status == "needs_mapping"
    line = receipt.lines.get()
    assert line.matched_product_id is None
    assert line.match_status == "unmapped"


@pytest.mark.django_db
def test_task_empty_supplier_dict_does_not_create(monkeypatch) -> None:
    """A supplier dict with only nulls does not create a placeholder supplier."""
    _patch_recognize(
        monkeypatch,
        {"supplier": {"name": None, "edrpou": None}, "lines": []},
    )

    receipt = Receipt.objects.create(supplier=None, status="recognizing")

    receipt_tasks.recognize_receipt_task(receipt.pk)

    receipt.refresh_from_db()
    assert receipt.supplier_id is None
    assert Supplier.objects.count() == 0
    # The (empty) detection is still recorded verbatim for audit.
    assert receipt.recognized_supplier == {"name": None, "edrpou": None}


@pytest.mark.django_db
def test_task_idempotent_on_supplier_and_lines(monkeypatch, product) -> None:
    """Re-running detection converges: one supplier, one line, same state."""
    remember_target = product
    _patch_recognize(
        monkeypatch,
        {
            "supplier": {"name": "ТОВ Демо", "edrpou": "12345678"},
            "lines": [
                {
                    "supplier_sku": "ABC-1",
                    "name": "Гель-лак",
                    "quantity": 1,
                    "price": 10,
                }
            ],
        },
    )

    receipt = Receipt.objects.create(supplier=None, status="recognizing")

    receipt_tasks.recognize_receipt_task(receipt.pk)
    first_supplier_id = Receipt.objects.get(pk=receipt.pk).supplier_id

    # Second run: same OCR payload. ``match_or_create_supplier`` must match the
    # row the first run created (by ЄДРПОУ), and lines are rebuilt not duplicated.
    receipt_tasks.recognize_receipt_task(receipt.pk)

    receipt.refresh_from_db()
    assert receipt.supplier_id == first_supplier_id
    assert Supplier.objects.filter(edrpou="12345678").count() == 1
    assert receipt.lines.count() == 1
    assert remember_target is product  # sanity: fixture wired
