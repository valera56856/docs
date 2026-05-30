"""Views for the mapping app.

The contract's only mapping mutation —
``POST /api/receipts/{id}/lines/{line_id}/map/`` — is implemented in the receipts
app because its URL is nested under a receipt line (see
``apps.receipts.views.ReceiptLineMapView``). It calls
``apps.mapping.services.remember_mapping``.

This module is intentionally left without endpoints; it exists so the app package
is complete and ``apps.mapping.urls`` is importable from ``valeraup/urls.py``.
"""

from __future__ import annotations
