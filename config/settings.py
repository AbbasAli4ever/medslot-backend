"""
Django settings for the Clinic Appointment Booker API.

No database is used: all data lives in an in-memory Python store.
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def env_list(name: str, default: str) -> list[str]:
    return [item.strip() for item in os.environ.get(name, default).split(",") if item.strip()]


SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY",
    "django-insecure-dev-only-change-me",
)

DEBUG = os.environ.get("DJANGO_DEBUG", "True").lower() in ("1", "true", "yes")

ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")


INSTALLED_APPS = [
    "django.contrib.staticfiles",
    "rest_framework",
    "drf_spectacular",
    "corsheaders",
    "appointments",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"


# No database: data is held in an in-memory Python store.
DATABASES = {}


LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Karachi"  # The clinic's local time; "now" for booking rules.
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# Staff login (no database: one staff account configured here)
STAFF_EMAIL = os.environ.get("STAFF_EMAIL", "staff@medslot.app")
STAFF_PASSWORD = os.environ.get("STAFF_PASSWORD", "medslot123")
AUTH_TOKEN_MAX_AGE = int(os.environ.get("AUTH_TOKEN_MAX_AGE", 12 * 60 * 60))  # seconds


# Django REST Framework
REST_FRAMEWORK = {
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "appointments.authentication.BearerTokenAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.AllowAny"],
    "UNAUTHENTICATED_USER": None,
    "EXCEPTION_HANDLER": "appointments.exceptions.api_exception_handler",
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
        "rest_framework.renderers.BrowsableAPIRenderer",
    ],
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Clinic Appointment Booker API",
    "DESCRIPTION": "REST API for booking, listing and cancelling clinic appointments.",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    # PATCH only accepts a required "status", so document it as such.
    "COMPONENT_SPLIT_PATCH": False,
}


# CORS
CORS_ALLOWED_ORIGINS = env_list(
    "CORS_ALLOWED_ORIGINS",
    "http://localhost:3000,http://127.0.0.1:3000",
)
