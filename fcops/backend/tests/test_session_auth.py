"""WP2: session authentication, CSRF, lockout, deactivation, single origin."""
import shutil
import tempfile
import time
from pathlib import Path

from django.contrib.sessions.models import Session
from django.core.cache import cache
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import Client, TestCase, override_settings
from rest_framework.test import APIClient

from accounts.models import Department, Role
from core.middleware import AbsoluteSessionTimeoutMiddleware

from .factories import make_department, make_user

PASSWORD = "TestPass123!"


class SessionAuthTests(TestCase):
    def setUp(self):
        cache.clear()
        dept = make_department("assembly", Department.KIND_HARDWARE)
        self.tech = make_user("tech", Role.TECHNICIAN, dept)
        self.admin = make_user("admin", Role.ADMIN, dept)

    def login(self, user, client=None):
        client = client or APIClient()
        r = client.post("/api/auth/login/", {"username": user.username,
                                             "password": PASSWORD}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        return client

    def test_anonymous_api_requests_get_401(self):
        self.assertEqual(APIClient().get("/api/issues/").status_code, 401)
        r = APIClient().get("/api/auth/me/")
        self.assertEqual((r.status_code, r.data), (200, None))

    def test_login_sets_httponly_session_and_returns_profile(self):
        client = APIClient()
        r = client.post("/api/auth/login/", {"username": "tech", "password": PASSWORD},
                        format="json")
        self.assertEqual(r.data["username"], "tech")
        self.assertIn("permissions", r.data)
        self.assertNotIn("access", r.data)
        cookie = r.cookies["sessionid"]
        self.assertTrue(cookie["httponly"])
        self.assertEqual(cookie["samesite"], "Lax")
        self.assertEqual(client.get("/api/auth/me/").data["username"], "tech")

    def test_bad_password_is_401(self):
        r = APIClient().post("/api/auth/login/", {"username": "tech", "password": "x"},
                             format="json")
        self.assertEqual(r.status_code, 401)

    def test_post_without_csrf_token_is_rejected(self):
        client = APIClient(enforce_csrf_checks=True)
        r = client.post("/api/auth/login/", {"username": "tech", "password": PASSWORD},
                        format="json")
        self.assertEqual(r.status_code, 403, "login accepted without a CSRF token")

        token = client.get("/api/auth/csrf/").data["csrfToken"]
        r = client.post("/api/auth/login/", {"username": "admin", "password": PASSWORD},
                        format="json", HTTP_X_CSRFTOKEN=token)
        self.assertEqual(r.status_code, 200, r.content)

        payload = {"name": "New", "code": "new", "kind": "HARDWARE"}
        r = client.post("/api/departments/", payload, format="json")
        self.assertEqual(r.status_code, 403, "authenticated POST without CSRF accepted")
        # login() rotates the token, so fetch the current one.
        token = client.get("/api/auth/csrf/").data["csrfToken"]
        r = client.post("/api/departments/", payload, format="json",
                        HTTP_X_CSRFTOKEN=token)
        self.assertEqual(r.status_code, 201, r.content)

    def test_logout_ends_the_session(self):
        client = self.login(self.tech)
        self.assertEqual(client.post("/api/auth/logout/").status_code, 204)
        self.assertIsNone(client.get("/api/auth/me/").data)
        self.assertEqual(client.get("/api/issues/").status_code, 401)

    def test_deactivated_user_session_stops_working(self):
        tech_client = self.login(self.tech)
        self.assertEqual(tech_client.get("/api/issues/").status_code, 200)
        r = self.login(self.admin).patch(f"/api/users/{self.tech.pk}/",
                                         {"is_active": False}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(tech_client.get("/api/issues/").status_code, 401)
        live = [s for s in Session.objects.all()
                if s.get_decoded().get("_auth_user_id") == str(self.tech.pk)]
        self.assertEqual(live, [])

    @override_settings(LOGIN_FAILURE_LIMIT=3)
    def test_repeated_failures_lock_the_account(self):
        client = APIClient()
        for _ in range(3):
            client.post("/api/auth/login/", {"username": "tech", "password": "bad"},
                        format="json")
        r = client.post("/api/auth/login/", {"username": "tech", "password": PASSWORD},
                        format="json")
        self.assertEqual(r.status_code, 429)
        # Another user from the same IP is locked by the IP counter as well.
        r = client.post("/api/auth/login/", {"username": "admin", "password": PASSWORD},
                        format="json")
        self.assertEqual(r.status_code, 429)

    def test_absolute_session_lifetime(self):
        client = self.login(self.tech)
        session = client.session
        session[AbsoluteSessionTimeoutMiddleware.KEY] = time.time() - 10 ** 6
        session.save()
        self.assertEqual(client.get("/api/issues/").status_code, 401)

    def test_demo_seed_refuses_outside_debug(self):
        with override_settings(DEBUG=False):
            with self.assertRaises(CommandError):
                call_command("seed", demo=True)
        with override_settings(DEBUG=True, PRODUCTION=True):
            with self.assertRaises(CommandError):
                call_command("seed", demo=True)


class SingleOriginTests(TestCase):
    def setUp(self):
        self.dist = Path(tempfile.mkdtemp(prefix="wp2-dist-"))
        (self.dist / "assets").mkdir()
        (self.dist / "index.html").write_text("<!doctype html><div id=root></div>")
        (self.dist / "assets" / "app.js").write_text("console.log(1)")

    def tearDown(self):
        shutil.rmtree(self.dist, ignore_errors=True)

    def test_deep_links_load_the_spa_and_assets_share_the_origin(self):
        with override_settings(FRONTEND_DIST=self.dist, WHITENOISE_ROOT=self.dist):
            client = Client()
            for url in ("/", "/issues/42", "/fcs/7/timeline"):
                r = client.get(url)
                self.assertEqual(r.status_code, 200, url)
                self.assertIn(b"id=root", b"".join(r.streaming_content))
            r = client.get("/assets/app.js")
            self.assertEqual(r.status_code, 200)
            # API paths are never swallowed by the SPA route.
            self.assertEqual(client.get("/api/no-such-endpoint/").status_code, 404)
            self.assertEqual(client.get("/api/health/").json()["status"], "ok")

    def test_missing_build_is_a_404_not_a_crash(self):
        with override_settings(FRONTEND_DIST=self.dist / "missing"):
            self.assertEqual(Client().get("/issues/42").status_code, 404)
