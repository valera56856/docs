"""Receipt status-machine helpers.

The :class:`~apps.receipts.models.Receipt` ``status`` field is the spine of the
whole workflow (see ``docs/ARCHITECTURE.md`` and ``CLAUDE.md`` §8). This module
centralises the two operations that move a receipt through that machine so the
rules live in one place instead of being duplicated across views and tasks:

* :func:`recompute_receipt_status` — derive the *data-driven* status from the
  receipt's current lines (``needs_mapping`` vs ``ready``) without ever clobbering
  a terminal/explicit state (``xlsx_ready`` / ``error``).
* :func:`set_receipt_status` — apply an *explicit* status transition (e.g. the
  view flipping a receipt to ``recognizing`` or ``xlsx_ready``), validating that
  the transition is sane and logging it.

WHY a dedicated module:
    Both the synchronous line-edit/map views and the asynchronous OCR task need
    to recompute "is this receipt ready to export?" from the same rule. Keeping
    that single source of truth here prevents the views and the task from drifting
    apart on what ``ready`` means.

The canonical transitions (``→`` = allowed)::

    draft        → recognizing
    recognizing  → needs_mapping | ready | error
    needs_mapping → ready | needs_mapping | recognizing
    ready        → needs_mapping | xlsx_ready | recognizing
    xlsx_ready   → recognizing            (re-recognise re-opens the receipt)
    error        → recognizing            (retry)
    <any>        → error                  (a failure can always be recorded)
"""

from __future__ import annotations

import logging

from apps.receipts.models import Receipt

logger = logging.getLogger(__name__)

# Data-derived statuses :func:`recompute_receipt_status` is allowed to *set*.
# It only ever moves a receipt between these two; it never assigns a terminal or
# in-flight status (those are explicit transitions handled by callers/the task).
_DERIVED_STATUSES: frozenset[str] = frozenset({"needs_mapping", "ready"})

# Statuses :func:`recompute_receipt_status` must NOT overwrite. ``xlsx_ready`` is
# an explicit downstream result the operator reached deliberately; ``error`` is a
# terminal failure the UI surfaces for retry. Auto-downgrading either of these on
# a stray line edit would silently undo real progress, so we refuse.
_PROTECTED_FROM_RECOMPUTE: frozenset[str] = frozenset({"xlsx_ready", "error"})

# Allowed explicit transitions for :func:`set_receipt_status`. ``error`` is a
# valid target from every state (any step may fail), so it is handled separately
# rather than being listed under every key.
_ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    "draft": frozenset({"recognizing", "draft"}),
    "recognizing": frozenset({"needs_mapping", "ready", "recognizing"}),
    # ``needs_mapping → xlsx_ready`` is permitted: the Excel builder defensively
    # skips unmapped lines, so an operator may deliberately export only the
    # already-mapped subset of a partially-mapped receipt.
    "needs_mapping": frozenset(
        {"ready", "needs_mapping", "recognizing", "xlsx_ready"}
    ),
    "ready": frozenset({"needs_mapping", "ready", "xlsx_ready", "recognizing"}),
    # ``xlsx_ready → ready`` lets a re-generation (e.g. after a late edit that ran
    # recompute) flow back through the normal export path.
    "xlsx_ready": frozenset({"xlsx_ready", "ready", "recognizing"}),
    "error": frozenset({"recognizing", "error"}),
}


def recompute_receipt_status(receipt: Receipt) -> str:
    """Recompute a receipt's status from its current lines and persist it.

    The rule (the WHY for each branch):

    * **No lines** → ``needs_mapping``. An empty receipt cannot be exported and
      needs operator attention (re-shoot the photo, retry OCR).
    * **Any line lacks a ``matched_product``** → ``needs_mapping``. Unmapped
      lines have no SalesDrive SKU, so the receipt is not exportable yet.
    * **Every line has a ``matched_product``** → ``ready``. The Excel can be
      generated.

    Terminal/explicit states are protected: if the receipt is already
    ``xlsx_ready`` or ``error``, this function leaves it untouched and returns the
    existing status. WHY: a late line edit must not silently un-generate an
    already-exported receipt or clear a recorded failure — those transitions are
    the operator's/task's explicit decision, not a side effect of recompute.

    Args:
        receipt: The receipt to evaluate. Its related ``lines`` are read (one
            query); pass a prefetched receipt to avoid an N+1 in a loop.

    Returns:
        The receipt's status after recomputation (possibly unchanged).
    """

    if receipt.status in _PROTECTED_FROM_RECOMPUTE:
        # Never auto-downgrade a deliberate/terminal state.
        logger.info(
            "receipt_status_recompute_skipped",
            extra={"receipt_id": receipt.pk, "status": receipt.status},
        )
        return receipt.status

    lines = list(receipt.lines.all())
    if not lines:
        new_status = "needs_mapping"
    elif any(line.matched_product_id is None for line in lines):
        new_status = "needs_mapping"
    else:
        new_status = "ready"

    previous = receipt.status
    if new_status != previous:
        receipt.status = new_status
        receipt.save(update_fields=["status"])

    logger.info(
        "receipt_status_recomputed",
        extra={
            "receipt_id": receipt.pk,
            "previous_status": previous,
            "status": new_status,
            "line_count": len(lines),
        },
    )
    return new_status


def set_receipt_status(receipt: Receipt, status: str) -> str:
    """Apply an explicit status transition to a receipt and persist it.

    Used by callers that move a receipt by *intent* rather than by deriving it
    from lines — e.g. a view flipping to ``recognizing`` before enqueueing OCR,
    or to ``xlsx_ready`` after the Excel is built. The transition is validated
    against :data:`_ALLOWED_TRANSITIONS` (plus ``error`` from anywhere) so an
    obviously-wrong jump is caught and logged rather than silently saved.

    Args:
        receipt: The receipt to transition.
        status: The target status; must be one of
            :attr:`Receipt.STATUS` values.

    Returns:
        The receipt's status after the call (the new status, or the unchanged
        one if it was a no-op / rejected transition).

    Raises:
        ValueError: If ``status`` is not a recognised receipt status, or the
            transition from the current status is not allowed.
    """

    valid_statuses = {value for value, _label in Receipt.STATUS}
    if status not in valid_statuses:
        raise ValueError(f"Unknown receipt status: {status!r}")

    previous = receipt.status
    if status == previous:
        # No-op transition: nothing to save, but still report it.
        return previous

    # ``error`` is reachable from any state (any step may fail). Other targets
    # must appear in the allow-list for the current status.
    allowed = _ALLOWED_TRANSITIONS.get(previous, frozenset())
    if status != "error" and status not in allowed:
        logger.warning(
            "receipt_status_transition_rejected",
            extra={
                "receipt_id": receipt.pk,
                "previous_status": previous,
                "attempted_status": status,
            },
        )
        raise ValueError(
            f"Illegal receipt status transition: {previous!r} → {status!r}"
        )

    receipt.status = status
    receipt.save(update_fields=["status"])
    logger.info(
        "receipt_status_set",
        extra={
            "receipt_id": receipt.pk,
            "previous_status": previous,
            "status": status,
        },
    )
    return status
