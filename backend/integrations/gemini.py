"""Gemini 2.5 Flash Vision integration for supplier-invoice OCR.

This module is the single boundary between Valeraup and Google's Gemini API. It
sends one or more photographed invoice pages to the ``gemini-2.5-flash`` model
and returns a structured dict the receipts pipeline can turn into a detected
:class:`~apps.suppliers.models.Supplier` plus
:class:`~apps.receipts.models.ReceiptLine` rows.

The recognized shape is **one JSON object** (not a bare array)::

    {
      "supplier": {"name": <string|null>, "edrpou": <string|null>},
      "lines": [{"supplier_sku", "name", "quantity", "price"}, ...]
    }

Design decisions (the WHY):

* **One object, two payloads.** The auto-supplier feature needs both the vendor
  (read from the invoice header — постачальник/продавець name + ЄДРПОУ code) and
  the line items in a single OCR pass. Returning one object keeps that atomic:
  the supplier and its lines come from the *same* photographed invoice.
* **Strict JSON contract.** The model is instructed to return *only* the JSON
  object — no prose. ``supplier`` carries ``name``/``edrpou`` (each ``null`` when
  absent), and each line has the exact keys ``supplier_sku``, ``name``,
  ``quantity`` and ``price``. Missing fields are ``null`` so downstream code can
  distinguish "OCR could not read it" from "value is 0".
* **Legacy-array tolerance.** Earlier prompt versions returned a bare line array.
  To stay safe across a rolling deploy and prompt iterations, a top-level JSON
  *array* is accepted and wrapped as ``{"supplier": None, "lines": <array>}``.
* **Fence stripping.** LLMs frequently wrap JSON in Markdown code fences
  (```` ```json ... ``` ````) even when told not to. We strip those defensively
  before :func:`json.loads` rather than trusting the prompt alone.
* **One retry on parse failure.** A single malformed response is common and
  cheap to recover from by re-asking. We retry exactly once to avoid unbounded
  cost/latency, then surface a clear error.
* **Env-gated network call.** When ``GEMINI_API_KEY`` is unset (local/dev/CI),
  the SDK call is skipped and ``{"supplier": None, "lines": []}`` is returned, so
  the rest of the app — and the test suite — runs without network or secrets.

Structured JSON logging is emitted on the request and the result so OCR cost and
quality can be audited off-host.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from django.conf import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------
# The agreed system prompt. It is intentionally terse and imperative: the model
# tends to follow short, unambiguous instructions about output shape far more
# reliably than long descriptive ones. We pin the exact key names here because
# they are the contract consumed by ``recognize_receipt_task`` — the supplier
# (header) and the lines (table) in one object.
SYSTEM_PROMPT: str = (
    "Ти — система розпізнавання накладних постачальників. "
    "Тобі надсилають одне або кілька фото однієї накладної. "
    "Витягни ПОСТАЧАЛЬНИКА (із шапки накладної) та ВСІ позиції товарів.\n"
    "Поверни ВИКЛЮЧНО один валідний JSON-обʼєкт. "
    "Без пояснень, без markdown, без тексту до або після обʼєкта.\n"
    "Обʼєкт має рівно такі поля:\n"
    '  "supplier" — обʼєкт постачальника з полями:\n'
    '      "name" — назва постачальника / продавця / вантажовідправника (рядок),\n'
    '      "edrpou" — код ЄДРПОУ (8 цифр) або ІПН/РНОКПП для ФОП; рядок лише з цифр,\n'
    '  "lines" — масив позицій, де кожна позиція має рівно такі поля:\n'
    '      "supplier_sku" — артикул/код товару ПОСТАЧАЛЬНИКА (рядок). Шукай його у '
    "колонці з заголовком «Артикул», «Код», «Код товару», «Кат. №», "
    "«Артикул постачальника» або «SKU». Це алфавітно-цифровий код позиції, "
    "а НЕ порядковий номер рядка (№, № п/п) і не штрихкод. Якщо код у накладній "
    'є — обовʼязково витягни його; null лише коли колонки коду немає взагалі,\n'
    '      "name" — назва товару (рядок),\n'
    '      "quantity" — кількість (число),\n'
    '      "price" — ціна за одиницю / собівартість (число).\n'
    "Постачальника бери з шапки / реквізитів накладної (постачальник/продавець + ЄДРПОУ). "
    "Якщо якогось значення немає на накладній — постав null для цього поля "
    "(зокрема supplier.name або supplier.edrpou). "
    "НЕ вигадуй значення, яких немає на фото. "
    "Якщо позицій немає — постав порожній масив [] у полі \"lines\"."
)

# Matches an opening Markdown code fence with an optional language tag, e.g.
# ``` or ```json — and the closing fence. Used to unwrap fenced JSON.
_FENCE_RE = re.compile(r"^\s*```(?:json|JSON)?\s*|\s*```\s*$")


def _strip_code_fences(text: str) -> str:
    """Remove a surrounding Markdown code fence from a model response.

    Gemini frequently returns JSON wrapped in a ```` ```json ... ``` ```` block
    despite being told not to. Parsing must not depend on the model obeying that
    instruction, so we strip the fences defensively.

    Args:
        text: The raw text returned by the model.

    Returns:
        The text with a leading/trailing code fence removed and surrounding
        whitespace trimmed. If no fence is present the input is returned trimmed.
    """

    stripped = text.strip()
    if stripped.startswith("```"):
        # Remove the opening fence line and any trailing fence.
        stripped = _FENCE_RE.sub("", stripped)
        # A trailing fence on its own line may remain; drop it explicitly.
        if stripped.endswith("```"):
            stripped = stripped[: -len("```")]
    return stripped.strip()


def _clean_lines(rows: Any) -> list[dict[str, Any]]:
    """Keep only well-formed object rows from a decoded ``lines`` value.

    Args:
        rows: The decoded ``lines`` value (expected to be a list).

    Returns:
        A list of dicts; a non-list input yields ``[]`` and any non-dict element
        is dropped so a single stray element cannot poison the whole batch.
    """

    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict)]


def _clean_supplier(value: Any) -> dict[str, Any] | None:
    """Normalise the decoded ``supplier`` value to a dict or ``None``.

    The model is asked for ``{"name": ..., "edrpou": ...}``. We accept a dict and
    pass it through unchanged (downstream code reads ``.get('name')`` /
    ``.get('edrpou')``), and coerce anything else — ``null``, a string, a list —
    to ``None`` so the caller has a single "no supplier detected" sentinel.

    Args:
        value: The decoded ``supplier`` value from the model.

    Returns:
        The supplier dict if it is a dict, otherwise ``None``.
    """

    return value if isinstance(value, dict) else None


def _parse_response(text: str) -> dict[str, Any]:
    """Parse a Gemini text response into a ``{supplier, lines}`` dict.

    Tolerates two shapes for safety across prompt iterations / rolling deploys:

    * the **new object** ``{"supplier": {...}|null, "lines": [...]}``, and
    * a **legacy bare array** of line dicts, which is wrapped as
      ``{"supplier": None, "lines": <array>}``.

    Args:
        text: Raw response text from the model (may contain code fences).

    Returns:
        A dict with ``supplier`` (a dict or ``None``) and ``lines`` (a list of
        dicts).

    Raises:
        ValueError: If the response does not decode to a JSON object or array.
    """

    cleaned = _strip_code_fences(text)
    data = json.loads(cleaned)

    if isinstance(data, list):
        # Legacy shape: a bare array of line dicts, no supplier.
        return {"supplier": None, "lines": _clean_lines(data)}

    if isinstance(data, dict):
        return {
            "supplier": _clean_supplier(data.get("supplier")),
            "lines": _clean_lines(data.get("lines")),
        }

    raise ValueError(
        f"Gemini response decoded to {type(data).__name__}, "
        "expected a JSON object or array"
    )


def _call_gemini(images: list[bytes], model: str) -> str:
    """Send invoice images to Gemini and return the raw text response.

    Isolated from :func:`recognize_invoice` so the network boundary can be
    mocked in tests and so the retry logic stays readable.

    Args:
        images: Raw JPEG/PNG bytes, one entry per photographed invoice page.
        model: The Gemini model id to call (e.g. ``"gemini-2.5-flash"``).

    Returns:
        The concatenated text of the model's response.

    Raises:
        RuntimeError: If the ``google-genai`` SDK is not installed.
    """

    try:
        from google import genai
        from google.genai import types
    except ImportError as exc:  # pragma: no cover - depends on optional dep
        raise RuntimeError(
            "google-genai is not installed; cannot call Gemini"
        ) from exc

    client = genai.Client(api_key=settings.GEMINI_API_KEY)

    # Build the multimodal request: the system prompt followed by every page as
    # an inline image part. Most phone-camera invoice photos are JPEG; we tag
    # them as such for the SDK.
    parts: list[Any] = [SYSTEM_PROMPT]
    parts.extend(
        types.Part.from_bytes(data=image, mime_type="image/jpeg")
        for image in images
    )

    response = client.models.generate_content(model=model, contents=parts)
    return response.text or ""


def recognize_invoice(images: list[bytes], *, model: str | None = None) -> dict:
    """Recognise the supplier and line items from invoice pages via Gemini.

    Sends every page of a single supplier invoice to Gemini 2.5 Flash and returns
    the parsed ``{"supplier": {...}|None, "lines": [...]}`` dict. The supplier is
    read from the invoice header (постачальник/продавець name + ЄДРПОУ code) and
    feeds the auto-supplier detection; the lines feed
    :class:`~apps.receipts.models.ReceiptLine` creation and per-supplier mapping.

    The response is defensively unwrapped from any Markdown fences and
    JSON-decoded; both the new object shape **and** a legacy bare line-array are
    accepted (the array is wrapped as ``{"supplier": None, "lines": <array>}``).
    On a parse failure the call is retried exactly once before giving up.

    When ``settings.GEMINI_API_KEY`` is empty or there are no images
    (local/dev/CI without a key), the network call is skipped and the offline
    guard returns ``{"supplier": None, "lines": []}`` so the pipeline and tests
    run without secrets.

    Args:
        images: Raw image bytes, one entry per photographed invoice page. All
            pages are expected to belong to the *same* invoice.
        model: Optional model override; defaults to ``settings.GEMINI_MODEL``
            (``"gemini-2.5-flash"``).

    Returns:
        A dict with two keys:

        * ``supplier``: ``{"name": <str|None>, "edrpou": <str|None>}`` read from
          the invoice header, or ``None`` when no supplier was detected.
        * ``lines``: a list of dicts, each with keys ``supplier_sku``, ``name``,
          ``quantity`` and ``price`` (values may be ``None`` where OCR could not
          read them). Empty when there are no items.

        Both default to the offline sentinel ``{"supplier": None, "lines": []}``
        when there are no images, no API key, or nothing was recognized.

    Raises:
        ValueError: If Gemini returns a response that cannot be parsed as a JSON
            object or array even after one retry.
    """

    resolved_model = model or settings.GEMINI_MODEL

    if not images:
        logger.info(
            "gemini_recognize_skip",
            extra={"reason": "no_images", "model": resolved_model},
        )
        return {"supplier": None, "lines": []}

    if not settings.GEMINI_API_KEY:
        # Without a key we cannot (and must not) call out. Return the offline
        # sentinel so the task marks the receipt appropriately instead of crashing.
        logger.warning(
            "gemini_recognize_skip",
            extra={
                "reason": "no_api_key",
                "model": resolved_model,
                "image_count": len(images),
            },
        )
        return {"supplier": None, "lines": []}

    logger.info(
        "gemini_recognize_request",
        extra={"model": resolved_model, "image_count": len(images)},
    )

    last_error: Exception | None = None
    # Two attempts total: the initial call plus one retry. LLM JSON glitches are
    # usually transient, so a single re-ask recovers most of them cheaply.
    for attempt in range(2):
        try:
            raw = _call_gemini(images, resolved_model)
            data = _parse_response(raw)
            logger.info(
                "gemini_recognize_result",
                extra={
                    "model": resolved_model,
                    "image_count": len(images),
                    "line_count": len(data["lines"]),
                    # Record only WHETHER a supplier was detected — never the raw
                    # name/code in the result event (that lives in raw_ocr audit).
                    "supplier_detected": data["supplier"] is not None,
                    "attempt": attempt + 1,
                },
            )
            return data
        except (json.JSONDecodeError, ValueError) as exc:
            last_error = exc
            logger.warning(
                "gemini_recognize_parse_error",
                extra={
                    "model": resolved_model,
                    "attempt": attempt + 1,
                    "error": str(exc),
                },
            )

    # Both attempts failed to yield parseable JSON.
    logger.error(
        "gemini_recognize_failed",
        extra={"model": resolved_model, "error": str(last_error)},
    )
    raise ValueError(
        "Gemini returned an unparseable response after one retry"
    ) from last_error
