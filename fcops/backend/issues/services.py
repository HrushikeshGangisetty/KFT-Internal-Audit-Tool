"""Issue workflow services (PRD §9, §10, §11, §17)."""
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from core import audit
from core.exceptions import WorkflowError
from core.models import AuditLogEntry, Notification
from fc.models import FirmwareRecord, StageRecord
from fc.services import log_event

from .models import (ISSUE_TRANSITIONS, Category, Issue, IssueInvestigationNote,
                     IssueReassignmentLog, IssueStatus, KnownIssue, Severity)
from .search import reindex_issue, reindex_known_issue


def generate_key(year=None):
    year = year or timezone.now().year
    prefix = f"ISS-{year}-"
    last = (Issue.objects.filter(key__startswith=prefix).order_by("-key")
            .values_list("key", flat=True).first())
    seq = int(last.split("-")[-1]) + 1 if last else 1
    return f"{prefix}{seq:05d}"


def notify(user, verb, message, link=""):
    if user is None:
        return None
    return Notification.objects.create(recipient=user, verb=verb, message=message,
                                       link=link)


def notify_department(department, verb, message, link="", exclude=None):
    if department is None:
        return
    from accounts.models import User
    for user in User.objects.filter(department=department, is_active=True):
        if exclude and user.pk == exclude.pk:
            continue
        notify(user, verb, message, link)


def capture_versions(fc):
    """Snapshot the FC's currently-recorded versions at discovery time."""
    data = {
        "hardware_revision": fc.hardware_revision or "",
        "firmware_version": "",
        "parameter_profile": "",
        "gcs_version": "",
        "configurator_version": "",
    }
    fw = fc.firmware_records.filter(is_current=True).first() or \
        fc.firmware_records.first()
    if fw:
        data["firmware_version"] = fw.version
        if fw.parameter_profile:
            data["parameter_profile"] = str(fw.parameter_profile)
    test = fc.test_results.select_related("gcs_version", "configurator_version").first()
    if test:
        if test.gcs_version:
            data["gcs_version"] = test.gcs_version.version
        if test.configurator_version:
            data["configurator_version"] = test.configurator_version.version
    return data


@transaction.atomic
def create_issue(*, fc, title, symptoms, actor, discovered_stage=None,
                 discovered_stage_record=None, description="", category=None,
                 severity=Severity.MAJOR, assigned_department=None,
                 assigned_person=None, symptom_tags=None, version_overrides=None,
                 fail_stage=True):
    discovered_stage = discovered_stage or fc.current_stage
    if discovered_stage_record is None:
        discovered_stage_record = (fc.stage_records.filter(stage=discovered_stage)
                                   .order_by("-attempt").first())
    versions = capture_versions(fc)
    versions.update({k: v for k, v in (version_overrides or {}).items() if v})

    issue = Issue.objects.create(
        key=generate_key(),
        fc=fc,
        title=title,
        symptoms=symptoms,
        description=description,
        symptom_tags=symptom_tags or [],
        discovered_stage=discovered_stage,
        discovered_stage_record=discovered_stage_record,
        discovered_by=actor,
        discovering_department=getattr(actor, "department", None),
        assigned_department=assigned_department,
        assigned_person=assigned_person,
        category=category or Category.UNKNOWN,
        severity=severity,
        status=IssueStatus.OPEN,
        **versions,
    )
    reindex_issue(issue)
    audit.record(issue, AuditLogEntry.ACTION_CREATE, actor=actor,
                 after=audit.snapshot(issue), note="Issue created", fc=fc)
    log_event(fc, "ISSUE_OPENED", f"{issue.key} opened: {issue.title}",
              detail=symptoms, stage=discovered_stage, actor=actor, issue=issue,
              payload={"severity": severity, "category": issue.category})

    if assigned_department:
        IssueReassignmentLog.objects.create(
            issue=issue, from_department=None, to_department=assigned_department,
            to_person=assigned_person, reason="Initial assignment", actor=actor)
        notify_department(assigned_department, "ISSUE_ASSIGNED",
                          f"{issue.key} assigned to your department: {issue.title}",
                          link=f"/issues/{issue.id}", exclude=actor)
    if issue.severity in (Severity.BLOCKER, Severity.MAJOR):
        from accounts.models import Role, User
        for manager in User.objects.filter(role__in=[Role.MANAGER, Role.ADMIN],
                                           is_active=True):
            notify(manager, "HIGH_SEVERITY_ISSUE",
                   f"{issue.get_severity_display()} issue {issue.key} opened on "
                   f"{fc.serial}", link=f"/issues/{issue.id}")

    fc.recompute_status()
    return issue


