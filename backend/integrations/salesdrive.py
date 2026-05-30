"""SalesDrive catalog integration (YML export).

SalesDrive exposes the product catalog as a YML "shop" file (the same Yandex
Market XML dialect used across Ru/Ua e-commerce). Valeraup mirrors that catalog
locally into :class:`~apps.catalog.models.OurProduct` so mapping search is fast
and works offline from the source.

This module is the boundary that fetches and parses that file. It does two
things only:

* :func:`fetch_catalog_yml` — download the raw YML bytes over HTTP.
* :func:`parse_catalog_yml` — turn ``shop > offers > offer`` elements into plain
  ``{salesdrive_id, sku, name}`` dicts.

The parser is hardened against real-world export variance:

* **XML namespaces** — some exports declare a default namespace, which makes
  ``ElementTree`` report every tag in Clark notation (``{ns}offer``). All tag
  matching goes through :func:`_local`, which compares the bare *local* name, so
  the same code parses namespaced and plain exports identically.
* **Missing fields** — an offer with no ``name`` or no SKU candidate still parses
  (empty strings) rather than crashing; only offers lacking a usable ``id`` (the
  upsert key) are skipped.
* **SKU resolution priority** — ``vendorCode`` > ``article`` > ``param``
  named "Артикул"/"SKU" > offer ``id`` attribute (see :func:`_offer_sku`).

The upsert into the database lives in :mod:`apps.catalog.services` so this module
stays free of Django ORM concerns and is trivially unit-testable with a fixture
file.

WHY ``defusedxml``-style hardening note: the YML comes from a trusted SalesDrive
account export, but XML parsing is still a classic injection surface. We use the
stdlib :mod:`xml.etree.ElementTree` and never resolve external entities (ET does
not by default), which is sufficient here.
"""

from __future__ import annotations

import logging
from typing import Any
from xml.etree import ElementTree as ET

import requests

logger = logging.getLogger(__name__)

# How long to wait for the SalesDrive export before giving up. The export can be
# large, so we allow a generous read timeout while keeping the connect timeout
# short to fail fast on a dead host.
_HTTP_TIMEOUT: tuple[int, int] = (10, 120)  # (connect, read) seconds


def fetch_catalog_yml(yml_url: str) -> bytes:
    """Download the SalesDrive catalog YML export.

    Args:
        yml_url: Fully-qualified URL of the SalesDrive YML export
            (Установки → Товари/Послуги → Експорт YML).

    Returns:
        The raw response body as bytes (XML/YML), ready for
        :func:`parse_catalog_yml`.

    Raises:
        ValueError: If ``yml_url`` is empty.
        requests.HTTPError: If the server returns a non-2xx status.
        requests.RequestException: On network/transport errors or timeout.
    """

    if not yml_url:
        raise ValueError("SALESDRIVE_YML_URL is not configured")

    logger.info("salesdrive_fetch_request", extra={"url": yml_url})
    response = requests.get(yml_url, timeout=_HTTP_TIMEOUT)
    response.raise_for_status()
    content = response.content
    logger.info(
        "salesdrive_fetch_result",
        extra={"url": yml_url, "bytes": len(content)},
    )
    return content


def _local(tag: str | None) -> str:
    """Return an XML tag's local name, stripping any ``{namespace}`` prefix.

    ``ElementTree`` reports namespaced tags in Clark notation
    (``{http://...}offer``). SalesDrive exports are sometimes plain and sometimes
    carry a default namespace, so every tag comparison must be namespace-agnostic.
    This helper collapses both forms to the bare local name (``offer``).

    Args:
        tag: A raw tag string from ``element.tag`` (may be ``None`` for comments
            or processing instructions).

    Returns:
        The local tag name in lower case, or an empty string for a non-element
        node. Lower-casing makes downstream comparisons case-insensitive.
    """

    if not tag:
        return ""
    # Clark notation: "{ns}local" → take the part after the closing brace.
    local = tag.rsplit("}", 1)[-1]
    return local.lower()


