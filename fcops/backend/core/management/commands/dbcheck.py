"""Verify the database connection and the PostgreSQL-specific behaviour this
project depends on.

Run this immediately after pointing the project at a new database (Supabase or
otherwise). It never prints the password.

    python manage.py dbcheck
    python manage.py dbcheck --deep      # also exercises search and the audit trigger
"""
from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import connection, transaction

OK = "  [ok]   "
BAD = "  [FAIL] "
INFO = "  [info] "


class Command(BaseCommand):
    help = "Check database connectivity and PostgreSQL feature support."

    def add_arguments(self, parser):
        parser.add_argument("--deep", action="store_true",
                            help="Also test full-text search and audit immutability "
                                 "(writes and rolls back a temporary row).")

    def handle(self, *args, **options):
        failures = []

        self.stdout.write(self.style.MIGRATE_HEADING("Connection"))
        for key, value in settings.DATABASE_DESCRIPTION.items():
            self.stdout.write(f"{INFO}{key}: {value}")

        try:
            with connection.cursor() as cur:
                cur.execute("SELECT version(), current_database(), current_user, "
                            "inet_server_addr()::text")
                version, database, user, server_ip = cur.fetchone()
            self.stdout.write(f"{OK}connected")
            self.stdout.write(f"{INFO}server: {version.split(',')[0]}")
            self.stdout.write(f"{INFO}database={database} user={user} "
                              f"server={server_ip or 'n/a'}")
        except Exception as exc:
            self.stdout.write(f"{BAD}could not connect: {exc}")
            self.stdout.write(self.style.ERROR(
                "\nCheck DATABASE_URL in backend/.env. For Supabase, use the "
                "session pooler host (port 5432) — the direct db.<ref>.supabase.co "
                "host is IPv6-only and will time out on an IPv4 network."))
            return

        self._connection_budget()

        self.stdout.write(self.style.MIGRATE_HEADING("Capabilities"))
        checks = [
            ("plpgsql (required by the audit trigger)",
             "SELECT 1 FROM pg_language WHERE lanname='plpgsql'"),
            ("to_tsvector / full-text search",
             "SELECT to_tsvector('english', 'gps not detected') @@ "
             "websearch_to_tsquery('english', 'gps detected')"),
            ("GIN index support",
             "SELECT 1 FROM pg_am WHERE amname='gin'"),
            ("jsonb", "SELECT '{\"a\":1}'::jsonb ? 'a'"),
        ]
        for label, sql in checks:
            try:
                with connection.cursor() as cur:
                    cur.execute(sql)
                    row = cur.fetchone()
                if row and row[0]:
                    self.stdout.write(f"{OK}{label}")
                else:
                    failures.append(label)
                    self.stdout.write(f"{BAD}{label}")
            except Exception as exc:
                failures.append(label)
                self.stdout.write(f"{BAD}{label}: {exc}")

        self.stdout.write(self.style.MIGRATE_HEADING("Schema"))
        expectations = [
            ("core_auditlogentry table", """
                SELECT 1 FROM information_schema.tables
                WHERE table_name = 'core_auditlogentry'"""),
            ("append-only audit trigger", """
                SELECT 1 FROM pg_trigger
                WHERE tgname = 'core_auditlog_no_update' AND NOT tgisinternal"""),
            ("issue search_vector GIN index", """
                SELECT 1 FROM pg_indexes
                WHERE tablename = 'issues_issue' AND indexdef ILIKE '%gin%'"""),
            ("known-issue GIN index", """
                SELECT 1 FROM pg_indexes
                WHERE tablename = 'issues_knownissue' AND indexdef ILIKE '%gin%'"""),
        ]
        for label, sql in expectations:
            try:
                with connection.cursor() as cur:
                    cur.execute(sql)
                    found = cur.fetchone() is not None
                if found:
                    self.stdout.write(f"{OK}{label}")
                else:
                    failures.append(label)
                    self.stdout.write(f"{BAD}{label} missing — run "
                                      f"'python manage.py migrate'")
            except Exception as exc:
                failures.append(label)
                self.stdout.write(f"{BAD}{label}: {exc}")

        if options["deep"]:
            self.stdout.write(self.style.MIGRATE_HEADING("Behaviour"))
            self._deep_checks(failures)

        self.stdout.write("")
        if failures:
            self.stdout.write(self.style.ERROR(
                f"{len(failures)} check(s) failed: " + "; ".join(failures)))
            raise SystemExit(1)
        self.stdout.write(self.style.SUCCESS("All database checks passed."))

    def _connection_budget(self):
        """How many connections this app is holding. Pool exhaustion is the
        most common runtime failure against a hosted pooler."""
        try:
            with connection.cursor() as cur:
                cur.execute("""
                    SELECT count(*) FILTER (WHERE application_name = %s),
                           count(*)
                    FROM pg_stat_activity
                    WHERE datname = current_database()""",
                            [settings.DATABASES["default"]
                             .get("OPTIONS", {})
                             .get("application_name", "fcops-django")])
                ours, total = cur.fetchone()
            self.stdout.write(f"{INFO}open connections: {ours} from this app, "
                              f"{total} total on this database")
            if ours and ours > 8:
                self.stdout.write(
                    f"{INFO}that is high — if you hit 'max clients reached', stop "
                    f"the API server to release them and set DB_CONN_MAX_AGE=0")
        except Exception:
            pass  # pg_stat_activity is not essential to the check.

    def _deep_checks(self, failures):
        from core.models import AuditLogEntry
        from issues.models import Issue
        from issues.search import search_issues

        # Full-text search over real data.
        try:
            total = Issue.objects.count()
            hits = search_issues(Issue.objects.all(), text="gps not detected").count()
            self.stdout.write(f"{OK}tsvector search ran over {total} issue(s), "
                              f"{hits} hit(s) for 'gps not detected'")
            if total and not Issue.objects.filter(search_vector__isnull=False).exists():
                failures.append("search_vector never populated")
                self.stdout.write(f"{BAD}search_vector is NULL on every issue — "
                                  f"run 'python manage.py reindex_search'")
        except Exception as exc:
            failures.append("full-text search")
            self.stdout.write(f"{BAD}full-text search: {exc}")

        # The audit trigger must reject UPDATE and DELETE even from raw SQL.
        entry = AuditLogEntry.objects.order_by("-id").first()
        if entry is None:
            self.stdout.write(f"{INFO}no audit rows yet — immutability not exercised")
            return
        for operation, sql in (
            ("UPDATE", "UPDATE core_auditlogentry SET note = 'tamper' WHERE id = %s"),
            ("DELETE", "DELETE FROM core_auditlogentry WHERE id = %s"),
        ):
            try:
                with transaction.atomic():
                    with connection.cursor() as cur:
                        cur.execute(sql, [entry.pk])
                    raise AssertionError("no error raised")
            except AssertionError:
                failures.append(f"audit log accepted a raw {operation}")
                self.stdout.write(f"{BAD}audit log accepted a raw {operation} — "
                                  f"the append-only trigger is not installed")
            except Exception:
                self.stdout.write(f"{OK}audit log rejected a raw {operation}")
