"""DRF enforcement of access.policy (WP1)."""
from django.core.exceptions import ImproperlyConfigured
from rest_framework import serializers


class ScopedViewSetMixin:
    """Every queryset a view reads comes from ``get_scoped_queryset()``.

    Detail lookups go through it too, so a record outside scope is a 404,
    not a 403: existence does not leak. The route-coverage test fails for any
    API view that does not use this mixin and is not allowlisted.
    """

    def get_scoped_queryset(self):
        raise ImproperlyConfigured(
            f"{type(self).__name__} must define get_scoped_queryset().")

    def get_queryset(self):
        return self.get_scoped_queryset()


class ScopedPrimaryKeyRelatedField(serializers.PrimaryKeyRelatedField):
    """A foreign-key input that only accepts objects the request user can
    see. ``scope`` is an access.policy function taking the user."""

    def __init__(self, scope, **kwargs):
        self.scope = scope
        super().__init__(**kwargs)

    def get_queryset(self):
        return self.scope(self.context["request"].user)
