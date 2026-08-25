"""Flight Controller lifecycle models (PRD §7, §12, §13, §14, §15, §16, §25)."""
from django.conf import settings
from django.db import models
from django.db.models import F
from django.utils import timezone

from accounts.models import Department
from core.models import TimeStampedModel

from .lifecycle import STAGE_ORDER, Stage


class FCModelType(models.Model):
    """An FC product/model. Kept configurable so per-model checklists and,
    later, per-model workflow variants (Phase 2) can hang off it."""

    name = models.CharField(max_length=120, unique=True)
    code = models.SlugField(max_length=48, unique=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("name",)
        verbose_name = "FC model"

    def __str__(self):
        return self.name


class FCStatus(models.TextChoices):
    IN_PRODUCTION = "IN_PRODUCTION", "In production"
    BLOCKED = "BLOCKED", "Blocked"
    IN_TESTING = "IN_TESTING", "In testing"
    PENDING_APPROVAL = "PENDING_APPROVAL", "Pending approval"
    APPROVED = "APPROVED", "Approved"
    REJECTED = "REJECTED", "Rejected / scrapped"


class FlightController(TimeStampedModel):
    """The central entity. Everything else in the system hangs off an FC."""

    serial = models.CharField(max_length=32, unique=True, db_index=True,
                              help_text="FC-YYYY-NNNNN")
    fc_model = models.ForeignKey(FCModelType, on_delete=models.PROTECT,
                                 related_name="units")
    hardware_revision = models.CharField(max_length=64, blank=True)
    pcb_batch = models.CharField(max_length=64, blank=True,
                                 help_text="Fabrication batch / panel reference")
    current_stage = models.CharField(max_length=32, choices=Stage.choices,
                                     default=Stage.FABRICATION, db_index=True)
    status = models.CharField(max_length=24, choices=FCStatus.choices,
                              default=FCStatus.IN_PRODUCTION, db_index=True)
    notes = models.TextField(blank=True)
    registered_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True,
                                      on_delete=models.SET_NULL,
                                      related_name="registered_fcs")
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                    on_delete=models.SET_NULL,
                                    related_name="approved_fcs")
    approved_at = models.DateTimeField(null=True, blank=True)
    approval_note = models.TextField(blank=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return self.serial

    # -- derived helpers ---------------------------------------------------
    @property
    def open_blocking_issues(self):
        from issues.models import Issue, IssueStatus, Severity
        return self.issues.filter(
            severity__in=[Severity.BLOCKER, Severity.MAJOR],
        ).exclude(status__in=[IssueStatus.CLOSED])

    @property
    def open_issues(self):
        from issues.models import IssueStatus
        return self.issues.exclude(status=IssueStatus.CLOSED)

    def recompute_status(self, save=True):
        """FC status is derived, never hand-edited: an FC with any open issue
        is BLOCKED; otherwise its status follows its current stage."""
        from issues.models import IssueStatus
        if self.status in (FCStatus.APPROVED, FCStatus.REJECTED):
            return self.status
        has_open = self.issues.exclude(
            status__in=[IssueStatus.CLOSED, IssueStatus.VERIFIED]).exists()
        if has_open:
            new_status = FCStatus.BLOCKED
        elif self.current_stage == Stage.MANAGER_APPROVAL:
            new_status = FCStatus.PENDING_APPROVAL
        elif self.current_stage in (Stage.SENSOR_VALIDATION, Stage.BENCH_TESTING,
                                    Stage.GROUND_TESTING, Stage.FINAL_VALIDATION):
            new_status = FCStatus.IN_TESTING
        else:
            new_status = FCStatus.IN_PRODUCTION
        if new_status != self.status:
            self.status = new_status
            if save:
                super().save(update_fields=["status", "updated_at"])
        return self.status

    def stage_progress(self):
        """One row per lifecycle stage with its latest attempt — drives the
        ✓ / ⚠ / ○ progress strip on the FC detail page."""
        latest = {}
        for record in self.stage_records.all().order_by("attempt", "id"):
            latest[record.stage] = record
        rows = []
        for stage in STAGE_ORDER:
            record = latest.get(stage)
            rows.append({
                "stage": stage,
                "label": Stage(stage).label,
                "status": record.status if record else StageStatus.PENDING,
                "attempts": self.stage_records.filter(stage=stage).count(),
                "record_id": record.id if record else None,
                "completed_at": record.completed_at if record else None,
            })
        return rows


class StageStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    IN_PROGRESS = "IN_PROGRESS", "In progress"
    PASSED = "PASSED", "Passed"
    FAILED = "FAILED", "Failed"


class StageRecord(TimeStampedModel):
    """One *attempt* at one lifecycle stage.

    A re-run after rework creates a new record with attempt = n+1; previous
    attempts (including failures) are never overwritten (PRD §40).
    """

    fc = models.ForeignKey(FlightController, on_delete=models.CASCADE,
                           related_name="stage_records")
    stage = models.CharField(max_length=32, choices=Stage.choices, db_index=True)
    attempt = models.PositiveIntegerField(default=1)
    status = models.CharField(max_length=16, choices=StageStatus.choices,
                              default=StageStatus.PENDING, db_index=True)
    operator = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                 on_delete=models.SET_NULL,
                                 related_name="stage_records")
    department = models.ForeignKey(Department, null=True, blank=True,
                                   on_delete=models.SET_NULL,
                                   related_name="stage_records")
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)
    signed_off_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                      on_delete=models.SET_NULL,
                                      related_name="signed_stage_records")
    # Set when this attempt exists because an earlier stage/attempt failed.
    triggered_by_rework = models.ForeignKey(
        "ReworkRecord", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="retriggered_stage_records")

    class Meta:
        ordering = ("fc_id", "id")
        unique_together = ("fc", "stage", "attempt")
        indexes = [models.Index(fields=["fc", "stage"])]

    def __str__(self):
        return f"{self.fc.serial} · {Stage(self.stage).label} #{self.attempt}"

    @property
    def is_locked(self):
        """PASSED + signed-off stage records are immutable (PRD §8)."""
        return self.status == StageStatus.PASSED and self.signed_off_by_id is not None


