"""Database configuration: URL parsing, Supabase pooler handling, TLS defaults,
credential hygiene and the guard that keeps the test suite off a shared
database."""
import os
from unittest import mock

from django.test import SimpleTestCase

from config import db

SESSION_POOLER = ("postgresql://postgres.abcdefghijklmnop:s3cr3t"
                  "@aws-0-ap-south-1.pooler.supabase.com:5432/postgres")
TXN_POOLER = ("postgresql://postgres.abcdefghijklmnop:s3cr3t"
              "@aws-0-ap-south-1.pooler.supabase.com:6543/postgres")
DIRECT = "postgresql://postgres:s3cr3t@db.abcdefghijklmnop.supabase.co:5432/postgres"
LOCAL = "postgresql://fcops:fcops@127.0.0.1:5432/fcops"


class UrlParsingTests(SimpleTestCase):
    def test_parses_standard_url(self):
        config = db.build_database(SESSION_POOLER)
        self.assertEqual(config["ENGINE"], "django.db.backends.postgresql")
        self.assertEqual(config["NAME"], "postgres")
        self.assertEqual(config["USER"], "postgres.abcdefghijklmnop")
        self.assertEqual(config["PASSWORD"], "s3cr3t")
        self.assertEqual(config["HOST"], "aws-0-ap-south-1.pooler.supabase.com")
        self.assertEqual(config["PORT"], "5432")

    def test_percent_encoded_credentials_are_decoded(self):
        """Supabase passwords routinely contain characters that must be escaped."""
        url = ("postgresql://postgres.ref:p%40ss%3Aw%2Ford%231"
               "@aws-0-eu-west-1.pooler.supabase.com:5432/postgres")
        self.assertEqual(db.build_database(url)["PASSWORD"], "p@ss:w/ord#1")

    def test_rejects_non_postgres_scheme(self):
        with self.assertRaises(ValueError):
            db.build_database("mysql://user:pw@host:3306/db")

    def test_query_parameters_become_libpq_options(self):
        config = db.build_database(SESSION_POOLER + "?sslmode=verify-full&target_session_attrs=read-write")
        self.assertEqual(config["OPTIONS"]["sslmode"], "verify-full")
        self.assertEqual(config["OPTIONS"]["target_session_attrs"], "read-write")

    def test_individual_variables_used_when_no_url(self):
        env = {"POSTGRES_DB": "d", "POSTGRES_USER": "u", "POSTGRES_PASSWORD": "p",
               "POSTGRES_HOST": "example.internal", "POSTGRES_PORT": "5555"}
        with mock.patch.dict(os.environ, env, clear=False):
            config = db.build_database(None)
        self.assertEqual(config["HOST"], "example.internal")
        self.assertEqual(config["PORT"], "5555")
        self.assertEqual(config["NAME"], "d")


class TlsTests(SimpleTestCase):
    def test_remote_hosts_require_tls_by_default(self):
        self.assertEqual(db.build_database(SESSION_POOLER)["OPTIONS"]["sslmode"],
                         "require")

    def test_local_hosts_do_not_force_tls(self):
        self.assertNotIn("sslmode", db.build_database(LOCAL)["OPTIONS"])

    def test_explicit_sslmode_wins(self):
        with mock.patch.dict(os.environ, {"DB_SSLMODE": "verify-full"}, clear=False):
            self.assertEqual(db.build_database(SESSION_POOLER)["OPTIONS"]["sslmode"],
                             "verify-full")


class PoolerModeTests(SimpleTestCase):
    def test_session_pooler_keeps_full_postgres_behaviour(self):
        """Session mode supports server-side cursors; connection lifetime is a
        separate concern covered by ConnectionLifetimeTests."""
        config = db.build_database(SESSION_POOLER)
        self.assertFalse(config["DISABLE_SERVER_SIDE_CURSORS"])
        self.assertEqual(db.connection_mode(config), "Supabase session pooler")

    def test_transaction_pooler_disables_incompatible_features(self):
        """PgBouncer in transaction mode cannot hold server-side cursors or
        persistent connections."""
        config = db.build_database(TXN_POOLER)
        self.assertTrue(config["DISABLE_SERVER_SIDE_CURSORS"])
        self.assertEqual(config["CONN_MAX_AGE"], 0)
        self.assertFalse(config["CONN_HEALTH_CHECKS"])
        self.assertEqual(db.connection_mode(config), "Supabase transaction pooler")

    def test_direct_connection_is_identified(self):
        self.assertEqual(db.connection_mode(db.build_database(DIRECT)),
                         "Supabase direct connection (IPv6 only)")


