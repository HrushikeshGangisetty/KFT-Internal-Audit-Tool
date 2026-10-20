from django.contrib import admin
from django.urls import include, path, re_path
from rest_framework.routers import DefaultRouter

from accounts.views import (CsrfView, DepartmentViewSet, LoginView, LogoutView,
                            MeView, UserViewSet)
from core.views import (AuditLogViewSet, DashboardSummaryView, HealthView,
                        NotificationViewSet, WorkerHealthView,
                        spa_index)
from fc.views import (ChecklistItemViewSet, ChecklistTemplateViewSet,
                      FCModelTypeViewSet, FirmwareBuildViewSet,
                      FirmwareRecordViewSet, FlightControllerViewSet,
                      LifecycleMetaView, ParameterProfileViewSet,
                      ReworkRecordViewSet,
                      SoftwareVersionViewSet, StageRecordViewSet,
                      TestResultViewSet, ParameterFileViewSet,
                      ConfigEvidenceViewSet, ParameterComparisonViewSet)
from issues.views import (HandoffViewSet, IssueAttachmentViewSet, IssueViewSet,
                          KnownIssueViewSet, MyQueueView)

from customers.views import CustomerViewSet, ContactViewSet, DeploymentViewSet
from tasks.views import DailyUpdateViewSet, ProgressView, TaskViewSet
from releases.views import CampaignViewSet, ReleaseViewSet

router = DefaultRouter()
router.register("customers", CustomerViewSet, basename="customer")
router.register("customer-contacts", ContactViewSet, basename="customercontact")
router.register("deployments", DeploymentViewSet, basename="deployment")
router.register("tasks", TaskViewSet, basename="task")
router.register("releases", ReleaseViewSet, basename="release")
router.register("campaigns", CampaignViewSet, basename="campaign")
router.register("daily-updates", DailyUpdateViewSet, basename="dailyupdate")
router.register("departments", DepartmentViewSet, basename="department")
router.register("users", UserViewSet, basename="user")
router.register("fc-models", FCModelTypeViewSet, basename="fcmodeltype")
router.register("parameter-profiles", ParameterProfileViewSet, basename="parameterprofile")
router.register("software-versions", SoftwareVersionViewSet, basename="softwareversion")
router.register("checklist-templates", ChecklistTemplateViewSet, basename="checklisttemplate")
router.register("checklist-items", ChecklistItemViewSet, basename="checklistitem")
router.register("firmware-builds", FirmwareBuildViewSet, basename="firmwarebuild")
router.register("fcs", FlightControllerViewSet, basename="flightcontroller")
router.register("stage-records", StageRecordViewSet, basename="stagerecord")
router.register("rework-records", ReworkRecordViewSet, basename="reworkrecord")
router.register("firmware-records", FirmwareRecordViewSet, basename="firmwarerecord")
router.register("test-results", TestResultViewSet, basename="testresult")
router.register("parameter-files", ParameterFileViewSet, basename="parameterfile")
router.register("config-evidence", ConfigEvidenceViewSet, basename="configevidence")
router.register("parameter-comparisons", ParameterComparisonViewSet,
                basename="parametercomparison")
router.register("issues", IssueViewSet, basename="issue")
router.register("known-issues", KnownIssueViewSet, basename="knownissue")
router.register("issue-attachments", IssueAttachmentViewSet, basename="issueattachment")
router.register("handoffs", HandoffViewSet, basename="handoff")
router.register("audit-log", AuditLogViewSet, basename="auditlogentry")
router.register("notifications", NotificationViewSet, basename="notification")
router.register("lifecycle", LifecycleMetaView, basename="lifecycle")

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/health/", HealthView.as_view()),
    path("api/admin/health/", WorkerHealthView.as_view()),
    path("api/auth/csrf/", CsrfView.as_view()),
    path("api/auth/login/", LoginView.as_view()),
    path("api/auth/logout/", LogoutView.as_view()),
    path("api/auth/me/", MeView.as_view()),
    path("api/dashboard/summary/", DashboardSummaryView.as_view()),
    path("api/me/queue/", MyQueueView.as_view()),
    path("api/progress/", ProgressView.as_view()),
    path("api/", include(router.urls)),
    path("api-auth/", include("rest_framework.urls")),
    # Everything else is a frontend route: serve the SPA so deep links load.
    re_path(r"^(?!api/|api-auth/|admin/|static/|media/).*$", spa_index),
]

# Uploaded files are never served from a public media URL: attachments are
# downloaded through /api/issue-attachments/<id>/download/, which checks scope.
