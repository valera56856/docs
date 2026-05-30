"""Django settings for the Valeraup backend.

All environment-specific configuration is read through :mod:`environ`
(``django-environ``) so the same code runs locally, in CI, and on the Hetzner
Docker host with nothing but a ``.env`` file changing.

Sections, in order:

* Paths & environment bootstrap
* Core security / debug
* Applications & middleware
* URLs, templates, WSGI/ASGI
* Database (DATABASE_URL)
* Auth & password validation
* Internationalization
* Static / media
* Object storage (Cloudflare R2 via django-storages, env-gated)
* Django REST Framework + SimpleJWT
* drf-spectacular (OpenAPI)
* CORS
* Celery
* Gemini OCR
* SalesDrive
* Structured JSON logging

Why ``django-environ``: it gives typed env parsing (``env.bool``, ``env.list``,
``env.db``) and a single ``DATABASE_URL`` knob, which is exactly how the
docker-compose / Hetzner deploy is wired.
"""
from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import environ
from django.core.exceptions import ImproperlyConfigured

# Decompression-bomb guard (H4): cap the total pixel count Pillow will decode so
# a small, highly-compressed "bomb" image cannot exhaust memory when DRF's
# ``ImageField`` (or the OCR worker) opens an upload. This is a process-wide
# Pillow setting, so set it once here at settings import — before any image is
# ever opened. The same 40M-pixel cap is enforced per-upload in the receipts
# serializer; this is the defence-in-depth backstop inside Pillow itself.
from PIL import Image as _PILImage

_PILImage.MAX_IMAGE_PIXELS = 40_000_000

# ---------------------------------------------------------------------------
# Paths & environment bootstrap
# ---------------------------------------------------------------------------
# BASE_DIR points at ``backend/`` (the directory that contains ``manage.py`` and
# the ``valeraup`` package). Two ``.parent`` hops: settings.py -> valeraup -> backend.
BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(
    DEBUG=(bool, False),
    ALLOWED_HOSTS=(list, ["localhost", "127.0.0.1"]),
    CORS_ALLOWED_ORIGINS=(list, []),
    ACCESS_TOKEN_LIFETIME_MIN=(int, 15),
    REFRESH_TOKEN_LIFETIME_DAYS=(int, 30),
    GEMINI_MODEL=(str, "gemini-2.5-flash"),
    R2_REGION=(str, "auto"),
)

# Read ``backend/.env`` if present. In containers the variables are usually
# injected directly, so a missing file is not an error.
_env_file = BASE_DIR / ".env"
if _env_file.exists():
    environ.Env.read_env(str(_env_file))

# ---------------------------------------------------------------------------
# Core security / debug
# ---------------------------------------------------------------------------
DEBUG = env("DEBUG")
ALLOWED_HOSTS = env("ALLOWED_HOSTS")

# SECRET_KEY is fail-closed (H5). In DEBUG we fall back to a clearly-marked
# throwaway dev key so local runs need no .env. In production (DEBUG=False) the
# default is an EMPTY string: if ``SECRET_KEY`` is not supplied the next check
# raises and the process refuses to boot, rather than silently signing tokens
# with a publicly-known key. ``ImproperlyConfigured`` crashes loudly at import.
SECRET_KEY = env(
    "SECRET_KEY",
    default=("django-insecure-dev-only-do-not-use" if DEBUG else ""),
)
if not SECRET_KEY:
    raise ImproperlyConfigured("SECRET_KEY is required in production")

# ``_PROD`` gates every production-only security hardening below (cookies, HSTS,
# proxy SSL header). Derived once here so the intent reads the same everywhere.
_PROD = not DEBUG