class ReworkRecord(TimeStampedModel):
    """Rework attached to the stage that failed — not a fixed lifecycle
    position (PRD §16)."""

    OUTCOME_PENDING = "PENDING"
    OUTCOME_COMPLETED = "COMPLETED"
    OUTCOME_FAILED = "FAILED"
    OUTCOME_CHOICES = [
        (OUTCOME_PENDING, "Pending"),
        (OUTCOME_COMPLETED, "Completed"),
        (OUTCOME_FAILED, "Failed"),
    ]

    stage_record = models.ForeignKey(StageRecord, on_delete=models.CASCADE,
                                     related_name="rework_records")
    fc = models.ForeignKey(FlightController, on_delete=models.CASCADE,
                           related_name="rework_records")
    originating_issue = models.ForeignKey("issues.Issue", null=True, blank=True,
                                          on_delete=models.SET_NULL,
                                          related_name="rework_records")
    description = models.TextField()
    performed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True,
                                     on_delete=models.SET_NULL,
                                     related_name="rework_records")
    department = models.ForeignKey(Department, null=True, blank=True,
                                   on_delete=models.SET_NULL,
                                   related_name="rework_records")
    # Stage the FC is sent back to; must be in ALLOWED_REWORK_TARGETS.
    return_to_stage = models.CharField(max_length=32, choices=Stage.choices)
    outcome = models.CharField(max_length=16, choices=OUTCOME_CHOICES,
                               default=OUTCOME_PENDING)
    outcome_notes = models.TextField(blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return f"Rework on {self.stage_record}"


class ParameterProfile(models.Model):
    name = models.CharField(max_length=120)
    version = models.CharField(max_length=48)
    contents_ref = models.CharField(max_length=255, blank=True,
                                    help_text="Path/URL/git ref to the param file")
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("name", "version")
        ordering = ("name", "version")

    def __str__(self):
        return f"{self.name} v{self.version}"


class FirmwareRecord(TimeStampedModel):
    """Structured firmware metadata captured at the Firmware stage (PRD §13).

    Flashing, parameter configuration, scripts and signing are *not* separate
    lifecycle gates, but each has its own structured field here so issues can
    later be correlated against any of them.
    """

    SOURCE_OPEN = "OPEN_SOURCE"
    SOURCE_CLOSED = "CLOSED_SOURCE"
    SOURCE_CHOICES = [(SOURCE_OPEN, "Open source"), (SOURCE_CLOSED, "Closed source")]

    RESULT_SUCCESS = "SUCCESS"
    RESULT_FAILED = "FAILED"
    RESULT_PARTIAL = "PARTIAL"
    RESULT_CHOICES = [(RESULT_SUCCESS, "Success"), (RESULT_FAILED, "Failed"),
                      (RESULT_PARTIAL, "Partial")]

    fc = models.ForeignKey(FlightController, on_delete=models.CASCADE,
                           related_name="firmware_records")
    stage_record = models.ForeignKey(StageRecord, null=True, blank=True,
                                     on_delete=models.SET_NULL,
                                     related_name="firmware_records")
    firmware_name = models.CharField(max_length=120)
    version = models.CharField(max_length=64, db_index=True)
    source_type = models.CharField(max_length=24, choices=SOURCE_CHOICES,
                                   default=SOURCE_OPEN)
    is_signed = models.BooleanField(default=False)
    is_locked = models.BooleanField(default=False)
    bootloader_version = models.CharField(max_length=64, blank=True)
    build_ref = models.CharField(max_length=120, blank=True,
                                 help_text="Git SHA / CI build reference")
    parameter_profile = models.ForeignKey(ParameterProfile, null=True, blank=True,
                                          on_delete=models.SET_NULL,
                                          related_name="firmware_records")
    script_name = models.CharField(max_length=120, blank=True)
    script_version = models.CharField(max_length=64, blank=True)
    flashing_result = models.CharField(max_length=16, choices=RESULT_CHOICES,
                                       default=RESULT_SUCCESS)
    config_result = models.CharField(max_length=16, choices=RESULT_CHOICES,
                                     default=RESULT_SUCCESS)
    operator = models.ForeignKey(settings.AUTH_USER_MODEL, null=True,
                                 on_delete=models.SET_NULL,
                                 related_name="firmware_records")
    notes = models.TextField(blank=True)
    build = models.ForeignKey("FirmwareBuild", null=True, blank=True,
                              on_delete=models.PROTECT,
                              related_name="flashes",
                              help_text="Catalogue build this flash came from. "
                                        "PROTECT: a build that has been flashed "
                                        "can never be deleted.")
    is_current = models.BooleanField(default=True,
                                     help_text="Latest firmware state of this FC")

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return f"{self.firmware_name} {self.version} on {self.fc.serial}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.is_current:
            FirmwareRecord.objects.filter(fc=self.fc).exclude(pk=self.pk).update(
                is_current=False)


class SoftwareVersion(models.Model):
    """Known GCS / Configurator releases, maintained by the Software dept
    (PRD §14). A dropdown source, not a live version check."""

    KIND_GCS = "GCS"
    KIND_CONFIGURATOR = "CONFIGURATOR"
    KIND_CHOICES = [(KIND_GCS, "GCS"), (KIND_CONFIGURATOR, "Configurator")]

    kind = models.CharField(max_length=24, choices=KIND_CHOICES)
    version = models.CharField(max_length=64)
    released_on = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ("kind", "version")
        ordering = ("kind", "-version")

    def __str__(self):
        return f"{self.kind} {self.version}"


class FirmwareBuild(TimeStampedModel):
    """The catalogue of firmware builds that may be flashed onto an FC.

    This is the *definition* of a build. :class:`FirmwareRecord` remains the
    record of what was actually flashed onto one specific FC — it copies the
    build's fields at flash time, so an FC's history keeps showing exactly what
    went on it even if the build is later edited or retired (PRD §13, §40).
    """

    SOURCE_OPEN = "OPEN_SOURCE"
    SOURCE_CLOSED = "CLOSED_SOURCE"
    SOURCE_CHOICES = [(SOURCE_OPEN, "Open source"), (SOURCE_CLOSED, "Closed source")]

    # Deliberately not a DB-level choices constraint: new firmware formats must
    # not need a migration. These are the suggestions offered in the UI.
    SUGGESTED_TYPES = ["APJ", "PX4", "HEX", "BIN", "ELF", "UF2", "OTHER"]

    name = models.CharField(max_length=120)
    firmware_type = models.CharField(
        max_length=32, default="APJ",
        help_text="Build format, e.g. APJ. Free text so new formats need no "
                  "schema change.")
    version = models.CharField(max_length=64, db_index=True)
    git_sha = models.CharField(max_length=120, blank=True,
                               help_text="Source reference for this build")
    build_datetime = models.DateTimeField(null=True, blank=True)
    source_type = models.CharField(max_length=24, choices=SOURCE_CHOICES,
                                   default=SOURCE_OPEN)
    description = models.TextField(
        blank=True, help_text="What this build contains, changes and enables")
    includes_scripts = models.BooleanField(default=False)
    script_name = models.CharField(max_length=120, blank=True)
    script_version = models.CharField(max_length=64, blank=True)
    script_notes = models.TextField(blank=True)
    is_signed = models.BooleanField(default=False)
    is_locked = models.BooleanField(default=False)
    bootloader_version = models.CharField(max_length=64, blank=True)
    bootloader_notes = models.TextField(blank=True)
    parameter_profile = models.ForeignKey(ParameterProfile, null=True, blank=True,
                                          on_delete=models.SET_NULL,
                                          related_name="firmware_builds")
    fc_models = models.ManyToManyField(FCModelType, blank=True,
                                       related_name="firmware_builds",
                                       help_text="Empty = suitable for any model")
    is_active = models.BooleanField(
        default=True, help_text="Inactive builds cannot be selected for new "
                                "flashes but remain in FC history")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                   on_delete=models.SET_NULL,
                                   related_name="firmware_builds_created")

    class Meta:
        ordering = ("-created_at",)
        unique_together = ("name", "version")

    def __str__(self):
        return f"{self.name} {self.version}"

    @property
    def flash_count(self):
        return self.flashes.count()

    @property
    def is_in_use(self):
        return self.flashes.exists()


