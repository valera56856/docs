"""DRF permission classes for the accounts app.

Valeraup has two access roles, stored on :class:`~apps.accounts.models.Profile`:

* ``admin`` — may trigger catalog syncs, view mappings, manage suppliers.
* ``operator`` — the warehouse user who photographs invoices and maps lines.

These permission classes translate that role into DRF's permission protocol so
views can declare ``permission_classes = [IsAdmin]`` instead of re-deriving the
role check each time.

WHY role-based (not Django's ``is_staff``/``IsAdminUser``):
    Django's built-in :class:`~rest_framework.permissions.IsAdminUser` keys on the
    ``is_staff`` flag, which governs Django *admin-site* access — an orthogonal
    concept. Our "admin" is a product role on the profile. Keying on
    ``profile.role`` keeps app authorization independent of who can log into
    ``/admin/``.

Both classes are deliberately defensive about a missing profile: although the
``post_save`` signal guarantees one exists, a request must never 500 because a
profile row is absent — it should simply be treated as the least-privileged
operator.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from rest_framework.permissions import BasePermission
from rest_framework.request import Request

if TYPE_CHECKING:  # pragma: no cover - typing only
    from rest_framework.views import APIView

from .models import Profile


def _role_of(request: Request) -> str | None:
    """Return the authenticated user's role, or ``None`` if undeterminable.

    Resolves the role defensively so a missing/half-built profile degrades to
    "no role" rather than raising. An anonymous or inactive user yields ``None``.

    Args:
        request: The incoming DRF request.

    Returns:
        The profile role string (``"admin"`` / ``"operator"``) for an
        authenticated, active user that has a profile; otherwise ``None``.
    """

    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated or not user.is_active:
        return None

    # ``profile`` is the reverse OneToOne accessor; guard against it being absent
    # (e.g. a user created before the signal was wired, in an old fixture).
    profile = getattr(user, "profile", None)
    if profile is None:
        # Fall back to an explicit query in case the related object was not
        # prefetched and the accessor short-circuited to ``None`` via a guard.
        profile = Profile.objects.filter(user=user).first()
    return profile.role if profile is not None else None


class IsAdmin(BasePermission):
    """Allow only authenticated users whose profile role is ``admin``.

    Used to gate admin-only actions such as the manual catalog sync. Returns
    ``False`` (not an exception) for anonymous users, inactive users, users with
    no profile, and operators — so DRF answers 403/401 rather than 500.
    """

    message = "Потрібні права адміністратора."

    def has_permission(self, request: Request, view: "APIView") -> bool:
        """Return whether the caller is an authenticated admin.

        Args:
            request: The incoming DRF request.
            view: The view being accessed (unused; required by the protocol).

        Returns:
            ``True`` only when the resolved role is ``Profile.ROLE_ADMIN``.
        """

        return _role_of(request) == Profile.ROLE_ADMIN


class IsOperatorOrAdmin(BasePermission):
    """Allow any authenticated, active user (operator *or* admin).

    This is the default access level for the receipt-processing workflow: every
    signed-in warehouse user may create receipts, upload photos and map lines.
    It is functionally equivalent to ``IsAuthenticated`` but named for intent so
    views read self-documentingly and a future role split has an obvious seam.
    """

    message = "Потрібна автентифікація."

    def has_permission(self, request: Request, view: "APIView") -> bool:
        """Return whether the caller is any authenticated, active user.

        Args:
            request: The incoming DRF request.
            view: The view being accessed (unused; required by the protocol).

        Returns:
            ``True`` when the user is authenticated and active, regardless of
            role. A missing profile does not block access here.
        """

        user = getattr(request, "user", None)
        return bool(user is not None and user.is_authenticated and user.is_active)
