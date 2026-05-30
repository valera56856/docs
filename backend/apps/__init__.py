"""Container package for Valeraup Django applications.

This package groups all first-party Django apps for the Valeraup project
(accounts, suppliers, catalog, mapping, receipts). The backend directory is
placed on ``sys.path`` so that these apps can be imported with the
``apps.<app>`` dotted path (for example ``apps.receipts``).

Why a dedicated ``apps`` namespace:
    Keeping every domain app under a single namespace package keeps the
    project root tidy and makes the ``INSTALLED_APPS`` entries explicit and
    self-documenting (``"apps.receipts"`` rather than a bare ``"receipts"``).
"""

from __future__ import annotations
