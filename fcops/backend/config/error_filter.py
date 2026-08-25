"""Keep database credentials out of Django's debug error pages.

Django's ``SafeExceptionReporterFilter`` masks *settings* whose names look
sensitive, but it does not touch local variables inside traceback frames. When
psycopg2 fails to connect, the frame holds ``conn_params`` and a ``dsn`` string
that both contain the database password in clear text — so any error page
rendered with DEBUG=True leaks it to whoever can reach the server.

This filter redacts the live database password (and anything that looks like a
password inside a postgres URL or libpq DSN) from every frame's locals and from
the request payload.
"""
import re

from django.conf import settings
from django.views.debug import SafeExceptionReporterFilter

REDACTED = "***REDACTED***"

# password=<value> in a libpq DSN, and ://user:<value>@ in a URL.
_DSN_PASSWORD = re.compile(r"(password=)([^\s'\"]+)")
_URL_PASSWORD = re.compile(r"(://[^:/\s]+:)([^@/\s]+)(@)")


def _live_passwords():
    values = set()
    for config in getattr(settings, "DATABASES", {}).values():
        password = config.get("PASSWORD")
        if password:
            values.add(str(password))
    return values


def scrub(value):
    """Redact credentials from a value of any type, recursively."""
    if isinstance(value, str):
        for password in _live_passwords():
            if password in value:
                value = value.replace(password, REDACTED)
        value = _DSN_PASSWORD.sub(rf"\1{REDACTED}", value)
        value = _URL_PASSWORD.sub(rf"\1{REDACTED}\3", value)
        return value
    if isinstance(value, dict):
        return {k: (REDACTED if str(k).lower() in ("password", "passwd", "pwd")
                    else scrub(v))
                for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        cleaned = [scrub(v) for v in value]
        return type(value)(cleaned) if not isinstance(value, set) else set(cleaned)
    return value


class CredentialScrubbingFilter(SafeExceptionReporterFilter):
    def get_traceback_frame_variables(self, request, tb_frame):
        variables = super().get_traceback_frame_variables(request, tb_frame)
        cleaned = []
        for name, value in variables:
            if str(name).lower() in ("password", "passwd", "pwd"):
                cleaned.append((name, REDACTED))
                continue
            try:
                cleaned.append((name, scrub(value)))
            except Exception:
                # Never let scrubbing itself break the error page.
                cleaned.append((name, REDACTED))
        return cleaned

    def get_safe_settings(self):
        return scrub(super().get_safe_settings())
