from django.contrib.auth import get_user_model
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.views import TokenObtainPairView

from core import audit
from core.models import AuditLogEntry

from .models import Department, Role
from .permissions import IsAdmin
from .serializers import (DepartmentSerializer, MeSerializer, UserSerializer,
                          UserWriteSerializer)

User = get_user_model()


class AuditedTokenObtainPairView(TokenObtainPairView):
    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        username = request.data.get("username")
        user = User.objects.filter(username=username).first()
        if user and response.status_code == 200:
            audit.record(user, AuditLogEntry.ACTION_LOGIN, actor=user,
                         note="Successful login")
        return response


class DepartmentViewSet(viewsets.ModelViewSet):
    queryset = Department.objects.all()
    serializer_class = DepartmentSerializer
    filterset_fields = ("kind", "is_active")

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


class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.select_related("department").all().order_by("username")
    filterset_fields = ("role", "department", "is_active")

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

    def perform_update(self, serializer):
        before = audit.snapshot(serializer.instance,
                                fields=["username", "role", "department", "is_active"])
        obj = serializer.save()
        audit.record_change(obj, AuditLogEntry.ACTION_PERMISSION, before,
                            fields=["username", "role", "department", "is_active"],
                            note="User updated")

    @action(detail=False, methods=["get"], permission_classes=[IsAuthenticated])
    def me(self, request):
        return Response(MeSerializer(request.user).data)

    @action(detail=False, methods=["get"], permission_classes=[IsAuthenticated])
    def roles(self, request):
        return Response([{"value": v, "label": l} for v, l in Role.choices])
