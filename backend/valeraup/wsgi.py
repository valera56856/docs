"""WSGI config for the Valeraup project.

Exposes the WSGI callable as a module-level variable named ``application``. This
is the entry point used by Gunicorn in production (see ``backend/Dockerfile`` and
``docker-compose.yml``).
"""
from __future__ import annotations

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "valeraup.settings")

application = get_wsgi_application()
