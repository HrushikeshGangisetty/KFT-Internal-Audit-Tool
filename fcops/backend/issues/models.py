"""Issue management + knowledge base (PRD §9, §10, §11, §21)."""
from django.conf import settings
from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import SearchVectorField
from django.db import models
from django.utils import timezone

from accounts.models import Department
from core.models import TimeStampedModel
from fc.lifecycle import Stage


class IssueStatus(models.TextChoices):
    OPEN = "OPEN", "Open"
    INVESTIGATING = "INVESTIGATING", "Investigating"
    RESOLVED = "RESOLVED", "Resolved"
    VERIFIED = "VERIFIED", "Verified"
    CLOSED = "CLOSED", "Closed"


# Allowed status transitions. WAITING is a flag, not a status (PRD §9).
ISSUE_TRANSITIONS = {
    IssueStatus.OPEN: [IssueStatus.INVESTIGATING, IssueStatus.RESOLVED],
    IssueStatus.INVESTIGATING: [IssueStatus.RESOLVED, IssueStatus.OPEN],
    IssueStatus.RESOLVED: [IssueStatus.VERIFIED, IssueStatus.INVESTIGATING],
    IssueStatus.VERIFIED: [IssueStatus.CLOSED, IssueStatus.INVESTIGATING],
    IssueStatus.CLOSED: [],  # reopening is a manager-only action, audited
}


class Severity(models.TextChoices):
    BLOCKER = "BLOCKER", "Blocker"
    MAJOR = "MAJOR", "Major"
    MINOR = "MINOR", "Minor"
    COSMETIC = "COSMETIC", "Cosmetic"


class Category(models.TextChoices):
    HARDWARE = "HARDWARE", "Hardware"
    FIRMWARE = "FIRMWARE", "Firmware"
    SOFTWARE = "SOFTWARE", "Software"
    MECHANICAL = "MECHANICAL", "Mechanical"
    PROCESS = "PROCESS", "Process"
    UNKNOWN = "UNKNOWN", "Unknown"


class ProductArea(models.TextChoices):
    GCS = "GCS", "GCS"
    CONFIGURATOR = "CONFIGURATOR", "Configurator"
    FIRMWARE = "FIRMWARE", "Firmware"
    PARAMETERS = "PARAMETERS", "Parameters"
    FC_HARDWARE = "FC_HARDWARE", "FC hardware"
    MECHANICAL = "MECHANICAL", "Mechanical"
    ROVER = "ROVER", "Rover"
    OTHER = "OTHER", "Other"
    UNKNOWN = "UNKNOWN", "Unknown"


class Impact(models.TextChoices):
    STOPS_WORK = "STOPS_WORK", "Stops work or operation"
    DEGRADED = "DEGRADED", "Degraded, workaround exists"
    MINOR = "MINOR", "Minor"
    UNKNOWN = "UNKNOWN", "Unknown"


class Urgency(models.TextChoices):
    URGENT = "urgent", "Urgent"
    NORMAL = "normal", "Normal"
    UNKNOWN = "unknown", "Unknown"


class IssueKind(models.TextChoices):
    STANDALONE = "standalone", "Standalone"
    INCIDENT = "incident", "Incident"
    WORKSTREAM = "workstream", "Workstream"