class SoftwareUpdate(TimeStampedModel):
    """An internal release record for the in-house GCS / Configurator.

    This is a traceability record, not a deployment mechanism: it ties a
    version that people are running to the exact commit that produced it, plus
    who signed it off. Pushing an update also registers the version in
    :class:`SoftwareVersion` so it appears wherever testers pick a version
    (PRD §14).
    """

    KIND_CHOICES = SoftwareVersion.KIND_CHOICES

    kind = models.CharField(max_length=24, choices=KIND_CHOICES, db_index=True)
    version = models.CharField(max_length=64, db_index=True)
    git_sha = models.CharField(
        max_length=120, help_text="Commit that produced this build (required)")
    release_notes = models.TextField(help_text="What changed in this update")
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL,
                                    on_delete=models.PROTECT,
                                    related_name="approved_software_updates")
    approved_at = models.DateTimeField(null=True, blank=True)
    pushed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True,
                                  on_delete=models.SET_NULL,
                                  related_name="pushed_software_updates")
    software_version = models.ForeignKey(SoftwareVersion, null=True, blank=True,
                                         on_delete=models.SET_NULL,
                                         related_name="updates")

    class Meta:
        ordering = ("-created_at",)
        unique_together = ("kind", "version")

    def __str__(self):
        return f"{self.get_kind_display()} {self.version}"

    @property
    def short_sha(self):
        return self.git_sha[:12]


