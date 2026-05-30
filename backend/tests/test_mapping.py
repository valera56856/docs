"""Behavior tests for the mapping core (``apps.mapping.services``).

The mapping core is the heart of Valeraup's "map once, remember forever"
promise. These tests describe — and therefore pin down — the contract of the
three public service functions:

* :func:`apps.mapping.services.normalize_sku` — the normalization rules
  (trim / UPPER / collapse internal whitespace) that make cosmetic spelling
  variants of a supplier SKU resolve to the *same* mapping.
* :func:`apps.mapping.services.match_line` — the lookup that turns a recognized
  supplier SKU into ``(OurProduct | None, match_status)`` where status is
  ``"auto"`` when a mapping exists and ``"unmapped"`` otherwise.
* :func:`apps.mapping.services.remember_mapping` — the idempotent upsert that
  persists a manual mapping and increments ``times_used``.

Why these are tested together: ``match_line`` only returns ``"auto"`` *after*
``remember_mapping`` has stored a mapping, so the round-trip (remember → match)
is the most important behavior to lock in. The normalization rules are tested in
isolation because they are the subtle part — a single missed rule silently
breaks auto-matching for whole classes of SKUs.

All DB-touching tests use ``@pytest.mark.django_db``.
"""
from __future__ import annotations

import pytest

from apps.catalog.models import OurProduct
from apps.mapping.models import ArticleMapping
from apps.mapping.services import (
    match_line,
    normalize_sku,
    remember_mapping,
)
from apps.suppliers.models import Supplier


# ---------------------------------------------------------------------------
# normalize_sku — pure function, no DB
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        # Trimming: leading/trailing whitespace is removed.
        ("  abc  ", "ABC"),
        ("\tabc\n", "ABC"),
        # Upper-casing: lookups are case-insensitive, so we canonicalize to UPPER.
        ("abc", "ABC"),
        ("AbC-123", "ABC-123"),
        # Collapse internal whitespace: runs of spaces/tabs become a single space
        # so "ABC  123" and "ABC 123" are the same SKU.
        ("abc  123", "ABC 123"),
        ("abc \t 123", "ABC 123"),
        # Combination of all three rules at once.
        ("   sku-  7  ", "SKU- 7"),
        # Already-normalized input is returned unchanged (idempotent).
        ("ABC-123", "ABC-123"),
        # Cyrillic SKUs upper-case correctly (Ukrainian supplier catalogs).
        ("арт-1", "АРТ-1"),
    ],
)
def test_normalize_sku_rules(raw: str, expected: str) -> None:
    """``normalize_sku`` applies trim, UPPER and whitespace-collapse.

    These three transformations are what make two cosmetically different
    spellings of the same supplier SKU resolve to one canonical mapping. The
    parametrized cases assert each rule individually and in combination.
    """
    assert normalize_sku(raw) == expected


def test_normalize_sku_is_idempotent() -> None:
    """Normalizing an already-normalized SKU is a no-op.

    Idempotency matters because the normalized value is what gets stored in
    ``ArticleMapping.supplier_sku_normalized`` and re-normalized on every lookup;
    a non-idempotent function would let the stored key drift away from what
    lookups produce.
    """
    once = normalize_sku("  some  Sku-9 ")
    twice = normalize_sku(once)
    assert once == twice


# ---------------------------------------------------------------------------
# Fixtures for the DB-backed mapping tests
# ---------------------------------------------------------------------------
@pytest.fixture
def supplier(db) -> Supplier:
    """Return a persisted active supplier to own mappings."""
    return Supplier.objects.create(name="ACME Постачання", is_active=True)


@pytest.fixture
def product(db) -> OurProduct:
    """Return a persisted catalog product to map supplier SKUs to."""
    return OurProduct.objects.create(
        salesdrive_id="SD-1001",
        sku="OUR-1001",
        name="Сорочка біла",
    )