class ConnectionLifetimeTests(SimpleTestCase):
    """Django's dev server opens a connection per request thread. Against a
    pooled remote host, persistent connections accumulate until the pooler
    refuses new clients."""

    def test_remote_hosts_do_not_hold_persistent_connections_by_default(self):
        for url in (SESSION_POOLER, TXN_POOLER, DIRECT):
            with self.subTest(url=url):
                self.assertEqual(db.build_database(url)["CONN_MAX_AGE"], 0)

    def test_local_hosts_keep_persistent_connections(self):
        self.assertEqual(db.build_database(LOCAL)["CONN_MAX_AGE"], 60)

    def test_persistent_connections_can_be_opted_into(self):
        """Valid under a WSGI server with a bounded thread pool."""
        with mock.patch.dict(os.environ, {"DB_CONN_MAX_AGE": "60"}, clear=False):
            self.assertEqual(db.build_database(SESSION_POOLER)["CONN_MAX_AGE"], 60)

    def test_transaction_pooler_overrides_the_opt_in(self):
        with mock.patch.dict(os.environ, {"DB_CONN_MAX_AGE": "600"}, clear=False):
            self.assertEqual(db.build_database(TXN_POOLER)["CONN_MAX_AGE"], 0)


class MigrationRoutingTests(SimpleTestCase):
    """Schema changes need a real session, which the transaction pooler cannot
    provide."""

    def test_migrations_use_the_migration_url_when_set(self):
        env = {"DATABASE_URL": TXN_POOLER, "MIGRATION_DATABASE_URL": SESSION_POOLER}
        with mock.patch.dict(os.environ, env, clear=False):
            migrating = db.get_databases(is_migration_run=True)["default"]
            serving = db.get_databases(is_migration_run=False)["default"]
        self.assertEqual(migrating["PORT"], "5432")
        self.assertEqual(serving["PORT"], "6543")

    def test_migrations_fall_back_to_the_primary_url(self):
        with mock.patch.dict(os.environ, {"DATABASE_URL": SESSION_POOLER},
                             clear=False):
            os.environ.pop("MIGRATION_DATABASE_URL", None)
            os.environ.pop("DIRECT_DATABASE_URL", None)
            config = db.get_databases(is_migration_run=True)["default"]
        self.assertEqual(config["HOST"], "aws-0-ap-south-1.pooler.supabase.com")


class DebugPageCredentialTests(SimpleTestCase):
    """Django's debug page prints traceback locals, which for a failed psycopg2
    connect include the password in clear text."""

    def setUp(self):
        from config.error_filter import CredentialScrubbingFilter
        self.filter = CredentialScrubbingFilter()

    def test_password_is_scrubbed_from_a_libpq_dsn(self):
        from config.error_filter import REDACTED, scrub
        dsn = ("dbname=postgres sslmode=require user=postgres.ref "
               "password=SuperSecret1 host=db.example port=5432")
        cleaned = scrub(dsn)
        self.assertNotIn("SuperSecret1", cleaned)
        self.assertIn(REDACTED, cleaned)
        self.assertIn("user=postgres.ref", cleaned)

    def test_password_is_scrubbed_from_a_connection_url(self):
        from config.error_filter import scrub
        cleaned = scrub("postgresql://postgres.ref:SuperSecret1@host:5432/postgres")
        self.assertNotIn("SuperSecret1", cleaned)
        self.assertIn("postgres.ref", cleaned)

    def test_password_key_in_a_dict_is_redacted(self):
        from config.error_filter import REDACTED, scrub
        cleaned = scrub({"user": "postgres.ref", "password": "SuperSecret1",
                         "host": "db.example"})
        self.assertEqual(cleaned["password"], REDACTED)
        self.assertEqual(cleaned["user"], "postgres.ref")

    def test_live_database_password_is_scrubbed_anywhere_it_appears(self):
        from django.test import override_settings
        from config.error_filter import scrub
        databases = {"default": {"ENGINE": "django.db.backends.postgresql",
                                 "PASSWORD": "LiveSecret99"}}
        with override_settings(DATABASES=databases):
            self.assertNotIn("LiveSecret99",
                             scrub("some frame local holding LiveSecret99 inline"))

    def test_scrubbing_survives_unusual_values(self):
        from config.error_filter import scrub
        for value in (None, 42, object(), b"bytes", {"a": [1, {"password": "x"}]}):
            scrub(value)


class CredentialHygieneTests(SimpleTestCase):
    def test_safe_description_never_contains_the_password(self):
        description = db.safe_description(db.build_database(SESSION_POOLER))
        self.assertNotIn("s3cr3t", repr(description))
        self.assertNotIn("PASSWORD", description)
        self.assertEqual(description["user"], "postgres.abcdefghijklmnop")

    def test_settings_expose_a_password_free_description(self):
        """DATABASE_DESCRIPTION is printed by dbcheck, so it must carry only
        the allow-listed non-secret keys."""
        from django.conf import settings
        allowed = {"mode", "host", "port", "database", "user", "sslmode",
                   "conn_max_age", "server_side_cursors"}
        self.assertEqual(set(settings.DATABASE_DESCRIPTION), allowed)
        # A password that is not also the database name or username must never
        # appear in the description. (Checked with a synthetic config so the
        # assertion is meaningful regardless of local dev credentials.)
        config = db.build_database(
            "postgresql://someuser:uniquesecretvalue@remote.example:5432/somedb")
        self.assertNotIn("uniquesecretvalue", repr(db.safe_description(config)))


