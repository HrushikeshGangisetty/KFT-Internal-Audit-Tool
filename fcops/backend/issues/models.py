"""Issue management + knowledge base (PRD §9, §10, §11, §21)."""
from django.conf import settings
from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import SearchVectorField
from django.db import models

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
    """An issue is always anchored to an FC and a lifecycle stage.

    The discovery side (where the symptom was seen) and the ownership side
    (where the problem actually originated) are independent fields — this is
    the distinction the whole system exists to preserve (PRD §10).
    """

    key = models.CharField(max_length=24, unique=True, db_index=True,
                           help_text="ISS-YYYY-NNNNN")
    fc = models.ForeignKey("fc.FlightController", on_delete=models.CASCADE,
                           related_name="issues")

    # --- discovery (immutable once set) ---
    discovered_stage = models.CharField(max_length=32, choices=Stage.choices,
                                        db_index=True)
    discovered_stage_record = models.ForeignKey(
        "fc.StageRecord", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="discovered_issues")
    discovered_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True,
                                      on_delete=models.SET_NULL,
                                      related_name="discovered_issues")
    discovering_department = models.ForeignKey(
        Department, null=True, on_delete=models.SET_NULL,
        related_name="discovered_issues")

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
    """Append-only investigation log (PRD §9)."""

    issue = models.ForeignKey(Issue, on_delete=models.CASCADE,
                              related_name="investigation_notes")
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
