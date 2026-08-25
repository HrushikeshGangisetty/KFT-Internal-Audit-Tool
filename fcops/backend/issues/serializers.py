from rest_framework import serializers

from fc.lifecycle import Stage

from .models import (Category, Issue, IssueAttachment, IssueInvestigationNote,
                     IssueReassignmentLog, IssueStatus, KnownIssue, Severity)


class InvestigationNoteSerializer(serializers.ModelSerializer):
    author_name = serializers.CharField(source="author.full_name", read_only=True,
                                        default="")
    author_department = serializers.CharField(source="author.department.name",
                                              read_only=True, default="")

    class Meta:
        model = IssueInvestigationNote
        fields = ("id", "issue", "author", "author_name", "author_department",
                  "note", "created_at")
        read_only_fields = ("issue", "author")


class ReassignmentLogSerializer(serializers.ModelSerializer):
    from_department_name = serializers.CharField(source="from_department.name",
                                                 read_only=True, default="")
    to_department_name = serializers.CharField(source="to_department.name",
                                               read_only=True, default="")
    actor_name = serializers.CharField(source="actor.full_name", read_only=True,
                                       default="")
    to_person_name = serializers.CharField(source="to_person.full_name",
                                           read_only=True, default="")

    class Meta:
        model = IssueReassignmentLog
        fields = ("id", "from_department", "from_department_name", "to_department",
                  "to_department_name", "from_person", "to_person", "to_person_name",
                  "reason", "actor", "actor_name", "created_at")


class IssueAttachmentSerializer(serializers.ModelSerializer):
    uploaded_by_name = serializers.CharField(source="uploaded_by.full_name",
                                             read_only=True, default="")
    url = serializers.SerializerMethodField()

    class Meta:
        model = IssueAttachment
        fields = ("id", "issue", "file", "url", "original_name", "content_type",
                  "size", "uploaded_by", "uploaded_by_name", "created_at")
        read_only_fields = ("uploaded_by", "size", "content_type")

    def get_url(self, obj):
        try:
            return obj.file.url
        except ValueError:
            return ""


class KnownIssueSerializer(serializers.ModelSerializer):
    occurrence_count = serializers.IntegerField(read_only=True)
    promoted_by_name = serializers.CharField(source="promoted_by.full_name",
                                             read_only=True, default="")
    owning_department_name = serializers.CharField(source="owning_department.name",
                                                   read_only=True, default="")

    class Meta:
        model = KnownIssue
        fields = ("id", "title", "symptoms_summary", "root_cause", "resolution",
                  "category", "affected_revisions", "affected_firmware",
                  "affected_software", "owning_department", "owning_department_name",
                  "status", "promoted_by", "promoted_by_name",
                  "first_occurrence_issue", "last_occurrence_issue",
                  "verification_count", "occurrence_count", "created_at",
                  "updated_at")
        read_only_fields = ("promoted_by", "first_occurrence_issue",
                            "last_occurrence_issue", "verification_count")


class IssueListSerializer(serializers.ModelSerializer):
    fc_serial = serializers.CharField(source="fc.serial", read_only=True)
    stage_label = serializers.SerializerMethodField()
    discovering_department_name = serializers.CharField(
        source="discovering_department.name", read_only=True, default="")
    assigned_department_name = serializers.CharField(
        source="assigned_department.name", read_only=True, default="")
    assigned_person_name = serializers.CharField(source="assigned_person.full_name",
                                                 read_only=True, default="")
    rank = serializers.FloatField(read_only=True, required=False)

    class Meta:
        model = Issue
        fields = ("id", "key", "fc", "fc_serial", "title", "symptoms",
                  "discovered_stage", "stage_label", "discovering_department",
                  "discovering_department_name", "assigned_department",
                  "assigned_department_name", "assigned_person",
                  "assigned_person_name", "category", "severity", "status",
                  "is_waiting", "is_recurring", "known_issue", "firmware_version",
                  "hardware_revision", "gcs_version", "configurator_version",
                  "created_at", "updated_at", "resolved_at", "rank")

    def get_stage_label(self, obj):
        return Stage(obj.discovered_stage).label