class ChecklistTemplate(models.Model):
    """Manager-configurable per-FC-model, per-stage test checklist (PRD §15).

    The individual checks live in :class:`ChecklistItem` rows so they can be
    added, renamed, reordered and retired without a code change. ``version`` is
    bumped on every change to the item set; a :class:`TestResult` stores both
    the version it was captured against *and* a full copy of the answered
    items, so editing the checklist can never alter what a past test recorded.
    """

    fc_model = models.ForeignKey(FCModelType, null=True, blank=True,
                                 on_delete=models.CASCADE,
                                 related_name="checklist_templates",
                                 help_text="Null = applies to all FC models")
    stage = models.CharField(max_length=32, choices=Stage.choices)
    name = models.CharField(max_length=120)
    items = models.JSONField(
        default=list, blank=True,
        help_text="Legacy inline items. Superseded by ChecklistItem rows; kept "
                  "so historical templates remain readable.")
    version = models.PositiveIntegerField(
        default=1, help_text="Bumped whenever the item set changes.")
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("stage", "name")

    def __str__(self):
        return f"{self.name} ({Stage(self.stage).label})"

    def active_items(self):
        return self.checklist_items.filter(is_active=True).order_by("order", "id")

    def as_checklist(self):
        """The item set a tester should be shown right now."""
        rows = [{"key": item.key, "label": item.label,
                 "description": item.description,
                 "mandatory": item.is_mandatory}
                for item in self.active_items()]
        # Fall back to the legacy inline list for templates never migrated.
        return rows or list(self.items or [])

    def bump_version(self):
        ChecklistTemplate.objects.filter(pk=self.pk).update(version=F("version") + 1)
        self.refresh_from_db(fields=["version"])
        return self.version