@pytest.fixture
def other_product(db) -> OurProduct:
    """Return a second catalog product to test mapping corrections.

    Used by the "operator correction" case where a SKU is re-mapped from one
    product to another.
    """
    return OurProduct.objects.create(
        salesdrive_id="SD-2002",
        sku="OUR-2002",
        name="Штани сині",
    )


# ---------------------------------------------------------------------------
# match_line — lookup before/after a mapping exists
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_match_line_unmapped_when_no_mapping(supplier: Supplier) -> None:
    """With no stored mapping, ``match_line`` returns ``(None, "unmapped")``.

    This is the first-time-seen path: the SKU has never been mapped for this
    supplier, so the operator must map it manually.
    """
    product_result, status = match_line(supplier.id, "SKU-NEW")

    assert product_result is None
    assert status == "unmapped"


@pytest.mark.django_db
def test_match_line_auto_after_remember(
    supplier: Supplier, product: OurProduct
) -> None:
    """After ``remember_mapping``, the same SKU auto-matches.

    This is the core "remember forever" behavior: once a manual mapping is
    stored, recognizing the same supplier SKU resolves to the product
    automatically with status ``"auto"``.
    """
    remember_mapping(supplier.id, "SKU-7", product.id, created_by="operator")

    product_result, status = match_line(supplier.id, "SKU-7")

    assert product_result is not None
    assert product_result.id == product.id
    assert status == "auto"


@pytest.mark.django_db
def test_match_line_auto_ignores_sku_formatting(
    supplier: Supplier, product: OurProduct
) -> None:
    """Auto-match survives cosmetic SKU formatting differences.

    The mapping was remembered as ``"sku-7"`` but the OCR later reads
    ``"  SKU-7 "`` (different case + surrounding whitespace). Because both
    normalize to the same key, the lookup must still auto-match. This is the
    whole reason ``supplier_sku_normalized`` exists.
    """
    remember_mapping(supplier.id, "sku-7", product.id)

    product_result, status = match_line(supplier.id, "  SKU-7 ")

    assert product_result is not None
    assert product_result.id == product.id
    assert status == "auto"


@pytest.mark.django_db
def test_match_line_is_scoped_per_supplier(
    supplier: Supplier, product: OurProduct
) -> None:
    """A mapping for one supplier does not leak to another supplier.

    SKU namespaces are per-supplier (``unique_together`` includes ``supplier``),
    so the same printed SKU can mean different products for different vendors.
    A mapping stored for ``supplier`` must not auto-match for ``other``.
    """
    other = Supplier.objects.create(name="Інший Постачальник")
    remember_mapping(supplier.id, "SKU-7", product.id)

    product_result, status = match_line(other.id, "SKU-7")

    assert product_result is None
    assert status == "unmapped"


# ---------------------------------------------------------------------------
# remember_mapping — persistence, normalization, idempotency, times_used
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_remember_mapping_persists_manual_mapping(
    supplier: Supplier, product: OurProduct
) -> None:
    """``remember_mapping`` writes one manual ``ArticleMapping`` row.

    It must store the raw SKU for audit, the normalized SKU for lookups, and
    link the supplier and product. The first store starts ``times_used`` at 1
    (this store *is* one use) per the increment-on-use contract.
    """
    mapping = remember_mapping(
        supplier.id, "  sku-7 ", product.id, created_by="operator"
    )

    assert isinstance(mapping, ArticleMapping)
    assert mapping.supplier_id == supplier.id
    assert mapping.our_product_id == product.id
    assert mapping.supplier_sku == "  sku-7 "  # raw value retained for audit
    assert mapping.supplier_sku_normalized == normalize_sku("  sku-7 ")
    assert mapping.created_by == "operator"
    assert mapping.times_used >= 1
    assert ArticleMapping.objects.count() == 1


