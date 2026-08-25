"""Lifecycle engine. All stage/FC state changes go through here so that
validation, audit logging and timeline events cannot be bypassed by a new
endpoint or a serializer shortcut."""
from datetime import datetime

from django.db import transaction
from django.utils import timezone

from core import audit
from core.exceptions import WorkflowError
from core.models import AuditLogEntry

from .lifecycle import (ALLOWED_REWORK_TARGETS, STAGE_INDEX, STAGE_ORDER, Stage,
                        is_allowed_rework, next_stage)
from .models import (FCStatus, FlightController, FCEvent, ReworkRecord,
                     StageRecord, StageStatus)

AUDIT_FIELDS = None


def log_event(fc, kind, title, *, detail="", stage="", actor=None, issue=None,
              payload=None):
    return FCEvent.objects.create(fc=fc, kind=kind, title=title, detail=detail,
                                  stage=stage or "", actor=actor, issue=issue,
                                  payload=payload)


def generate_serial(year=None):
    year = year or timezone.now().year
    prefix = f"FC-{year}-"
    last = (FlightController.objects.filter(serial__startswith=prefix)
            .order_by("-serial").values_list("serial", flat=True).first())
    seq = int(last.split("-")[-1]) + 1 if last else 1
    return f"{prefix}{seq:05d}"


@transaction.atomic
def register_fc(*, fc_model, hardware_revision="", pcb_batch="", notes="",
                actor=None, serial=None):
    fc = FlightController.objects.create(
        serial=serial or generate_serial(),
        fc_model=fc_model,
        hardware_revision=hardware_revision,
        pcb_batch=pcb_batch,
        notes=notes,
        registered_by=actor,
        current_stage=Stage.FABRICATION,
        status=FCStatus.IN_PRODUCTION,
    )
    StageRecord.objects.create(fc=fc, stage=Stage.FABRICATION,
                               status=StageStatus.PENDING, attempt=1)
    audit.record(fc, AuditLogEntry.ACTION_CREATE, actor=actor,
                 after=audit.snapshot(fc), note="FC registered")
    log_event(fc, "FC_REGISTERED", f"FC {fc.serial} registered",
              stage=Stage.FABRICATION, actor=actor)
    return fc


def current_stage_record(fc, stage=None):
    stage = stage or fc.current_stage
    return (fc.stage_records.filter(stage=stage).order_by("-attempt").first())


def _ensure_stage_record(fc, stage, actor=None, department=None):
    record = current_stage_record(fc, stage)
    if record is None or record.status in (StageStatus.PASSED, StageStatus.FAILED):
        attempt = fc.stage_records.filter(stage=stage).count() + 1
        record = StageRecord.objects.create(
            fc=fc, stage=stage, attempt=attempt, status=StageStatus.PENDING,
            department=department)
    return record


@transaction.atomic
def start_stage(fc, stage=None, *, actor=None, department=None, notes=""):
    stage = stage or fc.current_stage
    if stage != fc.current_stage:
        raise WorkflowError(
            f"FC {fc.serial} is at {Stage(fc.current_stage).label}; cannot start "
            f"{Stage(stage).label}.", code="stage_not_current")
    record = _ensure_stage_record(fc, stage, actor=actor, department=department)
    if record.status == StageStatus.IN_PROGRESS:
        return record
    before = audit.snapshot(record)
    record.status = StageStatus.IN_PROGRESS
    record.started_at = record.started_at or timezone.now()
    record.operator = record.operator or actor
    record.department = department or record.department or getattr(actor, "department", None)
    if notes:
        record.notes = notes
    record.save()
    audit.record_change(record, AuditLogEntry.ACTION_STATUS, before,
                        note="Stage started", actor=actor)
    log_event(fc, "STAGE_STARTED", f"{Stage(stage).label} started",
              stage=stage, actor=actor)
    return record


def stage_blockers(fc, stage=None):
    """Why this stage cannot be marked PASSED yet, in plain language.

    A *resolved* issue still blocks: resolving records what was wrong and how it
    was fixed, but the fix has not been checked by anyone else. PRD §8/§17 keep
    verification as a separate gate precisely so a fix and its sign-off are
    never the same act by the same person.
    """
    from issues.models import IssueStatus

    stage = stage or fc.current_stage
    reasons = []
    issues = (fc.issues.filter(discovered_stage=stage)
              .exclude(status__in=[IssueStatus.VERIFIED, IssueStatus.CLOSED])
              .select_related("resolved_by"))
    for issue in issues:
        if issue.status == IssueStatus.RESOLVED:
            resolver = issue.resolved_by
            who = f" {resolver} resolved it, so someone else must verify it." \
                if resolver else ""
            reasons.append(
                f"{issue.key} is resolved but not yet verified.{who}")
        else:
            reasons.append(
                f"{issue.key} is still {issue.get_status_display().lower()} "
                f"— it needs a root cause and resolution first.")
    return reasons


