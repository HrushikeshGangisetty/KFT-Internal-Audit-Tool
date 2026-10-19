from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status as http_status
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from accounts.models import Department, Role, User
from accounts.permissions import (CanManageFirmware, CanPushSoftwareUpdate,
                                  CanWriteProduction, IsAdmin, IsManager,
                                  IsManagerOrReadOnly)
from access import policy
from access.mixins import ScopedViewSetMixin
from core import audit
from core.exceptions import WorkflowError
from core.models import AuditLogEntry

from . import config_services, services
from .lifecycle import (ALLOWED_REWORK_TARGETS, STAGE_ORDER, TEST_STAGES, Stage,
                        rework_targets)
from .models import (ChecklistItem, ChecklistTemplate, FCModelType,
                     FirmwareBuild, FirmwareRecord, FlightController,
                     ParameterProfile, ReworkRecord, SoftwareUpdate,
                     SoftwareVersion, StageRecord, StageStatus, TestResult)
from .serializers import (ActiveFlagSerializer, ApprovalSerializer,
                          ChecklistItemSerializer,
                          ChecklistTemplateDetailSerializer,
                          ChecklistTemplateSerializer, FirmwareBuildSerializer,
                          FlashBuildSerializer, ReorderSerializer,
                          SoftwareUpdateCreateSerializer, SoftwareUpdateSerializer,
                          FCCreateSerializer, FCEventSerializer,
                          FCModelTypeSerializer, FirmwareRecordSerializer,
                          FlightControllerDetailSerializer,
                          FlightControllerListSerializer, OverrideSerializer,
                          ParameterProfileSerializer, ReworkRecordSerializer,
                          SoftwareVersionSerializer, StageActionSerializer,
                          StageRecordSerializer, TestResultSerializer)