class KnownIssue(TimeStampedModel):
    """A curated rollup, not a copy of an issue (PRD §11)."""

    STATUS_ACTIVE = "ACTIVE"
    STATUS_RETIRED = "RETIRED"
    STATUS_CHOICES = [(STATUS_ACTIVE, "Active"), (STATUS_RETIRED, "Retired")]

    title = models.CharField(max_length=255)
    symptoms_summary = models.TextField()
    root_cause = models.TextField()
    resolution = models.TextField()
    category = models.CharField(max_length=24, choices=Category.choices,
                                default=Category.UNKNOWN)
    affected_revisions = models.CharField(max_length=255, blank=True)
    affected_firmware = models.CharField(max_length=255, blank=True)
    affected_software = models.CharField(max_length=255, blank=True)
    owning_department = models.ForeignKey(Department, null=True, blank=True,
                                          on_delete=models.SET_NULL,
                                          related_name="known_issues")
    status = models.CharField(max_length=16, choices=STATUS_CHOICES,
                              default=STATUS_ACTIVE)
    # Who may read the article itself (WP1). Occurrence links and counts are
    # still filtered per reader by their issue scope.
    AUDIENCE_ALL_STAFF = "all_staff"
    AUDIENCE_DEPARTMENTS = "departments"
    AUDIENCE_HEADS = "heads"
    AUDIENCE_CHOICES = [(AUDIENCE_ALL_STAFF, "All staff"),
                        (AUDIENCE_DEPARTMENTS, "Selected departments"),
                        (AUDIENCE_HEADS, "Heads and managers")]
    audience = models.CharField(max_length=16, choices=AUDIENCE_CHOICES,
                                default=AUDIENCE_HEADS)
    audience_departments = models.ManyToManyField(Department, blank=True,
                                                  related_name="+")
    promoted_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True,
                                    on_delete=models.SET_NULL,
                                    related_name="promoted_known_issues")
    first_occurrence_issue = models.ForeignKey(
        "Issue", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="known_issue_first_of")
    last_occurrence_issue = models.ForeignKey(
        "Issue", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="known_issue_last_of")
    verification_count = models.PositiveIntegerField(default=0)
    search_vector = SearchVectorField(null=True, editable=False)

    class Meta:
        ordering = ("-updated_at",)
        indexes = [GinIndex(fields=["search_vector"])]

    def __str__(self):
        return self.title

    @property
    def occurrence_count(self):
        return self.linked_issues.count()

    def refresh_rollup(self):
        linked = self.linked_issues.order_by("created_at")
        first = linked.first()
        last = linked.last()
        self.first_occurrence_issue = first
        self.last_occurrence_issue = last
        self.verification_count = linked.filter(
            status__in=[IssueStatus.VERIFIED, IssueStatus.CLOSED]).count()
        self.save(update_fields=["first_occurrence_issue", "last_occurrence_issue",
                                 "verification_count", "updated_at"])


