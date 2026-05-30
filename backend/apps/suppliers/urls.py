"""URL routes for the suppliers app.

Mounted under ``/api/`` by ``valeraup/urls.py``; the router registers the
``suppliers`` prefix here so the full contract paths are:

* ``GET/POST            /api/suppliers/``
* ``GET/PUT/PATCH/DELETE /api/suppliers/{pk}/``

A DRF :class:`~rest_framework.routers.DefaultRouter` generates these from
:class:`~apps.suppliers.views.SupplierViewSet`, so list/create and
retrieve/update/destroy stay in one place and the per-action permission split
(operators read, admins mutate) lives on the viewset.
"""

from __future__ import annotations

from rest_framework.routers import DefaultRouter

from .views import SupplierViewSet

app_name = "suppliers"

router = DefaultRouter()
router.register(r"suppliers", SupplierViewSet, basename="supplier")

urlpatterns = router.urls