class ChecklistItem(models.Model):
    """One check inside a checklist template.

    Items are never hard-deleted once used — they are deactivated, so a past
    TestResult referencing the key stays interpretable.
    """

    template = models.ForeignKey(ChecklistTemplate, on_delete=models.CASCADE,
                                 related_name="checklist_items")
    key = models.SlugField(max_length=64,
                           help_text="Stable identifier stored in test results")
    label = models.CharField(max_length=200)
    description = models.TextField(blank=True,
                                   help_text="Instructions shown to the tester")
    is_mandatory = models.BooleanField(
        default=True, help_text="A mandatory check must pass for the test to pass")
    order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("order", "id")
        unique_together = ("template", "key")

    def __str__(self):
        return f"{self.template.name}: {self.label}"

    @property
    def is_in_use(self):
        """True once a tester has answered this check on a real FC.

        Answers are stored by ``key`` inside TestResult.checklist_results, so a
        used key can be disabled but never renamed or removed.
        """
        return TestResult.objects.filter(
            template=self.template,
            checklist_results__contains=[{"key": self.key}]).exists()


class TestResult(TimeStampedModel):
    """Structured, per-item test outcome for a testing stage (PRD §15)."""

    fc = models.ForeignKey(FlightController, on_delete=models.CASCADE,
                           related_name="test_results")
    stage_record = models.ForeignKey(StageRecord, on_delete=models.CASCADE,
                                     related_name="test_results")
    test_type = models.CharField(max_length=32, choices=Stage.choices)
    template = models.ForeignKey(ChecklistTemplate, null=True, blank=True,
                                 on_delete=models.SET_NULL, related_name="results")
    template_version = models.PositiveIntegerField(
        null=True, blank=True,
        help_text="Template version answered, so a later edit cannot be "
                  "mistaken for what this tester actually saw.")
    checklist_results = models.JSONField(
        default=list,
        help_text='[{"key":"gps_lock","label":"GPS lock","passed":false,"note":"no fix"}]')
    overall_passed = models.BooleanField(default=True)
    tester = models.ForeignKey(settings.AUTH_USER_MODEL, null=True,
                               on_delete=models.SET_NULL, related_name="test_results")
    gcs_version = models.ForeignKey(SoftwareVersion, null=True, blank=True,
                                    on_delete=models.SET_NULL,
                                    related_name="gcs_test_results")
    configurator_version = models.ForeignKey(SoftwareVersion, null=True, blank=True,
                                             on_delete=models.SET_NULL,
                                             related_name="configurator_test_results")
    linked_issue = models.ForeignKey("issues.Issue", null=True, blank=True,
                                     on_delete=models.SET_NULL,
                                     related_name="test_results")
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return f"{self.test_type} on {self.fc.serial}"

    def recompute_overall(self):
        items = self.checklist_results or []
        self.overall_passed = all(bool(i.get("passed")) for i in items) if items else self.overall_passed
        return self.overall_passed


class FCEvent(models.Model):
    """Denormalised timeline entry so the FC history page is one cheap query
    rather than a fan-out across six tables (PRD §12)."""

    fc = models.ForeignKey(FlightController, on_delete=models.CASCADE,
                           related_name="events")
    kind = models.CharField(max_length=48, db_index=True)
    title = models.CharField(max_length=255)
    detail = models.TextField(blank=True)
    stage = models.CharField(max_length=32, blank=True)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True,
                              on_delete=models.SET_NULL, related_name="fc_events")
    issue = models.ForeignKey("issues.Issue", null=True, blank=True,
                              on_delete=models.SET_NULL, related_name="fc_events")
    payload = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ("created_at", "id")

    def __str__(self):
        return f"{self.fc.serial}: {self.title}"
