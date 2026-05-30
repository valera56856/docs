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
SECRET_KEY = env("SECRET_KEY", default="change-me-in-prod")
DEBUG = env("DEBUG")
ALLOWED_HOSTS = env("ALLOWED_HOSTS")

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
}

ACCESS_TOKEN_LIFETIME_MIN = env("ACCESS_TOKEN_LIFETIME_MIN")
REFRESH_TOKEN_LIFETIME_DAYS = env("REFRESH_TOKEN_LIFETIME_DAYS")

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=ACCESS_TOKEN_LIFETIME_MIN),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=REFRESH_TOKEN_LIFETIME_DAYS),
    # Rotate + blacklist on refresh would require the token_blacklist app; for
    # the skeleton we keep refresh tokens long-lived (30d) without rotation.
    "ROTATE_REFRESH_TOKENS": False,
    "AUTH_HEADER_TYPES": ("Bearer",),
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
