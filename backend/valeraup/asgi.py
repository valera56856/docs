"""ASGI config for the Valeraup project.

Exposes the ASGI callable as a module-level variable named ``application``.
Provided for completeness / future async needs (e.g. websockets). The default
deploy serves WSGI via Gunicorn; this module lets an ASGI server be swapped in
without code changes.
"""
from __future__ import annotations

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "valeraup.settings")

application = get_asgi_application()
