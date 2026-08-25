"""Server-side RBAC (PRD §18).

Every role has universal read/search access — knowledge retention only works if
nothing is siloed. Writes are gated per action.
"""
from rest_framework.permissions import BasePermission, SAFE_METHODS

from .models import Role


class IsAuthenticatedReadOnlyOrRole(BasePermission):
    """Base: any authenticated user may read; writes require ``allowed_roles``."""

    allowed_roles = ()

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        if request.method in SAFE_METHODS:
            return True
        return user.is_admin_role or user.role in self.allowed_roles


class ReadOnlyForAll(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated
                    and request.method in SAFE_METHODS)


class CanWriteProduction(IsAuthenticatedReadOnlyOrRole):
    """Stage records, rework, firmware records, test results."""
    allowed_roles = (Role.TECHNICIAN, Role.DEPARTMENT_LEAD,
                     Role.TEST_ENGINEER, Role.MANAGER)


class CanWriteIssues(IsAuthenticatedReadOnlyOrRole):
    allowed_roles = (Role.TECHNICIAN, Role.DEPARTMENT_LEAD,
                     Role.TEST_ENGINEER, Role.MANAGER)


class IsManager(BasePermission):
    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.is_manager_role)


class IsAdmin(BasePermission):
    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.is_admin_role)


class IsLeadOrAbove(BasePermission):
    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.is_lead_role)


class CanVerifyResolution(BasePermission):
    """Test engineers, leads and managers may verify a resolution."""

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        return user.is_test_engineer or user.is_lead_role
