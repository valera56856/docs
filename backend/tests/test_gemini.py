"""Tests for the Gemini OCR boundary parsing (``integrations.gemini``).

The auto-supplier feature changes the recognized contract from a bare line array
to one object ``{"supplier": {...}|None, "lines": [...]}``. These tests pin that
parsing behavior without touching the network:

* the **new object** shape is parsed into ``supplier`` + ``lines``;
* a **legacy bare array** is tolerated and wrapped as
  ``{"supplier": None, "lines": <array>}`` (rolling-deploy / prompt-iteration
  safety);
* Markdown code fences are stripped before decoding;
* malformed / non-dict elements are dropped, and a non-JSON body raises;
* the offline guard (no API key / no images) returns the
  ``{"supplier": None, "lines": []}`` sentinel.

The Gemini network call (``integrations.gemini._call_gemini``) is monkeypatched so
no SDK / HTTP is ever invoked — exactly the boundary CLAUDE.md §10 requires to be
mocked.
"""

from __future__ import annotations

import json

import pytest

from integrations import gemini


# ---------------------------------------------------------------------------
# _parse_response — new object shape
# ---------------------------------------------------------------------------
def test_parse_response_object_shape() -> None:
    """The new object is parsed into supplier + lines."""
    raw = json.dumps(
        {
            "supplier": {"name": "ТОВ Демо Постач", "edrpou": "12345678"},
            "lines": [
                {
                    "supplier_sku": "ABC-1",
                    "name": "Гель-лак",
                    "quantity": 12,
                    "price": 95.5,
                },
            ],
        }
    )

    data = gemini._parse_response(raw)

    assert data["supplier"] == {"name": "ТОВ Демо Постач", "edrpou": "12345678"}
    assert len(data["lines"]) == 1
    assert data["lines"][0]["supplier_sku"] == "ABC-1"


def test_parse_response_object_null_supplier() -> None:
    """A ``supplier: null`` in the object decodes to ``None``, lines preserved."""
    raw = json.dumps({"supplier": None, "lines": [{"supplier_sku": "X"}]})

    data = gemini._parse_response(raw)

    assert data["supplier"] is None
    assert data["lines"] == [{"supplier_sku": "X"}]


def test_parse_response_object_missing_keys() -> None:
    """Missing ``supplier`` / ``lines`` keys default to ``None`` / ``[]``."""
    data = gemini._parse_response(json.dumps({}))

    assert data["supplier"] is None
    assert data["lines"] == []


# ---------------------------------------------------------------------------
# _parse_response — legacy bare-array tolerance
# ---------------------------------------------------------------------------
def test_parse_response_legacy_array_is_wrapped() -> None:
    """A legacy bare line array is wrapped as ``{supplier: None, lines: [...]}``."""
    raw = json.dumps(
        [
            {"supplier_sku": "ABC-1", "name": "A", "quantity": 1, "price": 10},
            {"supplier_sku": "ABC-2", "name": "B", "quantity": 2, "price": 20},
        ]
    )

    data = gemini._parse_response(raw)

    assert data["supplier"] is None
    assert len(data["lines"]) == 2
    assert data["lines"][1]["supplier_sku"] == "ABC-2"


# ---------------------------------------------------------------------------
# _parse_response — robustness
# ---------------------------------------------------------------------------
def test_parse_response_strips_code_fences() -> None:
    """A fenced ```json object is unwrapped before decoding."""
    raw = '```json\n{"supplier": null, "lines": []}\n```'

    data = gemini._parse_response(raw)

    assert data == {"supplier": None, "lines": []}


def test_parse_response_drops_non_dict_lines() -> None:
    """Stray non-dict elements in ``lines`` are dropped, not fatal."""
    raw = json.dumps(
        {"supplier": None, "lines": [{"supplier_sku": "OK"}, "junk", 5, None]}
    )

    data = gemini._parse_response(raw)

    assert data["lines"] == [{"supplier_sku": "OK"}]


def test_parse_response_non_dict_supplier_becomes_none() -> None:
    """A non-dict ``supplier`` (e.g. a string) is coerced to ``None``."""
    raw = json.dumps({"supplier": "ТОВ Демо", "lines": []})

    data = gemini._parse_response(raw)

    assert data["supplier"] is None


