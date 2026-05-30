"""Root URL configuration for the Valeraup project.

Wires together:

* ``/admin/`` — Django admin.
* ``/api/schema/`` — raw OpenAPI 3 schema (drf-spectacular).
* ``/api/docs/`` — Swagger UI rendered from that schema.
* ``/api/auth/`` — authentication routes (login, refresh, PIN).
* ``/api/`` — every domain app's routes, included from the app ``urls.py``.

Why include the apps individually rather than a single router: the apps own
non-trivial nested resources (receipt lines, line mapping) and bespoke action
endpoints, so each app declares its own URL patterns and we simply mount them
all under the ``/api/`` prefix. The auth app is mounted under ``/api/auth/`` to
match the contract paths (``/api/auth/login/`` etc.).
"""
from __future__ import annotations

from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularSwaggerView,
)

urlpatterns = [
    # --- Admin --------------------------------------------------------------
    path("admin/", admin.site.urls),
    # --- API documentation --------------------------------------------------
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path(
        "api/docs/",
        SpectacularSwaggerView.as_view(url_name="schema"),
        name="swagger-ui",
    ),
    # --- Authentication -----------------------------------------------------
    path("api/auth/", include("apps.accounts.urls")),
    # --- Domain apps --------------------------------------------------------
    # Each app declares routes already prefixed with its resource segment
    # (e.g. ``suppliers/``, ``receipts/``), so a single ``api/`` prefix is enough.
    path("api/", include("apps.suppliers.urls")),
    path("api/", include("apps.catalog.urls")),
    path("api/", include("apps.mapping.urls")),
    path("api/", include("apps.receipts.urls")),
]