# ---------------------------------------------------------------------------
# Transport / cookie / header hardening (M1–M4)
# ---------------------------------------------------------------------------
# These knobs are gated on ``_PROD`` so local HTTP development still works (no
# Secure-only cookies over plain http, no HSTS pinning a dev box to https).
#
# The Hetzner deploy terminates TLS at an edge proxy and forwards plain HTTP to
# gunicorn with ``X-Forwarded-Proto: https``. ``SECURE_PROXY_SSL_HEADER`` lets
# Django trust that header so ``request.is_secure()`` is correct behind the
# proxy. We deliberately do NOT set ``SECURE_SSL_REDIRECT``: the edge proxy
# already redirects http→https, and enabling it here too can cause redirect
# loops when the proxy speaks plain HTTP to the app.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# Cookies: only send over https in prod; never expose the session cookie to JS.
SESSION_COOKIE_SECURE = _PROD
CSRF_COOKIE_SECURE = _PROD
SESSION_COOKIE_HTTPONLY = True

# HSTS: instruct browsers to use https for a year (with subdomains + preload) in
# prod only. Zero in dev so a local https experiment does not pin localhost.
SECURE_HSTS_SECONDS = 31536000 if _PROD else 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = _PROD
SECURE_HSTS_PRELOAD = _PROD

# Always-on, environment-independent header hardening.
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"

# Origins Django trusts for CSRF (unsafe POST/PUT) when behind the edge proxy —
# supplied via env so prod hosts are configured without code changes.
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])

# Upload size limits (H4): cap request body and in-memory file size at ~12 MB so
# a payload larger than the per-image 10 MB serializer cap is rejected by Django
# before it is fully buffered. Bytes: 12 * 1024 * 1024.
DATA_UPLOAD_MAX_MEMORY_SIZE = 12 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 12 * 1024 * 1024

# ---------------------------------------------------------------------------
# Applications
# ---------------------------------------------------------------------------
DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    # SimpleJWT refresh-token revocation (M5): provides the OutstandingToken /
    # BlacklistedToken tables so a rotated or logged-out refresh token can be
    # blacklisted and rejected on subsequent refresh. The integrator runs
    # ``makemigrations``/``migrate`` for this app.
    "rest_framework_simplejwt.token_blacklist",
    "drf_spectacular",
    "corsheaders",
]

# The five Valeraup domain apps. AppConfig.name in each ``apps/<x>/apps.py`` is
# the dotted ``apps.<x>`` path; that is the contract shared with other agents.
LOCAL_APPS = [
    "apps.accounts",
    "apps.suppliers",
    "apps.catalog",
    "apps.mapping",
    "apps.receipts",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------
# corsheaders must sit high in the stack (before CommonMiddleware) so it can
# attach CORS headers to every response, including errors.
#
# WhiteNoise sits immediately AFTER SecurityMiddleware (its documented required
# position) so that in production gunicorn can serve the collected static assets
# (Django admin, Swagger UI) itself — compressed, with far-future cache headers —
# without a separate static web server. It is a no-op in dev: `runserver` serves
# static via staticfiles, and WhiteNoise only intercepts paths under STATIC_URL.
MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

# ---------------------------------------------------------------------------
# URLs, templates, WSGI/ASGI
# ---------------------------------------------------------------------------
ROOT_URLCONF = "valeraup.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "valeraup.wsgi.application"
ASGI_APPLICATION = "valeraup.asgi.application"

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
# A single ``DATABASE_URL`` drives the connection (PostgreSQL in every
# environment). ``conn_max_age`` keeps connections warm between requests.
DATABASES = {
    "default": env.db(
        "DATABASE_URL",
        default="postgres://valeraup:valeraup@db:5432/valeraup",
    ),
}
DATABASES["default"]["CONN_MAX_AGE"] = 60

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------------------
# Auth & password validation
# ---------------------------------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation."
        "UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation."
        "MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation."
        "CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation."
        "NumericPasswordValidator",
    },
]

# ---------------------------------------------------------------------------
# Internationalization
# ---------------------------------------------------------------------------
# The product UI is Ukrainian; keep the timezone at Europe/Kyiv and store
# timezone-aware datetimes.
LANGUAGE_CODE = "uk"
TIME_ZONE = "Europe/Kyiv"
USE_I18N = True
USE_TZ = True

