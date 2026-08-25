from rest_framework import serializers

from accounts.serializers import DepartmentSerializer, UserSerializer

from .lifecycle import ALLOWED_REWORK_TARGETS, STAGE_ORDER, Stage, rework_targets
from .models import (ChecklistItem, ChecklistTemplate, FCEvent, FCModelType,
                     FirmwareBuild, FirmwareRecord, FlightController,
                     ParameterProfile, ReworkRecord, SoftwareUpdate,
                     SoftwareVersion, StageRecord, TestResult)


class FCModelTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = FCModelType
        fields = ("id", "name", "code", "description", "is_active")


class ParameterProfileSerializer(serializers.ModelSerializer):
    label = serializers.CharField(source="__str__", read_only=True)

    class Meta:
        model = ParameterProfile
        fields = ("id", "name", "version", "contents_ref", "notes", "label")


class SoftwareVersionSerializer(serializers.ModelSerializer):
    class Meta:
        model = SoftwareVersion
        fields = ("id", "kind", "version", "released_on", "notes", "is_active")


class ChecklistTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChecklistTemplate
        fields = ("id", "fc_model", "stage", "name", "items", "is_active")


class StageRecordSerializer(serializers.ModelSerializer):
    stage_label = serializers.SerializerMethodField()
    operator_name = serializers.CharField(source="operator.full_name", read_only=True,
                                          default="")
    department_name = serializers.CharField(source="department.name", read_only=True,
                                            default="")
    signed_off_by_name = serializers.CharField(source="signed_off_by.full_name",
                                               read_only=True, default="")
    is_locked = serializers.BooleanField(read_only=True)
    allowed_rework_targets = serializers.SerializerMethodField()

    class Meta:
        model = StageRecord
        fields = ("id", "fc", "stage", "stage_label", "attempt", "status",
                  "operator", "operator_name", "department", "department_name",
                  "started_at", "completed_at", "notes", "signed_off_by",
                  "signed_off_by_name", "is_locked", "triggered_by_rework",
                  "allowed_rework_targets", "created_at")
        read_only_fields = ("fc", "attempt", "status", "signed_off_by")

    def get_stage_label(self, obj):
        return Stage(obj.stage).label

    def get_allowed_rework_targets(self, obj):
        return [{"value": s, "label": Stage(s).label}
                for s in rework_targets(obj.stage)]


class ReworkRecordSerializer(serializers.ModelSerializer):
    performed_by_name = serializers.CharField(source="performed_by.full_name",
                                              read_only=True, default="")
    originating_issue_key = serializers.CharField(source="originating_issue.key",
                                                  read_only=True, default="")
    stage = serializers.CharField(source="stage_record.stage", read_only=True)

    class Meta:
        model = ReworkRecord
        fields = ("id", "fc", "stage_record", "stage", "originating_issue",
                  "originating_issue_key", "description", "performed_by",
                  "performed_by_name", "department", "return_to_stage", "outcome",
                  "outcome_notes", "completed_at", "created_at")
        read_only_fields = ("fc", "performed_by", "outcome", "completed_at")


class FirmwareRecordSerializer(serializers.ModelSerializer):
    operator_name = serializers.CharField(source="operator.full_name",
                                          read_only=True, default="")
    parameter_profile_label = serializers.CharField(source="parameter_profile.__str__",
                                                    read_only=True, default="")

    class Meta:
        model = FirmwareRecord
        fields = ("id", "fc", "stage_record", "firmware_name", "version",
                  "source_type", "is_signed", "is_locked", "bootloader_version",
                  "build_ref", "parameter_profile", "parameter_profile_label",
                  "script_name", "script_version", "flashing_result",
                  "config_result", "operator", "operator_name", "notes",
                  "is_current", "created_at")
        read_only_fields = ("operator",)