class Issue(TimeStampedModel):
    """An issue may concern an FC and a lifecycle stage, or neither (WP4):
    a general report needs only a title, a symptom and an urgency.

    The discovery side (where the symptom was seen) and the ownership side
    (where the problem actually originated) are independent fields — this is
    the distinction the whole system exists to preserve (PRD §10).
    """

    key = models.CharField(max_length=24, unique=True, db_index=True,
                           help_text="ISS-YYYY-NNNNN")
    fc = models.ForeignKey("fc.FlightController", null=True, blank=True,
                           on_delete=models.CASCADE, related_name="issues")

    # --- discovery (write-once, WP4: see services.IMMUTABLE_FIELDS) ---
    discovered_stage = models.CharField(max_length=32, choices=Stage.choices,
                                        blank=True, db_index=True)
    discovered_stage_record = models.ForeignKey(
        "fc.StageRecord", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="discovered_issues")
    discovered_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True,
                                      on_delete=models.SET_NULL,
                                      related_name="discovered_issues")
    discovering_department = models.ForeignKey(
        Department, null=True, on_delete=models.SET_NULL,
        related_name="discovered_issues")

    reporter = models.ForeignKey(settings.AUTH_USER_MODEL, null=True,
                                 on_delete=models.SET_NULL,
                                 related_name="reported_issues")
    submitted_at = models.DateTimeField(default=timezone.now)

    customer = models.ForeignKey("customers.Customer", null=True, blank=True,
                                 on_delete=models.PROTECT, related_name="issues")
    deployment = models.ForeignKey("customers.Deployment", null=True, blank=True,
                                   on_delete=models.PROTECT, related_name="issues")

    # --- report context (WP4) ---
    product_area = models.CharField(max_length=16, choices=ProductArea.choices,
                                    default=ProductArea.UNKNOWN, db_index=True)
    impact = models.CharField(max_length=16, choices=Impact.choices,
                              default=Impact.UNKNOWN)
    urgency = models.CharField(max_length=8, choices=Urgency.choices,
                               default=Urgency.UNKNOWN, db_index=True)
    occurred_at_approx = models.CharField(max_length=120, blank=True)
    location_context = models.CharField(max_length=255, blank=True)
    reproduction_notes = models.TextField(blank=True)
    kind = models.CharField(max_length=16, choices=IssueKind.choices,
                            default=IssueKind.STANDALONE)
    parent = models.ForeignKey("self", null=True, blank=True,
                               on_delete=models.PROTECT, related_name="workstreams")
    # An issue on an FC blocks its stage only once someone with lifecycle
    # authority decides so. Issues raised from the FC lifecycle (and every
    # pre-WP4 row) carry that decision; general reports do not.
    blocks_stage = models.BooleanField(default=False)

    # --- routing and accountability (WP5) ---
    queue = models.ForeignKey("Queue", null=True, blank=True,
                              on_delete=models.PROTECT, related_name="issues")
    accountable_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="accountable_issues")
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    acknowledged_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="acknowledged_issues")
    # WP6: each change of owner starts a fresh escalation sequence, keyed by
    # the epoch, timed from owner_since.
    owner_epoch = models.PositiveIntegerField(default=0)
    owner_since = models.DateTimeField(null=True, blank=True)

    # --- ownership / root cause (can change, always logged) ---
    assigned_department = models.ForeignKey(
        Department, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="assigned_issues")
    assigned_person = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="assigned_issues")

    category = models.CharField(max_length=24, choices=Category.choices,
                                default=Category.UNKNOWN, db_index=True)
    severity = models.CharField(max_length=16, choices=Severity.choices,
                                default=Severity.MAJOR, db_index=True)
    title = models.CharField(max_length=255)
    symptoms = models.TextField(help_text="Observed symptoms, free text")
    symptom_tags = models.JSONField(default=list, blank=True)
    description = models.TextField(blank=True)

    root_cause = models.TextField(blank=True)
    root_cause_department = models.ForeignKey(
        Department, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="root_cause_issues")
    resolution = models.TextField(blank=True)

    status = models.CharField(max_length=24, choices=IssueStatus.choices,
                              default=IssueStatus.OPEN, db_index=True)
    is_waiting = models.BooleanField(default=False,
                                     help_text="Waiting on parts/person (flag, not a status)")
    waiting_reason = models.CharField(max_length=255, blank=True)
    waiting_dependency_owner = models.CharField(max_length=255, blank=True)
    waiting_next_followup_at = models.DateTimeField(null=True, blank=True)

    # --- versions captured at discovery time (PRD §9) ---
    hardware_revision = models.CharField(max_length=64, blank=True, db_index=True)
    firmware_version = models.CharField(max_length=64, blank=True, db_index=True)
    parameter_profile = models.CharField(max_length=120, blank=True)
    gcs_version = models.CharField(max_length=64, blank=True, db_index=True)
    configurator_version = models.CharField(max_length=64, blank=True, db_index=True)

    known_issue = models.ForeignKey(KnownIssue, null=True, blank=True,
                                    on_delete=models.SET_NULL,
                                    related_name="linked_issues")
    is_recurring = models.BooleanField(default=False)

    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                    on_delete=models.SET_NULL,
                                    related_name="resolved_issues")
    verified_at = models.DateTimeField(null=True, blank=True)
    verified_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                    on_delete=models.SET_NULL,
                                    related_name="verified_issues")
    closed_at = models.DateTimeField(null=True, blank=True)
    closed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                  on_delete=models.SET_NULL,
                                  related_name="closed_issues")

    search_vector = SearchVectorField(null=True, editable=False)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            GinIndex(fields=["search_vector"]),
            models.Index(fields=["status", "severity"]),
            models.Index(fields=["fc", "status"]),
        ]

    def __str__(self):
        return f"{self.key} {self.title}"

    @property
    def is_blocking(self):
        return self.severity in (Severity.BLOCKER, Severity.MAJOR)

    @property
    def is_editable(self):
        return self.status != IssueStatus.CLOSED


class IssueInvestigationNote(models.Model):
    """Append-only, typed investigation log (PRD §9, WP7). Correcting a note
    adds a new one that ``supersedes`` it; the original stays."""

    TYPES = ("observation", "suspected_cause", "confirmed_cause", "workaround",
             "permanent_fix", "general")

    issue = models.ForeignKey(Issue, on_delete=models.CASCADE,
                              related_name="investigation_notes")
    note_type = models.CharField(max_length=16, choices=[(t, t) for t in TYPES],
                                 default="general")
    supersedes = models.ForeignKey("self", null=True, blank=True,
                                   on_delete=models.PROTECT,
                                   related_name="superseded_by")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, null=True,
                               on_delete=models.SET_NULL,
                               related_name="investigation_notes")
    note = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        # Tie-break on the primary key. Windows clocks have ~15 ms granularity,
        # so two notes written in the same tick share created_at; ordering on
        # the timestamp alone would then be undefined and an append-only log
        # could render out of order.
        ordering = ("created_at", "id")

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise PermissionError("Investigation notes are append-only.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionError("Investigation notes cannot be deleted.")


class IssueReassignmentLog(models.Model):
    """Who moved this issue where, and why (PRD §10) — the actual anti-blame
    mechanism."""

    issue = models.ForeignKey(Issue, on_delete=models.CASCADE,
                              related_name="reassignments")
    from_department = models.ForeignKey(Department, null=True, blank=True,
                                        on_delete=models.SET_NULL,
                                        related_name="reassignments_from")
    to_department = models.ForeignKey(Department, null=True, blank=True,
                                      on_delete=models.SET_NULL,
                                      related_name="reassignments_to")
    from_person = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                    on_delete=models.SET_NULL,
                                    related_name="reassignments_from")
    to_person = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                  on_delete=models.SET_NULL,
                                  related_name="reassignments_to")
    reason = models.TextField()
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True,
                              on_delete=models.SET_NULL,
                              related_name="reassignments_made")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        # Tie-break on the primary key — see IssueInvestigationNote.Meta.
        ordering = ("created_at", "id")


