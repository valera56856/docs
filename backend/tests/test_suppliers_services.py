"""Behavior tests for supplier auto-detection services.

Covers the two functions in :mod:`apps.suppliers.services` that power the
auto-supplier feature:

* :func:`normalize_supplier_name` — trim / collapse-whitespace / UPPER folding
  for the name-fallback comparison.
* :func:`match_or_create_supplier` — resolve a recognized ``(name, edrpou)`` pair
  by ЄДРПОУ first, then by normalized name, else create a new row. Idempotency is
  asserted by running the same recognized pair twice and checking only one row is
  created.

These are pure DB-layer tests (no HTTP, no Gemini) — the OCR boundary is exercised
elsewhere. All DB-touching tests use ``@pytest.mark.django_db``.
"""

from __future__ import annotations

import pytest

from apps.suppliers.models import Supplier
from apps.suppliers.services import (
    UNKNOWN_SUPPLIER_NAME,
    match_or_create_supplier,
    normalize_supplier_name,
)


# ---------------------------------------------------------------------------
# normalize_supplier_name
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("ТОВ Демо Постач", "ТОВ ДЕМО ПОСТАЧ"),
        ("  тов  демо   постач ", "ТОВ ДЕМО ПОСТАЧ"),  # trim + collapse + upper
        ("Acme  LLC", "ACME LLC"),
        ("", ""),
        ("   ", ""),  # whitespace-only → empty
    ],
)
def test_normalize_supplier_name_cases(raw: str, expected: str) -> None:
    """Trim, collapse internal whitespace, and uppercase for comparison."""
    assert normalize_supplier_name(raw) == expected


# ---------------------------------------------------------------------------
# match_or_create_supplier — match by ЄДРПОУ
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_match_by_edrpou_exact() -> None:
    """A non-empty ЄДРПОУ matches an existing supplier exactly (not created)."""
    existing = Supplier.objects.create(name="ТОВ Демо", edrpou="12345678")

    supplier, created = match_or_create_supplier(
        name="ЗОВСІМ ІНША НАЗВА",  # name differs — ЄДРПОУ still wins
        edrpou="12345678",
    )

    assert created is False
    assert supplier.pk == existing.pk


@pytest.mark.django_db
def test_match_by_edrpou_takes_priority_over_name() -> None:
    """ЄДРПОУ match wins even when a *different* supplier shares the name."""
    by_code = Supplier.objects.create(name="Демо", edrpou="12345678")
    Supplier.objects.create(name="Демо Постач", edrpou="87654321")

    supplier, created = match_or_create_supplier(
        name="Демо Постач",  # would name-match the second row...
        edrpou="12345678",  # ...but ЄДРПОУ pins the first
    )

    assert created is False
    assert supplier.pk == by_code.pk


# ---------------------------------------------------------------------------
# match_or_create_supplier — match by normalized name (no ЄДРПОУ)
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_match_by_name_when_no_edrpou() -> None:
    """With no code, a normalized-name match resolves to the existing row."""
    existing = Supplier.objects.create(name="ТОВ Демо Постач")

    supplier, created = match_or_create_supplier(
        name="  тов   демо  постач ",  # cosmetic OCR noise, same vendor
        edrpou=None,
    )

    assert created is False
    assert supplier.pk == existing.pk


@pytest.mark.django_db
def test_name_match_does_not_fire_for_empty_name() -> None:
    """An empty recognized name must not collide with any existing supplier."""
    Supplier.objects.create(name="ТОВ Демо")

    supplier, created = match_or_create_supplier(name="", edrpou="")

    # No name and no code → a placeholder supplier is created, not a name match.
    assert created is True
    assert supplier.name == UNKNOWN_SUPPLIER_NAME


# ---------------------------------------------------------------------------
# match_or_create_supplier — create new
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_creates_new_supplier_with_name_and_edrpou() -> None:
    """No match → a new supplier is created with the recognized name + code."""
    assert Supplier.objects.count() == 0

    supplier, created = match_or_create_supplier(
        name="ТОВ Новий Постач",
        edrpou=" 23456789 ",  # surrounding whitespace is stripped on store
    )

    assert created is True
    assert supplier.name == "ТОВ Новий Постач"
    assert supplier.edrpou == "23456789"
    assert supplier.is_active is True
    assert Supplier.objects.count() == 1


@pytest.mark.django_db
def test_creates_placeholder_when_nothing_recognized() -> None:
    """Both ``None`` → a single placeholder ``Невідомий постачальник`` row."""
    supplier, created = match_or_create_supplier(name=None, edrpou=None)

    assert created is True
    assert supplier.name == UNKNOWN_SUPPLIER_NAME
    assert supplier.edrpou == ""


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_match_or_create_is_idempotent_by_edrpou() -> None:
    """Re-running with the same ``(name, edrpou)`` returns the same row, once.

    The first call creates the supplier; the second must *match* it (by ЄДРПОУ)
    rather than create a duplicate — the property the OCR task relies on so a
    redelivered Celery task converges.
    """
    first, created_first = match_or_create_supplier(
        name="ТОВ Демо", edrpou="12345678"
    )
    second, created_second = match_or_create_supplier(
        name="ТОВ Демо (інша назва)", edrpou="12345678"
    )

    assert created_first is True
    assert created_second is False
    assert first.pk == second.pk
    assert Supplier.objects.filter(edrpou="12345678").count() == 1


@pytest.mark.django_db
def test_match_or_create_is_idempotent_by_name() -> None:
    """Code-less re-runs converge on one row via the normalized-name fallback."""
    first, created_first = match_or_create_supplier(name="ТОВ Демо", edrpou=None)
    second, created_second = match_or_create_supplier(
        name="  тов   демо ", edrpou=None
    )

    assert created_first is True
    assert created_second is False
    assert first.pk == second.pk
    assert Supplier.objects.count() == 1