class IssueDetailSerializer(IssueListSerializer):
    investigation_notes = InvestigationNoteSerializer(many=True, read_only=True)
    reassignments = ReassignmentLogSerializer(many=True, read_only=True)
    attachments = IssueAttachmentSerializer(many=True, read_only=True)
    known_issue_detail = KnownIssueSerializer(source="known_issue", read_only=True)
    discovered_by_name = serializers.CharField(source="discovered_by.full_name",
                                               read_only=True, default="")
    resolved_by_name = serializers.CharField(source="resolved_by.full_name",
                                             read_only=True, default="")
    verified_by_name = serializers.CharField(source="verified_by.full_name",
                                             read_only=True, default="")
    root_cause_department_name = serializers.CharField(
        source="root_cause_department.name", read_only=True, default="")
    allowed_transitions = serializers.SerializerMethodField()

    class Meta(IssueListSerializer.Meta):
        fields = IssueListSerializer.Meta.fields + (
            "description", "symptom_tags", "root_cause", "root_cause_department",
            "root_cause_department_name", "resolution", "waiting_reason",
            "parameter_profile", "discovered_by", "discovered_by_name",
            "discovered_stage_record", "resolved_by", "resolved_by_name",
            "verified_by", "verified_by_name", "verified_at", "closed_at",
            "investigation_notes", "reassignments", "attachments",
            "known_issue_detail", "allowed_transitions")

    def get_allowed_transitions(self, obj):
        from .models import ISSUE_TRANSITIONS
        return list(ISSUE_TRANSITIONS.get(obj.status, []))


class IssueCreateSerializer(serializers.Serializer):
    fc = serializers.IntegerField()
    title = serializers.CharField(max_length=255)
    symptoms = serializers.CharField()
    description = serializers.CharField(required=False, allow_blank=True, default="")
    discovered_stage = serializers.ChoiceField(choices=Stage.choices, required=False)
    discovered_stage_record = serializers.IntegerField(required=False, allow_null=True)
    category = serializers.ChoiceField(choices=Category.choices, required=False)
    severity = serializers.ChoiceField(choices=Severity.choices,
                                       default=Severity.MAJOR)
    assigned_department = serializers.IntegerField(required=False, allow_null=True)
    assigned_person = serializers.IntegerField(required=False, allow_null=True)
    symptom_tags = serializers.ListField(child=serializers.CharField(),
                                         required=False, default=list)
    firmware_version = serializers.CharField(required=False, allow_blank=True)
    hardware_revision = serializers.CharField(required=False, allow_blank=True)
    gcs_version = serializers.CharField(required=False, allow_blank=True)
    configurator_version = serializers.CharField(required=False, allow_blank=True)
    parameter_profile = serializers.CharField(required=False, allow_blank=True)


class StatusChangeSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=IssueStatus.choices)
    note = serializers.CharField(required=False, allow_blank=True, default="")
    root_cause = serializers.CharField(required=False, allow_blank=True)
    resolution = serializers.CharField(required=False, allow_blank=True)
    root_cause_department = serializers.IntegerField(required=False, allow_null=True)


class ReassignSerializer(serializers.Serializer):
    to_department = serializers.IntegerField(required=False, allow_null=True)
    to_person = serializers.IntegerField(required=False, allow_null=True)
    reason = serializers.CharField()


class SimilarQuerySerializer(serializers.Serializer):
    text = serializers.CharField(required=False, allow_blank=True, default="")
    stage = serializers.CharField(required=False, allow_blank=True)
    category = serializers.CharField(required=False, allow_blank=True)
    hardware_revision = serializers.CharField(required=False, allow_blank=True)
    firmware_version = serializers.CharField(required=False, allow_blank=True)
    gcs_version = serializers.CharField(required=False, allow_blank=True)
    configurator_version = serializers.CharField(required=False, allow_blank=True)
    parameter_profile = serializers.CharField(required=False, allow_blank=True)
    exclude_issue_id = serializers.IntegerField(required=False, allow_null=True)
    limit = serializers.IntegerField(required=False, default=10)
