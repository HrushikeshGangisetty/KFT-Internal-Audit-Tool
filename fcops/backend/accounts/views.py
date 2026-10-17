import time

from django.contrib.auth import authenticate, get_user_model, login, logout
from django.middleware.csrf import get_token
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from access.mixins import ScopedViewSetMixin
from core import audit
from core.middleware import AbsoluteSessionTimeoutMiddleware
from core.models import AuditLogEntry

from . import ratelimit, services
from .models import Department, Role
from .permissions import IsAdmin
from .serializers import (DepartmentSerializer, MeSerializer, UserSerializer,
                          UserWriteSerializer)

User = get_user_model()


# --- Session authentication (WP2) -----------------------------------------
class CsrfView(APIView):
    """Sets the CSRF cookie and returns the token for the X-CSRFToken header."""
    permission_classes = [AllowAny]

    @method_decorator(ensure_csrf_cookie)
    def get(self, request):
        return Response({"csrfToken": get_token(request)})


@method_decorator(csrf_protect, name="dispatch")
class LoginView(APIView):
    """Django ``login()`` rotates the session key and CSRF token. CSRF is
    enforced here too, so another site cannot log a browser in."""
    permission_classes = [AllowAny]

    def post(self, request):
        username = request.data.get("username") or ""
        ip = request.META.get("REMOTE_ADDR", "")
        if ratelimit.is_locked(username, ip):
            return Response({"detail": "Too many failed sign-in attempts. Try again "
                                       "later."},
                            status=status.HTTP_429_TOO_MANY_REQUESTS)
        user = authenticate(request, username=username,
                            password=request.data.get("password") or "")
        if user is None:
            ratelimit.record_failure(username, ip)
            return Response({"detail": "Incorrect username or password."},
                            status=status.HTTP_401_UNAUTHORIZED)
        ratelimit.clear(username, ip)
        login(request, user)
        request.session[AbsoluteSessionTimeoutMiddleware.KEY] = time.time()
        audit.record(user, AuditLogEntry.ACTION_LOGIN, actor=user,
                     note="Successful login")
        return Response(MeSerializer(user).data)


class LogoutView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        logout(request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    """The signed-in user, or an empty 200 when nobody is signed in: the SPA
    asks on every load, and that is not an error."""
    permission_classes = [AllowAny]

    def get(self, request):
        if not request.user.is_authenticated:
            return Response(None)
        return Response(MeSerializer(request.user).data)


class DepartmentViewSet(ScopedViewSetMixin, viewsets.ModelViewSet):
    serializer_class = DepartmentSerializer
    filterset_fields = ("kind", "is_active")

    def get_scoped_queryset(self):
        # The org chart is a directory every member of staff needs.
        return Department.objects.all()

    def get_permissions(self):
        if self.request.method in ("GET", "HEAD", "OPTIONS"):
            return [IsAuthenticated()]
        return [IsAdmin()]

    def perform_create(self, serializer):
        obj = serializer.save()
        audit.record(obj, AuditLogEntry.ACTION_PERMISSION,
                     after=audit.snapshot(obj), note="Department created")

    def perform_update(self, serializer):
        before = audit.snapshot(serializer.instance)
        obj = serializer.save()
        audit.record_change(obj, AuditLogEntry.ACTION_PERMISSION, before,
                            note="Department updated")


class UserViewSet(ScopedViewSetMixin, viewsets.ModelViewSet):
    filterset_fields = ("role", "department", "is_active")

    def get_scoped_queryset(self):
        # Staff directory: needed to assign, hand off and mention people.
        return User.objects.select_related("department").all().order_by("username")

    def get_serializer_class(self):
        if self.request.method in ("GET", "HEAD", "OPTIONS"):
            return UserSerializer
        return UserWriteSerializer

    def get_permissions(self):
        if self.request.method in ("GET", "HEAD", "OPTIONS"):
            return [IsAuthenticated()]
        return [IsAdmin()]

    def perform_create(self, serializer):
        obj = serializer.save()
        audit.record(obj, AuditLogEntry.ACTION_PERMISSION,
                     after=audit.snapshot(obj, fields=["username", "role",
                                                       "department", "is_active"]),
                     note="User created")
        services.sync_legacy_fields(obj, actor=self.request.user)

    def perform_update(self, serializer):
        before = audit.snapshot(serializer.instance,
                                fields=["username", "role", "department", "is_active"])
        old_department, old_role = serializer.instance.department, serializer.instance.role
        was_active = serializer.instance.is_active
        obj = serializer.save()
        if was_active and not obj.is_active:
            services.end_sessions(obj, actor=self.request.user)
        services.sync_legacy_fields(obj, actor=self.request.user,
                                    old_department=old_department, old_role=old_role)
        audit.record_change(obj, AuditLogEntry.ACTION_PERMISSION, before,
                            fields=["username", "role", "department", "is_active"],
                            note="User updated")

    @action(detail=False, methods=["get"], permission_classes=[IsAuthenticated])
    def roles(self, request):
        return Response([{"value": v, "label": l} for v, l in Role.choices])
