"""Accounts domain app for Valeraup.

This app owns user-adjacent data that does not belong on Django's built-in
``User`` model: the :class:`~apps.accounts.models.Profile` carries the user's
role (admin/operator) and a hashed PIN used for the fast PIN/biometric login
flow described in the product spec.

Why a separate ``Profile`` instead of a custom user model:
    The project relies on Django's stock ``auth.User`` plus SimpleJWT. A
    one-to-one ``Profile`` lets us attach role and PIN data without the
    migration cost and coupling of swapping ``AUTH_USER_MODEL`` after the fact.
"""

from __future__ import annotations
