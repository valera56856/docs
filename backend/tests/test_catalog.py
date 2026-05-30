"""Behavior tests for the catalog app and the SalesDrive YML parser.

Covers three layers of the catalog refresh pipeline:

* :func:`integrations.salesdrive.parse_catalog_yml` — parses a small sample YML
  string, including the namespace-tolerant path and the SKU-resolution priority
  (vendorCode > article > param "Артикул" > offer id).
* :func:`apps.catalog.services.sync_catalog` — upserts ``OurProduct`` by
  ``salesdrive_id`` and is idempotent on re-run (no duplicates; in-place updates).
* ``GET /api/products/search/`` — searches by SKU or name.

The SalesDrive HTTP boundary is mocked (``monkeypatch`` on
``fetch_catalog_yml``); no test hits a live export.
"""

from __future__ import annotations

import pytest

from apps.catalog import services
from apps.catalog.models import OurProduct
from integrations import salesdrive
from integrations.salesdrive import parse_catalog_yml

# A plain (no-namespace) export exercising every SKU-resolution branch:
#   - offer 1: vendorCode wins
#   - offer 2: no vendorCode → <article> wins
#   - offer 3: no vendorCode/article → <param name="Артикул"> wins
#   - offer 4: nothing → falls back to the offer id attribute
SAMPLE_YML = """<?xml version="1.0" encoding="UTF-8"?>
<yml_catalog date="2024-01-01 00:00">
  <shop>
    <name>Demo</name>
    <offers>
      <offer id="1001">
        <name>Сорочка біла</name>
        <vendorCode>VC-1</vendorCode>
        <article>ART-IGNORED</article>
      </offer>
      <offer id="1002">
        <name>Штани сині</name>
        <article>ART-2</article>
      </offer>
      <offer id="1003">
        <name>Кашкет</name>
        <param name="Артикул">PAR-3</param>
      </offer>
      <offer id="1004">
        <name>Без артикулу</name>
      </offer>
    </offers>
  </shop>
</yml_catalog>
"""

# Same data but with a default XML namespace on every element — the kind of
# export that breaks a naive ``findtext('vendorCode')`` parser.
SAMPLE_YML_NAMESPACED = """<?xml version="1.0" encoding="UTF-8"?>
<yml_catalog xmlns="http://example.com/yml" date="2024-01-01 00:00">
  <shop>
    <offers>
      <offer id="2001">
        <name>NS Товар</name>
        <vendorCode>NS-VC-1</vendorCode>
      </offer>
    </offers>
  </shop>
</yml_catalog>
"""


# ---------------------------------------------------------------------------
# parse_catalog_yml — pure parsing, no DB
# ---------------------------------------------------------------------------
def test_parse_catalog_yml_extracts_offers_and_sku_priority() -> None:
    """Parsing yields one dict per offer with SKU chosen by priority order.

    Asserts each SKU-resolution branch: vendorCode beats a present article,
    article beats nothing, a "Артикул" param is used when both are absent, and the
    offer id is the final fallback.
    """
    products = parse_catalog_yml(SAMPLE_YML.encode("utf-8"))

    by_id = {p["salesdrive_id"]: p for p in products}
    assert set(by_id) == {"1001", "1002", "1003", "1004"}

    assert by_id["1001"]["sku"] == "VC-1"  # vendorCode wins over article
    assert by_id["1001"]["name"] == "Сорочка біла"
    assert by_id["1002"]["sku"] == "ART-2"  # article when no vendorCode
    assert by_id["1003"]["sku"] == "PAR-3"  # param "Артикул" fallback
    assert by_id["1004"]["sku"] == "1004"  # offer id as last resort


def test_parse_catalog_yml_tolerates_xml_namespace() -> None:
    """A default-namespaced export still parses offers and SKUs.

    This is the regression guard for exports that declare ``xmlns=...`` on the
    root: tag matching is by local name, so the namespace does not hide offers.
    """
    products = parse_catalog_yml(SAMPLE_YML_NAMESPACED.encode("utf-8"))

    assert len(products) == 1
    assert products[0]["salesdrive_id"] == "2001"
    assert products[0]["sku"] == "NS-VC-1"
    assert products[0]["name"] == "NS Товар"


def test_parse_catalog_yml_rejects_invalid_xml() -> None:
    """Malformed XML raises a ``ValueError`` (not a raw ParseError)."""
    with pytest.raises(ValueError):
        parse_catalog_yml(b"<not><closed>")


