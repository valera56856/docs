"""Views for the receipts app — the core receipt workflow.

Implements every receipt endpoint in the contract:

* ``POST  /api/receipts/``                           — create draft + photos
  (:class:`ReceiptCreateView`).
* ``GET   /api/receipts/{id}/``                       — receipt with lines/status
  (:class:`ReceiptDetailView`).
* ``POST  /api/receipts/{id}/recognize/``             — enqueue Gemini OCR
  (:class:`ReceiptRecognizeView`).
* ``PATCH /api/receipts/{id}/lines/{line_id}/``       — edit qty/price/sku
  (:class:`ReceiptLineUpdateView`).
* ``POST  /api/receipts/{id}/lines/{line_id}/map/``   — map line to product
  (:class:`ReceiptLineMapView`).
* ``POST  /api/receipts/{id}/generate-xlsx/``         — build the Excel receipt
  (:class:`ReceiptGenerateXlsxView`).

Heavy collaborators (Gemini OCR task, mapping service, Excel builder) are
imported lazily inside the methods so this module stays importable even before
those round-2 service modules land, and to avoid import cycles.
"""

from __future__ import annotations

import logging

from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.generics import CreateAPIView, RetrieveAPIView
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.mapping.serializers import MapLineRequestSerializer

from .models import Receipt, ReceiptLine, ReceiptPhoto
from .serializers import (
    GenerateXlsxResultSerializer,
    ReceiptCreateSerializer,
    ReceiptLinePatchSerializer,
    ReceiptLineSerializer,
    ReceiptPhotoUploadResultSerializer,
    ReceiptPhotoUploadSerializer,
    ReceiptSerializer,
    RecognizeResultSerializer,
)
from .services.status import recompute_receipt_status, set_receipt_status

logger = logging.getLogger(__name__)


def _actor(request: Request) -> str:
    """Return a stable string identifier for the requesting user.

    Used to populate ``created_by`` fields on receipts and mappings for audit.

    Args:
        request: The authenticated DRF request.

    Returns:
        The user's email if set, otherwise the username, otherwise ``""``.
    """

    user = getattr(request, "user", None)
    if user is None:
        return ""
    return getattr(user, "email", "") or getattr(user, "username", "") or ""


@extend_schema(
    request=ReceiptCreateSerializer,
    responses={201: ReceiptSerializer},
    summary="Створити чернетку надходження",
    tags=["receipts"],
)
class ReceiptCreateView(CreateAPIView):
    """Create a draft receipt (``POST /api/receipts/``).

    The camera-first PWA flow posts just ``{"supplier": id}`` to open a ``draft``
    receipt, then uploads photos via ``POST .../photos/``. The legacy
    ``photo_urls`` field remains optional for back-compat (pre-upload-then-POST).
    """

    serializer_class = ReceiptCreateSerializer
    permission_classes = [IsAuthenticated]

    def perform_create(self, serializer: ReceiptCreateSerializer) -> None:
        """Persist the receipt, stamping the creator.

        Args:
            serializer: The validated create serializer.
        """

        receipt = serializer.save(created_by=_actor(self.request))
        logger.info(
            "receipt_created",
            extra={
                "receipt_id": receipt.pk,
                "supplier_id": receipt.supplier_id,
                "photo_count": receipt.photos.count(),
            },
        )


@extend_schema(
    responses={200: ReceiptSerializer},
    summary="Отримати надходження з рядками",
    tags=["receipts"],
)
class ReceiptDetailView(RetrieveAPIView):
    """Retrieve one receipt with nested photos and lines.

    ``GET /api/receipts/{id}/``. Prefetches related rows so the nested
    serializer does not issue N+1 queries.
    """

    serializer_class = ReceiptSerializer
    permission_classes = [IsAuthenticated]
    queryset = Receipt.objects.all().prefetch_related(
        "photos", "lines", "lines__matched_product"
    )


