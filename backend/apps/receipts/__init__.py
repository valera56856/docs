"""Receipts domain app for Valeraup — the core workflow.

This app models the end-to-end receipt flow: a manager creates a
:class:`~apps.receipts.models.Receipt` for a supplier, attaches one or more
photographed invoice pages (:class:`~apps.receipts.models.ReceiptPhoto`), Gemini
OCR turns them into :class:`~apps.receipts.models.ReceiptLine` rows, mapping
resolves each line to a catalog product, and finally an ``.xlsx`` receipt is
generated for manual import into SalesDrive.

The :class:`Receipt.STATUS <apps.receipts.models.Receipt>` field drives the UI
state machine: ``draft → recognizing → needs_mapping → ready → xlsx_ready`` with
``error`` as a terminal failure state.
"""

from __future__ import annotations
