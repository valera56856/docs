"""Serializers for the accounts (authentication) app.

This module defines the request/response serializers that power the three
authentication endpoints:

* :class:`EmailTokenObtainPairSerializer` — email + password to a JWT pair.
* :class:`PinLoginSerializer` — 4-digit PIN to a JWT pair (fast/biometric login).
* :class:`ProfileSerializer` — read-only representation of the caller's profile.

Why a custom token serializer:
    SimpleJWT's default ``TokenObtainPairSerializer`` authenticates by the auth
    model's ``USERNAME_FIELD`` (``username`` for the default user). The product
    requirement is to log in by **email**, so we subclass it and remap the input
    field to ``email`` while still issuing the standard access/refresh pair.
"""

from __future__ import annotations

from typing import Any

from django.contrib.auth import authenticate, get_user_model
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

User = get_user_model()


class EmailTokenObtainPairSerializer(TokenObtainPairSerializer):
    """Issue a JWT pair from an email + password.

    The default SimpleJWT serializer keys on ``username``. We rename the credential
    field to ``email`` and resolve the matching user before delegating the rest of
    the token issuance to the parent class.

    Attributes:
        username_field: Overridden to ``"email"`` so the generated serializer
            exposes an ``email`` field (and validation messages reference it).
    """

    username_field = "email"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Replace the inherited username field with an email field.

        Args:
            *args: Positional args forwarded to the DRF serializer.
            **kwargs: Keyword args forwarded to the DRF serializer.
        """

        super().__init__(*args, **kwargs)
        # Swap the auto-generated ``username`` field for an explicit email field.
        self.fields[self.username_field] = serializers.EmailField(write_only=True)
        self.fields["password"] = serializers.CharField(
            write_only=True,
            style={"input_type": "password"},
            trim_whitespace=False,
        )

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        """Authenticate by email + password and return the token pair.

        We look up the user by a case-insensitive email match, verify the password
        through Django's auth backend (keyed on the real ``USERNAME_FIELD`` — the
        default backend authenticates by username, not email), then mint the JWT
        pair via ``get_token``. We deliberately do NOT call ``super().validate``:
        SimpleJWT reads ``attrs[self.username_field]`` (== ``"email"``), which the
        resolved attrs don't carry, so delegating would raise ``KeyError``.

        Args:
            attrs: Validated input containing ``email`` and ``password``.

        Returns:
            A dict with ``access`` and ``refresh`` JWT strings.

        Raises:
            rest_framework.exceptions.AuthenticationFailed: If no active user
                matches the email or the password is wrong (raised by parent).
        """

        email = attrs.get("email", "")
        password = attrs.get("password", "")

        # Resolve the user by email (case-insensitive). We intentionally return a
        # generic failure to avoid leaking which emails exist.
        user = User.objects.filter(email__iexact=email).first()
        if user is None:
            raise serializers.ValidationError(
                {"detail": "Невірний email або пароль."}
            )

        # Verify the password via the auth backend, keyed on the real username
        # (default ModelBackend authenticates by USERNAME_FIELD, not email).
        auth_user = authenticate(
            request=self.context.get("request"),
            **{User.USERNAME_FIELD: user.get_username(), "password": password},
        )
        if auth_user is None:
            raise serializers.ValidationError(
                {"detail": "Невірний email або пароль."}
            )

        # Mint the access/refresh pair ourselves (get_token comes from
        # TokenObtainPairSerializer) — same claims/lifetimes SimpleJWT would issue.
        refresh = self.get_token(auth_user)
        return {"refresh": str(refresh), "access": str(refresh.access_token)}


class PinLoginSerializer(serializers.Serializer):
    """Validate a fast PIN login request.

    Accepts an ``email`` (to identify the profile whose PIN is checked) and a
    4-digit ``pin``. The actual hash verification happens in the view because it
    needs access to the resolved :class:`~apps.accounts.models.Profile`.

    Attributes:
        email: Email of the account attempting PIN login.
        pin: The 4-digit PIN, validated for length only here.
    """

    email = serializers.EmailField(write_only=True)
    pin = serializers.RegexField(
        r"^\d{4}$",
        write_only=True,
        error_messages={"invalid": "PIN має складатися з 4 цифр."},
    )


class SetPinSerializer(serializers.Serializer):
    """Validate a request to set/replace the caller's 4-digit PIN.

    Only the PIN itself is supplied — the account is taken from the authenticated
    request, so an operator can only set *their own* PIN. The PIN is validated for
    shape here (exactly 4 digits) and hashed in the view; it is never echoed back
    or logged.

    Attributes:
        pin: The new 4-digit PIN. ``write_only`` so it can never appear in a
            serialized response.
    """

    pin = serializers.RegexField(
        r"^\d{4}$",
        write_only=True,
        error_messages={"invalid": "PIN має складатися з 4 цифр."},
    )


class TokenPairSerializer(serializers.Serializer):
    """Response schema for a successful login: an access + refresh JWT pair.

    Used purely for OpenAPI documentation of the PIN endpoint (the SimpleJWT
    views document themselves).

    Attributes:
        access: Short-lived access token (Bearer).
        refresh: Long-lived refresh token.
    """

    access = serializers.CharField(read_only=True)
    refresh = serializers.CharField(read_only=True)


class ProfileSerializer(serializers.Serializer):
    """Read-only view of the authenticated user's profile.

    Attributes:
        email: The user's email.
        role: The profile role (``admin`` / ``operator``).
        has_pin: Whether a PIN has been set (``pin_hash`` is non-empty).
    """

    email = serializers.EmailField(read_only=True)
    role = serializers.CharField(read_only=True)
    has_pin = serializers.BooleanField(read_only=True)