class ReceiptPhotoUploadView(APIView):
    """Upload one invoice-page photo (``POST /api/receipts/{id}/photos/``).

    Accepts a multipart request with an ``image`` file, saves it as a
    :class:`~apps.receipts.models.ReceiptPhoto` through Django's default storage
    (Cloudflare R2 in production, local ``MEDIA_ROOT`` in dev), and returns the
    new photo's id and stored URL so the UI can show a thumbnail immediately.

    WHY a dedicated multipart endpoint (vs the legacy ``photo_urls`` on create):
        The OCR worker reads image bytes server-side, so the file must reach our
        storage. Uploading directly here means the client does not need its own
        R2 credentials and the bytes are guaranteed present before recognition.
    """

    permission_classes = [IsAuthenticated]
    # Accept multipart/form-data (the file) — without these parsers DRF would try
    # to JSON-decode the body and reject the upload.
    parser_classes = [MultiPartParser, FormParser]

    @extend_schema(
        request=ReceiptPhotoUploadSerializer,
        responses={201: ReceiptPhotoUploadResultSerializer},
        summary="Завантажити фото сторінки накладної",
        tags=["receipts"],
    )
    def post(self, request: Request, pk: int) -> Response:
        """Save the uploaded image as a receipt photo.

        Args:
            request: Authenticated multipart request carrying the ``image`` file.
            pk: Receipt primary key from the URL.

        Returns:
            ``201 Created`` with ``{"id", "image_url"}``. ``404`` if the receipt
            does not exist; ``400`` if no valid image was supplied.
        """

        receipt = get_object_or_404(Receipt, pk=pk)

        serializer = ReceiptPhotoUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        image_file = serializer.validated_data["image"]

        # Save the file first so storage assigns the final path, then mirror its
        # public URL into ``image_url`` (the single field the frontend renders).
        photo = ReceiptPhoto(receipt=receipt, image=image_file)
        photo.save()
        photo.image_url = photo.image.url
        photo.save(update_fields=["image_url"])

        logger.info(
            "receipt_photo_uploaded",
            extra={
                "receipt_id": receipt.pk,
                "photo_id": photo.pk,
                "image_url": photo.image_url,
            },
        )
        return Response(
            {"id": photo.pk, "image_url": photo.image_url},
            status=status.HTTP_201_CREATED,
        )


