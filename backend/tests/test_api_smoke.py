"""API smoke tests for the Valeraup backend.

These are intentionally thin: they verify the API is wired up correctly without
exercising business logic. Specifically they assert:

* ``GET /api/schema/`` returns 200 (drf-spectacular generates the OpenAPI doc —
  this catches view/serializer wiring errors that break schema generation).
* ``GET /api/suppliers/`` requires authentication (anonymous → 401) and succeeds
  for an authenticated client (→ 200), proving the global
  ``IsAuthenticated`` default and SimpleJWT auth are both in effect.

Fixtures (``api_client``, ``auth_client``) come from ``backend/conftest.py``.
``@pytest.mark.django_db`` is applied where the request flows through auth (which
touches the user table).
"""
from __future__ import annotations

import pytest
from django.urls import reverse

# Endpoint paths under test. Kept as constants so a path change is a one-line fix.
SCHEMA_PATH = "/api/schema/"
SUPPLIERS_PATH = "/api/suppliers/"


@pytest.mark.django_db
def test_schema_endpoint_returns_200(api_client) -> None:
    """The OpenAPI schema endpoint renders successfully.

    drf-spectacular walks every registered view/serializer to build the schema,
    so a 200 here is a strong signal the whole API surface is importable and
    introspectable. The schema endpoint is configured public (no auth) so the
    PWA/tooling can fetch it.
    """
    response = api_client.get(SCHEMA_PATH)

    assert response.status_code == 200


@pytest.mark.django_db
def test_schema_endpoint_reverses_by_name(api_client) -> None:
    """The schema URL is registered under the ``"schema"`` name.

    Reversing by name (rather than hard-coding the path) confirms the Swagger UI
    view can find the schema it renders from.
    """
    response = api_client.get(reverse("schema"))

    assert response.status_code == 200


@pytest.mark.django_db
def test_suppliers_requires_authentication(api_client) -> None:
    """Anonymous access to the suppliers list is rejected with 401.

    This proves the global ``DEFAULT_PERMISSION_CLASSES = [IsAuthenticated]`` is
    enforced. SimpleJWT returns 401 (not 403) for a missing/invalid credential.
    """
    response = api_client.get(SUPPLIERS_PATH)

    assert response.status_code == 401


@pytest.mark.django_db
def test_suppliers_succeeds_when_authenticated(auth_client) -> None:
    """An authenticated client can list suppliers (HTTP 200).

    Pairs with the 401 test above to demonstrate the auth boundary opens for a
    valid JWT issued by the ``auth_client`` fixture.
    """
    response = auth_client.get(SUPPLIERS_PATH)

    assert response.status_code == 200
