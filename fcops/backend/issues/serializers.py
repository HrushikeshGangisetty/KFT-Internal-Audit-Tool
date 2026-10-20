from rest_framework import serializers

from access import policy
from access.mixins import ScopedPrimaryKeyRelatedField
from fc.lifecycle import Stage

from .models import (Category, Handoff, Impact, Issue, IssueAttachment, IssueEvent,
                     IssueInvestigationNote, IssueKind, IssueParticipant,
                     IssueReassignmentLog, IssueStatus, IssueUnitLink, KnownIssue,
                     ProductArea, Resolution, Severity, Urgency, Verification)


def _scoped_issues(serializer):
    """The request user's visible issues, computed once per serializer tree."""
    root = serializer.root
    if not hasattr(root, "_visible_issues"):
        root._visible_issues = policy.visible_issues(root.context["request"].user)
    return root._visible_issues


class InvestigationNoteSerializer(serializers.ModelSerializer):
    author_name = serializers.CharField(source="author.full_name", read_only=True,
                                        default="")
    author_department = serializers.CharField(source="author.department.name",
                                              read_only=True, default="")

    class Meta:
        model = IssueInvestigationNote
        fields = ("id", "issue", "author", "author_name", "author_department",
                  "note", "note_type", "supersedes", "created_at")
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
    issue = ScopedPrimaryKeyRelatedField(policy.visible_issues)
    uploaded_by_name = serializers.CharField(source="uploaded_by.full_name",
                                             read_only=True, default="")
    url = serializers.SerializerMethodField()

    class Meta:
        model = IssueAttachment
        fields = ("id", "issue", "file", "url", "original_name", "content_type",
                  "size", "uploaded_by", "uploaded_by_name", "created_at")
        read_only_fields = ("uploaded_by", "size", "content_type")

    def get_url(self, obj):
        # Never the storage URL: downloads go through the scope check.
        return f"/api/issue-attachments/{obj.pk}/download/"

    def to_representation(self, obj):
        data = super().to_representation(obj)
        data.pop("file", None)
        return data


class KnownIssueSerializer(serializers.ModelSerializer):
    """Occurrence counts and links only ever cover the reader's visible
    issues, so a hidden issue can show up neither as a link nor as a count."""

    occurrence_count = serializers.SerializerMethodField()
    verification_count = serializers.SerializerMethodField()
    first_occurrence_issue = serializers.SerializerMethodField()
    last_occurrence_issue = serializers.SerializerMethodField()
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
                  "updated_at", "audience", "audience_departments")
        read_only_fields = ("promoted_by",)

    def _occurrences(self, obj):
        return _scoped_issues(self).filter(known_issue=obj)

    def get_occurrence_count(self, obj):
        return self._occurrences(obj).count()

    def get_verification_count(self, obj):
        return self._occurrences(obj).filter(
            status__in=[IssueStatus.VERIFIED, IssueStatus.CLOSED]).count()

    def get_first_occurrence_issue(self, obj):
        return self._occurrences(obj).order_by("created_at").values_list(
            "pk", flat=True).first()

    def get_last_occurrence_issue(self, obj):
        return self._occurrences(obj).order_by("-created_at").values_list(
            "pk", flat=True).first()


class IssueListSerializer(serializers.ModelSerializer):
    customer = ScopedPrimaryKeyRelatedField(policy.visible_customers, required=False, allow_null=True)
    deployment = ScopedPrimaryKeyRelatedField(policy.visible_deployments, required=False, allow_null=True)

    def to_representation(self, obj):
        data = super().to_representation(obj)
        user = self.context["request"].user
        if not policy.can_view_fcs(user):
            data["customer"] = None
            data["deployment"] = None
        return data

    fc_serial = serializers.CharField(source="fc.serial", read_only=True, default="")
    queue_name = serializers.CharField(source="queue.name", read_only=True, default="")
    accountable_user_name = serializers.CharField(
        source="accountable_user.full_name", read_only=True, default="")
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
                  "created_at", "updated_at", "resolved_at", "rank",
                  "product_area", "urgency", "impact", "kind", "parent",
                  "blocks_stage", "queue", "queue_name", "accountable_user",
                  "accountable_user_name", "acknowledged_at", "submitted_at", "customer", "deployment")

    def get_stage_label(self, obj):
        return Stage(obj.discovered_stage).label if obj.discovered_stage else ""


class ParticipantSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source="user.full_name", read_only=True,
                                      default="")

    class Meta:
        model = IssueParticipant
        fields = ("id", "user", "user_name", "role", "added_by", "added_at")


