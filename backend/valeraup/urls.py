"""Root URL configuration for the Valeraup project.

Wires together:

* ``/admin/`` — Django admin.
* ``/api/schema/`` — raw OpenAPI 3 schema (drf-spectacular).
* ``/api/docs/`` — Swagger UI rendered from that schema.
* ``/api/auth/`` — authentication routes (login, refresh, PIN).
* ``/api/`` — every domain app's routes, included from the app ``urls.py``.
* ``/media/`` — uploaded receipt photos / generated .xlsx, served by Django only
  in ``DEBUG`` with the local FileSystemStorage fallback (in production R2 or the
  web server serves media, so this route is not added).

Why include the apps individually rather than a single router: the apps own
non-trivial nested resources (receipt lines, line mapping) and bespoke action
endpoints, so each app declares its own URL patterns and we simply mount them
all under the ``/api/`` prefix. The auth app is mounted under ``/api/auth/`` to
match the contract paths (``/api/auth/login/`` etc.).
"""
from __future__ import annotations

from django.conf import settings
from django.conf.urls.static import static
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

# In development (DEBUG) with the local filesystem storage fallback, let Django
# serve uploaded media so receipt-photo thumbnails and generated .xlsx files are
# reachable at ``/media/...``. In production media lives on R2 (or is served by
# the web server / whitenoise), so this dev-only convenience is intentionally
# gated and never used to serve user uploads at scale.
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