# ---------------------------------------------------------------------------
# Static / media
# ---------------------------------------------------------------------------
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
# Leading slash is required so ``FileSystemStorage.url()`` returns a root-relative
# URL (``/media/receipts/...``) that the frontend and dev media-serving route can
# resolve regardless of the current request path. ``MEDIA_ROOT`` is where uploaded
# receipt photos and generated .xlsx files land when R2 is not configured.
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# ---------------------------------------------------------------------------
# Object storage (Cloudflare R2, env-gated)
# ---------------------------------------------------------------------------
# When the R2_* credentials are supplied, route the default file storage to the
# S3-compatible R2 backend (django-storages + boto3). Otherwise fall back to the
# local filesystem so development works with zero cloud setup.
R2_ACCESS_KEY_ID = env("R2_ACCESS_KEY_ID", default="")
R2_SECRET_ACCESS_KEY = env("R2_SECRET_ACCESS_KEY", default="")
R2_BUCKET_NAME = env("R2_BUCKET_NAME", default="")
R2_ENDPOINT_URL = env("R2_ENDPOINT_URL", default="")
R2_REGION = env("R2_REGION")

_R2_ENABLED = bool(
    R2_ACCESS_KEY_ID and R2_SECRET_ACCESS_KEY and R2_BUCKET_NAME and R2_ENDPOINT_URL
)

if _R2_ENABLED:
    STORAGES = {
        "default": {
            "BACKEND": "storages.backends.s3.S3Storage",
            "OPTIONS": {
                "access_key": R2_ACCESS_KEY_ID,
                "secret_key": R2_SECRET_ACCESS_KEY,
                "bucket_name": R2_BUCKET_NAME,
                "endpoint_url": R2_ENDPOINT_URL,
                "region_name": R2_REGION,
                # R2 ignores ACLs; signing v4 keeps boto3 happy against the
                # Cloudflare endpoint.
                "default_acl": None,
                "querystring_auth": True,
                "signature_version": "s3v4",
            },
        },
        # WhiteNoise compressed-manifest storage: collectstatic produces gzipped
        # copies and a content-hashed manifest so WhiteNoise (in MIDDLEWARE) can
        # serve /static/ with immutable far-future caching. User uploads (media)
        # still go to R2 via the ``default`` backend above.
        "staticfiles": {
            "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
        },
    }
else:
    STORAGES = {
        "default": {
            "BACKEND": "django.core.files.storage.FileSystemStorage",
        },
        # Same WhiteNoise static backend in the no-R2 (local/dev) case. In dev
        # `runserver` bypasses this via the staticfiles app, but keeping it here
        # means a prod-like container built from this code serves static via
        # WhiteNoise regardless of whether R2 media storage is configured.
        "staticfiles": {
            "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
        },
    }

# ---------------------------------------------------------------------------
# Cache — backs DRF throttling counters. It MUST be shared across processes in
# production: with the default per-process LocMemCache each gunicorn worker
# keeps its own counters, so the effective rate limit is multiplied by the
# worker count (a throttle bypass). In DEBUG/CI we use in-process LocMem so
# tests and local dev need no Redis.
# ---------------------------------------------------------------------------
if _PROD:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": env("CACHE_URL", default="redis://redis:6379/2"),
        }
    }
else:
    CACHES = {
        "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}
    }

# ---------------------------------------------------------------------------
# Django REST Framework + SimpleJWT
# ---------------------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    # Rate limiting (H1). The throttle CLASSES are global: every request is
    # checked against the anon/user limits, and any view that sets a
    # ``throttle_scope`` is additionally checked against that scope's RATE via
    # ScopedRateThrottle. Scopes label the sensitive endpoints (PIN/login brute
    # force, expensive OCR, the SalesDrive connectivity test) with tighter rates.
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
        "rest_framework.throttling.ScopedRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": "60/min",
        "user": "1000/day",
        "pin": "5/min",
        "login": "10/min",
        "recognize": "20/hour",
        "salesdrive_test": "10/hour",
    },
}