@transaction.atomic
def complete_stage(fc, stage=None, *, passed, actor=None, notes="",
                   department=None):
    """Mark the current stage attempt PASSED or FAILED.

    Passing advances the FC to the next stage. Failing leaves the FC on the
    stage and expects an issue to be raised against it.
    """
    stage = stage or fc.current_stage
    if stage != fc.current_stage:
        raise WorkflowError(
            f"FC {fc.serial} is at {Stage(fc.current_stage).label}; cannot complete "
            f"{Stage(stage).label}.", code="stage_not_current")
    record = _ensure_stage_record(fc, stage, actor=actor, department=department)
    if record.is_locked:
        raise WorkflowError("This stage record is signed off and immutable. "
                            "Create a rework record instead.", code="record_locked")
    if passed:
        blocking = stage_blockers(fc, stage)
        if blocking:
            raise WorkflowError(
                f"{Stage(stage).label} cannot pass yet. " + " ".join(blocking),
                code="open_issues")
    if stage == Stage.MANAGER_APPROVAL:
        raise WorkflowError("Manager Approval is completed via the approval "
                            "endpoint.", code="use_approval_endpoint")

    before = audit.snapshot(record)
    record.status = StageStatus.PASSED if passed else StageStatus.FAILED
    record.completed_at = timezone.now()
    record.started_at = record.started_at or record.completed_at
    record.operator = record.operator or actor
    record.department = department or record.department or getattr(actor, "department", None)
    if passed:
        record.signed_off_by = actor
    if notes:
        record.notes = (record.notes + "\n" if record.notes else "") + notes
    record.save()
    audit.record_change(record, AuditLogEntry.ACTION_TRANSITION, before,
                        note=f"Stage {'passed' if passed else 'failed'}", actor=actor)
    log_event(fc, "STAGE_PASSED" if passed else "STAGE_FAILED",
              f"{Stage(stage).label} {'passed' if passed else 'FAILED'} "
              f"(attempt {record.attempt})",
              detail=notes, stage=stage, actor=actor)

    if passed:
        nxt = next_stage(stage)
        if nxt is not None:
            _move_fc_to_stage(fc, nxt, actor=actor, reason="Stage passed")
    fc.recompute_status()
    return record


@transaction.atomic
def _move_fc_to_stage(fc, stage, *, actor=None, reason="", forced=False):
    before = audit.snapshot(fc)
    fc.current_stage = stage
    fc.save(update_fields=["current_stage", "updated_at"])
    _ensure_stage_record(fc, stage, actor=actor)
    audit.record_change(fc, AuditLogEntry.ACTION_TRANSITION, before,
                        note=reason or "Stage transition", actor=actor)
    log_event(fc, "STAGE_TRANSITION",
              f"Moved to {Stage(stage).label}" + (" (override)" if forced else ""),
              detail=reason, stage=stage, actor=actor)
    fc.recompute_status()
    return fc


@transaction.atomic
def create_rework(*, stage_record, description, return_to_stage, actor=None,
                  originating_issue=None, department=None):
    """Attach a rework sub-record to the failed stage and send the FC back to
    an explicitly-allowed earlier stage."""
    fc = stage_record.fc
    if stage_record.status != StageStatus.FAILED:
        raise WorkflowError("Rework can only be attached to a FAILED stage record.",
                            code="stage_not_failed")
    if not is_allowed_rework(stage_record.stage, return_to_stage):
        allowed = ", ".join(Stage(s).label for s in ALLOWED_REWORK_TARGETS.get(
            stage_record.stage, [])) or "none"
        raise WorkflowError(
            f"{Stage(return_to_stage).label} is not an allowed rework target for a "
            f"{Stage(stage_record.stage).label} failure. Allowed: {allowed}.",
            code="rework_target_not_allowed")
    rework = ReworkRecord.objects.create(
        stage_record=stage_record, fc=fc, description=description,
        return_to_stage=return_to_stage, performed_by=actor,
        originating_issue=originating_issue,
        department=department or getattr(actor, "department", None))
    audit.record(rework, AuditLogEntry.ACTION_CREATE, actor=actor,
                 after=audit.snapshot(rework),
                 note=f"Rework opened from {Stage(stage_record.stage).label}", fc=fc)
    log_event(fc, "REWORK_OPENED",
              f"Rework opened on {Stage(stage_record.stage).label} → returning to "
              f"{Stage(return_to_stage).label}",
              detail=description, stage=stage_record.stage, actor=actor,
              issue=originating_issue)
    _move_fc_to_stage(fc, return_to_stage, actor=actor,
                      reason=f"Rework from {Stage(stage_record.stage).label}")
    return rework


