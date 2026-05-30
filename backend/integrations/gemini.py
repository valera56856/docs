"""Gemini 2.5 Flash Vision integration for supplier-invoice OCR.

This module is the single boundary between Valeraup and Google's Gemini API. It
sends one or more photographed invoice pages to the ``gemini-2.5-flash`` model
and returns a list of structured line-item dicts that the receipts pipeline can
turn into :class:`~apps.receipts.models.ReceiptLine` rows.

Design decisions (the WHY):

* **Strict JSON contract.** The model is instructed to return *only* a JSON
  array of objects with the exact keys ``supplier_sku``, ``name``, ``quantity``
  and ``price``. We do not let the model prose-explain; structured output is the
  only thing the rest of the system can act on. Missing fields are ``null`` so
  downstream code can distinguish "OCR could not read it" from "value is 0".
* **Fence stripping.** LLMs frequently wrap JSON in Markdown code fences
  (```` ```json ... ``` ````) even when told not to. We strip those defensively
  before :func:`json.loads` rather than trusting the prompt alone.
* **One retry on parse failure.** A single malformed response is common and
  cheap to recover from by re-asking. We retry exactly once to avoid unbounded
  cost/latency, then surface a clear error.
* **Env-gated network call.** When ``GEMINI_API_KEY`` is unset (local/dev/CI),
  the SDK call is skipped and an empty list is returned, so the rest of the app
  — and the test suite — runs without network access or secrets.

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
# reliably than long descriptive ones. We pin the four field names here because
# they are the contract consumed by ``recognize_receipt_task``.
SYSTEM_PROMPT: str = (
    "Ти — система розпізнавання накладних постачальників. "
    "Тобі надсилають одне або кілька фото однієї накладної. "
    "Витягни ВСІ позиції товарів.\n"
    "Поверни ВИКЛЮЧНО валідний JSON-масив об'єктів. "
    "Без пояснень, без markdown, без тексту до або після масиву.\n"
    "Кожен об'єкт має рівно такі поля:\n"
    '  "supplier_sku" — артикул/код товару постачальника (рядок),\n'
    '  "name" — назва товару (рядок),\n'
    '  "quantity" — кількість (число),\n'
    '  "price" — ціна за одиницю / собівартість (число).\n'
    "Якщо якогось значення немає на накладній — постав null для цього поля. "
    "НЕ вигадуй значення, яких немає на фото. "
    "Якщо позицій немає — поверни порожній масив []."
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


def _parse_response(text: str) -> list[dict[str, Any]]:
    """Parse a Gemini text response into a list of line-item dicts.

    Args:
        text: Raw response text from the model (may contain code fences).

    Returns:
        The decoded JSON array as a list of dicts.

    Raises:
        ValueError: If the response does not decode to a JSON list.
    """

    cleaned = _strip_code_fences(text)
    data = json.loads(cleaned)
    if not isinstance(data, list):
        raise ValueError(
            f"Gemini response decoded to {type(data).__name__}, expected a JSON array"
        )
    # Keep only well-formed object rows; skip anything that is not a dict so a
    # single stray element cannot poison the whole batch.
    return [row for row in data if isinstance(row, dict)]


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


def recognize_invoice(images: list[bytes], *, model: str | None = None) -> list[dict]:
    """Recognise invoice line items from photographed pages via Gemini Vision.

    Sends every page of a single supplier invoice to Gemini 2.5 Flash and
    returns the parsed line-item dicts. The response is defensively unwrapped
    from any Markdown fences and JSON-decoded; on a parse failure the call is
    retried exactly once before giving up.

    When ``settings.GEMINI_API_KEY`` is empty (local/dev/CI without a key) the
    network call is skipped and an empty list is returned, so the pipeline and
    tests run without secrets.

    Args:
        images: Raw image bytes, one entry per photographed invoice page. All
            pages are expected to belong to the *same* invoice.
        model: Optional model override; defaults to ``settings.GEMINI_MODEL``
            (``"gemini-2.5-flash"``).

    Returns:
        A list of dicts, each with keys ``supplier_sku``, ``name``,
        ``quantity`` and ``price`` (values may be ``None`` where OCR could not
        read them). Empty when there are no images, no API key, or no items.

    Raises:
        ValueError: If Gemini returns a response that cannot be parsed as a JSON
            array even after one retry.
    """

    resolved_model = model or settings.GEMINI_MODEL

    if not images:
        logger.info(
            "gemini_recognize_skip",
            extra={"reason": "no_images", "model": resolved_model},
        )
        return []

    if not settings.GEMINI_API_KEY:
        # Without a key we cannot (and must not) call out. Return empty so the
        # task marks the receipt appropriately instead of crashing.
        logger.warning(
            "gemini_recognize_skip",
            extra={
                "reason": "no_api_key",
                "model": resolved_model,
                "image_count": len(images),
            },
        )
        return []

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
            lines = _parse_response(raw)
            logger.info(
                "gemini_recognize_result",
                extra={
                    "model": resolved_model,
                    "image_count": len(images),
                    "line_count": len(lines),
                    "attempt": attempt + 1,
                },
            )
            return lines
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