class IssueEventSerializer(serializers.ModelSerializer):
    actor_name = serializers.CharField(source="actor.full_name", read_only=True,
                                       default="")

    class Meta:
        model = IssueEvent
        fields = ("id", "type", "actor", "actor_name", "at", "data")


class HandoffSerializer(serializers.ModelSerializer):
    to_department_name = serializers.CharField(source="to_department.name",
                                               read_only=True)
    issue_key = serializers.CharField(source="issue.key", read_only=True)

    class Meta:
        model = Handoff
        fields = ("id", "issue", "issue_key", "from_user", "from_department",
                  "to_department", "to_department_name", "to_user", "reason",
                  "proposed_by", "proposed_at", "status", "responded_by",
                  "responded_at", "response_reason")
        read_only_fields = fields


class UnitLinkSerializer(serializers.ModelSerializer):
    fc_serial = serializers.CharField(source="fc.serial", read_only=True)

    class Meta:
        model = IssueUnitLink
        fields = ("id", "fc", "fc_serial", "linked_by", "linked_at", "reason")


class VerificationSerializer(serializers.ModelSerializer):
    verifier_name = serializers.CharField(source="verifier.full_name", read_only=True,
                                          default="")

    class Meta:
        model = Verification
        fields = ("id", "verifier", "verifier_name", "at", "what_tested", "evidence",
                  "result", "notes")


class ResolutionSerializer(serializers.ModelSerializer):
    resolved_by_name = serializers.CharField(source="resolved_by.full_name",
                                             read_only=True, default="")
    verifications = VerificationSerializer(many=True, read_only=True)

    class Meta:
        model = Resolution
        fields = ("id", "resolved_by", "resolved_by_name", "at", "change_summary",
                  "root_cause_status", "workaround", "evidence_links",
                  "affected_versions", "affected_units", "unresolved_risks",
                  "verifications")


class IssueDetailSerializer(IssueListSerializer):
    investigation_notes = InvestigationNoteSerializer(many=True, read_only=True)
    reassignments = ReassignmentLogSerializer(many=True, read_only=True)
    attachments = IssueAttachmentSerializer(many=True, read_only=True)
    known_issue_detail = serializers.SerializerMethodField()
    participants = serializers.SerializerMethodField()
    discovered_by_name = serializers.CharField(source="discovered_by.full_name",
                                               read_only=True, default="")
    resolved_by_name = serializers.CharField(source="resolved_by.full_name",
                                             read_only=True, default="")
    verified_by_name = serializers.CharField(source="verified_by.full_name",
                                             read_only=True, default="")
    root_cause_department_name = serializers.CharField(
        source="root_cause_department.name", read_only=True, default="")
    allowed_transitions = serializers.SerializerMethodField()
    parent_summary = serializers.SerializerMethodField()
    reporter_name = serializers.CharField(source="reporter.full_name", read_only=True,
                                          default="")
    events = IssueEventSerializer(many=True, read_only=True)
    handoffs = HandoffSerializer(many=True, read_only=True)
    unit_links = UnitLinkSerializer(many=True, read_only=True)
    resolutions = ResolutionSerializer(many=True, read_only=True)
    ack_due_at = serializers.SerializerMethodField()
    versions_at_time = serializers.SerializerMethodField()

    class Meta(IssueListSerializer.Meta):
        fields = IssueListSerializer.Meta.fields + (
            "description", "symptom_tags", "root_cause", "root_cause_department",
            "root_cause_department_name", "resolution", "waiting_reason",
            "parameter_profile", "discovered_by", "discovered_by_name",
            "discovered_stage_record", "resolved_by", "resolved_by_name",
            "verified_by", "verified_by_name", "verified_at", "closed_at",
            "investigation_notes", "reassignments", "attachments",
            "known_issue_detail", "participants", "allowed_transitions",
            "reporter", "reporter_name", "occurred_at_approx", "location_context",
            "reproduction_notes", "acknowledged_by", "parent_summary", "events",
            "handoffs", "unit_links", "resolutions", "ack_due_at",
            "waiting_dependency_owner", "waiting_next_followup_at", "owner_epoch",
            "versions_at_time")
        # Discovery facts and routing state change only through services.
        read_only_fields = ("fc", "discovered_stage", "discovered_stage_record",
                            "discovering_department", "discovered_by", "reporter",
                            "submitted_at", "queue", "accountable_user",
                            "acknowledged_at", "acknowledged_by", "blocks_stage",
                            "kind", "parent", "owner_epoch", "owner_since",
                            "is_waiting", "waiting_reason", "waiting_dependency_owner",
                            "waiting_next_followup_at", "status", "resolved_by",
                            "verified_by", "verified_at", "closed_at")

    def get_ack_due_at(self, obj):
        from .deadlines import ack_due_at
        return None if obj.acknowledged_at else ack_due_at(obj)

    def get_versions_at_time(self, obj):
        from fc.evidence import versions_at_time
        return versions_at_time(obj, self.context["request"].user)

    def get_parent_summary(self, obj):
        """Seeing a workstream shows its incident's headline, never the
        incident's notes or its sibling workstreams."""
        if obj.parent_id is None:
            return None
        p = obj.parent
        return {"id": p.pk, "key": p.key, "title": p.title, "status": p.status,
                "urgency": p.urgency}

    def get_known_issue_detail(self, obj):
        if obj.known_issue_id is None:
            return None
        user = self.context["request"].user
        known = policy.visible_knowledge(user).filter(pk=obj.known_issue_id).first()
        return KnownIssueSerializer(known, context=self.context).data if known else None

    def get_participants(self, obj):
        return ParticipantSerializer(
            obj.participants.filter(removed_at__isnull=True), many=True).data

    def get_allowed_transitions(self, obj):
        from .models import ISSUE_TRANSITIONS
        return list(ISSUE_TRANSITIONS.get(obj.status, []))


