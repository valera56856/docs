"""Celery tasks for the receipts app.

Hosts :func:`recognize_receipt_task`, the asynchronous OCR + mapping step
triggered by ``POST /api/receipts/{id}/recognize/``. It runs off the request
cycle because Gemini Vision calls take seconds and must not block the API.

Pipeline performed by the task:

1. Load the receipt and its photos; mark it ``recognizing``.
2. Send the photos to Gemini (:func:`integrations.gemini.recognize_invoice`),
   which returns ``{"supplier": {...}|None, "lines": [...]}``.
3. **Auto-detect the supplier.** If the receipt has no supplier yet and OCR read
   a supplier (a name or ЄДРПОУ), resolve it via
   :func:`apps.suppliers.services.match_or_create_supplier` and attach it. Always
   store the raw OCR supplier dict on ``receipt.recognized_supplier`` for audit.
4. Create one :class:`~apps.receipts.models.ReceiptLine` per recognized item,
   storing the raw OCR JSON for audit.
5. Auto-match each line against remembered mappings — but only when the receipt
   has a supplier (mapping is per-supplier). With no supplier the lines are left
   unmapped and the receipt settles at ``needs_mapping`` (the operator picks a
   supplier, which re-runs mapping). On hits, bump ``times_used``.
6. Set the receipt's final status: ``ready`` if every line matched,
   ``needs_mapping`` if any line is unmapped / no supplier, or ``error`` on
   failure.

WHY idempotency:
    Celery may redeliver a task (worker crash, retry). Re-running OCR for a
    receipt that already has lines would duplicate them, so the task deletes any
    prior lines for the receipt before recreating them. Supplier auto-detection
    is idempotent too: ``match_or_create_supplier`` returns the *same* supplier on
    a re-run (it matches the row it created), and we only auto-set the supplier
    when one is not already attached, so a re-run never clobbers an operator's
    manual supplier choice. This makes a re-run converge rather than compounding.
"""

from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation
from typing import Any

from celery import shared_task
from django.db import transaction

from apps.mapping.models import ArticleMapping
from apps.mapping.services import match_line
from apps.receipts.models import Receipt, ReceiptLine
from apps.receipts.services.status import recompute_receipt_status
from apps.suppliers.services import match_or_create_supplier
from integrations import gemini

logger = logging.getLogger(__name__)


def _to_decimal(value: Any, *, default: Decimal | None) -> Decimal | None:
    """Coerce an OCR JSON value to ``Decimal``, tolerating messy input.

    Gemini may return numbers, numeric strings (possibly with a comma decimal
    separator, common on Ukrainian invoices), or ``null``. We normalise all of
    these to a ``Decimal`` so they store cleanly in the model's ``DecimalField``.

    Args:
        value: The raw value from the OCR JSON (number, string, or ``None``).
        default: What to return when ``value`` is missing/unparseable —
            ``Decimal("0")`` for quantity, ``None`` for price.

    Returns:
        The parsed :class:`Decimal`, or ``default`` if the value is absent or
        cannot be parsed.
    """

    if value is None:
        return default
    try:
        # Normalise comma decimal separators ("12,5" → "12.5") before parsing.
        text = str(value).strip().replace(",", ".")
        if not text:
            return default
        return Decimal(text)
    except (InvalidOperation, ValueError, TypeError):
        return default