@transaction.atomic
def complete_rework(rework, *, outcome, outcome_notes="", actor=None):
    if rework.outcome != ReworkRecord.OUTCOME_PENDING:
        raise WorkflowError("This rework record is already completed.",
                            code="rework_already_completed")
    before = audit.snapshot(rework)
    rework.outcome = outcome
    rework.outcome_notes = outcome_notes
    rework.completed_at = timezone.now()
    rework.save()
    audit.record_change(rework, AuditLogEntry.ACTION_STATUS, before,
                        note="Rework completed", actor=actor, fields=None)
    log_event(rework.fc, "REWORK_COMPLETED",
              f"Rework {outcome.lower()} on "
              f"{Stage(rework.stage_record.stage).label}",
              detail=outcome_notes, stage=rework.return_to_stage, actor=actor,
              issue=rework.originating_issue)
    if outcome == ReworkRecord.OUTCOME_COMPLETED:
        # Re-run the returned-to stage; the stage must be explicitly re-passed.
        record = _ensure_stage_record(rework.fc, rework.return_to_stage, actor=actor)
        record.triggered_by_rework = rework
        record.save(update_fields=["triggered_by_rework"])
    return rework


def approval_blockers(fc):
    """Why can't this FC be approved? (PRD §17)"""
    from django.conf import settings
    from issues.models import IssueStatus
    blockers, warnings = [], []
    if fc.current_stage != Stage.MANAGER_APPROVAL:
        blockers.append(f"FC is at {Stage(fc.current_stage).label}, not Manager Approval.")
    for stage in STAGE_ORDER[:STAGE_INDEX[Stage.MANAGER_APPROVAL]]:
        rec = current_stage_record(fc, stage)
        if rec is None or rec.status != StageStatus.PASSED:
            blockers.append(f"{Stage(stage).label} has not passed.")
    for issue in fc.issues.all():
        if issue.status in (IssueStatus.OPEN, IssueStatus.INVESTIGATING):
            blockers.append(f"{issue.key} is unresolved ({issue.get_status_display()}).")
        elif issue.status == IssueStatus.RESOLVED:
            msg = f"{issue.key} is resolved but not verified."
            if issue.is_blocking:
                blockers.append(msg)
            else:
                warnings.append(msg)
    return blockers, warnings


@transaction.atomic
def manager_approve(fc, *, actor, approve, note="", deviation_justification=""):
    from django.conf import settings
    blockers, warnings = approval_blockers(fc)
    if approve:
        if blockers:
            raise WorkflowError("Cannot approve: " + " ".join(blockers),
                                code="approval_blocked")
        if warnings and not deviation_justification:
            raise WorkflowError(
                "Unverified non-blocking issues remain; a deviation justification "
                "is mandatory. " + " ".join(warnings), code="justification_required")
    before = audit.snapshot(fc)
    fc.status = FCStatus.APPROVED if approve else FCStatus.REJECTED
    fc.approved_by = actor
    fc.approved_at = timezone.now()
    fc.approval_note = note or deviation_justification
    fc.save(update_fields=["status", "approved_by", "approved_at", "approval_note",
                           "updated_at"])
    record = _ensure_stage_record(fc, Stage.MANAGER_APPROVAL, actor=actor)
    record.status = StageStatus.PASSED if approve else StageStatus.FAILED
    record.completed_at = timezone.now()
    record.started_at = record.started_at or record.completed_at
    record.operator = actor
    record.signed_off_by = actor if approve else None
    record.notes = note or deviation_justification
    record.save()
    audit.record_change(
        fc, AuditLogEntry.ACTION_APPROVE if approve else AuditLogEntry.ACTION_REJECT,
        before, note=note or deviation_justification, actor=actor)
    log_event(fc, "MANAGER_APPROVED" if approve else "MANAGER_REJECTED",
              f"FC {'approved for release' if approve else 'rejected / scrapped'} by "
              f"{actor}", detail=note or deviation_justification,
              stage=Stage.MANAGER_APPROVAL, actor=actor,
              payload={"deviations": warnings} if warnings else None)
    return fc


@transaction.atomic
def override_transition(fc, target_stage, *, actor, reason):
    """Admin/manager escape hatch. Always audited and marked as an override."""
    if not reason:
        raise WorkflowError("An override requires a reason.", code="reason_required")
    return _move_fc_to_stage(fc, target_stage, actor=actor,
                             reason=f"OVERRIDE: {reason}", forced=True)


def build_timeline(fc):
    return fc.events.select_related("actor", "issue").all()
