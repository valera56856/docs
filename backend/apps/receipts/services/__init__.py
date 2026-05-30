"""Service layer for the receipts app.

Groups the non-trivial business logic for receipts so views and Celery tasks
stay thin. Exposes:

* :func:`build_receipt_xlsx` — render matched lines into the SalesDrive-import
  ``.xlsx`` (with duplicate grouping + weighted-average price).
* :func:`recompute_receipt_status` / :func:`set_receipt_status` — the receipt
  status-machine helpers shared by the views and the OCR task.
* :func:`remap_receipt_lines` — re-resolve a receipt's existing lines against its
  current supplier's remembered mappings (used when a supplier is set/changed).

Re-exporting them here lets callers write
``from apps.receipts.services import build_receipt_xlsx`` (or the status / remap
helpers) without caring about the internal module layout.
"""

from __future__ import annotations

from apps.receipts.services.mapping import remap_receipt_lines
from apps.receipts.services.status import (
    recompute_receipt_status,
    set_receipt_status,
)
from apps.receipts.services.xlsx import build_receipt_xlsx

__all__ = [
    "build_receipt_xlsx",
    "recompute_receipt_status",
    "remap_receipt_lines",
    "set_receipt_status",
]
