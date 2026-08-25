"""Database configuration.

One code path builds the Django ``DATABASES`` setting from the environment.
It accepts either a single ``DATABASE_URL`` (what Supabase hands you on the
"Connect" screen) or the individual ``POSTGRES_*`` variables the project has
always used. ``DATABASE_URL`` wins when both are present.

Nothing here contains credentials — they come from the environment only, and
:func:`safe_description` deliberately omits the password so connection details
can be logged or printed without leaking a secret.

Supabase offers three ways in. Which one you use changes what Django is allowed
to do, so the mode is detected and compensated for automatically:

* **Session pooler** — ``aws-<n>-<region>.pooler.supabase.com:5432``, username
  ``postgres.<project-ref>``. Reachable over IPv4, and behaves like a normal
  PostgreSQL session: prepared statements, server-side cursors, advisory locks
  and ``CREATE DATABASE`` all work. **This is the recommended target for
  Django** and the default assumption here.
* **Transaction pooler** — same host on port ``6543``. Connections are handed
  back to the pool between statements, so server-side cursors and persistent
  connections break. Detected by port; ``CONN_MAX_AGE`` is forced to 0 and
  ``DISABLE_SERVER_SIDE_CURSORS`` is turned on so Django stays correct. Do not
  run migrations through it.
* **Direct connection** — ``db.<project-ref>.supabase.co:5432``. Full features,
  but Supabase now serves it over IPv6 only, so it fails on IPv4-only networks
  (most Windows/office/home setups without an IPv6 route).
"""
import os
from urllib.parse import parse_qsl, unquote, urlparse

LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", ""}
TRANSACTION_POOLER_PORT = "6543"


def _env(key, default=None):
    value = os.environ.get(key)
    return value if value not in (None, "") else default


