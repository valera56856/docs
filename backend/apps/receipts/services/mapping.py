"""Re-run per-supplier mapping over a receipt's existing lines.

The scan-first flow can create lines *before* a supplier is known (OCR found no
header, or detection failed). When a supplier is later attached — by
auto-detection or by the operator via ``PATCH /api/receipts/{id}/`` — the
already-stored lines must be re-resolved against that supplier's remembered
:class:`~apps.mapping.models.ArticleMapping` rows. This module owns that
re-mapping so the view and any future caller share one implementation.

WHY this lives in ``receipts.services`` and not ``mapping.services``:
    ``mapping.services`` operates on the *mapping* primitives (normalize, match,
    remember) and knows nothing about :class:`~apps.receipts.models.ReceiptLine`.
    Walking a receipt's lines and writing ``matched_product`` / ``match_status``
    back is receipt-flow orchestration, so it belongs with the receipt status
    machine — the same place the OCR task's line-build logic conceptually lives.
"""

from __future__ import annotations

import logging

from django.db import transaction
from django.db.models import F

from apps.mapping.models import ArticleMapping
from apps.mapping.services import match_line, normalize_sku
from apps.receipts.models import Receipt

logger = logging.getLogger(__name__)


def remap_receipt_lines(receipt: Receipt) -> int:
    """Re-resolve every line of a receipt against its current supplier's mappings.

    For each existing :class:`~apps.receipts.models.ReceiptLine`, calls
    :func:`apps.mapping.services.match_line` under ``receipt.supplier_id`` and
    writes the result back:

    * an auto-match points the line at the product with ``match_status="auto"``
      and bumps that mapping's ``times_used`` (an ``F`` expression avoids a
      read-modify-write race when lines share a mapping);
    * a miss clears the line to ``matched_product=None`` /
      ``match_status="unmapped"``.

    Lines that were *manually* mapped (``match_status="manual"``) are left
    untouched: the operator's explicit choice outranks an automatic re-resolve.

    When the receipt has no supplier this is a no-op (there is no SKU namespace to
    search) — every line simply stays unmapped.

    Idempotent: running it twice with the same supplier produces the same line
    states; the only cumulative effect is the ``times_used`` bump per auto-match,
    which is the intended "this mapping was used again" signal.

    Args:
        receipt: The receipt whose lines to re-map. Its supplier is read from
            ``receipt.supplier_id``.

    Returns:
        The number of lines that resolved to an automatic match in this pass.
    """

    if receipt.supplier_id is None:
        logger.info(
            "receipt_remap_skip_no_supplier",
            extra={"receipt_id": receipt.pk},
        )
        return 0

    auto_matched = 0
    with transaction.atomic():
        for line in receipt.lines.all():
            if line.match_status == ArticleMapping.MATCH_MANUAL:
                # Respect a deliberate operator mapping; do not auto-overwrite it.
                continue

            product, status = match_line(
                receipt.supplier_id, line.recognized_sku
            )

            if status == ArticleMapping.MATCH_AUTO and product is not None:
                line.matched_product = product
                line.match_status = ArticleMapping.MATCH_AUTO
                auto_matched += 1
                # Count the use so the most-relied-upon mappings surface later.
                ArticleMapping.objects.filter(
                    supplier_id=receipt.supplier_id,
                    supplier_sku_normalized=normalize_sku(line.recognized_sku),
                ).update(times_used=F("times_used") + 1)
            else:
                line.matched_product = None
                line.match_status = "unmapped"

            line.save(update_fields=["matched_product", "match_status"])

    logger.info(
        "receipt_remapped",
        extra={
            "receipt_id": receipt.pk,
            "supplier_id": receipt.supplier_id,
            "auto_matched": auto_matched,
        },
    )
    return auto_matched
