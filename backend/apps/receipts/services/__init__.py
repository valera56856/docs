"""Service layer for the receipts app.

Groups the non-trivial business logic for receipts so views and Celery tasks
stay thin. Currently exposes the Excel receipt builder.

Re-exporting :func:`build_receipt_xlsx` here lets callers write
``from apps.receipts.services import build_receipt_xlsx`` without caring about
the internal module layout.
"""

from __future__ import annotations

from apps.receipts.services.xlsx import build_receipt_xlsx

__all__ = ["build_receipt_xlsx"]