def _bool(value, default=False):
    if value is None:
        return default
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def parse_database_url(url):
    """Turn a postgres:// URL into Django connection parts.

    Handles percent-encoded usernames and passwords (Supabase passwords
    routinely contain characters that must be escaped in a URL) and carries
    any query parameters through as libpq options.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("postgres", "postgresql", "psql"):
        raise ValueError(
            f"DATABASE_URL must be a postgres:// URL, got scheme '{parsed.scheme}'.")
    options = {k: v for k, v in parse_qsl(parsed.query)}
    return {
        "NAME": unquote(parsed.path.lstrip("/")) or "postgres",
        "USER": unquote(parsed.username or ""),
        "PASSWORD": unquote(parsed.password or ""),
        "HOST": parsed.hostname or "",
        "PORT": str(parsed.port) if parsed.port else "",
        "_QUERY_OPTIONS": options,
    }


def _from_individual_vars(prefix="POSTGRES"):
    return {
        "NAME": _env(f"{prefix}_DB", "fcops"),
        "USER": _env(f"{prefix}_USER", "fcops"),
        "PASSWORD": _env(f"{prefix}_PASSWORD", ""),
        "HOST": _env(f"{prefix}_HOST", "127.0.0.1"),
        "PORT": _env(f"{prefix}_PORT", "5432"),
        "_QUERY_OPTIONS": {},
    }


def is_local(host):
    return (host or "").lower() in LOCAL_HOSTS


def build_database(url=None, prefix="POSTGRES"):
    """Build one entry for Django's ``DATABASES``.

    ``url`` takes precedence; otherwise the ``<prefix>_*`` variables are used.
    """
    parts = parse_database_url(url) if url else _from_individual_vars(prefix)
    query_options = parts.pop("_QUERY_OPTIONS")

    host, port = parts["HOST"], str(parts["PORT"] or "")

    # TLS: required for anything off-box, pointless for a local socket.
    # An explicit sslmode (in the URL or the environment) always wins.
    sslmode = (query_options.get("sslmode")
               or _env(f"{prefix}_SSLMODE")
               or _env("DB_SSLMODE")
               or ("disable" if is_local(host) else "require"))

    options = {k: v for k, v in query_options.items() if k != "sslmode"}
    if sslmode != "disable":
        options["sslmode"] = sslmode
    options.setdefault("connect_timeout", int(_env("DB_CONNECT_TIMEOUT", "10")))
    # Shows up in Supabase's dashboard and pg_stat_activity, which makes it
    # obvious which client is holding a connection.
    options.setdefault("application_name", _env("DB_APPLICATION_NAME", "fcops-django"))

    transaction_pooler = port == TRANSACTION_POOLER_PORT
    # Persistent connections are a big win against a local server, but a
    # liability against a pooled remote one. Django's dev server creates a new
    # thread per request and each thread opens its own connection, so with
    # CONN_MAX_AGE > 0 connections accumulate until the pooler refuses new
    # clients ("max clients reached in session mode"). Default to 0 for remote
    # hosts and raise it deliberately when running under a WSGI server with a
    # bounded thread pool (see README -> Connection limits).
    default_max_age = "60" if is_local(host) else "0"
    conn_max_age = int(_env("DB_CONN_MAX_AGE", default_max_age))
    if transaction_pooler:
        # PgBouncer in transaction mode returns the connection to the pool
        # between statements, so Django must not keep connections open or use
        # server-side cursors.
        conn_max_age = 0

    return {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": parts["NAME"],
        "USER": parts["USER"],
        "PASSWORD": parts["PASSWORD"],
        "HOST": host,
        "PORT": port,
        "CONN_MAX_AGE": conn_max_age,
        "CONN_HEALTH_CHECKS": conn_max_age > 0,
        "DISABLE_SERVER_SIDE_CURSORS": transaction_pooler,
        "OPTIONS": options,
    }


def connection_mode(config):
    """Human-readable description of how we are reaching PostgreSQL."""
    host = (config.get("HOST") or "").lower()
    port = str(config.get("PORT") or "")
    if is_local(host):
        return "local PostgreSQL"
    if "pooler.supabase.com" in host:
        return ("Supabase transaction pooler" if port == TRANSACTION_POOLER_PORT
                else "Supabase session pooler")
    if host.endswith(".supabase.co"):
        return "Supabase direct connection (IPv6 only)"
    return "remote PostgreSQL"


def safe_description(config):
    """Connection details with the password removed, safe to print or log."""
    return {
        "mode": connection_mode(config),
        "host": config.get("HOST"),
        "port": config.get("PORT"),
        "database": config.get("NAME"),
        "user": config.get("USER"),
        "sslmode": config.get("OPTIONS", {}).get("sslmode", "disable"),
        "conn_max_age": config.get("CONN_MAX_AGE"),
        "server_side_cursors": not config.get("DISABLE_SERVER_SIDE_CURSORS", False),
    }


def get_databases(is_test_run=False, is_migration_run=False):
    """The full ``DATABASES`` dict.

    During a test run the suite creates and drops a database and writes
    destructive fixtures, so it must never point at the shared Supabase
    instance by accident. If ``TEST_DATABASE_URL`` (or ``TEST_POSTGRES_*``) is
    configured it is used instead; otherwise tests fall back to the local
    PostgreSQL defaults. Set ``ALLOW_TESTS_ON_REMOTE_DB=True`` to override.
    """
    # Schema changes need a real session: prepared statements, advisory locks
    # and DDL in a transaction. The transaction pooler cannot provide that, so
    # a separate session-pooler URL can be supplied for migrations while normal
    # traffic goes through the transaction pooler.
    migration_url = _env("MIGRATION_DATABASE_URL") or _env("DIRECT_DATABASE_URL")
    if is_migration_run and migration_url:
        return {"default": build_database(migration_url)}

    primary = build_database(_env("DATABASE_URL"))

    if not is_test_run:
        return {"default": primary}

    test_url = _env("TEST_DATABASE_URL")
    if test_url:
        return {"default": build_database(test_url)}
    if _env("TEST_POSTGRES_HOST") or _env("TEST_POSTGRES_DB"):
        return {"default": build_database(None, prefix="TEST_POSTGRES")}
    if is_local(primary["HOST"]) or _bool(_env("ALLOW_TESTS_ON_REMOTE_DB")):
        return {"default": primary}

    # Remote primary and no test database configured: refuse to touch it.
    # Prefer the POSTGRES_* variables if they describe a local server, so a
    # developer who set up local PostgreSQL with their own credentials does not
    # also have to set TEST_DATABASE_URL.
    fallback = build_database(None, prefix="POSTGRES")
    if not is_local(fallback["HOST"]):
        fallback = build_database("postgresql://fcops:fcops@127.0.0.1:5432/fcops")
    fallback["_REDIRECTED_FROM_REMOTE"] = True
    return {"default": fallback}