@transaction.atomic
def add_note(issue, *, author, note):
    if issue.status == IssueStatus.CLOSED:
        raise WorkflowError("Closed issues are read-only.", code="issue_closed")
    entry = IssueInvestigationNote.objects.create(issue=issue, author=author,
                                                  note=note)
    audit.record(issue, AuditLogEntry.ACTION_UPDATE, actor=author,
                 after={"investigation_note": note[:500]},
                 note="Investigation note added", fc=issue.fc)
    if issue.status == IssueStatus.OPEN:
        change_status(issue, IssueStatus.INVESTIGATING, actor=author,
                      note="Auto-advanced on first investigation note")
    return entry


@transaction.atomic
def reassign(issue, *, actor, to_department=None, to_person=None, reason):
    if not reason:
        raise WorkflowError("Reassignment requires a reason.", code="reason_required")
    if issue.status == IssueStatus.CLOSED:
        raise WorkflowError("Closed issues are read-only.", code="issue_closed")
    if not (actor.is_lead_role or actor.is_admin_role
            or actor.in_department(issue.assigned_department)
            or issue.assigned_department is None):
        raise WorkflowError(
            "Only a department lead, a manager, or a member of the currently "
            "assigned department may reassign this issue.", code="forbidden")
    before = audit.snapshot(issue)
    from_department, from_person = issue.assigned_department, issue.assigned_person
    if to_department is not None:
        issue.assigned_department = to_department
    issue.assigned_person = to_person
    issue.save(update_fields=["assigned_department", "assigned_person", "updated_at"])
    IssueReassignmentLog.objects.create(
        issue=issue, from_department=from_department,
        to_department=issue.assigned_department, from_person=from_person,
        to_person=to_person, reason=reason, actor=actor)
    audit.record_change(issue, AuditLogEntry.ACTION_REASSIGN, before,
                        note=reason, actor=actor)
    log_event(issue.fc, "ISSUE_REASSIGNED",
              f"{issue.key} reassigned to "
              f"{issue.assigned_department or 'unassigned'}",
              detail=reason, stage=issue.discovered_stage, actor=actor, issue=issue)
    notify_department(issue.assigned_department, "ISSUE_ASSIGNED",
                      f"{issue.key} reassigned to your department: {issue.title}",
                      link=f"/issues/{issue.id}", exclude=actor)
    if to_person:
        notify(to_person, "ISSUE_ASSIGNED",
               f"{issue.key} assigned to you: {issue.title}",
               link=f"/issues/{issue.id}")
    return issue


def _require_transition(issue, new_status):
    if new_status == issue.status:
        return
    allowed = ISSUE_TRANSITIONS.get(issue.status, [])
    if new_status not in allowed:
        raise WorkflowError(
            f"Cannot move issue from {issue.status} to {new_status}. "
            f"Allowed: {', '.join(allowed) or 'none'}.",
            code="invalid_issue_transition")


@transaction.atomic
def change_status(issue, new_status, *, actor, note="", root_cause=None,
                  resolution=None, root_cause_department=None):
    _require_transition(issue, new_status)
    before = audit.snapshot(issue)

    if new_status == IssueStatus.RESOLVED:
        if root_cause is not None:
            issue.root_cause = root_cause
        if resolution is not None:
            issue.resolution = resolution
        if root_cause_department is not None:
            issue.root_cause_department = root_cause_department
        if not issue.root_cause.strip() or not issue.resolution.strip():
            raise WorkflowError("Root cause and resolution are required to resolve "
                                "an issue.", code="root_cause_required")
        if issue.assigned_person_id is None and issue.assigned_department_id is None:
            raise WorkflowError("An issue must be assigned before it can be resolved.",
                                code="assignment_required")
        issue.resolved_at = timezone.now()
        issue.resolved_by = actor
    elif new_status == IssueStatus.VERIFIED:
        if settings.REQUIRE_INDEPENDENT_VERIFICATION and \
                issue.resolved_by_id and actor and issue.resolved_by_id == actor.pk:
            raise WorkflowError(
                "Verification must be performed by someone other than the person "
                "who resolved the issue.", code="independent_verification_required")
        if not (actor.is_test_engineer or actor.is_lead_role):
            raise WorkflowError("Only a test engineer, department lead or manager "
                                "may verify a resolution.", code="forbidden")
        issue.verified_at = timezone.now()
        issue.verified_by = actor
    elif new_status == IssueStatus.CLOSED:
        issue.closed_at = timezone.now()
        issue.closed_by = actor

    issue.status = new_status
    issue.save()
    reindex_issue(issue)
    action = (AuditLogEntry.ACTION_VERIFY if new_status == IssueStatus.VERIFIED
              else AuditLogEntry.ACTION_STATUS)
    audit.record_change(issue, action, before, note=note, actor=actor)
    log_event(issue.fc, f"ISSUE_{new_status}",
              f"{issue.key} → {issue.get_status_display()}", detail=note,
              stage=issue.discovered_stage, actor=actor, issue=issue)
    for watcher in {issue.discovered_by, issue.assigned_person}:
        if watcher and actor and watcher.pk != actor.pk:
            notify(watcher, "ISSUE_STATUS",
                   f"{issue.key} is now {issue.get_status_display()}",
                   link=f"/issues/{issue.id}")
    if issue.known_issue_id:
        issue.known_issue.refresh_rollup()
    issue.fc.recompute_status()
    return issue


