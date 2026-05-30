# Valeraup backend image — Django REST API + Celery worker.
#
# A single image serves both the `backend` and `worker` Compose services; the
# command differs per service (runserver/gunicorn vs. `celery ... worker`).
#
# Base: python:3.12-slim — small, modern, matches the CI Python version.

FROM python:3.12-slim

# --- Python runtime hygiene ---------------------------------------------------
# PYTHONDONTWRITEBYTECODE: no .pyc files (cleaner layers, no stale bytecode).
# PYTHONUNBUFFERED:        flush stdout/stderr immediately so JSON logs stream
#                          straight to the Docker log driver.
# PIP_NO_CACHE_DIR:        keep the image lean (no pip wheel cache).
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# --- System dependencies ------------------------------------------------------
# build-essential + libpq-dev: compile/link headers for psycopg and Pillow.
# We deliberately keep this list minimal; psycopg[binary] ships wheels, but the
# headers make source builds and other C extensions reliable across platforms.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# --- Python dependencies (cached layer) ---------------------------------------
# Copy requirements first so Docker can cache the (slow) pip install whenever
# only application source changes.
COPY requirements.txt ./
RUN pip install --upgrade pip \
    && pip install -r requirements.txt

# --- Application source --------------------------------------------------------
COPY . .

# Django dev/prod server port.
EXPOSE 8000

# Default command is the API server; Compose overrides this for the worker.
# `migrate` is run by the Compose `command`, not here, to keep the image command
# side-effect free and reusable by the worker.
CMD ["gunicorn", "valeraup.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3"]