class TestResultSerializer(serializers.ModelSerializer):
    tester_name = serializers.CharField(source="tester.full_name", read_only=True,
                                        default="")
    gcs_version_label = serializers.CharField(source="gcs_version.version",
                                              read_only=True, default="")
    configurator_version_label = serializers.CharField(
        source="configurator_version.version", read_only=True, default="")

    class Meta:
        model = TestResult
        fields = ("id", "fc", "stage_record", "test_type", "template",
                  "template_version", "checklist_results", "overall_passed",
                  "tester", "tester_name",
                  "gcs_version", "gcs_version_label", "configurator_version",
                  "configurator_version_label", "linked_issue", "notes",
                  "created_at")
        read_only_fields = ("tester", "overall_passed", "template_version")


class FCEventSerializer(serializers.ModelSerializer):
    actor_name = serializers.CharField(source="actor.full_name", read_only=True,
                                       default="")
    issue_key = serializers.CharField(source="issue.key", read_only=True, default="")
    stage_label = serializers.SerializerMethodField()

    class Meta:
        model = FCEvent
        fields = ("id", "kind", "title", "detail", "stage", "stage_label",
                  "actor", "actor_name", "issue", "issue_key", "payload",
                  "created_at")

    def get_stage_label(self, obj):
        return Stage(obj.stage).label if obj.stage else ""


class FlightControllerListSerializer(serializers.ModelSerializer):
    fc_model_name = serializers.CharField(source="fc_model.name", read_only=True)
    stage_label = serializers.SerializerMethodField()
    open_issue_count = serializers.SerializerMethodField()

    class Meta:
        model = FlightController
        fields = ("id", "serial", "fc_model", "fc_model_name", "hardware_revision",
                  "pcb_batch", "current_stage", "stage_label", "status",
                  "open_issue_count", "created_at", "updated_at")

    def get_stage_label(self, obj):
        return Stage(obj.current_stage).label

    def get_open_issue_count(self, obj):
        return obj.open_issues.count()


class FlightControllerDetailSerializer(FlightControllerListSerializer):
    stage_progress = serializers.SerializerMethodField()
    current_firmware = serializers.SerializerMethodField()
    registered_by_name = serializers.CharField(source="registered_by.full_name",
                                               read_only=True, default="")
    approved_by_name = serializers.CharField(source="approved_by.full_name",
                                             read_only=True, default="")
    approval_blockers = serializers.SerializerMethodField()
    stage_blockers = serializers.SerializerMethodField()

    class Meta(FlightControllerListSerializer.Meta):
        fields = FlightControllerListSerializer.Meta.fields + (
            "notes", "stage_progress", "current_firmware", "registered_by_name",
            "approved_by_name", "approved_at", "approval_note", "approval_blockers",
            "stage_blockers")

    def get_stage_progress(self, obj):
        rows = obj.stage_progress()
        for row in rows:
            row["stage"] = str(row["stage"])
        return rows

    def get_current_firmware(self, obj):
        fw = obj.firmware_records.filter(is_current=True).first()
        return FirmwareRecordSerializer(fw).data if fw else None

    def get_approval_blockers(self, obj):
        from .services import approval_blockers
        blockers, warnings = approval_blockers(obj)
        return {"blockers": blockers, "warnings": warnings}

    def get_stage_blockers(self, obj):
        """Why the *current* stage cannot be passed — shown before the user
        clicks, not only after the attempt fails."""
        from .services import stage_blockers
        return stage_blockers(obj)


class FCCreateSerializer(serializers.Serializer):
    fc_model = serializers.PrimaryKeyRelatedField(queryset=FCModelType.objects.all())
    hardware_revision = serializers.CharField(required=False, allow_blank=True,
                                              default="")
    pcb_batch = serializers.CharField(required=False, allow_blank=True, default="")
    notes = serializers.CharField(required=False, allow_blank=True, default="")
    serial = serializers.CharField(required=False, allow_blank=True)


class StageActionSerializer(serializers.Serializer):
    stage = serializers.ChoiceField(choices=Stage.choices, required=False)
    notes = serializers.CharField(required=False, allow_blank=True, default="")
    department = serializers.IntegerField(required=False, allow_null=True)


class ApprovalSerializer(serializers.Serializer):
    approve = serializers.BooleanField()
    note = serializers.CharField(required=False, allow_blank=True, default="")
    deviation_justification = serializers.CharField(required=False, allow_blank=True,
                                                    default="")


class OverrideSerializer(serializers.Serializer):
    target_stage = serializers.ChoiceField(choices=Stage.choices)
    reason = serializers.CharField()


