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

WHY duplicate lines are grouped by product:
    OCR can split one catalog product across several invoice lines (a multi-page
    invoice, or the same article listed twice), and two different supplier SKUs
    can map to the same ``OurProduct``. SalesDrive's receipt importer expects one
    row per product, so we **group by ``matched_product`` and SUM the
    quantities**. For the price of a merged row we use the **quantity-weighted
    average** of the duplicates' prices — i.e. ``Σ(qty·price) / Σ(qty)`` — so the
    total receipt cost (``Σ qty·price``) is preserved exactly through the merge.

    OPEN QUESTION (ТЗ §16): the business may instead prefer *last* price (the most
    recent purchase) or *min* price (most conservative cost). Weighted average is
    the cost-preserving default; if the SalesDrive workflow dictates otherwise,
    change :func:`_weighted_price` and update ``docs/INTEGRATIONS.md`` + the tests
    together. # TODO(ТЗ §16): confirm desired price-merge rule with the business.

NOTE: The exact header strings and column order must be verified against the
live SalesDrive import template before production use — see ``docs/INTEGRATIONS.md``.
The constants below are centralized so that verification is a one-line change.
"""

from __future__ import annotations

import logging
from decimal import ROUND_HALF_UP, Decimal
from io import BytesIO

from openpyxl import Workbook

logger = logging.getLogger(__name__)

# Quantization targets matching the model's ``DecimalField`` precision: quantity
# is exact to 3 dp, price/cost to 2 dp. Applied to merged results so summed
# quantities and weighted-average prices never carry spurious extra digits.
_QTY_QUANT = Decimal("0.001")
_PRICE_QUANT = Decimal("0.01")

# Sheet title and column headers, centralized so the SalesDrive-template
# verification step touches exactly one place. Order here defines column order.
SHEET_TITLE: str = "Надходження"
COLUMN_HEADERS: list[str] = [
    "SKU/Артикул",
    "Назва",
    "Кількість",
    "Ціна (собівартість)",
]


def _weighted_price(
    total_qty: Decimal, weighted_sum: Decimal, fallback_count: int, simple_sum: Decimal
) -> Decimal | None:
    """Compute the quantity-weighted average price for a merged product row.

    The weighted average ``Σ(qty·price) / Σ(qty)`` preserves total cost across a
    merge (see the module docstring's ТЗ §16 note). Two edge cases are handled so
    a degenerate input never crashes the export:

    * **Zero total quantity** (every duplicate had qty 0): there is no weight to
      divide by, so fall back to the plain arithmetic mean of the available
      prices, or ``None`` if none had a price.
    * **No priced duplicates at all**: return ``None`` (OCR never read a price);
      the cell is left blank for the operator to fill in SalesDrive.

    Args:
        total_qty: Sum of the duplicates' quantities (the divisor).
        weighted_sum: Sum of ``qty·price`` over duplicates that had a price.
        fallback_count: Count of duplicates that had a price (for the mean).
        simple_sum: Sum of the raw prices over priced duplicates (for the mean).

    Returns:
        The merged price as a 2-dp :class:`Decimal`, or ``None`` if no duplicate
        carried a price.
    """

    if fallback_count == 0:
        return None
    if total_qty > 0:
        price = weighted_sum / total_qty
    else:
        # No quantity weight available — fall back to the simple mean so a
        # zero-qty row still carries a sensible cost.
        price = simple_sum / Decimal(fallback_count)
    return price.quantize(_PRICE_QUANT, rounding=ROUND_HALF_UP)


def build_receipt_xlsx(receipt) -> bytes:
    """Render a receipt's matched lines into a SalesDrive-import ``.xlsx``.

    Produces a single-sheet workbook with a header row followed by **one row per
    distinct matched product**, in the four-column format SalesDrive's receipt
    importer expects. Lines that resolved to the *same* product are grouped: their
    quantities are summed and their prices combined into a quantity-weighted
    average (``Σ(qty·price) / Σ(qty)``), so a product split across several OCR
    lines imports as a single, cost-correct row (see the module docstring and the
    ТЗ §16 open question on the price-merge rule).

    Unmatched lines (no ``matched_product``) are skipped because they have no
    SalesDrive SKU to import against.

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

    # Accumulate per-product totals. Keyed by product pk; insertion order is
    # preserved (dict ordering) so rows appear in first-seen order — stable and
    # predictable for the operator reviewing the file.
    groups: dict[int, dict] = {}
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

        qty = line.quantity if line.quantity is not None else Decimal("0")
        bucket = groups.setdefault(
            product.pk,
            {
                "sku": product.sku,
                "name": product.name,
                "total_qty": Decimal("0"),
                "weighted_sum": Decimal("0"),  # Σ(qty·price) over priced lines
                "simple_sum": Decimal("0"),  # Σ(price) over priced lines
                "priced_count": 0,
            },
        )
        bucket["total_qty"] += qty
        if line.price is not None:
            bucket["weighted_sum"] += qty * line.price
            bucket["simple_sum"] += line.price
            bucket["priced_count"] += 1

    rows_written = 0
    for bucket in groups.values():
        total_qty = bucket["total_qty"].quantize(_QTY_QUANT, rounding=ROUND_HALF_UP)
        price = _weighted_price(
            bucket["total_qty"],
            bucket["weighted_sum"],
            bucket["priced_count"],
            bucket["simple_sum"],
        )
        sheet.append([bucket["sku"], bucket["name"], total_qty, price])
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