@shared_task(name="apps.receipts.tasks.recognize_receipt_task")
def recognize_receipt_task(receipt_id: int) -> None:
    """Run Gemini OCR and auto-mapping for a receipt (Celery task).

    Idempotent: any existing lines for the receipt are cleared before new ones
    are created, so a redelivered task converges instead of duplicating rows.

    On any unhandled error the receipt is moved to ``error`` so the UI can show a
    retry affordance rather than hanging in ``recognizing``.

    Args:
        receipt_id: Primary key of the :class:`~apps.receipts.models.Receipt`
            to process.

    Returns:
        ``None``. Side effects: creates ``ReceiptLine`` rows, increments
        ``ArticleMapping.times_used`` for auto-matched lines, and advances
        ``Receipt.status``.
    """

    logger.info("receipt_recognize_start", extra={"receipt_id": receipt_id})

    try:
        receipt = Receipt.objects.get(pk=receipt_id)
    except Receipt.DoesNotExist:
        # Nothing to do; log and return rather than raise so a stale task does
        # not retry forever.
        logger.error(
            "receipt_recognize_missing", extra={"receipt_id": receipt_id}
        )
        return

    # Mark in-progress immediately so the UI reflects the running OCR.
    receipt.status = "recognizing"
    receipt.save(update_fields=["status"])

    try:
        # Gather the photographed pages by reading their bytes back from storage
        # (Cloudflare R2 in prod, local MEDIA_ROOT in dev) via ``photo.image``.
        # When no readable image is available, ``recognize_invoice`` short-circuits
        # to the offline sentinel, keeping the pipeline runnable without
        # storage/credentials.
        images: list[bytes] = _load_photo_bytes(receipt)

        # New OCR contract: a single object {"supplier": {...}|None, "lines": [...]}.
        data = gemini.recognize_invoice(images)
        ocr_lines = data["lines"]
        ocr_supplier = data.get("supplier")

        unmapped_count = 0
        with transaction.atomic():
            # --- Auto-detect the supplier (scan-first flow) ----------------
            # Only auto-set the supplier when the receipt does not already have
            # one (never clobber an operator's manual choice on a re-run) and OCR
            # actually read a supplier name or ЄДРПОУ. ``match_or_create_supplier``
            # is idempotent, so a redelivered task resolves to the same row.
            if receipt.supplier_id is None and ocr_supplier and (
                ocr_supplier.get("name") or ocr_supplier.get("edrpou")
            ):
                supplier, was_created = match_or_create_supplier(
                    ocr_supplier.get("name"),
                    ocr_supplier.get("edrpou"),
                    created_by=receipt.created_by,
                )
                receipt.supplier = supplier
                logger.info(
                    "receipt_supplier_detected",
                    extra={
                        "receipt_id": receipt_id,
                        "supplier_id": supplier.pk,
                        "supplier_created": was_created,
                    },
                )

            # Always record the raw OCR supplier dict for audit, even when it was
            # empty or the receipt already had a supplier. Persist both fields
            # together so the row is consistent before lines are (re)built.
            receipt.recognized_supplier = ocr_supplier
            receipt.save(update_fields=["supplier", "recognized_supplier"])

            # --- Rebuild lines + run per-supplier mapping -------------------
            # Idempotency: drop any lines from a prior run before recreating.
            receipt.lines.all().delete()

            for row in ocr_lines:
                recognized_sku = str(row.get("supplier_sku") or "").strip()
                recognized_name = str(row.get("name") or "").strip()
                quantity = _to_decimal(row.get("quantity"), default=Decimal("0"))
                price = _to_decimal(row.get("price"), default=None)

                # Mapping is per-supplier. With no supplier (OCR found none and
                # the operator hasn't picked one) there is no SKU namespace to
                # search, so the line stays unmapped — it will be re-mapped when a
                # supplier is set via PATCH /api/receipts/{id}/.
                if receipt.supplier_id is None:
                    product, status = None, "unmapped"
                else:
                    product, status = match_line(
                        receipt.supplier_id, recognized_sku
                    )

                if status == ArticleMapping.MATCH_AUTO and product is not None:
                    # A remembered mapping resolved this line: count the use so
                    # the most-relied-upon mappings surface over time.
                    ArticleMapping.objects.filter(
                        supplier_id=receipt.supplier_id,
                        supplier_sku_normalized=_normalized(recognized_sku),
                    ).update(times_used=_increment("times_used"))
                else:
                    unmapped_count += 1

                ReceiptLine.objects.create(
                    receipt=receipt,
                    recognized_sku=recognized_sku,
                    recognized_name=recognized_name,
                    quantity=quantity if quantity is not None else Decimal("0"),
                    price=price,
                    matched_product=product,
                    match_status=status,
                    raw_ocr_json=row,
                )

            # Derive the final status from the freshly-created lines via the
            # shared status-machine helper: ``ready`` only when every line is
            # mapped, otherwise ``needs_mapping`` (including the no-lines and
            # no-supplier cases). Using the same recompute the views use keeps the
            # rule in one place.
            final_status = recompute_receipt_status(receipt)

        logger.info(
            "receipt_recognize_done",
            extra={
                "receipt_id": receipt_id,
                "line_count": len(ocr_lines),
                "unmapped": unmapped_count,
                "supplier_id": receipt.supplier_id,
                "status": final_status,
            },
        )
    except Exception as exc:  # noqa: BLE001 - we must record any failure
        # Any failure (OCR, parsing, DB) moves the receipt to ``error`` so the
        # UI can offer a retry; we log with the exception for diagnosis.
        logger.exception(
            "receipt_recognize_error",
            extra={"receipt_id": receipt_id, "error": str(exc)},
        )
        Receipt.objects.filter(pk=receipt_id).update(status="error")


