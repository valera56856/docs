"""URL routes for the receipts app.

Mounted under ``/api/`` by ``valeraup/urls.py``. Patterns carry their own
``receipts/`` prefix, producing the contract paths:

* ``POST  /api/receipts/``                         to :class:`ReceiptCreateView`
* ``GET   /api/receipts/{id}/``                     to :class:`ReceiptDetailView`
* ``POST  /api/receipts/{id}/photos/``              to :class:`ReceiptPhotoUploadView`
* ``POST  /api/receipts/{id}/recognize/``           to :class:`ReceiptRecognizeView`
* ``POST  /api/receipts/{id}/generate-xlsx/``       to :class:`ReceiptGenerateXlsxView`
* ``PATCH /api/receipts/{id}/lines/{line_id}/``     to :class:`ReceiptLineUpdateView`
* ``POST  /api/receipts/{id}/lines/{line_id}/map/`` to :class:`ReceiptLineMapView`

Order matters: the more specific ``lines/<line_id>/map/`` pattern is declared
before the generic ``lines/<line_id>/`` so ``map`` is not swallowed as a line id.
"""

from __future__ import annotations

from django.urls import path

from .views import (
    ReceiptCreateView,
    ReceiptDetailView,
    ReceiptGenerateXlsxView,
    ReceiptLineMapView,
    ReceiptLineUpdateView,
    ReceiptPhotoUploadView,
    ReceiptRecognizeView,
)

app_name = "receipts"

urlpatterns = [
    path("receipts/", ReceiptCreateView.as_view(), name="receipt-create"),
    path("receipts/<int:pk>/", ReceiptDetailView.as_view(), name="receipt-detail"),
    path(
        "receipts/<int:pk>/photos/",
        ReceiptPhotoUploadView.as_view(),
        name="receipt-photo-upload",
    ),
    path(
        "receipts/<int:pk>/recognize/",
        ReceiptRecognizeView.as_view(),
        name="receipt-recognize",
    ),
    path(
        "receipts/<int:pk>/generate-xlsx/",
        ReceiptGenerateXlsxView.as_view(),
        name="receipt-generate-xlsx",
    ),
    # Specific (map) before generic (line update) so "map" is not read as a pk.
    path(
        "receipts/<int:pk>/lines/<int:line_id>/map/",
        ReceiptLineMapView.as_view(),
        name="receipt-line-map",
    ),
    path(
        "receipts/<int:pk>/lines/<int:line_id>/",
        ReceiptLineUpdateView.as_view(),
        name="receipt-line-update",
    ),
]
