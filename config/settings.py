"""
Django settings for PleaseFix.

12-factor: all deploy-specific values come from the environment (see
.env.example). No code changes between dev, sandbox, and production —
same image, different env. See docs/DESIGN.md.
"""

from pathlib import Path
from typing import Any

import environ

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(
    DEBUG=(bool, False),
    ALLOWED_HOSTS=(list, ["localhost", "127.0.0.1"]),
    TIME_ZONE=(str, "Asia/Kuala_Lumpur"),
    LANGUAGE_CODE=(str, "en"),
    # Map defaults: deploy-specific, never code literals (DESIGN §2).
    MAP_CENTER_LAT=(float, 3.1390),
    MAP_CENTER_LON=(float, 101.6869),
    MAP_DEFAULT_ZOOM=(int, 12),
    SITE_NAME=(str, "PleaseFix"),
    GDAL_LIBRARY_PATH=(str, ""),
    GEOS_LIBRARY_PATH=(str, ""),
)

environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("SECRET_KEY", default="dev-only-insecure-key")  # noqa: S106
DEBUG = env("DEBUG")
ALLOWED_HOSTS = env("ALLOWED_HOSTS")

# Homebrew/macOS local dev: point these at your libgdal/libgeos dylibs.
# Ignored when the path doesn't exist, so the same .env works inside the
# Linux containers (which find the libraries without help).
if env("GDAL_LIBRARY_PATH") and Path(env("GDAL_LIBRARY_PATH")).exists():
    GDAL_LIBRARY_PATH = env("GDAL_LIBRARY_PATH")
if env("GEOS_LIBRARY_PATH") and Path(env("GEOS_LIBRARY_PATH")).exists():
    GEOS_LIBRARY_PATH = env("GEOS_LIBRARY_PATH")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sites",
    "django.contrib.gis",
    "allauth",
    "allauth.account",
    "django_htmx",
    "core",
    "api",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "allauth.account.middleware.AccountMiddleware",
    "django_htmx.middleware.HtmxMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "core.context_processors.site_settings",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": env.db_url(
        "DATABASE_URL",
        default="postgis://pleasefix:pleasefix@localhost:5432/pleasefix",
    )
}
DATABASES["default"]["ENGINE"] = "django.contrib.gis.db.backends.postgis"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]

SITE_ID = 1
SITE_NAME = env("SITE_NAME")

# i18n: BM + EN from day one (docs/DESIGN.md — bilingual or never dig out).
LANGUAGE_CODE = env("LANGUAGE_CODE")
LANGUAGES = [("ms", "Bahasa Melayu"), ("en", "English")]
LOCALE_PATHS = [BASE_DIR / "locale"]
TIME_ZONE = env("TIME_ZONE")
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
STORAGES: dict[str, dict[str, Any]] = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

# Object storage: the app speaks only "dumb S3" (put/get/presign/delete).
# When S3_* env vars are set, photos go to any S3-compatible backend
# (VersityGW in the default compose bundle).
if env("S3_ENDPOINT_URL", default=""):
    STORAGES["default"] = {
        "BACKEND": "storages.backends.s3.S3Storage",
        "OPTIONS": {
            "endpoint_url": env("S3_ENDPOINT_URL"),
            "access_key": env("S3_ACCESS_KEY"),
            "secret_key": env("S3_SECRET_KEY"),
            "bucket_name": env("S3_BUCKET", default="pleasefix"),
            "addressing_style": "path",
        },
    }

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

CELERY_BROKER_URL = env("REDIS_URL", default="redis://localhost:6379/0")
CELERY_TASK_ACKS_LATE = True

EMAIL_BACKEND = env("EMAIL_BACKEND", default="django.core.mail.backends.console.EmailBackend")

# Deploy-specific map configuration (config, never code literals).
MAP_CENTER = {"lat": env("MAP_CENTER_LAT"), "lon": env("MAP_CENTER_LON")}
MAP_DEFAULT_ZOOM = env("MAP_DEFAULT_ZOOM")

if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])
