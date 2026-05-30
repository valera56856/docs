"""URL routes for the accounts (authentication) app.

Mounted under ``/api/auth/`` by ``valeraup/urls.py``, so the paths declared here
are relative to that prefix:

* ``login/``   to :class:`EmailTokenObtainPairView` (email + password to JWT)
* ``refresh/`` to SimpleJWT ``TokenRefreshView`` (refresh access to JWT)
* ``pin/``     to :class:`PinLoginView` (PIN to JWT)
* ``me/``      to :class:`MeView` (current profile summary)
"""

from __future__ import annotations

from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from .views import EmailTokenObtainPairView, MeView, PinLoginView

app_name = "accounts"

urlpatterns = [
    path("login/", EmailTokenObtainPairView.as_view(), name="login"),
    path("refresh/", TokenRefreshView.as_view(), name="refresh"),
    path("pin/", PinLoginView.as_view(), name="pin"),
    path("me/", MeView.as_view(), name="me"),
]