class FCModelTypeViewSet(ScopedViewSetMixin, viewsets.ModelViewSet):
    """FC models, owned by the Manager. Models in use are archived, never
    deleted, so historical FCs keep a valid reference."""

    serializer_class = FCModelTypeSerializer
    permission_classes = [IsManagerOrReadOnly]
    filterset_fields = ("is_active",)

    def get_scoped_queryset(self):
        # Catalogue/configuration: readable by all staff.
        return FCModelType.objects.all()

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        model = config_services.create_fc_model(actor=request.user,
                                                **serializer.validated_data)
        return Response(FCModelTypeSerializer(model).data,
                        status=http_status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        model = self.get_object()
        serializer = self.get_serializer(model, data=request.data,
                                         partial=kwargs.pop("partial", False))
        serializer.is_valid(raise_exception=True)
        model = config_services.update_fc_model(model, actor=request.user,
                                                **serializer.validated_data)
        return Response(FCModelTypeSerializer(model).data)

    def partial_update(self, request, *args, **kwargs):
        return self.update(request, *args, partial=True, **kwargs)

    def destroy(self, request, *args, **kwargs):
        config_services.delete_fc_model(self.get_object(), actor=request.user)
        return Response(status=http_status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["post"], url_path="set-active")
    def set_active(self, request, pk=None):
        s = ActiveFlagSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        model = config_services.set_fc_model_active(
            self.get_object(), actor=request.user,
            is_active=s.validated_data["is_active"])
        return Response(FCModelTypeSerializer(model).data)


class ParameterProfileViewSet(ScopedViewSetMixin, viewsets.ModelViewSet):
    serializer_class = ParameterProfileSerializer
    permission_classes = [CanWriteProduction]

    def get_scoped_queryset(self):
        # Catalogue/configuration: readable by all staff.
        return ParameterProfile.objects.all()


class SoftwareVersionViewSet(ScopedViewSetMixin, viewsets.ModelViewSet):
    serializer_class = SoftwareVersionSerializer
    permission_classes = [CanWriteProduction]
    filterset_fields = ("kind", "is_active")

    def get_scoped_queryset(self):
        # Catalogue/configuration: readable by all staff.
        return SoftwareVersion.objects.all()


class ChecklistTemplateViewSet(ScopedViewSetMixin, viewsets.ModelViewSet):
    """Test checklists. Managers configure them; everyone can read the current
    definition because testers need it to run a test."""

    permission_classes = [IsManagerOrReadOnly]
    filterset_fields = ("stage", "fc_model", "is_active")

    def get_scoped_queryset(self):
        # Catalogue/configuration: readable by all staff.
        return ChecklistTemplate.objects.prefetch_related("checklist_items").all()

    def get_serializer_class(self):
        if self.action in ("list", "retrieve"):
            return ChecklistTemplateDetailSerializer
        return ChecklistTemplateSerializer

    def perform_create(self, serializer):
        obj = serializer.save()
        audit.record(obj, AuditLogEntry.ACTION_CONFIG, actor=self.request.user,
                     after=audit.snapshot(obj), note="Checklist template created")

    def perform_update(self, serializer):
        before = audit.snapshot(serializer.instance)
        obj = serializer.save()
        audit.record_change(obj, AuditLogEntry.ACTION_CONFIG, before,
                            note="Checklist template updated", actor=self.request.user)

    @action(detail=True, methods=["post"])
    def reorder(self, request, pk=None):
        s = ReorderSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        config_services.reorder_checklist_items(
            self.get_object(), actor=request.user,
            ordered_ids=s.validated_data["ordered_ids"])
        return Response(ChecklistTemplateDetailSerializer(self.get_object()).data)

    @action(detail=True, methods=["get"])
    def current(self, request, pk=None):
        """The checklist a tester should be shown right now, plus the version
        it corresponds to."""
        template = self.get_object()
        return Response({"template": template.id, "version": template.version,
                         "items": template.as_checklist()})


class FlightControllerViewSet(ScopedViewSetMixin, viewsets.ModelViewSet):
    permission_classes = [CanWriteProduction]
    filterset_fields = ("status", "current_stage", "fc_model", "hardware_revision")
    ordering_fields = ("created_at", "serial", "updated_at")

    def get_scoped_queryset(self):
        return policy.scope_by_fc(
            self.request.user,
            FlightController.objects.select_related("fc_model", "registered_by",
                                                    "approved_by"))

    def get_serializer_class(self):
        if self.action == "list":
            return FlightControllerListSerializer
        if self.action == "create":
            return FCCreateSerializer
        return FlightControllerDetailSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        search = self.request.query_params.get("search")
        if search:
            qs = qs.filter(Q(serial__icontains=search)
                           | Q(hardware_revision__icontains=search)
                           | Q(pcb_batch__icontains=search)
                           | Q(notes__icontains=search))
        return qs

    def create(self, request, *args, **kwargs):
        serializer = FCCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        fc = services.register_fc(
            fc_model=data["fc_model"],
            hardware_revision=data.get("hardware_revision", ""),
            pcb_batch=data.get("pcb_batch", ""),
            notes=data.get("notes", ""),
            serial=data.get("serial") or None,
            actor=request.user)
        return Response(FlightControllerDetailSerializer(fc).data,
                        status=http_status.HTTP_201_CREATED)

    def destroy(self, request, *args, **kwargs):
        return Response({"detail": "FCs are never deleted; reject/scrap instead."},
                        status=http_status.HTTP_405_METHOD_NOT_ALLOWED)

    # --- lifecycle actions ------------------------------------------------
    def _department(self, request):
        dept_id = request.data.get("department")
        return Department.objects.filter(pk=dept_id).first() if dept_id else None

    @action(detail=True, methods=["post"])
    def start_stage(self, request, pk=None):
        fc = self.get_object()
        s = StageActionSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        record = services.start_stage(fc, s.validated_data.get("stage"),
                                      actor=request.user,
                                      department=self._department(request),
                                      notes=s.validated_data.get("notes", ""))
        return Response(StageRecordSerializer(record).data)

    @action(detail=True, methods=["post"])
    def pass_stage(self, request, pk=None):
        return self._complete(request, passed=True)

    @action(detail=True, methods=["post"])
    def fail_stage(self, request, pk=None):
        return self._complete(request, passed=False)

    def _complete(self, request, *, passed):
        fc = self.get_object()
        s = StageActionSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        record = services.complete_stage(fc, s.validated_data.get("stage"),
                                         passed=passed, actor=request.user,
                                         notes=s.validated_data.get("notes", ""),
                                         department=self._department(request))
        fc.refresh_from_db()
        return Response({"stage_record": StageRecordSerializer(record).data,
                         "fc": FlightControllerDetailSerializer(fc).data})

    @action(detail=True, methods=["post"], permission_classes=[IsManager])
    def approve(self, request, pk=None):
        fc = self.get_object()
        s = ApprovalSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        fc = services.manager_approve(
            fc, actor=request.user, approve=s.validated_data["approve"],
            note=s.validated_data.get("note", ""),
            deviation_justification=s.validated_data.get("deviation_justification", ""))
        return Response(FlightControllerDetailSerializer(fc).data)

    @action(detail=True, methods=["post"], permission_classes=[IsManager])
    def override_stage(self, request, pk=None):
        fc = self.get_object()
        s = OverrideSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        fc = services.override_transition(fc, s.validated_data["target_stage"],
                                          actor=request.user,
                                          reason=s.validated_data["reason"])
        return Response(FlightControllerDetailSerializer(fc).data)

    # --- read-only sub-resources -----------------------------------------
    @action(detail=True, methods=["get"])
    def timeline(self, request, pk=None):
        fc = self.get_object()
        # Events about an issue the reader cannot see are left out entirely:
        # their titles and details are copied from the issue.
        events = services.build_timeline(fc).filter(
            Q(issue__isnull=True)
            | Q(issue__in=policy.visible_issues(request.user)))
        return Response(FCEventSerializer(events, many=True).data)

    @action(detail=True, methods=["get"])
    def stage_records(self, request, pk=None):
        fc = self.get_object()
        qs = fc.stage_records.select_related("operator", "department",
                                             "signed_off_by").all()
        return Response(StageRecordSerializer(qs, many=True).data)

    @action(detail=True, methods=["get"])
    def issues(self, request, pk=None):
        from issues.serializers import IssueListSerializer
        fc = self.get_object()
        from issues.models import IssueUnitLink
        linked = IssueUnitLink.objects.filter(fc=fc).values("issue_id")
        qs = policy.visible_issues(request.user).filter(
            Q(fc=fc) | Q(pk__in=linked)).select_related(
            "assigned_department", "discovering_department", "assigned_person",
            "discovered_by")
        return Response(IssueListSerializer(qs, many=True).data)

    @action(detail=True, methods=["get"])
    def audit_log(self, request, pk=None):
        from core.serializers import AuditLogEntrySerializer
        fc = self.get_object()
        qs = (policy.visible_audit_entries(request.user).filter(fc=fc)
              .select_related("actor")[:500])
        return Response(AuditLogEntrySerializer(qs, many=True).data)


class StageRecordViewSet(ScopedViewSetMixin, viewsets.ReadOnlyModelViewSet):
    serializer_class = StageRecordSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ("fc", "stage", "status")

    def get_scoped_queryset(self):
        return policy.scope_by_fc(
            self.request.user,
            StageRecord.objects.select_related("fc", "operator", "department"))


class ReworkRecordViewSet(ScopedViewSetMixin, viewsets.ModelViewSet):
    serializer_class = ReworkRecordSerializer
    permission_classes = [CanWriteProduction]
    filterset_fields = ("fc", "outcome", "stage_record")

    def get_scoped_queryset(self):
        return policy.scope_by_fc(
            self.request.user,
            ReworkRecord.objects.select_related("fc", "stage_record", "performed_by"))

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        stage_record = data["stage_record"]
        rework = services.create_rework(
            stage_record=stage_record,
            description=data["description"],
            return_to_stage=data["return_to_stage"],
            originating_issue=data.get("originating_issue"),
            department=data.get("department"),
            actor=request.user)
        return Response(ReworkRecordSerializer(rework).data,
                        status=http_status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        rework = self.get_object()
        outcome = request.data.get("outcome", ReworkRecord.OUTCOME_COMPLETED)
        if outcome not in dict(ReworkRecord.OUTCOME_CHOICES):
            raise WorkflowError(f"Unknown outcome '{outcome}'.")
        rework = services.complete_rework(rework, outcome=outcome,
                                          outcome_notes=request.data.get("outcome_notes", ""),
                                          actor=request.user)
        return Response(ReworkRecordSerializer(rework).data)


class FirmwareRecordViewSet(ScopedViewSetMixin, viewsets.ModelViewSet):
    serializer_class = FirmwareRecordSerializer
    permission_classes = [CanWriteProduction]
    filterset_fields = ("fc", "version", "source_type", "flashing_result")

    def get_scoped_queryset(self):
        return policy.scope_by_fc(
            self.request.user,
            FirmwareRecord.objects.select_related("fc", "operator", "parameter_profile"))

    def perform_create(self, serializer):
        obj = serializer.save(operator=self.request.user)
        audit.record(obj, AuditLogEntry.ACTION_CREATE, actor=self.request.user,
                     after=audit.snapshot(obj), note="Firmware record created",
                     fc=obj.fc)
        services.log_event(obj.fc, "FIRMWARE_RECORDED",
                           f"Firmware {obj.firmware_name} {obj.version} flashed "
                           f"({obj.get_flashing_result_display()})",
                           detail=obj.notes, stage=Stage.FIRMWARE,
                           actor=self.request.user)

    def perform_update(self, serializer):
        before = audit.snapshot(serializer.instance)
        obj = serializer.save()
        audit.record_change(obj, AuditLogEntry.ACTION_UPDATE, before,
                            note="Firmware record updated", actor=self.request.user)


class TestResultViewSet(ScopedViewSetMixin, viewsets.ModelViewSet):
    serializer_class = TestResultSerializer
    permission_classes = [CanWriteProduction]
    filterset_fields = ("fc", "test_type", "overall_passed")

    def get_scoped_queryset(self):
        return policy.scope_by_fc(
            self.request.user,
            TestResult.objects.select_related("fc", "tester", "stage_record",
                                              "gcs_version", "configurator_version"))

    def perform_create(self, serializer):
        obj = serializer.save(tester=self.request.user)
        obj.recompute_overall()
        # Stamp which version of the checklist this tester actually answered, so
        # a later edit by a manager can never be mistaken for what they saw.
        if obj.template_id:
            obj.template_version = obj.template.version
        obj.save(update_fields=["overall_passed", "template_version"])
        audit.record(obj, AuditLogEntry.ACTION_CREATE, actor=self.request.user,
                     after=audit.snapshot(obj), note="Test result recorded", fc=obj.fc)
        failed = [i.get("label") or i.get("key")
                  for i in (obj.checklist_results or []) if not i.get("passed")]
        services.log_event(
            obj.fc, "TEST_RESULT",
            f"{Stage(obj.test_type).label}: "
            f"{'PASSED' if obj.overall_passed else 'FAILED'}",
            detail=("Failed items: " + ", ".join(failed)) if failed else obj.notes,
            stage=obj.test_type, actor=self.request.user,
            payload={"gcs_version": getattr(obj.gcs_version, "version", None),
                     "configurator_version": getattr(obj.configurator_version,
                                                     "version", None)})


class LifecycleMetaView(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    def list(self, request):
        return Response({
            "stages": [{"value": s, "label": Stage(s).label,
                        "is_test_stage": s in TEST_STAGES} for s in STAGE_ORDER],
            "rework_targets": {
                s: [{"value": t, "label": Stage(t).label} for t in targets]
                for s, targets in ALLOWED_REWORK_TARGETS.items()},
        })


# ---------------------------------------------------------------------------
# Configuration & catalogue features
# ---------------------------------------------------------------------------
class SoftwareUpdateViewSet(ScopedViewSetMixin, viewsets.ModelViewSet):
    """Internal release records for the in-house GCS / Configurator.

    Readable by everyone (the release history is knowledge), writable only by
    the Software department. Records are never edited or deleted: a release
    happened, and correcting it means pushing another one.
    """

    serializer_class = SoftwareUpdateSerializer
    permission_classes = [CanPushSoftwareUpdate]
    filterset_fields = ("kind", "approved_by", "pushed_by")
    ordering_fields = ("created_at", "version")

    def get_scoped_queryset(self):
        # Release history: readable by all staff until WP11.
        return SoftwareUpdate.objects.select_related(
            "approved_by", "pushed_by", "software_version")

    def get_queryset(self):
        qs = super().get_queryset()
        search = self.request.query_params.get("search")
        if search:
            qs = qs.filter(Q(version__icontains=search)
                           | Q(git_sha__icontains=search)
                           | Q(release_notes__icontains=search))
        return qs

    def create(self, request, *args, **kwargs):
        s = SoftwareUpdateCreateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        data = s.validated_data
        update = config_services.push_software_update(
            kind=data["kind"], version=data["version"], git_sha=data["git_sha"],
            release_notes=data["release_notes"],
            approved_by=User.objects.filter(pk=data["approved_by"]).first(),
            actor=request.user)
        return Response(SoftwareUpdateSerializer(update).data,
                        status=http_status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        return Response(
            {"detail": "A release record is immutable. Push a new update instead."},
            status=http_status.HTTP_405_METHOD_NOT_ALLOWED)

    partial_update = update

    def destroy(self, request, *args, **kwargs):
        return Response(
            {"detail": "Release history is never deleted."},
            status=http_status.HTTP_405_METHOD_NOT_ALLOWED)

    @action(detail=False, methods=["get"])
    def approvers(self, request):
        """Users entitled to sign off a release — leads, managers and admins."""
        from accounts.serializers import UserSerializer
        qs = User.objects.filter(
            is_active=True,
            role__in=[Role.DEPARTMENT_LEAD, Role.MANAGER, Role.ADMIN]
        ).select_related("department").order_by("full_name", "username")
        return Response(UserSerializer(qs, many=True).data)


class FirmwareBuildViewSet(ScopedViewSetMixin, viewsets.ModelViewSet):
    """The catalogue of firmware builds that may be flashed onto an FC."""

    serializer_class = FirmwareBuildSerializer
    permission_classes = [CanManageFirmware]
    filterset_fields = ("is_active", "source_type", "firmware_type", "is_signed")
    ordering_fields = ("created_at", "name", "version")

    def get_scoped_queryset(self):
        # Catalogue/configuration: readable by all staff.
        return (FirmwareBuild.objects.select_related("parameter_profile", "created_by")
                .prefetch_related("fc_models"))

    def get_queryset(self):
        qs = super().get_queryset()
        search = self.request.query_params.get("search")
        if search:
            qs = qs.filter(Q(name__icontains=search) | Q(version__icontains=search)
                           | Q(git_sha__icontains=search)
                           | Q(description__icontains=search))
        return qs

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        build = config_services.create_firmware_build(
            actor=request.user, **serializer.validated_data)
        return Response(FirmwareBuildSerializer(build).data,
                        status=http_status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        build = self.get_object()
        serializer = self.get_serializer(build, data=request.data,
                                         partial=kwargs.pop("partial", False))
        serializer.is_valid(raise_exception=True)
        build = config_services.update_firmware_build(
            build, actor=request.user, **serializer.validated_data)
        return Response(FirmwareBuildSerializer(build).data)

    def partial_update(self, request, *args, **kwargs):
        return self.update(request, *args, partial=True, **kwargs)

    def destroy(self, request, *args, **kwargs):
        config_services.delete_firmware_build(self.get_object(), actor=request.user)
        return Response(status=http_status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["post"], url_path="set-active")
    def set_active(self, request, pk=None):
        s = ActiveFlagSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        build = config_services.set_firmware_build_active(
            self.get_object(), actor=request.user,
            is_active=s.validated_data["is_active"])
        return Response(FirmwareBuildSerializer(build).data)

    @action(detail=True, methods=["get"])
    def flashes(self, request, pk=None):
        """Every FC this build has been flashed onto."""
        build = self.get_object()
        qs = policy.scope_by_fc(request.user, build.flashes.select_related(
            "fc", "operator"))
        return Response(FirmwareRecordSerializer(qs, many=True).data)

    @action(detail=False, methods=["post"])
    def flash(self, request):
        """Record a flash of a catalogue build onto an FC, copying the build's
        fields into the FC's own firmware record."""
        s = FlashBuildSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        data = s.validated_data
        fc = get_object_or_404(policy.visible_fcs(request.user), pk=data["fc"])
        build = get_object_or_404(FirmwareBuild, pk=data["build"])
        stage_record = (StageRecord.objects.filter(pk=data.get("stage_record"),
                                                   fc=fc).first()
                        if data.get("stage_record") else None)
        record = config_services.flash_build_onto_fc(
            fc=fc, build=build, actor=request.user, stage_record=stage_record,
            flashing_result=data["flashing_result"],
            config_result=data["config_result"], notes=data.get("notes", ""))
        return Response(FirmwareRecordSerializer(record).data,
                        status=http_status.HTTP_201_CREATED)

    @action(detail=False, methods=["get"])
    def meta(self, request):
        return Response({
            "suggested_types": FirmwareBuild.SUGGESTED_TYPES,
            "source_types": [{"value": v, "label": l}
                             for v, l in FirmwareBuild.SOURCE_CHOICES],
            "results": [{"value": v, "label": l}
                        for v, l in FirmwareRecord.RESULT_CHOICES],
        })


class ChecklistItemViewSet(ScopedViewSetMixin, viewsets.ModelViewSet):
    """Individual tests inside a checklist. Manager-configurable."""

    serializer_class = ChecklistItemSerializer
    permission_classes = [IsManagerOrReadOnly]
    filterset_fields = ("template", "is_active", "is_mandatory")

    def get_scoped_queryset(self):
        # Catalogue/configuration: readable by all staff.
        return ChecklistItem.objects.select_related("template").all()

    def create(self, request, *args, **kwargs):
        template = get_object_or_404(ChecklistTemplate,
                                     pk=request.data.get("template"))
        item = config_services.add_checklist_item(
            template, actor=request.user,
            key=request.data.get("key", ""),
            label=request.data.get("label", ""),
            description=request.data.get("description", ""),
            is_mandatory=bool(request.data.get("is_mandatory", True)))
        return Response(ChecklistItemSerializer(item).data,
                        status=http_status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        item = self.get_object()
        serializer = self.get_serializer(item, data=request.data,
                                         partial=kwargs.pop("partial", False))
        serializer.is_valid(raise_exception=True)
        item = config_services.update_checklist_item(
            item, actor=request.user, **serializer.validated_data)
        return Response(ChecklistItemSerializer(item).data)

    def partial_update(self, request, *args, **kwargs):
        return self.update(request, *args, partial=True, **kwargs)

    def destroy(self, request, *args, **kwargs):
        config_services.delete_checklist_item(self.get_object(), actor=request.user)
        return Response(status=http_status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["post"], url_path="set-active")
    def set_active(self, request, pk=None):
        s = ActiveFlagSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        item = config_services.set_checklist_item_active(
            self.get_object(), actor=request.user,
            is_active=s.validated_data["is_active"])
        return Response(ChecklistItemSerializer(item).data)


# --- WP8: parameter files and configuration evidence --------------------------
from django.http import FileResponse  # noqa: E402
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser  # noqa: E402

from . import evidence as evidence_svc  # noqa: E402
from . import parameters as param_parser  # noqa: E402
from .models import ConfigEvidence, ParameterComparison, ParameterFile  # noqa: E402
from .serializers import (ConfigEvidenceSerializer,  # noqa: E402
                          ParameterCompareSerializer, ParameterComparisonSerializer,
                          ParameterFileSerializer)


class ParameterFileViewSet(ScopedViewSetMixin, viewsets.ReadOnlyModelViewSet):
    """Uploaded ``.param`` dumps (bytes stored once, by SHA-256), and the
    quick comparison between any two of them. Follows FC scope."""

    serializer_class = ParameterFileSerializer
    permission_classes = [CanWriteProduction]
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    filterset_fields = ("fc", "parameter_profile", "sha256")

    def get_scoped_queryset(self):
        # The parsed parameters and raw text are large and never needed for a
        # listing.
        return policy.scope_by_fc(self.request.user, ParameterFile.objects.select_related(
            "fc", "uploaded_by", "parameter_profile")).defer("parameters", "raw_text")

    def create(self, request, *args, **kwargs):
        upload = request.FILES.get("file")
        if upload is None:
            raise WorkflowError("Attach a .param file to upload.", code="file_required")
        fc_id = request.data.get("fc")
        fc = get_object_or_404(policy.visible_fcs(request.user), pk=fc_id) if fc_id else None
        record, created, skipped = evidence_svc.store_parameter_file(
            upload, actor=request.user, label=request.data.get("label", ""), fc=fc,
            parameter_profile=ParameterProfile.objects.filter(
                pk=request.data.get("parameter_profile")).first()
            if request.data.get("parameter_profile") else None)
        data = ParameterFileSerializer(record).data
        data["skipped_lines"] = skipped
        data["already_stored"] = not created
        return Response(data, status=http_status.HTTP_201_CREATED if created
                        else http_status.HTTP_200_OK)

    @action(detail=True, methods=["get"])
    def parameters(self, request, pk=None):
        record = self.get_object()
        record = ParameterFile.objects.only("id", "name", "parameters").get(pk=record.pk)
        return Response({"id": record.id, "name": record.name,
                         "parameters": record.parameters})

    @action(detail=True, methods=["get"])
    def download(self, request, pk=None):
        """The original bytes, after the scope check."""
        record = self.get_object()
        if not record.file:
            raise WorkflowError("This file predates byte storage; only its text was "
                                "kept.", code="no_original_bytes")
        response = FileResponse(record.file.open("rb"), as_attachment=True,
                                filename=record.name)
        response["X-Content-Type-Options"] = "nosniff"
        return response

    @action(detail=False, methods=["post"], permission_classes=[IsAuthenticated])
    def compare(self, request):
        """Diff two parameter sets. Each side may be a stored file
        (``left``/``right`` id) or an upload (``left_file``/``right_file``)."""
        s = ParameterCompareSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        tolerance = s.validated_data.get("tolerance") or 0.0
        left, left_name, left_skipped = self._side(request, "left")
        right, right_name, right_skipped = self._side(request, "right")
        result = param_parser.compare(left, right, tolerance=tolerance)
        result["left_name"] = left_name
        result["right_name"] = right_name
        result["skipped"] = {"left": left_skipped, "right": right_skipped}
        return Response(result)

    def _side(self, request, side):
        upload = request.FILES.get(f"{side}_file")
        if upload is not None:
            parameters, skipped = evidence_svc.parse_upload(upload)
            return parameters, upload.name, skipped
        stored_id = request.data.get(side)
        if not stored_id:
            raise WorkflowError(f"Provide a file or a stored dump for the {side}-hand "
                                "side.", code="side_required")
        record = policy.scope_by_fc(request.user, ParameterFile.objects.all()).filter(
            pk=stored_id).first()
        if record is None:
            raise WorkflowError(f"Parameter file {stored_id} was not found.",
                                code="not_found")
        return record.parameters, (record.label or record.name), record.parse_warnings


class ConfigEvidenceViewSet(ScopedViewSetMixin, viewsets.ReadOnlyModelViewSet):
    """Baselines, flashed records and read-backs. Created and associated
    through services; never edited or deleted."""

    serializer_class = ConfigEvidenceSerializer
    permission_classes = [CanWriteProduction]
    filterset_fields = ("fc", "kind", "file")

    def get_scoped_queryset(self):
        return policy.scope_by_fc(self.request.user, ConfigEvidence.objects.select_related(
            "file", "fc"))

    def create(self, request, *args, **kwargs):
        s = ConfigEvidenceSerializer(data=request.data,
                                     context=self.get_serializer_context())
        s.is_valid(raise_exception=True)
        d = dict(s.validated_data)
        evidence = evidence_svc.record_evidence(
            kind=d.pop("kind"), file=d.pop("file"), fc=d.pop("fc", None),
            actor=request.user, **d)
        return Response(ConfigEvidenceSerializer(
            evidence, context=self.get_serializer_context()).data,
            status=http_status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def associate(self, request, pk=None):
        fc = get_object_or_404(policy.visible_fcs(request.user), pk=request.data.get("fc"))
        new = evidence_svc.associate_unit(
            self.get_object(), fc=fc, actor=request.user,
            reason=request.data.get("reason", ""),
            confidence=request.data.get("confidence") or ConfigEvidence.PROBABLE)
        return Response(ConfigEvidenceSerializer(
            new, context=self.get_serializer_context()).data,
            status=http_status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="approve-baseline")
    def approve_baseline(self, request, pk=None):
        evidence_svc.approve_baseline(
            self.get_object(), actor=request.user,
            revision=request.data.get("revision", ""),
            compatibility=request.data.get("compatibility", ""),
            scope=request.data.get("scope", ""))
        return Response(ConfigEvidenceSerializer(
            self.get_object(), context=self.get_serializer_context()).data)


class ParameterComparisonViewSet(ScopedViewSetMixin, viewsets.ReadOnlyModelViewSet):
    """Recorded comparisons between two pieces of evidence: differences and
    parser warnings, with no safety verdict."""

    serializer_class = ParameterComparisonSerializer
    permission_classes = [CanWriteProduction]

    def get_scoped_queryset(self):
        return policy.scope_by_fc(self.request.user, ParameterComparison.objects.all())

    def create(self, request, *args, **kwargs):
        s = ParameterComparisonSerializer(data=request.data,
                                          context=self.get_serializer_context())
        s.is_valid(raise_exception=True)
        d = s.validated_data
        comparison = evidence_svc.compare_evidence(
            d["left_evidence"], d["right_evidence"], actor=request.user,
            tolerance=d.get("tolerance") or 0.0)
        return Response(ParameterComparisonSerializer(
            comparison, context=self.get_serializer_context()).data,
            status=http_status.HTTP_201_CREATED)