class ReportSerializer(serializers.Serializer):
    """The quick report (WP4): three required fields, the rest optional."""
    title = serializers.CharField(max_length=255)
    symptom = serializers.CharField()
    urgency = serializers.ChoiceField(choices=Urgency.choices)
    impact = serializers.ChoiceField(choices=Impact.choices, required=False)
    product_area = serializers.ChoiceField(choices=ProductArea.choices, required=False)
    kind = serializers.ChoiceField(choices=IssueKind.choices, required=False,
                                   default=IssueKind.STANDALONE)
    parent = serializers.IntegerField(required=False, allow_null=True)
    fc = serializers.IntegerField(required=False, allow_null=True)
    description = serializers.CharField(required=False, allow_blank=True)
    occurred_at_approx = serializers.CharField(required=False, allow_blank=True,
                                               max_length=120)
    location_context = serializers.CharField(required=False, allow_blank=True,
                                             max_length=255)
    reproduction_notes = serializers.CharField(required=False, allow_blank=True)


class HandoffProposeSerializer(serializers.Serializer):
    to_department = serializers.IntegerField()
    to_user = serializers.IntegerField(required=False, allow_null=True)
    reason = serializers.CharField(allow_blank=True)


class HandoffRespondSerializer(serializers.Serializer):
    accept = serializers.BooleanField()
    reason = serializers.CharField(required=False, allow_blank=True, default="")


class IssueCreateSerializer(serializers.Serializer):
    fc = serializers.IntegerField(required=False, allow_null=True)
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
    root_cause_status = serializers.ChoiceField(
        choices=Resolution.ROOT_CAUSE_CHOICES, required=False)
    workaround = serializers.CharField(required=False, allow_blank=True)
    affected_versions = serializers.CharField(required=False, allow_blank=True)
    affected_units = serializers.CharField(required=False, allow_blank=True)
    unresolved_risks = serializers.CharField(required=False, allow_blank=True)
    evidence_links = serializers.ListField(child=serializers.CharField(),
                                           required=False)
    what_tested = serializers.CharField(required=False, allow_blank=True)
    evidence = serializers.CharField(required=False, allow_blank=True)


class VerifySerializer(serializers.Serializer):
    result = serializers.ChoiceField(choices=[("pass", "pass"), ("fail", "fail")])
    what_tested = serializers.CharField()
    evidence = serializers.CharField(required=False, allow_blank=True, default="")
    notes = serializers.CharField(required=False, allow_blank=True, default="")


class WaitingSerializer(serializers.Serializer):
    waiting = serializers.BooleanField()
    reason = serializers.CharField(required=False, allow_blank=True, default="")
    dependency_owner = serializers.CharField(required=False, allow_blank=True,
                                             default="")
    next_followup_at = serializers.DateTimeField(required=False, allow_null=True)


class ParticipantAddSerializer(serializers.Serializer):
    user = serializers.IntegerField()
    role = serializers.ChoiceField(choices=IssueParticipant.ROLE_CHOICES)


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