class IssueAttachment(models.Model):
    issue = models.ForeignKey(Issue, on_delete=models.CASCADE,
                              related_name="attachments")
    file = models.FileField(upload_to="issue-attachments/%Y/%m/")
    original_name = models.CharField(max_length=255, blank=True)
    content_type = models.CharField(max_length=120, blank=True)
    size = models.PositiveIntegerField(default=0)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True,
                                    on_delete=models.SET_NULL,
                                    related_name="issue_attachments")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)


class IssueParticipant(models.Model):
    """A person explicitly involved in an issue outside its department scope
    (WP1): a collaborator or an assigned verifier. Removal sets
    ``removed_at``; the row is kept as history."""

    ROLE_COLLABORATOR = "collaborator"
    ROLE_VERIFIER = "verifier"
    ROLE_CHOICES = [(ROLE_COLLABORATOR, "Collaborator"), (ROLE_VERIFIER, "Verifier")]

    issue = models.ForeignKey(Issue, on_delete=models.CASCADE,
                              related_name="participants")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                             related_name="issue_participations")
    role = models.CharField(max_length=16, choices=ROLE_CHOICES)
    added_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                 on_delete=models.SET_NULL, related_name="+")
    added_at = models.DateTimeField(auto_now_add=True)
    removed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("added_at", "id")
        constraints = [
            models.UniqueConstraint(fields=["issue", "user", "role"],
                                    condition=models.Q(removed_at__isnull=True),
                                    name="one_active_participation_per_role"),
        ]


class IssueUnitLink(models.Model):
    """A unit linked after discovery (WP4). The discovery FC is never edited;
    a link records later evidence and never blocks a stage by itself."""

    issue = models.ForeignKey(Issue, on_delete=models.CASCADE,
                              related_name="unit_links")
    fc = models.ForeignKey("fc.FlightController", on_delete=models.PROTECT,
                           related_name="issue_links")
    linked_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True,
                                  on_delete=models.SET_NULL, related_name="+")
    linked_at = models.DateTimeField(auto_now_add=True)
    reason = models.TextField()

    class Meta:
        ordering = ("linked_at", "id")


# --- WP5: routing, events and handoffs ---------------------------------------
class Queue(models.Model):
    """Where reports land. Head and backup are required; exactly one queue is
    the fallback for unknown or unmatched reports (coordinator as head,
    manager as backup). People are PLACEHOLDER data until the PRD decision."""

    name = models.CharField(max_length=120, unique=True)
    department = models.OneToOneField(Department, null=True, blank=True,
                                      on_delete=models.PROTECT, related_name="queue")
    head = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                             related_name="headed_queues")
    backup = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                               related_name="backed_up_queues")
    is_fallback = models.BooleanField(default=False)

    class Meta:
        ordering = ("name",)
        constraints = [models.UniqueConstraint(
            fields=["is_fallback"], condition=models.Q(is_fallback=True),
            name="one_fallback_queue")]

    def __str__(self):
        return self.name


class RoutingRule(models.Model):
    product_area = models.CharField(max_length=16, choices=ProductArea.choices)
    queue = models.ForeignKey(Queue, on_delete=models.CASCADE, related_name="rules")
    priority = models.IntegerField(default=100, help_text="Lower wins")

    class Meta:
        ordering = ("priority", "id")