@pytest.mark.django_db
def test_remember_mapping_is_idempotent_and_increments_use(
    supplier: Supplier, product: OurProduct
) -> None:
    """Re-remembering the same SKU upserts (no duplicate) and bumps ``times_used``.

    Calling ``remember_mapping`` twice for the same supplier + normalized SKU
    must NOT create a second row (the ``unique_together`` constraint would
    otherwise raise). Instead it updates the existing row and increments
    ``times_used``. We pass formatting-variant SKUs to prove the upsert keys on
    the *normalized* value.
    """
    first = remember_mapping(supplier.id, "sku-7", product.id)
    second = remember_mapping(supplier.id, "  SKU-7  ", product.id)

    assert ArticleMapping.objects.count() == 1
    assert first.id == second.id

    second.refresh_from_db()
    assert second.times_used >= 2


@pytest.mark.django_db
def test_remember_mapping_handles_cyrillic_sku(
    supplier: Supplier, product: OurProduct
) -> None:
    """A Cyrillic supplier SKU normalizes and auto-matches round-trip.

    Ukrainian supplier catalogs use Cyrillic article codes (``арт-1``). The stored
    normalized key must upper-case the Cyrillic letters so a later OCR read of
    ``"  АРТ-1 "`` (different case + whitespace) still auto-matches.
    """
    mapping = remember_mapping(supplier.id, "арт-1", product.id)

    assert mapping.supplier_sku_normalized == normalize_sku("арт-1") == "АРТ-1"

    product_result, status = match_line(supplier.id, "  Арт-1 ")
    assert product_result is not None
    assert product_result.id == product.id
    assert status == "auto"


@pytest.mark.django_db
def test_remember_mapping_is_isolated_per_supplier(
    supplier: Supplier, product: OurProduct, other_product: OurProduct
) -> None:
    """The same SKU can map to different products for different suppliers.

    SKU namespaces are per-supplier, so remembering ``"SKU-1"→product`` for one
    supplier and ``"SKU-1"→other_product`` for another must create two distinct
    mappings, each resolving correctly within its own supplier.
    """
    other_supplier = Supplier.objects.create(name="Інший Постачальник")

    remember_mapping(supplier.id, "SKU-1", product.id)
    remember_mapping(other_supplier.id, "SKU-1", other_product.id)

    assert ArticleMapping.objects.count() == 2

    first, _ = match_line(supplier.id, "SKU-1")
    second, _ = match_line(other_supplier.id, "SKU-1")
    assert first.id == product.id
    assert second.id == other_product.id


@pytest.mark.django_db
def test_remember_mapping_correction_retargets_product(
    supplier: Supplier, product: OurProduct, other_product: OurProduct
) -> None:
    """Re-mapping an existing SKU re-targets the product (operator correction).

    When an operator realizes a SKU was mapped to the wrong product, re-calling
    ``remember_mapping`` with the same SKU but a new product must update the
    existing row in place (no duplicate) and point auto-match at the corrected
    product, while still bumping ``times_used``.
    """
    first = remember_mapping(supplier.id, "SKU-9", product.id, created_by="op-1")
    corrected = remember_mapping(
        supplier.id, "SKU-9", other_product.id, created_by="op-2"
    )

    assert ArticleMapping.objects.count() == 1
    assert corrected.id == first.id
    assert corrected.our_product_id == other_product.id
    assert corrected.times_used >= 2

    matched, status = match_line(supplier.id, "SKU-9")
    assert matched.id == other_product.id
    assert status == "auto"


@pytest.mark.django_db
def test_remember_mapping_preserves_original_created_by(
    supplier: Supplier, product: OurProduct, other_product: OurProduct
) -> None:
    """A correction never overwrites the original ``created_by``.

    ``created_by`` records who *first* authored the mapping for audit; later
    confirmations or corrections (possibly by a different operator) must leave it
    untouched.
    """
    remember_mapping(supplier.id, "SKU-9", product.id, created_by="original-op")
    corrected = remember_mapping(
        supplier.id, "SKU-9", other_product.id, created_by="different-op"
    )

    assert corrected.created_by == "original-op"
