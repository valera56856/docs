"""URL routes for the mapping app.

Mounted under ``/api/`` by ``valeraup/urls.py``. Two mapping mutation surfaces
exist (see ``apps.mapping.views``): the receipt-line map action is nested under a
receipt line and routed by the receipts app, while the **admin
mappings-management API** lives here.

A DRF :class:`~rest_framework.routers.DefaultRouter` registers
:class:`~apps.mapping.views.ArticleMappingViewSet` under ``mappings``
(basename ``mapping``), producing:

* ``GET    /api/mappings/``        — list (filters ``?supplier``, ``?q``)
* ``POST   /api/mappings/``        — create / re-target
* ``PATCH  /api/mappings/{pk}/``   — partial update
* ``DELETE /api/mappings/{pk}/``   — delete

WHY a router (vs explicit ``path`` entries): the viewset exposes the standard
collection/detail action set, so the router gives stable, conventional URLs and
names with no hand-maintained boilerplate. The action endpoint stays in the
receipts app because its URL is genuinely nested and bespoke.
"""

from __future__ import annotations

from rest_framework.routers import DefaultRouter

from .views import ArticleMappingViewSet

app_name = "mapping"

router = DefaultRouter()
router.register(r"mappings", ArticleMappingViewSet, basename="mapping")

urlpatterns = router.urls