ACCESS_TOKEN_LIFETIME_MIN = env("ACCESS_TOKEN_LIFETIME_MIN")
REFRESH_TOKEN_LIFETIME_DAYS = env("REFRESH_TOKEN_LIFETIME_DAYS")

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=ACCESS_TOKEN_LIFETIME_MIN),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=REFRESH_TOKEN_LIFETIME_DAYS),
    # Token revocation (M5): rotate the refresh token on every use and blacklist
    # the previous one. Combined with the ``token_blacklist`` app and the logout
    # endpoint, this lets a stolen/old refresh token be invalidated server-side
    # (a JWT is otherwise valid until expiry). Requires the blacklist migrations.
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
    # Sign JWTs explicitly with SECRET_KEY (H5). SimpleJWT defaults to SECRET_KEY
    # already, but pinning it here documents the dependency and gives one obvious
    # seam to split token signing onto its own key later (rotate JWT keys without
    # invalidating Django's SECRET_KEY-derived state).
    "SIGNING_KEY": SECRET_KEY,
}

# ---------------------------------------------------------------------------
# drf-spectacular (OpenAPI / Swagger)
# ---------------------------------------------------------------------------
SPECTACULAR_SETTINGS = {
    "TITLE": "Valeraup API",
    "DESCRIPTION": (
        "Supplier-invoice OCR to SalesDrive receipt pipeline. Photograph an "
        "invoice, recognise line items with Gemini, map supplier SKUs to the "
        "SalesDrive catalog, and export an .xlsx receipt."
    ),
    "VERSION": "2.2.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
}

# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------
# The Vite dev server (and the deployed PWA origin) must be whitelisted. Values
# come from the env so production hosts are configured without code changes.
CORS_ALLOWED_ORIGINS = env("CORS_ALLOWED_ORIGINS")
CORS_ALLOW_CREDENTIALS = True

# ---------------------------------------------------------------------------
# Celery
# ---------------------------------------------------------------------------
# All values are namespaced ``CELERY_*`` so ``celery.py`` can load them via
# ``config_from_object(..., namespace="CELERY")``.
CELERY_BROKER_URL = env("CELERY_BROKER_URL", default="redis://redis:6379/0")
CELERY_RESULT_BACKEND = env(
    "CELERY_RESULT_BACKEND", default="redis://redis:6379/1"
)
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_TRACK_STARTED = True

# ---------------------------------------------------------------------------
# Gemini OCR
# ---------------------------------------------------------------------------
GEMINI_API_KEY = env("GEMINI_API_KEY", default="")
GEMINI_MODEL = env("GEMINI_MODEL")

# ---------------------------------------------------------------------------
# SalesDrive
# ---------------------------------------------------------------------------
SALESDRIVE_YML_URL = env("SALESDRIVE_YML_URL", default="")

# ---------------------------------------------------------------------------
# Structured JSON logging
# ---------------------------------------------------------------------------
# Every log record is emitted as a single JSON object via python-json-logger.
# This keeps logs greppable/queryable when shipped off the Hetzner host and lets
# us attach structured context (receipt_id, supplier_id, line counts) at the key
# pipeline steps (OCR request, mapping result, Excel generation).
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {
            "()": "pythonjsonlogger.jsonlogger.JsonFormatter",
            "format": "%(asctime)s %(levelname)s %(name)s %(message)s",
        },
    },
    "handlers": {
        "json": {
            "class": "logging.StreamHandler",
            "formatter": "json",
        },
    },
    "root": {
        "handlers": ["json"],
        "level": "INFO",
    },
    "loggers": {
        # Quiet Django's request noise to WARNING, keep our app namespaces at
        # INFO so structured pipeline events are visible.
        "django": {
            "handlers": ["json"],
            "level": "WARNING",
            "propagate": False,
        },
        "apps": {
            "handlers": ["json"],
            "level": "INFO",
            "propagate": False,
        },
        "integrations": {
            "handlers": ["json"],
            "level": "INFO",
            "propagate": False,
        },
        "celery": {
            "handlers": ["json"],
            "level": "INFO",
            "propagate": False,
        },
    },
}
