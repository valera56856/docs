#!/bin/sh
# Valeraup backend production entrypoint.
#
# Runs the one-time-per-boot bootstrap steps, then hands the container's PID 1
# over to gunicorn via `exec` so SIGTERM from `docker stop` / orchestrators
# reaches the web server directly (clean, fast shutdown — no shell wrapper
# swallowing signals).
#
# Steps:
#   1. migrate     — apply DB schema. Committed migrations make this a no-op
#                    once converged; safe to run on every boot (idempotent).
#   2. collectstatic — gather Django admin + Swagger UI assets into STATIC_ROOT
#                    so WhiteNoise (in MIDDLEWARE) can serve them. --noinput so
#                    it never blocks on a prompt.
#   3. exec gunicorn — 3 sync workers, 60s timeout (Gemini OCR calls run in the
#                    Celery worker, NOT here, so 60s is ample for API requests).
#
# This script is the image's default CMD. The DEV docker-compose.yml overrides
# `command:` with runserver, so dev keeps live reload and skips collectstatic.
#
# NOTE: never `docker compose down -v` in production — DB and media volumes must
# persist across redeploys. Use `build` + `up -d` (see docker-compose.prod.yml).
set -e

echo "[entrypoint] applying database migrations"
python manage.py migrate --noinput

echo "[entrypoint] collecting static files"
python manage.py collectstatic --noinput

echo "[entrypoint] starting gunicorn on 0.0.0.0:8000"
exec gunicorn valeraup.wsgi:application \
    -b 0.0.0.0:8000 \
    -w 3 \
    --timeout 60