class IssueEvent(models.Model):
    """Append-only issue timeline and measurement source (PRD §14). A
    database trigger refuses UPDATE and DELETE, as for the audit log."""

    TYPES = ("submitted", "routed", "assigned", "notified", "acknowledged",
             "handoff_proposed", "handoff_accepted", "handoff_rejected",
             "ownership_accepted", "waiting_set", "waiting_cleared",
             "reminder_sent", "escalated", "unit_linked", "blocks_stage_set",
             "coverage_gap", "resolved", "verified", "verification_failed",
             "reopened", "evidence_linked")

    issue = models.ForeignKey(Issue, on_delete=models.PROTECT, related_name="events")
    type = models.CharField(max_length=24, choices=[(t, t) for t in TYPES],
                            db_index=True)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                              on_delete=models.SET_NULL, related_name="+")
    at = models.DateTimeField(default=timezone.now, db_index=True)
    data = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("at", "id")

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise PermissionError("Issue events are append-only.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionError("Issue events cannot be deleted.")


class Handoff(models.Model):
    """A proposal to move an issue to another team. Accountability stays with
    the current owner until the receiver accepts (PRD §6.2)."""

    PENDING, ACCEPTED, REJECTED, WITHDRAWN = "pending", "accepted", "rejected", "withdrawn"
    STATUS_CHOICES = [(x, x) for x in (PENDING, ACCEPTED, REJECTED, WITHDRAWN)]

    issue = models.ForeignKey(Issue, on_delete=models.CASCADE, related_name="handoffs")
    from_user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                  on_delete=models.SET_NULL, related_name="+")
    from_department = models.ForeignKey(Department, null=True, blank=True,
                                        on_delete=models.SET_NULL, related_name="+")
    to_department = models.ForeignKey(Department, on_delete=models.PROTECT,
                                      related_name="+")
    to_user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                on_delete=models.SET_NULL, related_name="+")
    reason = models.TextField()
    proposed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True,
                                    on_delete=models.SET_NULL, related_name="+")
    proposed_at = models.DateTimeField(default=timezone.now)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=PENDING)
    responded_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                     on_delete=models.SET_NULL, related_name="+")
    responded_at = models.DateTimeField(null=True, blank=True)
    response_reason = models.TextField(blank=True)

    class Meta:
        ordering = ("proposed_at", "id")
        constraints = [models.UniqueConstraint(
            fields=["issue"], condition=models.Q(status="pending"),
            name="one_pending_handoff_per_issue")]

    @property
    def to_queue(self):
        return Queue.objects.filter(department_id=self.to_department_id).first()


# --- WP6: deadlines ------------------------------------------------------------
class DeadlinePolicy(models.Model):
    """Acknowledgement target and escalation steps per urgency (data, not
    code). ``escalation_steps`` is a list of
    ``{"after_minutes": n, "to": "owner"|"backup"|"manager", "channels":
    "urgent"|"normal"}``, measured on the policy's clock. PLACEHOLDER values
    are seeded by migration until the PRD decision."""

    urgency = models.CharField(max_length=8, unique=True)
    ack_target_minutes = models.PositiveIntegerField()
    ack_uses_working_hours = models.BooleanField(default=False)
    followup_interval_minutes = models.PositiveIntegerField()
    escalation_steps = models.JSONField(default=list)

    def __str__(self):
        return self.urgency


# --- WP7: resolution and verification -----------------------------------------
class Resolution(models.Model):
    """What was done. A confirmed root cause is not required."""

    CONFIRMED, SUSPECTED, UNKNOWN, MITIGATED = (
        "confirmed", "suspected", "unknown", "mitigated_only")
    ROOT_CAUSE_CHOICES = [(c, c) for c in (CONFIRMED, SUSPECTED, UNKNOWN, MITIGATED)]

    issue = models.ForeignKey(Issue, on_delete=models.PROTECT, related_name="resolutions")
    resolved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                                    related_name="+")
    at = models.DateTimeField(default=timezone.now)
    change_summary = models.TextField()
    root_cause_status = models.CharField(max_length=16, choices=ROOT_CAUSE_CHOICES)
    workaround = models.TextField(blank=True)
    evidence_links = models.JSONField(default=list, blank=True)
    affected_versions = models.TextField(blank=True)
    affected_units = models.TextField(blank=True)
    unresolved_risks = models.TextField(blank=True)

    class Meta:
        ordering = ("at", "id")


class Verification(models.Model):
    PASS, FAIL = "pass", "fail"

    resolution = models.ForeignKey(Resolution, on_delete=models.PROTECT,
                                   related_name="verifications")
    verifier = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                                 related_name="+")
    at = models.DateTimeField(default=timezone.now)
    what_tested = models.TextField()
    evidence = models.TextField(blank=True)
    result = models.CharField(max_length=4, choices=[(PASS, "Pass"), (FAIL, "Fail")])
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ("at", "id")
