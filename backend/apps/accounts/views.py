"""Authentication views for the accounts app.

Implements the three contract auth endpoints:

* ``POST /api/auth/login/`` — email + password to JWT pair
  (:class:`EmailTokenObtainPairView`).
* ``POST /api/auth/refresh/`` — refresh access token (SimpleJWT
  ``TokenRefreshView``, wired directly in ``urls.py``).
* ``POST /api/auth/pin/`` — 4-digit PIN to JWT pair (:class:`PinLoginView`).

All three are deliberately ``AllowAny``: they are how a client *obtains*
credentials, so requiring authentication would be circular.
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


class PinLoginView(APIView):
    """Fast login by 4-digit PIN, returning a JWT pair.

    The PWA stores the long-lived refresh token in Capacitor Secure Storage and
    lets the operator re-authenticate with a PIN (optionally behind device
    biometrics). This endpoint verifies the PIN against the user's
    :class:`~apps.accounts.models.Profile.pin_hash` and, on success, mints the
    same access/refresh pair the password flow returns.
    """

    permission_classes = [AllowAny]

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
