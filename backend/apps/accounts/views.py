"""Authentication views for the accounts app.

Implements the contract auth endpoints:

* ``POST /api/auth/login/`` — email + password to JWT pair
  (:class:`EmailTokenObtainPairView`).
* ``POST /api/auth/refresh/`` — refresh access token (SimpleJWT
  ``TokenRefreshView``, wired directly in ``urls.py``).
* ``POST /api/auth/pin/`` — 4-digit PIN to JWT pair (:class:`PinLoginView`).
* ``GET  /api/auth/me/`` — current profile summary (:class:`MeView`).
* ``POST /api/auth/set-pin/`` — set/replace the caller's PIN
  (:class:`SetPinView`, authenticated).

The first three are deliberately ``AllowAny``: they are how a client *obtains*
credentials, so requiring authentication would be circular. ``me`` and
``set-pin`` instead require an authenticated caller — you cannot set a PIN for an
account you have not already proven you own.
"""

from __future__ import annotations

import logging

from django.contrib.auth import get_user_model
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView

from .serializers import (
    EmailTokenObtainPairSerializer,
    PinLoginSerializer,
    ProfileSerializer,
    SetPinSerializer,
    TokenPairSerializer,
)

logger = logging.getLogger(__name__)
User = get_user_model()


class EmailTokenObtainPairView(TokenObtainPairView):
    """Obtain a JWT pair using email + password.

    Subclasses SimpleJWT's view only to swap in
    :class:`~apps.accounts.serializers.EmailTokenObtainPairSerializer`, which
    authenticates by email instead of username.
    """

    permission_classes = [AllowAny]
    serializer_class = EmailTokenObtainPairSerializer
    # Brute-force throttle (H1): cap password-login attempts at the ``login``
    # rate via ScopedRateThrottle. This is an unauthenticated endpoint, so the
    # scope is the meaningful brake (the global ``anon`` limit also applies).
    throttle_scope = "login"


class PinLoginView(APIView):
    """Fast login by 4-digit PIN, returning a JWT pair.

    The PWA stores the long-lived refresh token in Capacitor Secure Storage and
    lets the operator re-authenticate with a PIN (optionally behind device
    biometrics). This endpoint verifies the PIN against the user's
    :class:`~apps.accounts.models.Profile.pin_hash` and, on success, mints the
    same access/refresh pair the password flow returns.
    """

    permission_classes = [AllowAny]
    # Brute-force throttle (H1): a 4-digit PIN has only 10k combinations, so cap
    # attempts hard at the ``pin`` rate to make online guessing infeasible.
    throttle_scope = "pin"

    @extend_schema(
        request=PinLoginSerializer,
        responses={200: TokenPairSerializer},
        summary="Швидкий вхід за PIN-кодом",
        description=(
            "Перевіряє 4-значний PIN проти Profile.pin_hash та повертає пару "
            "JWT (access + refresh)."
        ),
    )
    def post(self, request: Request) -> Response:
        """Verify the PIN and return a fresh JWT pair.

        Args:
            request: DRF request carrying ``email`` and ``pin`` in the body.

        Returns:
            ``200`` with ``{"access", "refresh"}`` on success, or ``401`` with a
            generic error message if the email/PIN combination is invalid.

        Notes:
            The PIN is verified with Django's ``check_password`` against the
            stored hash. We return an identical generic error for "no such user",
            "no PIN set", and "wrong PIN" so the endpoint does not leak which
            accounts exist or have PINs configured.
        """

        # Avoid a circular import at module load: Profile lives in the same app
        # but importing it lazily keeps the view importable during app loading.
        from django.contrib.auth.hashers import check_password

        from .models import Profile

        serializer = PinLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"]
        pin = serializer.validated_data["pin"]

        invalid = Response(
            {"detail": "Невірний email або PIN."},
            status=status.HTTP_401_UNAUTHORIZED,
        )

        user = User.objects.filter(email__iexact=email).first()
        if user is None or not user.is_active:
            logger.info(
                "pin_login_failed",
                extra={"reason": "no_user", "email": email},
            )
            return invalid

        profile = Profile.objects.filter(user=user).first()
        if profile is None or not profile.pin_hash:
            logger.info(
                "pin_login_failed",
                extra={"reason": "no_pin", "user_id": user.pk},
            )
            return invalid

        if not check_password(pin, profile.pin_hash):
            logger.info(
                "pin_login_failed",
                extra={"reason": "bad_pin", "user_id": user.pk},
            )
            return invalid

        refresh = RefreshToken.for_user(user)
        logger.info("pin_login_ok", extra={"user_id": user.pk})
        return Response(
            {"access": str(refresh.access_token), "refresh": str(refresh)},
            status=status.HTTP_200_OK,
        )


