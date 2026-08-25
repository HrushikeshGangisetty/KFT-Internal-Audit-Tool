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


class FCModelTypeViewSet(viewsets.ModelViewSet):
    """FC models, owned by the Manager. Models in use are archived, never
    deleted, so historical FCs keep a valid reference."""

    queryset = FCModelType.objects.all()
    serializer_class = FCModelTypeSerializer
    permission_classes = [IsManagerOrReadOnly]
    filterset_fields = ("is_active",)

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


class ParameterProfileViewSet(viewsets.ModelViewSet):
    queryset = ParameterProfile.objects.all()
    serializer_class = ParameterProfileSerializer
    permission_classes = [CanWriteProduction]


class SoftwareVersionViewSet(viewsets.ModelViewSet):
    queryset = SoftwareVersion.objects.all()
    serializer_class = SoftwareVersionSerializer
    permission_classes = [CanWriteProduction]
    filterset_fields = ("kind", "is_active")


class ChecklistTemplateViewSet(viewsets.ModelViewSet):
    """Test checklists. Managers configure them; everyone can read the current
    definition because testers need it to run a test."""

    queryset = ChecklistTemplate.objects.prefetch_related("checklist_items").all()
    permission_classes = [IsManagerOrReadOnly]
    filterset_fields = ("stage", "fc_model", "is_active")

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


class FlightControllerViewSet(viewsets.ModelViewSet):
    queryset = (FlightController.objects.select_related("fc_model", "registered_by",
                                                        "approved_by")
                .all())
    permission_classes = [CanWriteProduction]
    filterset_fields = ("status", "current_stage", "fc_model", "hardware_revision")
    ordering_fields = ("created_at", "serial", "updated_at")

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
        return Response(FCEventSerializer(services.build_timeline(fc), many=True).data)

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
        qs = fc.issues.select_related("assigned_department", "discovering_department",
                                      "assigned_person", "discovered_by").all()
        return Response(IssueListSerializer(qs, many=True).data)

    @action(detail=True, methods=["get"])
    def audit_log(self, request, pk=None):
        from core.serializers import AuditLogEntrySerializer
        fc = self.get_object()
        qs = fc.audit_entries.select_related("actor").all()[:500]
        return Response(AuditLogEntrySerializer(qs, many=True).data)


class StageRecordViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = StageRecord.objects.select_related("fc", "operator", "department").all()
    serializer_class = StageRecordSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ("fc", "stage", "status")


class ReworkRecordViewSet(viewsets.ModelViewSet):
    queryset = ReworkRecord.objects.select_related("fc", "stage_record",
                                                   "performed_by").all()
    serializer_class = ReworkRecordSerializer
    permission_classes = [CanWriteProduction]
    filterset_fields = ("fc", "outcome", "stage_record")

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


class FirmwareRecordViewSet(viewsets.ModelViewSet):
    queryset = FirmwareRecord.objects.select_related("fc", "operator",
                                                     "parameter_profile").all()
    serializer_class = FirmwareRecordSerializer
    permission_classes = [CanWriteProduction]
    filterset_fields = ("fc", "version", "source_type", "flashing_result")

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


class TestResultViewSet(viewsets.ModelViewSet):
    queryset = TestResult.objects.select_related("fc", "tester", "stage_record",
                                                 "gcs_version",
                                                 "configurator_version").all()
    serializer_class = TestResultSerializer
    permission_classes = [CanWriteProduction]
    filterset_fields = ("fc", "test_type", "overall_passed")

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
class SoftwareUpdateViewSet(viewsets.ModelViewSet):
    """Internal release records for the in-house GCS / Configurator.

    Readable by everyone (the release history is knowledge), writable only by
    the Software department. Records are never edited or deleted: a release
    happened, and correcting it means pushing another one.
    """

    queryset = (SoftwareUpdate.objects
                .select_related("approved_by", "pushed_by", "software_version")
                .all())
    serializer_class = SoftwareUpdateSerializer
    permission_classes = [CanPushSoftwareUpdate]
    filterset_fields = ("kind", "approved_by", "pushed_by")
    ordering_fields = ("created_at", "version")

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


class FirmwareBuildViewSet(viewsets.ModelViewSet):
    """The catalogue of firmware builds that may be flashed onto an FC."""

    queryset = (FirmwareBuild.objects
                .select_related("parameter_profile", "created_by")
                .prefetch_related("fc_models").all())
    serializer_class = FirmwareBuildSerializer
    permission_classes = [CanManageFirmware]
    filterset_fields = ("is_active", "source_type", "firmware_type", "is_signed")
    ordering_fields = ("created_at", "name", "version")

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
        qs = build.flashes.select_related("fc", "operator").all()
        return Response(FirmwareRecordSerializer(qs, many=True).data)

    @action(detail=False, methods=["post"])
    def flash(self, request):
        """Record a flash of a catalogue build onto an FC, copying the build's
        fields into the FC's own firmware record."""
        s = FlashBuildSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        data = s.validated_data
        fc = get_object_or_404(FlightController, pk=data["fc"])
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


class ChecklistItemViewSet(viewsets.ModelViewSet):
    """Individual tests inside a checklist. Manager-configurable."""

    queryset = ChecklistItem.objects.select_related("template").all()
    serializer_class = ChecklistItemSerializer
    permission_classes = [IsManagerOrReadOnly]
    filterset_fields = ("template", "is_active", "is_mandatory")

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