class ReceiptRecognizeView(APIView):
    """Enqueue Gemini OCR for a receipt (``POST /api/receipts/{id}/recognize/``).

    Sets the receipt to ``recognizing`` and dispatches the Celery task that
    fetches the photos, calls Gemini, creates lines and runs mapping. Returns
    ``202`` immediately — the work happens on a worker.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=None,
        responses={202: RecognizeResultSerializer},
        summary="Запустити розпізнавання (OCR)",
        tags=["receipts"],
    )
    def post(self, request: Request, pk: int) -> Response:
        """Mark the receipt as recognizing and enqueue the OCR task.

        Args:
            request: Authenticated request.
            pk: Receipt primary key from the URL.

        Returns:
            ``202 Accepted`` with ``{"task_id", "status"}``.

        Notes:
            The task and its enqueue are intentionally idempotent at the task
            level: re-running recognition rebuilds lines from the photos.
        """

        from .tasks import recognize_receipt_task

        receipt = get_object_or_404(Receipt, pk=pk)

        # Flip to ``recognizing`` so the UI shows progress as soon as the task is
        # queued; the task itself moves it on to needs_mapping/ready/error. The
        # status helper validates the transition is legal from the current state.
        set_receipt_status(receipt, "recognizing")

        async_result = recognize_receipt_task.delay(receipt.pk)
        logger.info(
            "receipt_recognize_enqueued",
            extra={"receipt_id": receipt.pk, "task_id": async_result.id},
        )
        return Response(
            {"task_id": async_result.id, "status": receipt.status},
            status=status.HTTP_202_ACCEPTED,
        )


class ReceiptLineUpdateView(APIView):
    """Edit a single receipt line (``PATCH /api/receipts/{id}/lines/{line_id}/``).

    Lets the operator correct OCR mistakes (quantity, price, recognized SKU/name)
    before Excel generation. Mapping changes go through the dedicated map
    endpoint, not here.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=ReceiptLinePatchSerializer,
        responses={200: ReceiptLineSerializer},
        summary="Редагувати рядок (кількість/ціна/sku)",
        tags=["receipts"],
    )
    def patch(self, request: Request, pk: int, line_id: int) -> Response:
        """Apply a partial update to the line and return it.

        Args:
            request: Authenticated request with the partial fields.
            pk: Receipt primary key (scopes the line lookup).
            line_id: Line primary key.

        Returns:
            ``200`` with the updated, fully serialized line.
        """

        line = get_object_or_404(
            ReceiptLine.objects.select_related("receipt"),
            pk=line_id,
            receipt_id=pk,
        )
        serializer = ReceiptLinePatchSerializer(
            line, data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()

        # An edit can change whether the receipt is exportable (e.g. clearing a
        # required field), so re-derive its status from the current lines. The
        # helper is a no-op when nothing changed and never downgrades a terminal
        # ``xlsx_ready`` / ``error`` state.
        recompute_receipt_status(line.receipt)

        logger.info(
            "receipt_line_updated",
            extra={
                "receipt_id": pk,
                "line_id": line.pk,
                "fields": list(serializer.validated_data.keys()),
            },
        )
        return Response(
            ReceiptLineSerializer(line).data, status=status.HTTP_200_OK
        )


class ReceiptLineMapView(APIView):
    """Map a receipt line to one of our products.

    ``POST /api/receipts/{id}/lines/{line_id}/map/``. Persists a manual
    :class:`~apps.mapping.models.ArticleMapping` (remembered for next time,
    ``times_used`` incremented), then updates the line to point at the chosen
    product with ``match_status="manual"``.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=MapLineRequestSerializer,
        responses={200: ReceiptLineSerializer},
        summary="Зіставити рядок із товаром каталогу",
        tags=["receipts"],
    )
    def post(self, request: Request, pk: int, line_id: int) -> Response:
        """Map the line and remember the mapping for the supplier.

        Args:
            request: Authenticated request carrying ``our_product_id``.
            pk: Receipt primary key.
            line_id: Line primary key.

        Returns:
            ``200`` with the updated line. ``404`` if the line or product is not
            found.

        Notes:
            ``remember_mapping`` is idempotent on (supplier, normalized sku), so
            re-mapping the same line just bumps ``times_used`` / repoints the
            existing mapping rather than creating duplicates.
        """

        from apps.catalog.models import OurProduct
        from apps.mapping.services import remember_mapping

        serializer = MapLineRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        our_product_id = serializer.validated_data["our_product_id"]

        line = get_object_or_404(
            ReceiptLine.objects.select_related("receipt"),
            pk=line_id,
            receipt_id=pk,
        )
        product = get_object_or_404(OurProduct, pk=our_product_id)

        # Persist (and remember) the manual mapping for this supplier's SKU.
        remember_mapping(
            supplier_id=line.receipt.supplier_id,
            supplier_sku=line.recognized_sku,
            our_product_id=product.pk,
            created_by=_actor(request),
        )

        # Point the line at the chosen product and mark it manually matched.
        line.matched_product = product
        line.match_status = "manual"
        line.save(update_fields=["matched_product", "match_status"])

        # Mapping this line may have been the last unmapped one — recompute so the
        # receipt flips to ``ready`` as soon as every line is matched.
        recompute_receipt_status(line.receipt)

        logger.info(
            "receipt_line_mapped",
            extra={
                "receipt_id": pk,
                "line_id": line.pk,
                "our_product_id": product.pk,
                "supplier_id": line.receipt.supplier_id,
            },
        )
        return Response(
            ReceiptLineSerializer(line).data, status=status.HTTP_200_OK
        )


class ReceiptGenerateXlsxView(APIView):
    """Generate the Excel receipt (``POST /api/receipts/{id}/generate-xlsx/``).

    Builds the ``.xlsx`` workbook from the receipt's matched lines, saves it to
    storage, records the URL on the receipt, flips status to ``xlsx_ready`` and
    returns the URL for download / manual SalesDrive import.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=None,
        responses={200: GenerateXlsxResultSerializer},
        summary="Згенерувати .xlsx надходження",
        tags=["receipts"],
    )
    def post(self, request: Request, pk: int) -> Response:
        """Build and store the Excel file, returning its URL.

        Args:
            request: Authenticated request.
            pk: Receipt primary key.

        Returns:
            ``200`` with ``{"xlsx_url", "status"}``.

        Notes:
            The build runs synchronously (it is fast — a handful of rows in
            ``openpyxl``). The bytes are written through Django's default storage
            (Cloudflare R2 in production, local filesystem in dev), so the saved
            URL is whatever that backend exposes.
        """

        from django.core.files.base import ContentFile
        from django.core.files.storage import default_storage

        from .services.xlsx import build_receipt_xlsx

        receipt = get_object_or_404(
            Receipt.objects.prefetch_related("lines", "lines__matched_product"),
            pk=pk,
        )

        xlsx_bytes = build_receipt_xlsx(receipt)
        filename = f"receipts/xlsx/{receipt.pk}.xlsx"
        saved_path = default_storage.save(filename, ContentFile(xlsx_bytes))
        xlsx_url = default_storage.url(saved_path)

        # Record the URL, then flip status via the status helper (which validates
        # the transition and logs it) so the workflow advances in one place.
        receipt.xlsx_url = xlsx_url
        receipt.save(update_fields=["xlsx_url"])
        set_receipt_status(receipt, "xlsx_ready")

        logger.info(
            "receipt_xlsx_generated",
            extra={
                "receipt_id": receipt.pk,
                "xlsx_url": xlsx_url,
                "line_count": receipt.lines.count(),
            },
        )
        return Response(
            {"xlsx_url": xlsx_url, "status": receipt.status},
            status=status.HTTP_200_OK,
        )
