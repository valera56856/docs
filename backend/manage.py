#!/usr/bin/env python
"""Django's command-line utility for administrative tasks.

This is the standard ``manage.py`` entry point, lightly customised for the
Valeraup backend layout:

* The default settings module is ``valeraup.settings``.
* The directory containing this file (``backend/``) is added to ``sys.path`` so
  that the project package (``valeraup``) **and** the application namespaces
  (``apps.*``, ``integrations.*``) all import cleanly without an extra ``src``
  layer.

Why the explicit ``sys.path`` insert: when ``manage.py`` is invoked as a script
its own directory is normally already on ``sys.path``, but being explicit keeps
behaviour identical whether the file is executed directly, via ``python -m``, or
from inside a Docker ``WORKDIR`` that differs from the file location.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def main() -> None:
    """Run administrative tasks.

    Sets the default settings module, ensures ``backend/`` is importable, and
    delegates to Django's command executor.

    Raises:
        ImportError: If Django is not installed or not importable in the active
            environment (re-raised with a helpful hint).
    """
    # Ensure ``backend/`` (this file's parent) is importable as a source root.
    backend_dir = Path(__file__).resolve().parent
    if str(backend_dir) not in sys.path:
        sys.path.insert(0, str(backend_dir))

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "valeraup.settings")

    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:  # pragma: no cover - defensive import guard
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc

    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
