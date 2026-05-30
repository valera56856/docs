"""Excel (.xlsx) receipt generation for SalesDrive import.

Builds the ``.xlsx`` file a manager imports into SalesDrive via
``Склад → Надходження → Імпорт``. The output is intentionally minimal — exactly
the four columns SalesDrive's receipt importer needs:

==================  ==========================================================
Column header       Source
==================  ==========================================================
SKU/Артикул         ``line.matched_product.sku``
Назва               ``line.matched_product.name``
Кількість           ``line.quantity``
Ціна (собівартість) ``line.price`` (purchase cost)
==================  ==========================================================

WHY only matched lines are exported:
    An unmapped line has no ``matched_product`` and therefore no SalesDrive SKU
    to import against. Including it would produce a row SalesDrive cannot resolve.
    Such lines must be mapped first (the receipt only reaches ``ready`` once
    every line is matched), so here we defensively skip any that slipped through.

WHY ``DecimalField`` values are written as-is:
    openpyxl serializes ``Decimal`` to an exact numeric cell, preserving the
    quantity (3 dp) and price (2 dp) precision without float rounding.

NOTE: The exact header strings and column order must be verified against the
live SalesDrive import template before production use — see ``docs/INTEGRATIONS.md``.
The constants below are centralized so that verification is a one-line change.
"""

from __future__ import annotations

import logging
from io import BytesIO

from openpyxl import Workbook

logger = logging.getLogger(__name__)

# Sheet title and column headers, centralized so the SalesDrive-template
# verification step touches exactly one place. Order here defines column order.
SHEET_TITLE: str = "Надходження"
COLUMN_HEADERS: list[str] = [
    "SKU/Артикул",
    "Назва",
    "Кількість",
    "Ціна (собівартість)",
]


def build_receipt_xlsx(receipt) -> bytes:
    """Render a receipt's matched lines into a SalesDrive-import ``.xlsx``.

    Produces a single-sheet workbook with a header row followed by one row per
    matched line, in the four-column format SalesDrive's receipt importer
    expects. Unmatched lines (no ``matched_product``) are skipped because they
    have no SalesDrive SKU to import against.

    Args:
        receipt: A :class:`~apps.receipts.models.Receipt` instance. Its related
            ``lines`` are read; for efficiency the caller may pass a receipt with
            ``lines`` prefetched (``select_related("matched_product")``), but this
            function does not require it.

    Returns:
        The ``.xlsx`` file contents as bytes, ready to upload to storage (R2) or
        stream as an HTTP download.
    """

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = SHEET_TITLE

    # Header row.
    sheet.append(COLUMN_HEADERS)

    rows_written = 0
    skipped = 0
    # ``select_related`` here avoids an N+1 query when ``matched_product`` was not
    # prefetched by the caller; it is a no-op if it already was.
    for line in receipt.lines.select_related("matched_product").all():
        product = line.matched_product
        if product is None:
            # Unmapped line — cannot be imported into SalesDrive. Skip it; the
            # receipt should not have reached generation with unmapped lines.
            skipped += 1
            continue

        sheet.append(
            [
                product.sku,
                product.name,
                line.quantity,
                line.price,
            ]
        )
        rows_written += 1

    buffer = BytesIO()
    workbook.save(buffer)
    data = buffer.getvalue()

    logger.info(
        "receipt_xlsx_built",
        extra={
            "receipt_id": getattr(receipt, "pk", None),
            "rows_written": rows_written,
            "rows_skipped": skipped,
            "bytes": len(data),
        },
    )
    return data
