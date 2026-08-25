from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView, TokenVerifyView

from accounts.views import (AuditedTokenObtainPairView, DepartmentViewSet,
                            UserViewSet)
from core.views import (AuditLogViewSet, DashboardSummaryView, HealthView,
                        NotificationViewSet)
from fc.views import (ChecklistTemplateViewSet, FCModelTypeViewSet,
                      FirmwareRecordViewSet, FlightControllerViewSet,
                      LifecycleMetaView, ParameterProfileViewSet,
                      ReworkRecordViewSet, SoftwareVersionViewSet,
                      StageRecordViewSet, TestResultViewSet)
from issues.views import (IssueAttachmentViewSet, IssueViewSet, KnownIssueViewSet)

router = DefaultRouter()
router.register("departments", DepartmentViewSet)
router.register("users", UserViewSet)
router.register("fc-models", FCModelTypeViewSet)
router.register("parameter-profiles", ParameterProfileViewSet)
router.register("software-versions", SoftwareVersionViewSet)
router.register("checklist-templates", ChecklistTemplateViewSet)
router.register("fcs", FlightControllerViewSet)
router.register("stage-records", StageRecordViewSet)
router.register("rework-records", ReworkRecordViewSet)
router.register("firmware-records", FirmwareRecordViewSet)
router.register("test-results", TestResultViewSet)
router.register("issues", IssueViewSet)
router.register("known-issues", KnownIssueViewSet)
router.register("issue-attachments", IssueAttachmentViewSet)
router.register("audit-log", AuditLogViewSet)
router.register("notifications", NotificationViewSet, basename="notification")
router.register("lifecycle", LifecycleMetaView, basename="lifecycle")

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/health/", HealthView.as_view()),
    path("api/auth/token/", AuditedTokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("api/auth/token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("api/auth/token/verify/", TokenVerifyView.as_view()),
    path("api/dashboard/summary/", DashboardSummaryView.as_view()),
    path("api/", include(router.urls)),
    path("api-auth/", include("rest_framework.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