@transaction.atomic
def reopen(issue, *, actor, reason):
    if not actor.is_manager_role:
        raise WorkflowError("Only a manager or admin may reopen a closed issue.",
                            code="forbidden")
    if not reason:
        raise WorkflowError("Reopening requires a reason.", code="reason_required")
    before = audit.snapshot(issue)
    issue.status = IssueStatus.INVESTIGATING
    issue.closed_at = None
    issue.closed_by = None
    issue.verified_at = None
    issue.verified_by = None
    issue.save()
    audit.record_change(issue, AuditLogEntry.ACTION_STATUS, before,
                        note=f"REOPENED: {reason}", actor=actor)
    log_event(issue.fc, "ISSUE_REOPENED", f"{issue.key} reopened", detail=reason,
              stage=issue.discovered_stage, actor=actor, issue=issue)
    issue.fc.recompute_status()
    return issue


@transaction.atomic
def set_waiting(issue, *, actor, waiting, reason=""):
    before = audit.snapshot(issue)
    issue.is_waiting = waiting
    issue.waiting_reason = reason if waiting else ""
    issue.save(update_fields=["is_waiting", "waiting_reason", "updated_at"])
    audit.record_change(issue, AuditLogEntry.ACTION_UPDATE, before,
                        note="Waiting flag changed", actor=actor)
    return issue


@transaction.atomic
def promote_to_known_issue(issue, *, actor, title=None, symptoms_summary=None,
                           root_cause=None, resolution=None,
                           affected_revisions=None, affected_firmware=None,
                           affected_software=None):
    if not (actor.is_lead_role or actor.is_manager_role):
        raise WorkflowError("Only a department lead, manager or admin may promote "
                            "an issue to a Known Issue.", code="forbidden")
    if issue.status not in (IssueStatus.RESOLVED, IssueStatus.VERIFIED,
                            IssueStatus.CLOSED):
        raise WorkflowError("Only a resolved issue can be promoted to a Known Issue.",
                            code="issue_not_resolved")
    known = KnownIssue.objects.create(
        title=title or issue.title,
        symptoms_summary=symptoms_summary or issue.symptoms,
        root_cause=root_cause or issue.root_cause,
        resolution=resolution or issue.resolution,
        category=issue.category,
        affected_revisions=affected_revisions or issue.hardware_revision,
        affected_firmware=affected_firmware or issue.firmware_version,
        affected_software=affected_software or " ".join(
            filter(None, [issue.gcs_version, issue.configurator_version])),
        owning_department=issue.root_cause_department or issue.assigned_department,
        promoted_by=actor,
    )
    link_issue_to_known(issue, known, actor=actor, reason="Promoted from this issue")
    reindex_known_issue(known)
    audit.record(known, AuditLogEntry.ACTION_PROMOTE, actor=actor,
                 after=audit.snapshot(known),
                 note=f"Promoted from {issue.key}", fc=issue.fc)
    return known


@transaction.atomic
def link_issue_to_known(issue, known, *, actor, reason=""):
    before = audit.snapshot(issue)
    issue.known_issue = known
    issue.is_recurring = known.linked_issues.exclude(pk=issue.pk).exists()
    issue.save(update_fields=["known_issue", "is_recurring", "updated_at"])
    known.refresh_rollup()
    audit.record_change(issue, AuditLogEntry.ACTION_UPDATE, before,
                        note=reason or f"Linked to known issue {known.pk}",
                        actor=actor)
    log_event(issue.fc, "ISSUE_LINKED_KNOWN",
              f"{issue.key} linked to known issue “{known.title}”",
              stage=issue.discovered_stage, actor=actor, issue=issue)
    return issue
