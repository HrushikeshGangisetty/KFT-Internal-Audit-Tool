"""Test runner that explains database problems instead of dumping a traceback.

The suite creates, populates and drops a database, so ``config.db`` refuses to
let it run against a remote primary (the shared Supabase instance) and
redirects it to a local PostgreSQL. When that local server is missing, the raw
psycopg2 error — "connection to server at 127.0.0.1 refused" — looks like a
misconfiguration rather than the safety net working as intended. This runner
says what actually happened and what to do about it.
"""
from django.conf import settings
from django.db.utils import OperationalError
from django.test.runner import DiscoverRunner

from .db import safe_description


class GuardedTestRunner(DiscoverRunner):
    def setup_databases(self, **kwargs):
        config = settings.DATABASES["default"]
        redirected = config.get("_REDIRECTED_FROM_REMOTE")
        if redirected:
            self.log(
                "\nDATABASE_URL points at a remote server. The test suite creates, "
                "populates and drops a database, so it has been redirected to "
                f"{config['HOST']}:{config['PORT']}/{config['NAME']} to protect the "
                "shared data.")
        try:
            return super().setup_databases(**kwargs)
        except OperationalError as exc:
            raise SystemExit(self._explain(config, redirected, exc)) from None

    @staticmethod
    def _explain(config, redirected, exc):
        where = safe_description(config)
        lines = [
            "",
            "=" * 72,
            "The test database could not be reached.",
            "=" * 72,
            f"  tried: {where['host']}:{where['port']}/{where['database']} "
            f"as {where['user']}",
            f"  error: {str(exc).strip().splitlines()[0]}",
            "",
        ]
        if redirected:
            lines += [
                "This is the safety guard, not a misconfiguration. DATABASE_URL",
                "points at a shared remote database; the suite would CREATE and",
                "DROP a database there, so it was redirected to local PostgreSQL",
                "instead — and no local PostgreSQL is running.",
                "",
                "Pick one:",
                "",
                "  1. Install PostgreSQL locally (recommended). Then:",
                '       psql -U postgres -c "CREATE USER fcops WITH PASSWORD \'fcops\';"',
                '       psql -U postgres -c "ALTER USER fcops CREATEDB;"',
                '       psql -U postgres -c "CREATE DATABASE fcops OWNER fcops;"',
                "     and set POSTGRES_PASSWORD in .env to match.",
                "",
                "  2. Run PostgreSQL in Docker:",
                "       docker run -d --name fcops-pg -p 5432:5432 \\",
                "         -e POSTGRES_USER=fcops -e POSTGRES_PASSWORD=fcops \\",
                "         -e POSTGRES_DB=fcops postgres:17",
                "",
                "  3. Point TEST_DATABASE_URL at a SEPARATE database you are happy",
                "     to have created and dropped repeatedly.",
                "",
                "Do NOT set ALLOW_TESTS_ON_REMOTE_DB unless that database is",
                "disposable — it removes this protection.",
            ]
        else:
            lines += [
                "Check that PostgreSQL is running and that the credentials in",
                "backend/.env are correct.",
            ]
        lines += ["", "See the 'Running the tests' section of README.md.", ""]
        return "\n".join(lines)
