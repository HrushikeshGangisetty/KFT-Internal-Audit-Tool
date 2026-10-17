from django.contrib import admin
from django.urls import include, path, re_path
from rest_framework.routers import DefaultRouter

from accounts.views import (CsrfView, DepartmentViewSet, LoginView, LogoutView,
                            MeView, UserViewSet)
from core.views import (AuditLogViewSet, DashboardSummaryView, HealthView,
                        NotificationViewSet, spa_index)
from fc.views import (ChecklistItemViewSet, ChecklistTemplateViewSet,
                      FCModelTypeViewSet, FirmwareBuildViewSet,
                      FirmwareRecordViewSet, FlightControllerViewSet,
                      LifecycleMetaView, ParameterProfileViewSet,
                      ReworkRecordViewSet, SoftwareUpdateViewSet,
                      SoftwareVersionViewSet, StageRecordViewSet,
                      TestResultViewSet)
from issues.views import (IssueAttachmentViewSet, IssueViewSet, KnownIssueViewSet)

router = DefaultRouter()
router.register("departments", DepartmentViewSet, basename="department")
router.register("users", UserViewSet, basename="user")
router.register("fc-models", FCModelTypeViewSet, basename="fcmodeltype")
router.register("parameter-profiles", ParameterProfileViewSet, basename="parameterprofile")
router.register("software-versions", SoftwareVersionViewSet, basename="softwareversion")
router.register("checklist-templates", ChecklistTemplateViewSet, basename="checklisttemplate")
router.register("checklist-items", ChecklistItemViewSet, basename="checklistitem")
router.register("firmware-builds", FirmwareBuildViewSet, basename="firmwarebuild")
router.register("software-updates", SoftwareUpdateViewSet, basename="softwareupdate")
router.register("fcs", FlightControllerViewSet, basename="flightcontroller")
router.register("stage-records", StageRecordViewSet, basename="stagerecord")
router.register("rework-records", ReworkRecordViewSet, basename="reworkrecord")
router.register("firmware-records", FirmwareRecordViewSet, basename="firmwarerecord")
router.register("test-results", TestResultViewSet, basename="testresult")
router.register("issues", IssueViewSet, basename="issue")
router.register("known-issues", KnownIssueViewSet, basename="knownissue")
router.register("issue-attachments", IssueAttachmentViewSet, basename="issueattachment")
router.register("audit-log", AuditLogViewSet, basename="auditlogentry")
router.register("notifications", NotificationViewSet, basename="notification")
router.register("lifecycle", LifecycleMetaView, basename="lifecycle")

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/health/", HealthView.as_view()),
    path("api/auth/csrf/", CsrfView.as_view()),
    path("api/auth/login/", LoginView.as_view()),
    path("api/auth/logout/", LogoutView.as_view()),
    path("api/auth/me/", MeView.as_view()),
    path("api/dashboard/summary/", DashboardSummaryView.as_view()),
    path("api/", include(router.urls)),
    path("api-auth/", include("rest_framework.urls")),
    # Everything else is a frontend route: serve the SPA so deep links load.
    re_path(r"^(?!api/|api-auth/|admin/|static/|media/).*$", spa_index),
]

# Uploaded files are never served from a public media URL: attachments are
# downloaded through /api/issue-attachments/<id>/download/, which checks scope.