class TestDatabaseGuardTests(SimpleTestCase):
    """The suite creates, populates and drops a database. It must never do that
    to the shared Supabase instance by accident."""

    def test_remote_primary_is_not_used_for_tests(self):
        with mock.patch.dict(os.environ, {"DATABASE_URL": SESSION_POOLER},
                             clear=False):
            os.environ.pop("TEST_DATABASE_URL", None)
            os.environ.pop("ALLOW_TESTS_ON_REMOTE_DB", None)
            config = db.get_databases(is_test_run=True)["default"]
        self.assertTrue(db.is_local(config["HOST"]),
                        "test run must fall back to a local database")

    def test_explicit_test_database_url_is_honoured(self):
        with mock.patch.dict(os.environ,
                             {"DATABASE_URL": SESSION_POOLER,
                              "TEST_DATABASE_URL": LOCAL}, clear=False):
            config = db.get_databases(is_test_run=True)["default"]
        self.assertEqual(config["HOST"], "127.0.0.1")
        self.assertEqual(config["NAME"], "fcops")

    def test_opt_in_allows_remote_test_database(self):
        with mock.patch.dict(os.environ,
                             {"DATABASE_URL": SESSION_POOLER,
                              "ALLOW_TESTS_ON_REMOTE_DB": "True"}, clear=False):
            os.environ.pop("TEST_DATABASE_URL", None)
            config = db.get_databases(is_test_run=True)["default"]
        self.assertEqual(config["HOST"], "aws-0-ap-south-1.pooler.supabase.com")

    def test_redirected_fallback_is_flagged_for_the_test_runner(self):
        """GuardedTestRunner uses this flag to explain *why* it is pointing at
        localhost when the connection fails."""
        with mock.patch.dict(os.environ, {"DATABASE_URL": SESSION_POOLER},
                             clear=False):
            os.environ.pop("TEST_DATABASE_URL", None)
            os.environ.pop("ALLOW_TESTS_ON_REMOTE_DB", None)
            config = db.get_databases(is_test_run=True)["default"]
        self.assertTrue(config.get("_REDIRECTED_FROM_REMOTE"))

    def test_local_postgres_vars_are_reused_for_the_fallback(self):
        """A developer who set up local PostgreSQL with their own credentials
        should not also have to set TEST_DATABASE_URL."""
        env = {"DATABASE_URL": SESSION_POOLER, "POSTGRES_HOST": "127.0.0.1",
               "POSTGRES_DB": "mylocal", "POSTGRES_USER": "me",
               "POSTGRES_PASSWORD": "mypw"}
        with mock.patch.dict(os.environ, env, clear=False):
            os.environ.pop("TEST_DATABASE_URL", None)
            os.environ.pop("ALLOW_TESTS_ON_REMOTE_DB", None)
            config = db.get_databases(is_test_run=True)["default"]
        self.assertEqual(config["NAME"], "mylocal")
        self.assertEqual(config["USER"], "me")

    def test_normal_run_uses_the_primary_database(self):
        with mock.patch.dict(os.environ, {"DATABASE_URL": SESSION_POOLER},
                             clear=False):
            config = db.get_databases(is_test_run=False)["default"]
        self.assertEqual(config["HOST"], "aws-0-ap-south-1.pooler.supabase.com")


class PoolExhaustionResponseTests(SimpleTestCase):
    """A full connection pool should produce an actionable 503, not a 500 with
    a psycopg2 string the user cannot act on."""

    def _handle(self, message):
        from django.db.utils import OperationalError
        from core.exceptions import api_exception_handler
        return api_exception_handler(OperationalError(message), {})

    def test_pool_exhaustion_returns_503_with_guidance(self):
        response = self._handle(
            'connection to server at "aws-0-ap-southeast-2.pooler.supabase.com" '
            "failed: FATAL: (EMAXCONNSESSION) max clients reached in session mode "
            "- max clients are limited to pool_size: 15")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.data["code"], "db_pool_exhausted")
        self.assertIn("Connection limits", str(response.data["detail"]))

    def test_other_database_outages_return_503_too(self):
        response = self._handle("could not connect to server: Connection refused")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.data["code"], "db_unavailable")

    def test_pool_error_message_does_not_leak_credentials(self):
        response = self._handle(
            "FATAL: max clients reached in session mode; "
            "dsn was password=SuperSecret1 host=x")
        self.assertNotIn("SuperSecret1", str(response.data))
