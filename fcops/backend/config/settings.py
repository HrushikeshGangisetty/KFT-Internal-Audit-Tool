"""Django settings for the FC Production, Traceability & Engineering Knowledge System."""
import os
import sys
from pathlib import Path
from datetime import timedelta

from dotenv import load_dotenv

from .db import get_databases, safe_description

# Django 5.2, DRF 3.18, django-filter and python-dotenv all declare
# Requires-Python >= 3.10. Fail with an explanation rather than an import error
# somewhere deep in a third-party package.
if sys.version_info < (3, 10):
    raise RuntimeError(
        "This project requires Python 3.10 or newer (3.12 recommended); "
        f"you are running {sys.version.split()[0]}. "
        "See the 'Python version' section of README.md."
    )

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def env(key, default=None):
    return os.environ.get(key, default)


def env_bool(key, default=False):
    return str(env(key, str(default))).lower() in ("1", "true", "yes", "on")


SECRET_KEY = env("DJANGO_SECRET_KEY", "dev-insecure-change-me-please-set-a-real-32-byte-secret")
DEBUG = env_bool("DJANGO_DEBUG", True)
ALLOWED_HOSTS = [h for h in env("DJANGO_ALLOWED_HOSTS", "*").split(",") if h]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.postgres",
    "rest_framework",
    "django_filters",
    "corsheaders",
    "accounts",
    "core",
    "fc",
    "issues",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "core.middleware.CurrentActorMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# --- Database -------------------------------------------------------------
# Configured entirely from the environment: DATABASE_URL if present, otherwise
# the individual POSTGRES_* variables. See config/db.py for the Supabase
# connection modes and why the pooler port changes Django's behaviour.
IS_TEST_RUN = "test" in sys.argv[1:2] or env_bool("DJANGO_TEST_RUN", False)
# Schema changes need a full session (advisory locks, DDL in a transaction), so
# they can be routed to MIGRATION_DATABASE_URL when normal traffic goes through
# the transaction pooler.
MIGRATION_COMMANDS = {"migrate", "makemigrations", "sqlmigrate", "showmigrations",
                      "flush", "dbcheck"}
IS_MIGRATION_RUN = bool(sys.argv[1:2]) and sys.argv[1] in MIGRATION_COMMANDS
DATABASES = get_databases(is_test_run=IS_TEST_RUN, is_migration_run=IS_MIGRATION_RUN)
# Password intentionally excluded — this is safe to print or log.
DATABASE_DESCRIPTION = safe_description(DATABASES["default"])

# Explains database failures during test setup instead of raising a raw
# psycopg2 traceback. See config/test_runner.py.
TEST_RUNNER = "config.test_runner.GuardedTestRunner"

# Django's debug page prints traceback locals, which include the psycopg2
# connection parameters — and therefore the database password. This filter
# redacts credentials from error pages. It is a safety net, not a licence to
# run with DEBUG=True on a reachable interface.
DEFAULT_EXCEPTION_REPORTER_FILTER = "config.error_filter.CredentialScrubbingFilter"

AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
     "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = env("TIME_ZONE", "UTC")
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "media/"
MEDIA_ROOT = Path(env("MEDIA_ROOT", str(BASE_DIR / "media")))

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_FILTER_BACKENDS": (
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.OrderingFilter",
    ),
    "DEFAULT_PAGINATION_CLASS": "core.pagination.DefaultPagination",
    "PAGE_SIZE": 25,
    "EXCEPTION_HANDLER": "core.exceptions.api_exception_handler",
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=int(env("JWT_ACCESS_MINUTES", "120"))),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=int(env("JWT_REFRESH_DAYS", "7"))),
    "AUTH_HEADER_TYPES": ("Bearer",),
}

CORS_ALLOW_ALL_ORIGINS = env_bool("CORS_ALLOW_ALL_ORIGINS", True)
CORS_ALLOWED_ORIGINS = [o for o in env("CORS_ALLOWED_ORIGINS", "").split(",") if o]
CSRF_TRUSTED_ORIGINS = [o for o in env("CSRF_TRUSTED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",") if o]

# --- Domain policy toggles (see IMPLEMENTATION_NOTES.md) -------------------
# Require verification (by a different user than the resolver) before an issue
# can be closed / before manager approval is allowed.
REQUIRE_INDEPENDENT_VERIFICATION = env_bool("REQUIRE_INDEPENDENT_VERIFICATION", True)
# Allow manager approval with a mandatory justification even when non-blocking
# issues remain unverified.
ALLOW_MANAGER_DEVIATION = env_bool("ALLOW_MANAGER_DEVIATION", True)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL", "INFO")},
}