def test_parse_catalog_yml_raises_without_offers() -> None:
    """A well-formed document with no offers raises a clear ``ValueError``."""
    empty = b"<yml_catalog><shop><offers></offers></shop></yml_catalog>"
    with pytest.raises(ValueError):
        parse_catalog_yml(empty)


# ---------------------------------------------------------------------------
# sync_catalog — upsert + idempotency
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_sync_catalog_upserts_products(monkeypatch) -> None:
    """A first sync creates one ``OurProduct`` per offer.

    The SalesDrive fetch is stubbed to return the sample YML so the test stays
    offline; ``sync_catalog`` then parses and upserts each offer.
    """
    monkeypatch.setattr(
        salesdrive, "fetch_catalog_yml", lambda url: SAMPLE_YML.encode("utf-8")
    )

    count = services.sync_catalog("https://example.com/yml")

    assert count == 4
    assert OurProduct.objects.count() == 4
    assert OurProduct.objects.get(salesdrive_id="1001").sku == "VC-1"


@pytest.mark.django_db
def test_sync_catalog_is_idempotent(monkeypatch) -> None:
    """Re-syncing the same YML updates in place — no duplicate rows.

    The upsert keys on ``salesdrive_id``, so running the sync twice converges to
    the same four rows rather than inserting eight.
    """
    monkeypatch.setattr(
        salesdrive, "fetch_catalog_yml", lambda url: SAMPLE_YML.encode("utf-8")
    )

    services.sync_catalog("https://example.com/yml")
    services.sync_catalog("https://example.com/yml")

    assert OurProduct.objects.count() == 4


@pytest.mark.django_db
def test_sync_catalog_updates_changed_fields(monkeypatch) -> None:
    """A changed name/SKU in the YML is written over the existing row.

    Proves the upsert *updates* (not just ignores) when the source changes — the
    whole point of a cache refresh.
    """
    monkeypatch.setattr(
        salesdrive, "fetch_catalog_yml", lambda url: SAMPLE_YML.encode("utf-8")
    )
    services.sync_catalog("https://example.com/yml")

    changed = SAMPLE_YML.replace("Сорочка біла", "Сорочка оновлена")
    monkeypatch.setattr(
        salesdrive, "fetch_catalog_yml", lambda url: changed.encode("utf-8")
    )
    services.sync_catalog("https://example.com/yml")

    assert OurProduct.objects.get(salesdrive_id="1001").name == "Сорочка оновлена"
    assert OurProduct.objects.count() == 4


@pytest.mark.django_db
def test_sync_catalog_without_url_raises(settings) -> None:
    """With no URL argument and no setting, the sync raises ``ValueError``."""
    settings.SALESDRIVE_YML_URL = ""
    with pytest.raises(ValueError):
        services.sync_catalog("")


# ---------------------------------------------------------------------------
# product search endpoint
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_product_search_by_sku_and_name(auth_client) -> None:
    """Search matches on both SKU and name, case-insensitively.

    The mapping dropdown depends on this: typing part of a SKU *or* part of a name
    should surface the product.
    """
    OurProduct.objects.create(salesdrive_id="SD-1", sku="ABC-100", name="Сорочка")
    OurProduct.objects.create(salesdrive_id="SD-2", sku="XYZ-200", name="Штани")

    by_sku = auth_client.get("/api/products/search/?q=abc")
    assert by_sku.status_code == 200
    assert [p["sku"] for p in by_sku.data] == ["ABC-100"]

    by_name = auth_client.get("/api/products/search/?q=штани")
    assert [p["sku"] for p in by_name.data] == ["XYZ-200"]


@pytest.mark.django_db
def test_product_search_empty_query_returns_empty(auth_client) -> None:
    """A blank query returns an empty list (dropdown shows nothing until typing)."""
    OurProduct.objects.create(salesdrive_id="SD-1", sku="ABC-100", name="Сорочка")

    response = auth_client.get("/api/products/search/?q=")
    assert response.status_code == 200
    assert response.data == []


@pytest.mark.django_db
def test_product_search_requires_authentication(api_client) -> None:
    """Anonymous product search is rejected with 401."""
    response = api_client.get("/api/products/search/?q=abc")
    assert response.status_code == 401
