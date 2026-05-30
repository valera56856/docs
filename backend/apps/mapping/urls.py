"""URL routes for the mapping app.

The single mapping mutation in the contract is nested under a receipt line
(``POST /api/receipts/{id}/lines/{line_id}/map/``) and is therefore routed by the
receipts app. This module declares an empty ``urlpatterns`` so that
``valeraup/urls.py`` can ``include("apps.mapping.urls")`` uniformly across apps
without a special case, and so new mapping-scoped routes have an obvious home.
"""

from __future__ import annotations

from django.urls import path  # noqa: F401  (kept for future mapping routes)

app_name = "mapping"

urlpatterns: list = []
