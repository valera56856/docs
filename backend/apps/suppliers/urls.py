"""URL routes for the suppliers app.

Mounted under ``/api/`` by ``valeraup/urls.py``; the pattern here carries its own
``suppliers/`` segment so the full path is ``/api/suppliers/``.
"""

from __future__ import annotations

from django.urls import path

from .views import SupplierListView

app_name = "suppliers"

urlpatterns = [
    path("suppliers/", SupplierListView.as_view(), name="supplier-list"),
]
