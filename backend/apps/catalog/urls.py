"""URL routes for the catalog app.

Mounted under ``/api/`` by ``valeraup/urls.py``. Patterns carry their own
segments, producing:

* ``/api/products/search/``           to :class:`ProductSearchView`
* ``/api/sync/catalog/``              to :class:`CatalogSyncView`
* ``/api/settings/salesdrive/``       to :class:`SalesDriveSettingsView`
* ``/api/settings/salesdrive/test/``  to :class:`SalesDriveTestView`
"""

from __future__ import annotations

from django.urls import path

from .views import (
    CatalogSyncView,
    ProductSearchView,
    SalesDriveSettingsView,
    SalesDriveTestView,
)

app_name = "catalog"

urlpatterns = [
    path("products/search/", ProductSearchView.as_view(), name="product-search"),
    path("sync/catalog/", CatalogSyncView.as_view(), name="catalog-sync"),
    path(
        "settings/salesdrive/",
        SalesDriveSettingsView.as_view(),
        name="salesdrive-settings",
    ),
    path(
        "settings/salesdrive/test/",
        SalesDriveTestView.as_view(),
        name="salesdrive-settings-test",
    ),
]
