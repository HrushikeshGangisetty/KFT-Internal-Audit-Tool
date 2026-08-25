from django.db.models import Count, Q
from django.utils import timezone
from rest_framework import status as http_status
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from accounts.models import Department
from accounts.permissions import CanWriteProduction, IsAdmin, IsManager
from core import audit
from core.exceptions import WorkflowError
from core.models import AuditLogEntry

from . import services
from .lifecycle import (ALLOWED_REWORK_TARGETS, STAGE_ORDER, TEST_STAGES, Stage,
                        rework_targets)
from .models import (ChecklistTemplate, FCModelType, FirmwareRecord,
                     FlightController, ParameterProfile, ReworkRecord,
                     SoftwareVersion, StageRecord, StageStatus, TestResult)
from .serializers import (ApprovalSerializer, ChecklistTemplateSerializer,
                          FCCreateSerializer, FCEventSerializer,
                          FCModelTypeSerializer, FirmwareRecordSerializer,
                          FlightControllerDetailSerializer,
                          FlightControllerListSerializer, OverrideSerializer,
                          ParameterProfileSerializer, ReworkRecordSerializer,
                          SoftwareVersionSerializer, StageActionSerializer,
                          StageRecordSerializer, TestResultSerializer)


class FCModelTypeViewSet(viewsets.ModelViewSet):
    queryset = FCModelType.objects.all()
    serializer_class = FCModelTypeSerializer

    def get_permissions(self):
        return [IsAuthenticated()] if self.request.method in ("GET", "HEAD", "OPTIONS") \
            else [IsAdmin()]


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
    queryset = ChecklistTemplate.objects.all()
    serializer_class = ChecklistTemplateSerializer
    filterset_fields = ("stage", "fc_model", "is_active")

    def get_permissions(self):
        return [IsAuthenticated()] if self.request.method in ("GET", "HEAD", "OPTIONS") \
            else [IsAdmin()]


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
        obj.save(update_fields=["overall_passed"])
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
