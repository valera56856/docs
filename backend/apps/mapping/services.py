"""Mapping core: normalize, look up, and learn supplier-SKU → product links.

This is the heart of Valeraup's "map once, remember forever" behaviour. Three
functions:

* :func:`normalize_sku` — canonicalize a raw SKU string so cosmetic variants of
  the same code collide on one key.
* :func:`match_line` — resolve a (supplier, supplier_sku) pair to an
  :class:`~apps.catalog.models.OurProduct` via a remembered
  :class:`~apps.mapping.models.ArticleMapping`, returning an ``auto`` /
  ``unmapped`` status.
* :func:`remember_mapping` — persist a manual mapping (idempotently) and bump its
  ``times_used`` counter so the system learns.

WHY normalization matters:
    OCR and printed invoices introduce trivial formatting noise — leading or
    trailing whitespace, mixed case, and doubled spaces — that should NOT create
    a new, separate mapping. ``"abc 123 "``, ``"ABC  123"`` and ``"ABC 123"`` are
    the same article. Normalizing to a single canonical form lets the unique
    constraint ``(supplier, supplier_sku_normalized)`` enforce one mapping per
    real SKU, and lets auto-match find a previously-saved mapping even when the
    new OCR spacing/case differs.
"""

from __future__ import annotations

import logging

from django.db import transaction

from apps.catalog.models import OurProduct
from apps.mapping.models import ArticleMapping

logger = logging.getLogger(__name__)


def normalize_sku(raw: str) -> str:
    """Canonicalize a supplier SKU for storage and lookup.

    Normalization rules (and the WHY for each):

    * **Strip surrounding whitespace** — OCR and copy/paste routinely add leading
      or trailing spaces that carry no meaning.
    * **Uppercase** — supplier codes are case-insensitive in practice; ``abc-1``
      and ``ABC-1`` are the same article, so we fold case to avoid duplicate
      mappings.
    * **Collapse internal whitespace runs to a single space** — a doubled space
      from OCR (``"ABC  123"``) must match a single space (``"ABC 123"``).

    We deliberately do NOT strip punctuation or dashes: those are often
    significant parts of a supplier's article code (e.g. ``A-100`` vs ``A100``),
    so removing them could merge genuinely different products.

    Args:
        raw: The SKU exactly as recognized/printed (may be empty or messy).

    Returns:
        The normalized SKU. Returns an empty string for empty/whitespace input.
    """

    if not raw:
        return ""
    # ``str.split()`` with no args splits on any run of whitespace and drops
    # empty tokens, so joining with a single space both trims the ends and
    # collapses internal runs in one step.
    return " ".join(raw.split()).upper()


def match_line(supplier_id: int, supplier_sku: str) -> tuple[OurProduct | None, str]:
    """Resolve a supplier SKU to a catalog product via remembered mappings.

    Looks up an existing :class:`ArticleMapping` for this supplier and the
    normalized SKU. A hit is an automatic match; a miss is unmapped (the operator
    must map it manually, after which :func:`remember_mapping` records it).

    This function does NOT mutate state — it is a pure read. ``times_used`` is
    incremented only when a mapping is actually applied to a stored line, which
    is the caller's responsibility (see ``apps.receipts.tasks``), to keep the
    counter meaningful.

    Args:
        supplier_id: Primary key of the supplier whose SKU namespace to search.
        supplier_sku: The raw recognized SKU (will be normalized internally).

    Returns:
        A tuple ``(our_product, match_status)`` where ``match_status`` is
        :attr:`ArticleMapping.MATCH_AUTO` (``"auto"``) on a hit with the resolved
        :class:`OurProduct`, or ``"unmapped"`` with ``None`` on a miss.
    """

    normalized = normalize_sku(supplier_sku)
    if not normalized:
        logger.info(
            "mapping_match_empty_sku",
            extra={"supplier_id": supplier_id},
        )
        return None, "unmapped"

    mapping = (
        ArticleMapping.objects.select_related("our_product")
        .filter(supplier_id=supplier_id, supplier_sku_normalized=normalized)
        .first()
    )

    if mapping is None:
        logger.info(
            "mapping_match_miss",
            extra={"supplier_id": supplier_id, "normalized_sku": normalized},
        )
        return None, "unmapped"

    logger.info(
        "mapping_match_auto",
        extra={
            "supplier_id": supplier_id,
            "normalized_sku": normalized,
            "our_product_id": mapping.our_product_id,
            "mapping_id": mapping.pk,
        },
    )
    return mapping.our_product, ArticleMapping.MATCH_AUTO


def remember_mapping(
    supplier_id: int,
    supplier_sku: str,
    our_product_id: int,
    created_by: str = "",
) -> ArticleMapping:
    """Persist (or refresh) a manual supplier-SKU → product mapping.

    Idempotent on ``(supplier, normalized sku)``: the first manual map creates
    the row; subsequent confirmations of the same SKU update the target product
    if it changed (an operator correcting a mistake) and always increment
    ``times_used``.

    WHY ``get_or_create`` + explicit update rather than ``update_or_create``:
        We must increment ``times_used`` using the current value and only set
        ``created_by`` when the row is first created (it records the *original*
        author). That two-path logic is clearer than overloading
        ``update_or_create`` defaults.

    Args:
        supplier_id: Primary key of the supplier.
        supplier_sku: The raw SKU as recognized/printed; the normalized form is
            the lookup key, the raw form is stored for audit/display.
        our_product_id: Primary key of the :class:`OurProduct` to map to.
        created_by: Identifier (username/email) of the operator creating the
            mapping. Recorded only on first creation.

    Returns:
        The created or updated :class:`ArticleMapping`.
    """

    normalized = normalize_sku(supplier_sku)

    # A single transaction so the lookup, create, and counter bump are atomic;
    # ``select_for_update`` would be needed under heavy concurrency, but for this
    # single-operator workflow ``get_or_create`` inside ``atomic`` is sufficient
    # and the unique constraint protects against races.
    with transaction.atomic():
        mapping, created = ArticleMapping.objects.get_or_create(
            supplier_id=supplier_id,
            supplier_sku_normalized=normalized,
            defaults={
                "supplier_sku": supplier_sku,
                "our_product_id": our_product_id,
                "created_by": created_by,
                "times_used": 0,
            },
        )

        if not created:
            # Existing mapping: allow re-targeting (operator correction) and keep
            # the raw SKU fresh, but never overwrite the original ``created_by``.
            mapping.our_product_id = our_product_id
            mapping.supplier_sku = supplier_sku

        # Every confirmation counts as a use — it strengthens this mapping.
        mapping.times_used = (mapping.times_used or 0) + 1
        mapping.save(update_fields=["our_product", "supplier_sku", "times_used"])

    logger.info(
        "mapping_remembered",
        extra={
            "supplier_id": supplier_id,
            "normalized_sku": normalized,
            "our_product_id": our_product_id,
            "mapping_id": mapping.pk,
            "created": created,
            "times_used": mapping.times_used,
        },
    )
    return mapping
