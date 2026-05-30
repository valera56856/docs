"""Namespace package for external service integrations.

Holds adapters that talk to third-party systems used by Valeraup:

* ``gemini`` — Gemini 2.5 Flash Vision invoice OCR.
* ``salesdrive`` — SalesDrive YML catalog fetch + parse.

Keeping integrations in their own top-level package (importable as
``integrations.<name>`` because ``backend/`` is on ``sys.path``) separates
"talk to the outside world" code from Django app/domain logic.
"""
from __future__ import annotations