def _normalized(supplier_sku: str) -> str:
    """Return the normalized form of a SKU (thin import-local helper).

    Imported lazily inside the function body would be cleaner, but a small
    module-level indirection keeps :func:`recognize_receipt_task` readable. We
    reuse the canonical normalizer from the mapping service so the ``times_used``
    update targets exactly the row :func:`match_line` matched.

    Args:
        supplier_sku: Raw recognized SKU.

    Returns:
        The normalized SKU string.
    """

    from apps.mapping.services import normalize_sku

    return normalize_sku(supplier_sku)


def _increment(field: str):
    """Build an ``F``-expression that increments an integer field by one.

    Using a database ``F`` expression avoids a read-modify-write race on
    ``times_used`` when multiple lines share a mapping in the same run.

    Args:
        field: The model field name to increment.

    Returns:
        A Django ``F(field) + 1`` expression.
    """

    from django.db.models import F

    return F(field) + 1


def _load_photo_bytes(receipt: Receipt) -> list[bytes]:
    """Load the raw image bytes for every photo attached to a receipt.

    Reads each :class:`~apps.receipts.models.ReceiptPhoto`'s ``image`` file back
    from Django's default storage (Cloudflare R2 in production, local
    ``MEDIA_ROOT`` in dev). Reading the file server-side — rather than fetching
    the public ``image_url`` over HTTP — means the OCR worker needs no outbound
    network access to storage and works even when the bucket is private.

    A photo whose ``image`` is empty (e.g. created from a pre-uploaded
    ``image_url`` only, or a missing object) is skipped with a warning rather than
    aborting the whole run, so one bad page does not fail recognition of the rest.

    Args:
        receipt: The receipt whose photo bytes to load.

    Returns:
        A list of image byte-strings, one per readable photo. Empty when the
        receipt has no photos with stored image files.
    """

    images: list[bytes] = []
    photos = list(receipt.photos.all())
    for photo in photos:
        image_field = photo.image
        if not image_field:
            # No stored file (URL-only photo, or never uploaded) — nothing to OCR.
            logger.warning(
                "receipt_photo_no_image",
                extra={"receipt_id": receipt.pk, "photo_id": photo.pk},
            )
            continue
        try:
            with image_field.open("rb") as handle:
                images.append(handle.read())
        except (OSError, ValueError) as exc:  # storage miss / closed file
            # Skip an unreadable page; recognition continues on the others.
            logger.warning(
                "receipt_photo_read_failed",
                extra={
                    "receipt_id": receipt.pk,
                    "photo_id": photo.pk,
                    "error": str(exc),
                },
            )

    logger.info(
        "receipt_photos_load",
        extra={
            "receipt_id": receipt.pk,
            "photo_count": len(photos),
            "loaded": len(images),
        },
    )
    return images