def test_parse_response_rejects_non_json() -> None:
    """A non-JSON body raises (the caller retries / surfaces the error)."""
    with pytest.raises((ValueError, json.JSONDecodeError)):
        gemini._parse_response("totally not json")


def test_parse_response_rejects_scalar_json() -> None:
    """A JSON scalar (neither object nor array) is rejected with ``ValueError``."""
    with pytest.raises(ValueError):
        gemini._parse_response("42")


# ---------------------------------------------------------------------------
# recognize_invoice — offline guard + end-to-end parse with a mocked call
# ---------------------------------------------------------------------------
def test_recognize_invoice_offline_no_key(settings) -> None:
    """No API key → the offline sentinel, no network call."""
    settings.GEMINI_API_KEY = ""

    assert gemini.recognize_invoice([b"image-bytes"]) == {
        "supplier": None,
        "lines": [],
    }


def test_recognize_invoice_offline_no_images(settings) -> None:
    """No images → the offline sentinel even with a key set."""
    settings.GEMINI_API_KEY = "test-key"

    assert gemini.recognize_invoice([]) == {"supplier": None, "lines": []}


def test_recognize_invoice_parses_object(settings, monkeypatch) -> None:
    """With a key + mocked SDK call, the object response is parsed end-to-end."""
    settings.GEMINI_API_KEY = "test-key"

    def _fake_call(images: list[bytes], model: str) -> str:
        return json.dumps(
            {
                "supplier": {"name": "ТОВ Демо", "edrpou": "12345678"},
                "lines": [
                    {
                        "supplier_sku": "ABC-1",
                        "name": "Гель-лак",
                        "quantity": 3,
                        "price": 50,
                    }
                ],
            }
        )

    monkeypatch.setattr(gemini, "_call_gemini", _fake_call)

    data = gemini.recognize_invoice([b"image-bytes"])

    assert data["supplier"] == {"name": "ТОВ Демо", "edrpou": "12345678"}
    assert data["lines"][0]["supplier_sku"] == "ABC-1"


def test_recognize_invoice_tolerates_legacy_array(settings, monkeypatch) -> None:
    """A model still emitting a bare array is wrapped, not rejected."""
    settings.GEMINI_API_KEY = "test-key"

    monkeypatch.setattr(
        gemini,
        "_call_gemini",
        lambda images, model: json.dumps([{"supplier_sku": "ABC-1"}]),
    )

    data = gemini.recognize_invoice([b"image-bytes"])

    assert data["supplier"] is None
    assert data["lines"] == [{"supplier_sku": "ABC-1"}]


def test_recognize_invoice_retries_then_raises(settings, monkeypatch) -> None:
    """Persistent unparseable responses raise after exhausting all attempts."""
    settings.GEMINI_API_KEY = "test-key"
    # Skip the real exponential backoff so the test is instant.
    monkeypatch.setattr(gemini.time, "sleep", lambda *_a, **_k: None)
    calls = {"n": 0}

    def _bad(images: list[bytes], model: str) -> str:
        calls["n"] += 1
        return "not json"

    monkeypatch.setattr(gemini, "_call_gemini", _bad)

    with pytest.raises(ValueError):
        gemini.recognize_invoice([b"image-bytes"])
    assert calls["n"] == 4  # initial attempt + 3 retries (max_attempts)


def test_recognize_invoice_retries_transient_gemini_error(
    settings, monkeypatch
) -> None:
    """A transient Gemini 503 is retried with backoff and recovers next call."""
    from google.genai import errors as genai_errors

    settings.GEMINI_API_KEY = "test-key"
    monkeypatch.setattr(gemini.time, "sleep", lambda *_a, **_k: None)
    calls = {"n": 0}

    def _flaky(images: list[bytes], model: str) -> str:
        calls["n"] += 1
        if calls["n"] == 1:
            raise genai_errors.ServerError(
                503, {"error": {"message": "high demand"}}
            )
        return '{"supplier": null, "lines": [{"supplier_sku": "X"}]}'

    monkeypatch.setattr(gemini, "_call_gemini", _flaky)

    data = gemini.recognize_invoice([b"image-bytes"])
    assert calls["n"] == 2  # failed once, recovered on retry
    assert data["lines"] == [{"supplier_sku": "X"}]