# ---------------------------------------------------------------------------
# Configuration & catalogue features
# ---------------------------------------------------------------------------
class SoftwareUpdateSerializer(serializers.ModelSerializer):
    kind_display = serializers.CharField(source="get_kind_display", read_only=True)
    pushed_by_name = serializers.CharField(source="pushed_by.full_name",
                                           read_only=True, default="")
    approved_by_name = serializers.CharField(source="approved_by.full_name",
                                             read_only=True, default="")
    approved_by_role = serializers.CharField(source="approved_by.get_role_display",
                                             read_only=True, default="")
    short_sha = serializers.CharField(read_only=True)

    class Meta:
        model = SoftwareUpdate
        fields = ("id", "kind", "kind_display", "version", "git_sha", "short_sha",
                  "release_notes", "approved_by", "approved_by_name",
                  "approved_by_role", "approved_at", "pushed_by", "pushed_by_name",
                  "software_version", "created_at")
        read_only_fields = ("pushed_by", "approved_at", "software_version")


class SoftwareUpdateCreateSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=SoftwareUpdate.KIND_CHOICES)
    version = serializers.CharField(max_length=64)
    git_sha = serializers.CharField(max_length=120)
    release_notes = serializers.CharField()
    approved_by = serializers.IntegerField()


class FirmwareBuildSerializer(serializers.ModelSerializer):
    created_by_name = serializers.CharField(source="created_by.full_name",
                                            read_only=True, default="")
    parameter_profile_label = serializers.CharField(
        source="parameter_profile.__str__", read_only=True, default="")
    flash_count = serializers.IntegerField(read_only=True)
    is_in_use = serializers.BooleanField(read_only=True)
    source_type_display = serializers.CharField(source="get_source_type_display",
                                                read_only=True)

    class Meta:
        model = FirmwareBuild
        fields = ("id", "name", "firmware_type", "version", "git_sha",
                  "build_datetime", "source_type", "source_type_display",
                  "description", "includes_scripts", "script_name",
                  "script_version", "script_notes", "is_signed", "is_locked",
                  "bootloader_version", "bootloader_notes", "parameter_profile",
                  "parameter_profile_label", "fc_models", "is_active",
                  "created_by", "created_by_name", "flash_count", "is_in_use",
                  "created_at", "updated_at")
        read_only_fields = ("created_by",)


class ChecklistItemSerializer(serializers.ModelSerializer):
    is_in_use = serializers.BooleanField(read_only=True)

    class Meta:
        model = ChecklistItem
        fields = ("id", "template", "key", "label", "description", "is_mandatory",
                  "order", "is_active", "is_in_use", "created_at", "updated_at")
        read_only_fields = ("template",)


class ChecklistTemplateDetailSerializer(serializers.ModelSerializer):
    checklist_items = ChecklistItemSerializer(many=True, read_only=True)
    active_item_count = serializers.SerializerMethodField()
    stage_label = serializers.SerializerMethodField()

    class Meta:
        model = ChecklistTemplate
        fields = ("id", "fc_model", "stage", "stage_label", "name", "version",
                  "is_active", "checklist_items", "active_item_count")

    def get_active_item_count(self, obj):
        return obj.active_items().count()

    def get_stage_label(self, obj):
        return Stage(obj.stage).label


class ReorderSerializer(serializers.Serializer):
    ordered_ids = serializers.ListField(child=serializers.IntegerField())


class ActiveFlagSerializer(serializers.Serializer):
    is_active = serializers.BooleanField()


class FlashBuildSerializer(serializers.Serializer):
    fc = serializers.IntegerField()
    build = serializers.IntegerField()
    stage_record = serializers.IntegerField(required=False, allow_null=True)
    flashing_result = serializers.ChoiceField(
        choices=FirmwareRecord.RESULT_CHOICES, default=FirmwareRecord.RESULT_SUCCESS)
    config_result = serializers.ChoiceField(
        choices=FirmwareRecord.RESULT_CHOICES, default=FirmwareRecord.RESULT_SUCCESS)
    notes = serializers.CharField(required=False, allow_blank=True, default="")
