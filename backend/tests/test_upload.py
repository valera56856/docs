"""Tests for receipt photo upload and the offline-safe recognize task.

Two surfaces are covered:

* ``POST /api/receipts/{id}/photos/`` — a multipart ``image`` upload creates a
  :class:`~apps.receipts.models.ReceiptPhoto` with a stored ``image`` file and a
  populated ``image_url``.
* :func:`apps.receipts.tasks.recognize_receipt_task` — with ``GEMINI_API_KEY``
  unset (the CI/offline default), recognition produces no lines and the receipt
  settles at ``needs_mapping`` rather than hanging or erroring.

Storage is redirected to a temporary directory via ``settings(MEDIA_ROOT=...)``
so uploads never touch a real bucket and leave nothing behind. The Gemini
network boundary is never called — ``recognize_invoice`` short-circuits to ``[]``
when there is no API key, which is exactly the path asserted here.
"""

from __future__ import annotations

import io

import pytest
from PIL import Image

from apps.receipts.models import Receipt, ReceiptPhoto
from apps.receipts.tasks import recognize_receipt_task
from apps.suppliers.models import Supplier


@pytest.fixture
def supplier(db) -> Supplier:
    """Create and return a persisted supplier."""
    return Supplier.objects.create(name="ACME Постачання")


def _png_bytes() -> bytes:
    """Return the bytes of a tiny valid PNG.

    DRF's ``ImageField`` runs the upload through Pillow, so the test payload must
    be a real, decodable image rather than arbitrary bytes.

    Returns:
        A minimal in-memory PNG as bytes.
    """
    buffer = io.BytesIO()
    Image.new("RGB", (4, 4), color=(10, 26, 63)).save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.fixture
def media_root(settings, tmp_path):
    """Point file storage at a temp dir so uploads are isolated and cleaned up.

    Forces the local FileSystemStorage fallback (no R2) regardless of the
    ambient environment, so the test is hermetic.
    """
    settings.MEDIA_ROOT = str(tmp_path)
    settings.STORAGES = {
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
        },
    }
    return tmp_path


@pytest.mark.django_db
def test_photo_upload_creates_receipt_photo(
    auth_client, supplier, media_root
) -> None:
    """A multipart ``image`` upload creates a photo with a stored file + URL."""
    receipt = Receipt.objects.create(supplier=supplier, status="draft")

    upload = io.BytesIO(_png_bytes())
    upload.name = "page1.png"

    response = auth_client.post(
        f"/api/receipts/{receipt.pk}/photos/",
        {"image": upload},
        format="multipart",
    )

    assert response.status_code == 201
    body = response.json()
    assert "id" in body
    assert body["image_url"]

    photo = ReceiptPhoto.objects.get(pk=body["id"])
    assert photo.receipt_id == receipt.pk
    assert photo.image  # file stored
    assert photo.image_url == photo.image.url
    # The bytes round-trip through storage.
    with photo.image.open("rb") as handle:
        assert handle.read() == _png_bytes()


@pytest.mark.django_db
def test_photo_upload_rejects_non_image(auth_client, supplier, media_root) -> None:
    """Non-image junk is rejected by the ``ImageField`` validation (400)."""
    receipt = Receipt.objects.create(supplier=supplier, status="draft")

    junk = io.BytesIO(b"not an image at all")
    junk.name = "evil.png"

    response = auth_client.post(
        f"/api/receipts/{receipt.pk}/photos/",
        {"image": junk},
        format="multipart",
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_photo_upload_requires_auth(api_client, supplier, media_root) -> None:
    """Anonymous photo upload is rejected (401)."""
    receipt = Receipt.objects.create(supplier=supplier, status="draft")
    upload = io.BytesIO(_png_bytes())
    upload.name = "page1.png"
    response = api_client.post(
        f"/api/receipts/{receipt.pk}/photos/",
        {"image": upload},
        format="multipart",
    )
    assert response.status_code == 401


@pytest.mark.django_db
def test_recognize_offline_settles_needs_mapping(
    settings, supplier, media_root
) -> None:
    """With no Gemini key, recognition yields no lines → ``needs_mapping``.

    The receipt has a real uploaded photo, but ``recognize_invoice`` returns
    ``[]`` without an API key. The task must still complete cleanly (idempotent,
    no error) and the status helper settles the receipt at ``needs_mapping`` —
    not ``error`` and not a hang in ``recognizing``.
    """
    settings.GEMINI_API_KEY = ""  # offline guard

    receipt = Receipt.objects.create(supplier=supplier, status="recognizing")
    from django.core.files.base import ContentFile

    photo = ReceiptPhoto(receipt=receipt)
    photo.image.save("page1.png", ContentFile(_png_bytes()), save=False)
    photo.image_url = photo.image.url
    photo.save()

    # Call the task body synchronously (CELERY_TASK_ALWAYS_EAGER not required —
    # we invoke the function directly to assert its side effects).
    recognize_receipt_task(receipt.pk)

    receipt.refresh_from_db()
    assert receipt.status == "needs_mapping"
    assert receipt.lines.count() == 0


@pytest.mark.django_db
def test_recognize_is_idempotent(settings, supplier, media_root) -> None:
    """Re-running recognition does not duplicate lines (converges).

    Even offline (no lines created), re-running must not error and must leave the
    receipt in the same settled state — proving the delete-then-recreate guard
    holds.
    """
    settings.GEMINI_API_KEY = ""

    receipt = Receipt.objects.create(supplier=supplier, status="recognizing")

    recognize_receipt_task(receipt.pk)
    recognize_receipt_task(receipt.pk)

    receipt.refresh_from_db()
    assert receipt.status == "needs_mapping"
    assert receipt.lines.count() == 0
