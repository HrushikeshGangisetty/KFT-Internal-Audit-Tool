"""Route-coverage meta-test (WP1): every API view goes through the access
layer, so a new endpoint cannot bypass it by forgetting to scope."""
from django.test import SimpleTestCase
from django.urls import get_resolver, path
from rest_framework import viewsets
from rest_framework.routers import APIRootView
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenRefreshView, TokenVerifyView

from access.mixins import ScopedViewSetMixin
from accounts.views import AuditedTokenObtainPairView
from core.views import DashboardSummaryView, HealthView
from fc.views import LifecycleMetaView
from issues.models import Issue

ALLOWLIST = {
    AuditedTokenObtainPairView,  # login: no records before authentication
    TokenRefreshView,            # token exchange, no records
    TokenVerifyView,             # token check, no records
    HealthView,                  # static status and time
    APIRootView,                 # router index of endpoint names
    LifecycleMetaView,           # stage enum metadata only
    DashboardSummaryView,        # aggregates built from access.policy scopes;
                                 # per-actor counts covered in test_access_matrix
}


def find_unscoped_views(patterns):
    offenders = set()
    for pattern in patterns:
        if hasattr(pattern, "url_patterns"):
            offenders |= find_unscoped_views(pattern.url_patterns)
            continue
        cls = getattr(pattern.callback, "cls", None)
        if cls is None or not issubclass(cls, APIView):
            continue  # Django views (admin, DRF login form) are not API views
        if cls in ALLOWLIST or issubclass(cls, ScopedViewSetMixin):
            continue
        offenders.add(cls)
    return offenders


class UnscopedViewSet(viewsets.ReadOnlyModelViewSet):
    """Deliberately unscoped, to prove the meta-test catches it."""
    queryset = Issue.objects.all()


class RouteCoverageTests(SimpleTestCase):
    def test_every_api_view_is_scoped_or_allowlisted(self):
        self.assertEqual(find_unscoped_views(get_resolver().url_patterns), set())

    def test_an_unscoped_viewset_is_caught(self):
        patterns = get_resolver().url_patterns + [
            path("api/temp/", UnscopedViewSet.as_view({"get": "list"}))]
        self.assertEqual(find_unscoped_views(patterns), {UnscopedViewSet})

    def test_mixin_without_scope_is_improperly_configured(self):
        from django.core.exceptions import ImproperlyConfigured

        class Forgot(ScopedViewSetMixin, viewsets.ReadOnlyModelViewSet):
            pass

        with self.assertRaises(ImproperlyConfigured):
            Forgot().get_queryset()