class MeView(APIView):
    """Return the authenticated caller's profile summary.

    Convenience endpoint the PWA uses after login to learn the user's role and
    whether a PIN is configured (to decide whether to offer the PIN flow).
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        responses={200: ProfileSerializer},
        summary="Поточний користувач",
    )
    def get(self, request: Request) -> Response:
        """Return ``email``, ``role`` and ``has_pin`` for the current user.

        Args:
            request: Authenticated DRF request.

        Returns:
            ``200`` with the serialized profile summary.
        """

        from .models import Profile

        profile = Profile.objects.filter(user=request.user).first()
        data = {
            "email": request.user.email,
            "role": profile.role if profile else Profile.ROLE_OPERATOR,
            "has_pin": bool(profile and profile.pin_hash),
        }
        return Response(ProfileSerializer(data).data, status=status.HTTP_200_OK)


class SetPinView(APIView):
    """Set or replace the authenticated caller's 4-digit PIN.

    The PWA calls this after the operator chooses a PIN so that future logins can
    use the fast :class:`PinLoginView` flow (optionally behind device
    biometrics). The PIN is hashed with Django's ``make_password`` and stored on
    the caller's :class:`~apps.accounts.models.Profile.pin_hash` — it is never
    persisted or logged in plaintext.

    Requires authentication: a user may only set *their own* PIN, identified by
    the request's JWT, so this endpoint cannot be used to overwrite another
    account's credential.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=SetPinSerializer,
        responses={204: None},
        summary="Встановити PIN-код",
        description=(
            "Хешує переданий 4-значний PIN та зберігає його у Profile.pin_hash "
            "поточного користувача. Повертає 204 без тіла."
        ),
    )
    def post(self, request: Request) -> Response:
        """Hash the supplied PIN onto the caller's profile.

        Args:
            request: Authenticated DRF request carrying ``pin`` (4 digits).

        Returns:
            ``204 No Content`` on success. The PIN itself is never echoed.

        Notes:
            Uses ``get_or_create`` to be robust even if the profile is somehow
            missing (defence in depth on top of the auto-create signal). Only the
            ``pin_hash`` column is written via ``update_fields`` to avoid touching
            the role.
        """

        from django.contrib.auth.hashers import make_password

        from .models import Profile

        serializer = SetPinSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        pin = serializer.validated_data["pin"]

        profile, _ = Profile.objects.get_or_create(
            user=request.user,
            defaults={"role": Profile.ROLE_OPERATOR},
        )
        profile.pin_hash = make_password(pin)
        profile.save(update_fields=["pin_hash"])

        # Log the action but NEVER the PIN value.
        logger.info("pin_set", extra={"user_id": request.user.pk})
        return Response(status=status.HTTP_204_NO_CONTENT)


class LogoutView(APIView):
    """Revoke a refresh token (``POST /api/auth/logout/``).

    Token revocation (M5). A JWT is otherwise valid until it expires; with
    rotation + blacklisting enabled (``SIMPLE_JWT`` + the ``token_blacklist``
    app), a client logging out can have its refresh token *blacklisted* so it can
    no longer be exchanged for new access tokens. The short-lived access token
    still works until it expires (minutes), which is the standard JWT tradeoff;
    the long-lived refresh token is what we kill here.

    Requires authentication: only the holder of a valid access token may revoke
    a refresh token.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=None,
        responses={205: None},
        summary="Вийти (відкликати refresh-токен)",
        description=(
            "Додає переданий refresh-токен до чорного списку, щоб його більше "
            "не можна було обміняти на нові access-токени. Тіло: "
            "``{\"refresh\": <token>}``. Невалідний токен толерується (200)."
        ),
    )
    def post(self, request: Request) -> Response:
        """Blacklist the supplied refresh token.

        Args:
            request: Authenticated request carrying ``{"refresh": <token>}``.

        Returns:
            ``205 Reset Content`` once the token is blacklisted. An
            absent/invalid/already-blacklisted token is tolerated and returns
            ``200`` — logout must always appear to succeed (a client clearing
            local credentials should never be blocked by a bad token), and not
            leaking which tokens are valid avoids an oracle.
        """

        refresh = (request.data or {}).get("refresh")
        if not refresh:
            # Nothing to revoke (e.g. client only held an access token). Treat as
            # a successful logout so the client can clear its local state.
            return Response(status=status.HTTP_200_OK)

        try:
            RefreshToken(refresh).blacklist()
        except Exception:  # noqa: BLE001 - any bad token is a tolerated no-op
            # Invalid / expired / already-blacklisted: logout still "succeeds".
            logger.info("logout_invalid_token", extra={"user_id": request.user.pk})
            return Response(status=status.HTTP_200_OK)

        logger.info("logout_ok", extra={"user_id": request.user.pk})
        return Response(status=status.HTTP_205_RESET_CONTENT)