def _child_text(parent: ET.Element, name: str) -> str:
    """Return the stripped text of the first child whose local tag is ``name``.

    Namespace-tolerant replacement for ``parent.findtext(name)``: it matches on
    the local tag name (ignoring any XML namespace) and is case-insensitive, so a
    ``<vendorCode>`` works whether or not the export declares a default namespace.

    Args:
        parent: The element to scan the direct children of.
        name: The local child tag name to look for (compared case-insensitively).

    Returns:
        The first matching child's stripped text, or an empty string if there is
        no such child or it has no text.
    """

    wanted = name.lower()
    for child in parent:
        if _local(child.tag) == wanted and child.text and child.text.strip():
            return child.text.strip()
    return ""


def _offer_sku(offer: ET.Element) -> str:
    """Extract the SKU for a single ``<offer>`` element.

    SalesDrive does not have one canonical SKU tag across all exports, so we look
    in a fixed priority order at the places it commonly appears, falling back to
    the offer's ``id`` attribute as a last resort. The lookup is namespace- and
    case-tolerant so exports with a default XML namespace still resolve.

    Priority (highest first): ``vendorCode`` > ``article`` > a ``param`` named
    "Артикул"/"SKU"/"vendorCode" > the offer ``id`` attribute.

    Args:
        offer: An ``<offer>`` XML element.

    Returns:
        The first non-empty SKU candidate found, or an empty string.
    """

    vendor_code = _child_text(offer, "vendorCode")
    if vendor_code:
        return vendor_code

    article = _child_text(offer, "article")
    if article:
        return article

    # A param-based article: <param name="Артикул">A-100</param>. Match the param
    # name case-insensitively against the known aliases.
    for child in offer:
        if _local(child.tag) != "param":
            continue
        param_name = (child.get("name") or "").strip().lower()
        if param_name in {"артикул", "sku", "vendorcode"} and child.text:
            text = child.text.strip()
            if text:
                return text

    return (offer.get("id") or "").strip()


def parse_catalog_yml(yml_bytes: bytes) -> list[dict]:
    """Parse SalesDrive YML bytes into a list of product dicts.

    Walks ``yml_catalog > shop > offers > offer`` and produces one dict per
    offer. Offers without a usable ``id`` are skipped (an offer we cannot key on
    is useless as an upsert target).

    Args:
        yml_bytes: Raw YML/XML bytes (e.g. from :func:`fetch_catalog_yml`).

    Returns:
        A list of dicts shaped ``{"salesdrive_id": str, "sku": str,
        "name": str}``, ready to be upserted by
        :func:`apps.catalog.services.sync_catalog`.

    Raises:
        ValueError: If the bytes are not well-formed XML or contain no
            ``<offers>`` block.
    """

    try:
        root = ET.fromstring(yml_bytes)
    except ET.ParseError as exc:
        logger.error("salesdrive_parse_error", extra={"error": str(exc)})
        raise ValueError(f"Invalid SalesDrive YML: {exc}") from exc

    # The structure is yml_catalog/shop/offers/offer. ``iter()`` walks the whole
    # tree regardless of wrapper depth; we filter by *local* tag name so a default
    # XML namespace (which would otherwise prefix every tag) does not hide offers.
    offers = [el for el in root.iter() if _local(el.tag) == "offer"]
    if not offers:
        logger.warning("salesdrive_parse_no_offers")
        raise ValueError("SalesDrive YML contains no <offer> elements")

    products: list[dict[str, Any]] = []
    skipped = 0
    for offer in offers:
        salesdrive_id = (offer.get("id") or "").strip()
        if not salesdrive_id:
            # No stable key → cannot upsert deterministically; skip it.
            skipped += 1
            continue

        # ``name`` is namespace-tolerant too; tolerate a missing/empty name.
        name = _child_text(offer, "name")
        sku = _offer_sku(offer)

        products.append(
            {
                "salesdrive_id": salesdrive_id,
                "sku": sku,
                "name": name,
            }
        )

    logger.info(
        "salesdrive_parse_result",
        extra={"parsed": len(products), "skipped": skipped},
    )
    return products
