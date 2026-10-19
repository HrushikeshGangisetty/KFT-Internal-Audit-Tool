"""Django settings for the FC Production, Traceability & Engineering Knowledge System."""
import os
import sys
from pathlib import Path

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
    "accounts",
    "core",
    "fc",
    "issues",
    "access",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # Serves the built SPA (WHITENOISE_ROOT) and collected static files from
    # the same origin as the API (WP2).
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "core.middleware.AbsoluteSessionTimeoutMiddleware",
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
    # Session cookie only (WP2): no token is ever handed to the browser.
    "DEFAULT_AUTHENTICATION_CLASSES": ("core.authentication.SessionAuthentication",),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_FILTER_BACKENDS": (
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.OrderingFilter",
    ),
    "DEFAULT_PAGINATION_CLASS": "core.pagination.DefaultPagination",
    "PAGE_SIZE": 25,
    "EXCEPTION_HANDLER": "core.exceptions.api_exception_handler",
}

# --- Sessions and CSRF (WP2) ------------------------------------------------
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
# Secure cookies whenever the site is not a DEBUG dev server (HTTPS in prod).
SESSION_COOKIE_SECURE = env_bool("SESSION_COOKIE_SECURE", not DEBUG)
CSRF_COOKIE_SECURE = env_bool("CSRF_COOKIE_SECURE", not DEBUG)
# Idle timeout: the expiry slides on every request.
SESSION_COOKIE_AGE = int(env("SESSION_IDLE_SECONDS", str(8 * 3600)))
SESSION_SAVE_EVERY_REQUEST = True
# Absolute lifetime regardless of activity (core.middleware).
SESSION_ABSOLUTE_SECONDS = int(env("SESSION_ABSOLUTE_SECONDS", str(24 * 3600)))
# Login lockout (accounts.ratelimit): failures per username and per IP.
LOGIN_FAILURE_LIMIT = int(env("LOGIN_FAILURE_LIMIT", "5"))
LOGIN_LOCKOUT_SECONDS = int(env("LOGIN_LOCKOUT_SECONDS", "900"))

# --- Single origin (WP2) ------------------------------------------------------
# The production build of the frontend, served by WhiteNoise at the site root;
# any non-API path returns its index.html so deep links load the SPA.
FRONTEND_DIST = Path(env("FRONTEND_DIST", str(BASE_DIR.parent / "frontend" / "dist")))
WHITENOISE_ROOT = FRONTEND_DIST if FRONTEND_DIST.is_dir() else None
WHITENOISE_INDEX_FILE = True
# Refuse demo seeding on anything that looks like production.
PRODUCTION = env_bool("PRODUCTION", False)

# Only needed when a proxy rewrites Host; the Vite dev proxy keeps it intact.
CSRF_TRUSTED_ORIGINS = [o for o in env("CSRF_TRUSTED_ORIGINS", "").split(",") if o]

# --- Domain policy toggles (see IMPLEMENTATION_NOTES.md) -------------------
# Require verification (by a different user than the resolver) before an issue
# can be closed / before manager approval is allowed.
REQUIRE_INDEPENDENT_VERIFICATION = env_bool("REQUIRE_INDEPENDENT_VERIFICATION", True)

# PLACEHOLDER until the FC access matrix is agreed (PRD §5): members of these
# department kinds read every FC record; heads and managers always do.
FC_VISIBLE_DEPARTMENT_KINDS = [k.strip() for k in env(
    "FC_VISIBLE_DEPARTMENT_KINDS",
    "HARDWARE,FIRMWARE,SOFTWARE,MECHANICAL,TESTING,QUALITY,SERVICE").split(",") if k.strip()]
# Allow manager approval with a mandatory justification even when non-blocking
# issues remain unverified.
ALLOW_MANAGER_DEVIATION = env_bool("ALLOW_MANAGER_DEVIATION", True)

# --- Jobs, worker and alerts (WP3) -----------------------------------------
APP_VERSION = env("APP_VERSION", "dev")
JOB_MAX_ATTEMPTS = int(env("JOB_MAX_ATTEMPTS", "5"))
JOB_RETRY_BASE_SECONDS = int(env("JOB_RETRY_BASE_SECONDS", "30"))
JOB_LOCK_TIMEOUT_SECONDS = int(env("JOB_LOCK_TIMEOUT_SECONDS", "600"))
PERIODIC_INTERVAL_SECONDS = int(env("PERIODIC_INTERVAL_SECONDS", "60"))
WORKER_STALE_SECONDS = int(env("WORKER_STALE_SECONDS", "180"))
# Console in development; the approved provider only after the decision.
EMAIL_BACKEND = env("EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend")
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", "fcops@localhost")
SITE_URL = env("SITE_URL", "http://localhost:8000")
# PLACEHOLDER channels until the after-hours decision (PRD §15).
ALERT_CHANNELS_URGENT = [c for c in env("ALERT_CHANNELS_URGENT", "in_app,email").split(",") if c]
ALERT_CHANNELS_NORMAL = [c for c in env("ALERT_CHANNELS_NORMAL", "in_app").split(",") if c]

# PLACEHOLDER working calendar (Appendix A): Monday=0.
WORKING_DAYS = [int(d) for d in env("WORKING_DAYS", "0,1,2,3,4").split(",") if d]
WORKING_HOURS = tuple(int(h) for h in env("WORKING_HOURS", "10,18").split(","))
WORKING_TIMEZONE = env("WORKING_TIMEZONE", "Asia/Kolkata")

# --- Issues, routing and handoffs (WP4, WP5) -------------------------------
ATTACHMENT_MAX_BYTES = int(env("ATTACHMENT_MAX_BYTES", str(10 * 1024 * 1024)))
# PLACEHOLDER until the PRD decision: the previous team keeps read access
# after an accepted handoff ("read") or loses it ("none").
HANDOFF_PREVIOUS_TEAM_ACCESS = env("HANDOFF_PREVIOUS_TEAM_ACCESS", "read")

# --- Deadlines, waiting and reopening (WP6, WP7) ---------------------------
# PLACEHOLDER: no after-hours duty contact until the PRD decision; urgent
# alerts after hours go to the owner and the gap is shown to managers.
DUTY_CONTACT_USER_ID = int(env("DUTY_CONTACT_USER_ID", "0")) or None
WAITING_MAX_DAYS = int(env("WAITING_MAX_DAYS", "14"))
# PLACEHOLDER: who may reopen a resolved, verified or closed issue.
REOPEN_ALLOWED = [r for r in env(
    "REOPEN_ALLOWED", "accountable,queue_head,any_head,manager").split(",") if r]

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL", "INFO")},
}
