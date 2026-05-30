"""Views for the catalog app.

Implements:

* ``GET  /api/products/search/?q=`` — search :class:`OurProduct` by SKU or name
  for the manual-mapping dropdown (:class:`ProductSearchView`).
* ``POST /api/sync/catalog/`` — admin-only trigger that enqueues the Celery
  catalog-sync task (:class:`CatalogSyncView`).
"""

from __future__ import annotations

import logging

from django.db.models import Q
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.generics import ListAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsAdmin

from .models import OurProduct
from .serializers import CatalogSyncResultSerializer, OurProductSerializer

logger = logging.getLogger(__name__)

# Cap result size: the dropdown only needs a handful of candidates, and an
# unbounded LIKE scan over the whole catalog would be wasteful on mobile.
SEARCH_LIMIT = 20


@extend_schema(
    summary="Пошук товарів каталогу",
    description=(
        "Пошук OurProduct за артикулом (sku) або назвою для випадаючого "
        "списку маппінгу. Порожній запит повертає порожній список."
    ),
    parameters=[
        OpenApiParameter(
            name="q",
            description="Підрядок для пошуку за sku або name.",
            required=False,
            type=str,
        ),
    ],
    tags=["catalog"],
)
class ProductSearchView(ListAPIView):
    """Search catalog products by SKU or name (``GET /api/products/search/``).

    The ``q`` query parameter is matched case-insensitively against both ``sku``
    and ``name``. Results are capped at :data:`SEARCH_LIMIT`. An empty/blank query
    returns an empty list (so the dropdown shows nothing until the user types).
    """

    serializer_class = OurProductSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None

    def get_queryset(self):
        """Return up to :data:`SEARCH_LIMIT` products matching ``q``.

        Returns:
            QuerySet[OurProduct]: Matching products ordered by SKU. Empty when no
                ``q`` is supplied.
        """

        q = self.request.query_params.get("q", "").strip()
        if not q:
            return OurProduct.objects.none()
        return (
            OurProduct.objects.filter(Q(sku__icontains=q) | Q(name__icontains=q))
            .order_by("sku")[:SEARCH_LIMIT]
        )


class CatalogSyncView(APIView):
    """Trigger a SalesDrive catalog sync (``POST /api/sync/catalog/``).

    Admin-only. Enqueues the Celery task that fetches and parses the SalesDrive
    YML export and upserts :class:`OurProduct` rows, then returns the task id so
    the caller can poll progress. The actual sync runs out-of-band on a worker.

    ``admin`` here is the Valeraup product role on the user's
    :class:`~apps.accounts.models.Profile` (see :class:`IsAdmin`), *not* Django's
    ``is_staff`` flag — catalog sync is a product-admin action.
    """

    permission_classes = [IsAuthenticated, IsAdmin]

    @extend_schema(
        request=None,
        responses={202: CatalogSyncResultSerializer},
        summary="Запустити синхронізацію каталогу (адмін)",
        tags=["catalog"],
    )
    def post(self, request: Request) -> Response:
        """Enqueue the catalog-sync Celery task.

        Args:
            request: Authenticated admin request. Body is ignored — the YML URL
                comes from ``settings.SALESDRIVE_YML_URL`` inside the task.

        Returns:
            ``202 Accepted`` with ``{"task_id", "detail"}``.

        Notes:
            The task is imported lazily so this module stays importable even
            before the catalog ``tasks.py`` (written by another agent) lands.
            ``.delay()`` returns immediately; the sync itself happens on a worker.
        """

        from .tasks import sync_catalog_task

        async_result = sync_catalog_task.delay()
        logger.info(
            "catalog_sync_enqueued",
            extra={"task_id": async_result.id, "user_id": request.user.pk},
        )
        return Response(
            {
                "task_id": async_result.id,
                "detail": "Синхронізацію каталогу поставлено в чергу.",
            },
            status=status.HTTP_202_ACCEPTED,
        )
