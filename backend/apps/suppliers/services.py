"""Supplier detection services: normalize a vendor name and match-or-create.

The auto-supplier feature turns the scan-first flow upside down: instead of the
operator picking a vendor before photographing an invoice, Gemini reads the
supplier from the invoice header (постачальник/продавець name + ЄДРПОУ code) and
the system resolves it to a :class:`~apps.suppliers.models.Supplier` row. This
module holds that resolution logic so the Celery task and views stay thin (see
``CLAUDE.md`` §3 — "services hold business logic").

Two functions:

* :func:`normalize_supplier_name` — canonicalize a raw supplier name so cosmetic
  variants of the same vendor collide on one key (the name fallback path).
* :func:`match_or_create_supplier` — resolve a recognized ``(name, edrpou)`` pair
  to an existing supplier (by ЄДРПОУ first, then normalized name) or create a new
  one, returning ``(supplier, was_created)``.

WHY ЄДРПОУ is the primary key and name is only a fallback:
    A printed name is noisy — OCR mis-reads characters, abbreviations differ
    («ТОВ» vs «Товариство з обмеженою відповідальністю»), and two unrelated
    vendors can share a similar name. The ЄДРПОУ tax code, by contrast, uniquely
    and stably identifies a legal entity. So we match on a *non-empty* ЄДРПОУ
    exactly first; only when the invoice omitted the code do we fall back to a
    normalized-name comparison, which is best-effort.
"""

from __future__ import annotations

import logging

from apps.suppliers.models import Supplier

logger = logging.getLogger(__name__)

# Shown when an invoice yields neither a usable name nor a ЄДРПОУ code but the
# caller still wants a placeholder supplier created. Kept as a constant so the
# string has one home (and the tests can assert it without duplication).
UNKNOWN_SUPPLIER_NAME = "Невідомий постачальник"


def normalize_supplier_name(s: str) -> str:
    """Canonicalize a supplier name for fallback matching.

    Normalization rules (and the WHY for each):

    * **Strip surrounding whitespace** — OCR routinely adds leading/trailing
      spaces that carry no meaning.
    * **Collapse internal whitespace runs to a single space** — a doubled space
      from OCR (``"ТОВ  Демо"``) must compare equal to a single space
      (``"ТОВ Демо"``).
    * **Uppercase (casefold to UPPER)** — supplier names are matched
      case-insensitively; ``"тов демо"`` and ``"ТОВ Демо"`` are the same vendor,
      so we fold case to avoid creating a duplicate row.

    The result is used only for *comparison* (the name fallback), never stored —
    the human-readable ``Supplier.name`` keeps its original casing/spacing. We
    deliberately keep this conservative (no punctuation stripping, no «ТОВ»
    de-abbreviation): aggressive normalization risks merging genuinely different
    vendors, and ЄДРПОУ is the reliable key anyway.

    Args:
        s: The supplier name exactly as recognized/printed (may be empty/messy).

    Returns:
        The normalized name for comparison. Empty string for empty/whitespace
        input.
    """

    if not s:
        return ""
    # ``str.split()`` with no args splits on any run of whitespace and drops
    # empty tokens, so joining with a single space trims the ends and collapses
    # internal runs in one step; ``.upper()`` then folds case for matching.
    return " ".join(s.split()).upper()


def match_or_create_supplier(
    name: str | None,
    edrpou: str | None,
    created_by: str = "",
) -> tuple[Supplier, bool]:
    """Resolve a recognized supplier to a row, creating one if necessary.

    Resolution order (the WHY for the ordering is in the module docstring):

    1. **Exact ЄДРПОУ match** — if ``edrpou`` is non-empty (after trimming),
       return the first supplier whose ``edrpou`` equals it. This is the reliable
       key, so it wins over any name comparison.
    2. **Normalized-name match** — otherwise compare
       :func:`normalize_supplier_name` of ``name`` against every existing
       supplier's normalized name. Best-effort fallback for invoices with no
       code.
    3. **Create** — if nothing matched, create a new ``Supplier`` with
       ``name = name or UNKNOWN_SUPPLIER_NAME``, ``edrpou = (edrpou or '').strip()``
       and ``is_active=True``.

    Idempotent in practice: re-running with the same recognized ``(name, edrpou)``
    returns the *same* existing supplier on the second call rather than creating a
    duplicate, because the first call's row now matches in step 1 (or step 2).
    The function never mutates an existing supplier — it only reads or inserts —
    so re-detection cannot clobber an admin's hand-edited name/code.

    Args:
        name: The recognized supplier name, or ``None``/empty if OCR omitted it.
        edrpou: The recognized ЄДРПОУ tax code, or ``None``/empty if absent.
        created_by: Identifier (username/email) of the operator whose scan
            triggered the creation. Recorded in the structured log for audit; the
            ``Supplier`` model has no ``created_by`` column, so it is not stored
            on the row (kept here to mirror the mapping-service signature and to
            make the audit log attributable).

    Returns:
        A tuple ``(supplier, was_created)`` where ``was_created`` is ``True`` only
        when a new row was inserted by this call.
    """

    edrpou_clean = (edrpou or "").strip()
    normalized_name = normalize_supplier_name(name or "")

    # 1) ЄДРПОУ is the reliable key — match it exactly when present.
    if edrpou_clean:
        existing = Supplier.objects.filter(edrpou=edrpou_clean).first()
        if existing is not None:
            logger.info(
                "supplier_match_edrpou",
                extra={
                    "supplier_id": existing.pk,
                    "edrpou": edrpou_clean,
                    "created_by": created_by,
                },
            )
            return existing, False

    # 2) Fall back to a normalized-name comparison (only meaningful when we have
    #    a name to compare). We normalize in Python rather than the DB because we
    #    do not persist a normalized-name column — the set of suppliers is small
    #    (a single warehouse's vendor list), so an in-memory scan is fine.
    if normalized_name:
        for candidate in Supplier.objects.all():
            if normalize_supplier_name(candidate.name) == normalized_name:
                logger.info(
                    "supplier_match_name",
                    extra={
                        "supplier_id": candidate.pk,
                        "normalized_name": normalized_name,
                        "created_by": created_by,
                    },
                )
                return candidate, False

    # 3) No match — create a new supplier. A blank name still gets a readable
    #    placeholder so the receipt header and pickers never show an empty label.
    supplier = Supplier.objects.create(
        name=name or UNKNOWN_SUPPLIER_NAME,
        edrpou=edrpou_clean,
        is_active=True,
    )
    logger.info(
        "supplier_created",
        extra={
            "supplier_id": supplier.pk,
            "edrpou": edrpou_clean,
            "normalized_name": normalized_name,
            "created_by": created_by,
        },
    )
    return supplier, True
