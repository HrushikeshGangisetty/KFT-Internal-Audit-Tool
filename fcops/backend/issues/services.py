"""Issue workflow services (PRD §9, §10, §11, §17)."""
from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from core import alerts, audit
from core.exceptions import WorkflowError
from core.models import AuditLogEntry, Notification
from fc.models import FirmwareRecord, StageRecord
from fc.services import log_event

from .models import (ISSUE_TRANSITIONS, Category, Handoff, Issue, IssueAttachment,
                     IssueEvent, IssueInvestigationNote, IssueKind,
                     IssueParticipant, IssueReassignmentLog, IssueStatus,
                     IssueUnitLink, KnownIssue, ProductArea, Queue, Resolution,
                     RoutingRule, Severity, Urgency, Verification)
from . import deadlines
from .search import reindex_issue, reindex_known_issue


def generate_key(year=None):
    year = year or timezone.now().year
    prefix = f"ISS-{year}-"
    last = (Issue.objects.filter(key__startswith=prefix).order_by("-key")
            .values_list("key", flat=True).first())
    seq = int(last.split("-")[-1]) + 1 if last else 1
    return f"{prefix}{seq:05d}"


def notify(user, kind, issue):
    """Store a pointer only; the text is rendered at read time (WP1)."""
    if user is None:
        return None
    return Notification.objects.create(recipient=user, kind=kind,
                                       target_type="issue", target_id=issue.pk)


def notify_department(department, kind, issue, exclude=None):
    if department is None:
        return
    from accounts.models import User
    for user in User.objects.filter(
            is_active=True, pk__in=_active_member_ids(department)):
        if exclude and user.pk == exclude.pk:
            continue
        notify(user, kind, issue)


def _active_member_ids(department):
    from accounts.models import TeamMembership
    now = timezone.now()
    return TeamMembership.objects.filter(
        Q(active_to__isnull=True) | Q(active_to__gt=now),
        department=department, active_from__lte=now).values("user_id")


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


def _recompute_fc(issue):
    if issue.fc_id:
        issue.fc.recompute_status()


@transaction.atomic
def create_issue(*, fc, title, symptoms, actor, discovered_stage=None,
                 discovered_stage_record=None, description="", category=None,
                 severity=Severity.MAJOR, assigned_department=None,
                 assigned_person=None, symptom_tags=None, version_overrides=None,
                 fail_stage=True, blocks_stage=None, **report_fields):
    """Create an issue, with or without an FC (WP4).

    ``blocks_stage`` defaults to True for an issue raised against an FC from
    the lifecycle (the pre-WP4 behaviour); a general report passes False.
    """
    if fc is not None:
        discovered_stage = discovered_stage or fc.current_stage
        if discovered_stage_record is None:
            discovered_stage_record = (fc.stage_records.filter(stage=discovered_stage)
                                       .order_by("-attempt").first())
        versions = capture_versions(fc)
    else:
        discovered_stage, discovered_stage_record = discovered_stage or "", None
        versions = {}
    versions.update({k: v for k, v in (version_overrides or {}).items() if v})
    if blocks_stage is None:
        blocks_stage = fc is not None

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
        reporter=actor,
        submitted_at=timezone.now(),
        blocks_stage=blocks_stage and fc is not None,
        assigned_department=assigned_department,
        assigned_person=assigned_person,
        category=category or Category.UNKNOWN,
        severity=severity,
        status=IssueStatus.OPEN,
        **versions,
        **report_fields,
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
        notify_department(assigned_department, "ISSUE_ASSIGNED", issue,
                          exclude=actor)
    if issue.severity in (Severity.BLOCKER, Severity.MAJOR):
        from accounts.models import Capability, User
        for manager in User.objects.filter(
                is_active=True, capability_grants__capability=Capability.IS_MANAGER,
                capability_grants__revoked_at__isnull=True):
            notify(manager, "HIGH_SEVERITY_ISSUE", issue)

    if fc is not None:
        fc.recompute_status()
    return issue


@transaction.atomic
def add_note(issue, *, author, note, note_type="general", supersedes=None):
    """Append a typed note. A correction is a new note that supersedes the
    old one; the original is kept."""
    if issue.status == IssueStatus.CLOSED:
        raise WorkflowError("Closed issues are read-only.", code="issue_closed")
    if note_type not in IssueInvestigationNote.TYPES:
        raise WorkflowError(f"Unknown note type '{note_type}'.", code="invalid_note_type")
    if supersedes is not None and supersedes.issue_id != issue.pk:
        raise WorkflowError("A note can only supersede a note on the same issue.",
                            code="invalid_supersedes")
    entry = IssueInvestigationNote.objects.create(issue=issue, author=author,
                                                  note=note, note_type=note_type,
                                                  supersedes=supersedes)
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
    notify_department(issue.assigned_department, "ISSUE_ASSIGNED", issue,
                      exclude=actor)
    if to_person:
        notify(to_person, "ISSUE_ASSIGNED", issue)
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
                  resolution=None, root_cause_department=None,
                  root_cause_status=None, resolution_details=None,
                  verification_details=None):
    """Move an issue along the allow-list. Resolving writes a Resolution row
    (a confirmed root cause is not required, WP7); verifying writes a
    Verification row against the latest resolution and is refused for the
    resolver. A failed verification goes through ``verify``."""
    _require_transition(issue, new_status)
    before = audit.snapshot(issue)
    if new_status == IssueStatus.VERIFIED:
        return verify(issue, verifier=actor, passed=True, note=note,
                      **(verification_details or {}))

    if new_status == IssueStatus.RESOLVED:
        if root_cause is not None:
            issue.root_cause = root_cause
        if resolution is not None:
            issue.resolution = resolution
        if root_cause_department is not None:
            issue.root_cause_department = root_cause_department
        if not issue.resolution.strip():
            raise WorkflowError("A change summary (resolution) is required to resolve "
                                "an issue.", code="root_cause_required")
        if root_cause_status is None:
            root_cause_status = (Resolution.CONFIRMED if issue.root_cause.strip()
                                 else Resolution.UNKNOWN)
        if root_cause_status not in dict(Resolution.ROOT_CAUSE_CHOICES):
            raise WorkflowError("Unknown root cause status.", code="invalid_root_cause")
        if root_cause_status == Resolution.CONFIRMED and not issue.root_cause.strip():
            raise WorkflowError("A confirmed root cause needs a description.",
                                code="root_cause_required")
        if issue.assigned_person_id is None and issue.assigned_department_id is None:
            raise WorkflowError("An issue must be assigned before it can be resolved.",
                                code="assignment_required")
        issue.resolved_at = timezone.now()
        issue.resolved_by = actor
        res = Resolution.objects.create(
            issue=issue, resolved_by=actor, at=issue.resolved_at,
            change_summary=issue.resolution, root_cause_status=root_cause_status,
            **(resolution_details or {}))
        record_event(issue, "resolved", actor, resolution=res.pk,
                     root_cause_status=root_cause_status)
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
            notify(watcher, "ISSUE_STATUS", issue)
    if issue.known_issue_id:
        issue.known_issue.refresh_rollup()
    _recompute_fc(issue)
    return issue


@transaction.atomic
def reopen(issue, *, actor, reason):
    """Back to investigating; earlier resolutions and verifications stay.
    Authority is ``settings.REOPEN_ALLOWED`` (placeholder)."""
    if not can_reopen(issue, actor):
        raise WorkflowError("You are not allowed to reopen this issue.",
                            code="forbidden")
    if not reason:
        raise WorkflowError("Reopening requires a reason.", code="reason_required")
    if issue.status not in (IssueStatus.RESOLVED, IssueStatus.VERIFIED,
                            IssueStatus.CLOSED):
        raise WorkflowError("Only a resolved, verified or closed issue can be "
                            "reopened.", code="invalid_issue_transition")
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
    record_event(issue, "reopened", actor, reason=reason)
    _recompute_fc(issue)
    return issue


@transaction.atomic
def set_waiting(issue, *, actor, waiting, reason="", dependency_owner="",
                next_followup_at=None):
    """Waiting needs a reason and a follow-up date within WAITING_MAX_DAYS.
    It pauses ordinary follow-ups, never acknowledgement escalation."""
    from datetime import timedelta
    if waiting:
        now = timezone.now()
        if not (reason or "").strip() or next_followup_at is None:
            raise WorkflowError("Waiting needs a reason and a follow-up date.",
                                code="waiting_incomplete")
        if not now < next_followup_at <= now + timedelta(days=settings.WAITING_MAX_DAYS):
            raise WorkflowError(f"The follow-up date must be within "
                                f"{settings.WAITING_MAX_DAYS} days.",
                                code="followup_out_of_range")
    before = audit.snapshot(issue)
    issue.is_waiting = waiting
    issue.waiting_reason = reason if waiting else ""
    issue.waiting_dependency_owner = dependency_owner if waiting else ""
    issue.waiting_next_followup_at = next_followup_at if waiting else None
    issue.save(update_fields=["is_waiting", "waiting_reason",
                              "waiting_dependency_owner", "waiting_next_followup_at",
                              "updated_at"])
    audit.record_change(issue, AuditLogEntry.ACTION_UPDATE, before,
                        note="Waiting flag changed", actor=actor)
    record_event(issue, "waiting_set" if waiting else "waiting_cleared", actor,
                 reason=issue.waiting_reason,
                 dependency_owner=issue.waiting_dependency_owner,
                 next_followup_at=next_followup_at.isoformat() if waiting else None)
    return issue


@transaction.atomic
def promote_to_known_issue(issue, *, actor, title=None, symptoms_summary=None,
                           root_cause=None, resolution=None,
                           affected_revisions=None, affected_firmware=None,
                           affected_software=None, audience=None):
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
        audience=audience or KnownIssue.AUDIENCE_HEADS,
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


@transaction.atomic
def add_participant(issue, *, user, role, actor):
    """Give someone outside the issue's department scope explicit access as a
    collaborator or assigned verifier (WP1). Adding is idempotent."""
    if role not in dict(IssueParticipant.ROLE_CHOICES):
        raise WorkflowError(f"Unknown participant role '{role}'.", code="invalid_role")
    existing = IssueParticipant.objects.filter(issue=issue, user=user, role=role,
                                               removed_at__isnull=True).first()
    if existing:
        return existing
    participant = IssueParticipant.objects.create(issue=issue, user=user, role=role,
                                                  added_by=actor)
    audit.record(issue, AuditLogEntry.ACTION_UPDATE, actor=actor,
                 after={"participant": user.pk, "role": role},
                 note=f"{role.title()} added", fc=issue.fc)
    notify(user, "ISSUE_ASSIGNED", issue)
    return participant


@transaction.atomic
def remove_participant(participant, *, actor):
    if participant.removed_at is not None:
        return participant
    participant.removed_at = timezone.now()
    participant.save(update_fields=["removed_at"])
    audit.record(participant.issue, AuditLogEntry.ACTION_UPDATE, actor=actor,
                 after={"participant_removed": participant.user_id,
                        "role": participant.role},
                 note=f"{participant.role.title()} removed", fc=participant.issue.fc)
    return participant


# --- WP4: general reports, discovery facts, unit links ----------------------
# Write-once discovery facts and fields only the routing/handoff services
# may change. Neither the API nor edit_issue can touch them.
IMMUTABLE_FIELDS = ("fc", "discovered_stage", "discovered_stage_record",
                    "discovering_department", "discovered_by", "reporter",
                    "submitted_at")
SERVICE_OWNED_FIELDS = ("queue", "accountable_user", "acknowledged_at",
                        "acknowledged_by", "blocks_stage", "kind", "parent",
                        "owner_epoch", "owner_since", "is_waiting", "waiting_reason",
                        "waiting_dependency_owner", "waiting_next_followup_at",
                        # status and its sign-offs move only through
                        # change_status / verify / reopen (WP7)
                        "status", "resolved_at", "resolved_by", "verified_at",
                        "verified_by", "closed_at", "closed_by")


@transaction.atomic
def edit_issue(issue, *, actor, changes):
    """Edit plain fields; discovery facts and service-owned fields are
    refused rather than silently ignored."""
    refused = sorted(set(changes) & set(IMMUTABLE_FIELDS + SERVICE_OWNED_FIELDS))
    if refused:
        raise WorkflowError(f"These fields cannot be edited: {', '.join(refused)}.",
                            code="immutable_field")
    if {"customer", "deployment"} & changes.keys():
        issue = Issue.objects.select_for_update().get(pk=issue.pk)
        from customers.services import validate_issue_context
        validate_issue_context(actor, changes.get("customer", issue.customer),
                               changes.get("deployment", issue.deployment))
    before = audit.snapshot(issue)
    for field, value in changes.items():
        setattr(issue, field, value)
    issue.save()
    reindex_issue(issue)
    audit.record_change(issue, AuditLogEntry.ACTION_UPDATE, before,
                        note="Issue edited", actor=actor)
    return issue


def record_event(issue, type, actor=None, **data):
    return IssueEvent.objects.create(issue=issue, type=type, actor=actor,
                                     at=timezone.now(), data=data)


@transaction.atomic
def submit_report(*, reporter, title, symptom, urgency, impact=None,
                  product_area=None, kind=IssueKind.STANDALONE, parent=None,
                  fc=None, **optional):
    """A quick report (scenario 1): only title, symptom and urgency are
    required; everything else may be Unknown. Returns the routed issue."""
    title, symptom = (title or "").strip(), (symptom or "").strip()
    if not title or not symptom:
        raise WorkflowError("A title and a symptom are required.", code="report_incomplete")
    if urgency not in Urgency.values:
        raise WorkflowError("Urgency must be urgent, normal or unknown.",
                            code="report_incomplete")
    if kind == IssueKind.WORKSTREAM:
        if parent is None or parent.kind != IssueKind.INCIDENT:
            raise WorkflowError("A workstream needs a parent incident.",
                                code="invalid_parent")
    elif parent is not None:
        raise WorkflowError("Only a workstream can have a parent.", code="invalid_parent")
    issue = create_issue(
        fc=fc, title=title, symptoms=symptom, actor=reporter, blocks_stage=False,
        urgency=urgency, impact=impact or "UNKNOWN",
        product_area=product_area or ProductArea.UNKNOWN, kind=kind, parent=parent,
        **optional)
    record_event(issue, "submitted", reporter, urgency=urgency,
                 product_area=issue.product_area)
    return route(issue)


@transaction.atomic
def add_attachment(issue, *, upload, actor):
    if upload.size > settings.ATTACHMENT_MAX_BYTES:
        raise WorkflowError(
            f"{upload.name} is larger than {settings.ATTACHMENT_MAX_BYTES} bytes.",
            code="attachment_too_large")
    obj = IssueAttachment.objects.create(
        issue=issue, file=upload, uploaded_by=actor, original_name=upload.name,
        content_type=getattr(upload, "content_type", "") or "", size=upload.size)
    audit.record(issue, AuditLogEntry.ACTION_UPDATE, actor=actor,
                 after={"attachment": obj.original_name},
                 note="Attachment added", fc=issue.fc)
    return obj


@transaction.atomic
def link_unit(issue, *, fc, actor, reason):
    """Record that a unit is involved, without editing the discovery FC and
    without blocking that unit's stage."""
    if not (reason or "").strip():
        raise WorkflowError("Linking a unit requires a reason.", code="reason_required")
    link = IssueUnitLink.objects.create(issue=issue, fc=fc, linked_by=actor,
                                        reason=reason)
    record_event(issue, "unit_linked", actor, fc=fc.pk, reason=reason)
    log_event(fc, "ISSUE_LINKED", f"{issue.key} linked to this unit", detail=reason,
              actor=actor, issue=issue)
    audit.record(issue, AuditLogEntry.ACTION_UPDATE, actor=actor,
                 after={"unit_linked": fc.serial}, note=reason, fc=fc)
    return link


@transaction.atomic
def set_blocks_stage(issue, *, actor, blocks, reason):
    """The lifecycle decision that an issue blocks its FC's stage.
    PLACEHOLDER authority: department leads and managers."""
    if issue.fc_id is None:
        raise WorkflowError("Only an issue discovered on an FC can block a stage.",
                            code="no_fc")
    if not actor.is_lead_role:
        raise WorkflowError("Only a department lead or manager may decide whether "
                            "an issue blocks a stage.", code="forbidden")
    if not (reason or "").strip():
        raise WorkflowError("A reason is required.", code="reason_required")
    before = audit.snapshot(issue)
    issue.blocks_stage = bool(blocks)
    issue.save(update_fields=["blocks_stage", "updated_at"])
    record_event(issue, "blocks_stage_set", actor, blocks=issue.blocks_stage,
                 reason=reason)
    audit.record_change(issue, AuditLogEntry.ACTION_UPDATE, before, note=reason,
                        actor=actor)
    issue.fc.recompute_status()
    return issue


# --- WP5: routing, acknowledgement, ownership, handoffs ---------------------
def _lock(issue):
    return Issue.objects.select_for_update().get(pk=issue.pk)


def _managers():
    from accounts.models import Capability, User
    return list(User.objects.filter(
        is_active=True, capability_grants__capability=Capability.IS_MANAGER,
        capability_grants__revoked_at__isnull=True))


def pick_queue(product_area):
    rule = (RoutingRule.objects.filter(product_area=product_area)
            .select_related("queue").order_by("priority", "id").first())
    return rule.queue if rule else Queue.objects.filter(is_fallback=True).first()


@transaction.atomic
def route(issue, actor=None):
    """Send the issue to its queue; the queue head is accountable until a
    member accepts ownership. With no fallback queue configured the report
    stays unrouted rather than failing."""
    issue = _lock(issue)
    queue = pick_queue(issue.product_area)
    if queue is None:
        return issue
    now = timezone.now()
    issue.queue = queue
    issue.accountable_user = queue.head
    issue.owner_since = now
    if queue.department_id:
        issue.assigned_department_id = queue.department_id
    issue.save(update_fields=["queue", "accountable_user", "assigned_department",
                              "owner_since", "updated_at"])
    record_event(issue, "routed", actor, queue=queue.pk, queue_name=queue.name,
                 fallback=queue.is_fallback,
                 seconds_since_submission=(now - issue.submitted_at).total_seconds())
    record_event(issue, "assigned", actor, accountable=queue.head_id, queue=queue.pk)
    deadlines.check_issue(issue, now)  # step 0: the head is alerted now
    return issue


def _queue_leads(queue):
    return {queue.head_id, queue.backup_id} if queue else set()


@transaction.atomic
def acknowledge(issue, *, user):
    """Explicit acknowledgement by the accountable person, the queue head or
    its backup. Idempotent; viewing an issue never calls this."""
    issue = _lock(issue)
    if user.pk not in {issue.accountable_user_id} | _queue_leads(issue.queue):
        raise WorkflowError("Only the accountable person, the queue head or the "
                            "backup can acknowledge this issue.", code="forbidden")
    if issue.acknowledged_at is not None:
        return issue
    issue.acknowledged_at = timezone.now()
    issue.acknowledged_by = user
    issue.save(update_fields=["acknowledged_at", "acknowledged_by", "updated_at"])
    record_event(issue, "acknowledged", user, seconds_since_submission=(
        issue.acknowledged_at - issue.submitted_at).total_seconds())
    audit.record(issue, AuditLogEntry.ACTION_UPDATE, actor=user,
                 after={"acknowledged_by": user.pk}, note="Acknowledged")
    return issue


@transaction.atomic
def accept_ownership(issue, *, actor, member):
    """The queue head (or backup) names the member who owns the issue."""
    from access.policy import active_memberships
    issue = _lock(issue)
    if actor.pk not in _queue_leads(issue.queue):
        raise WorkflowError("Only the queue head or backup can assign ownership.",
                            code="forbidden")
    dept = issue.queue.department_id
    if dept and not active_memberships(member).filter(department_id=dept).exists():
        raise WorkflowError("The owner must be an active member of the queue's team.",
                            code="not_team_member")
    before = audit.snapshot(issue)
    issue.accountable_user = member
    issue.owner_epoch += 1
    issue.owner_since = timezone.now()
    issue.save(update_fields=["accountable_user", "owner_epoch", "owner_since",
                              "updated_at"])
    record_event(issue, "ownership_accepted", actor, accountable=member.pk,
                 owner_epoch=issue.owner_epoch)
    audit.record_change(issue, AuditLogEntry.ACTION_REASSIGN, before,
                        note="Ownership accepted", actor=actor)
    notify(member, "ISSUE_ASSIGNED", issue)
    deadlines.check_issue(issue)
    return issue


@transaction.atomic
def propose_handoff(issue, *, actor, to_department, reason, to_user=None):
    """Propose moving the issue to another team. Accountability does not
    change until the receiver accepts."""
    from access.policy import is_head_or_manager
    if not (reason or "").strip():
        raise WorkflowError("A handoff needs a reason.", code="reason_required")
    issue = _lock(issue)
    if not (actor.pk in {issue.accountable_user_id} | _queue_leads(issue.queue)
            or is_head_or_manager(actor)):
        raise WorkflowError("Only the accountable person, the queue head or backup, "
                            "or a head may propose a handoff.", code="forbidden")
    if issue.handoffs.filter(status=Handoff.PENDING).exists():
        raise WorkflowError("A handoff is already pending for this issue.",
                            code="handoff_pending")
    try:
        with transaction.atomic():
            handoff = Handoff.objects.create(
                issue=issue, from_user=issue.accountable_user,
                from_department=issue.assigned_department, to_department=to_department,
                to_user=to_user, reason=reason, proposed_by=actor,
                proposed_at=timezone.now())
    except IntegrityError:
        raise WorkflowError("A handoff is already pending for this issue.",
                            code="handoff_pending")
    record_event(issue, "handoff_proposed", actor, handoff=handoff.pk,
                 to_department=to_department.pk,
                 to_user=getattr(to_user, "pk", None), reason=reason)
    audit.record(issue, AuditLogEntry.ACTION_UPDATE, actor=actor,
                 after={"handoff_to": to_department.pk}, note=reason)
    deadlines.check_handoff(handoff)  # step 0: the receiver is alerted now
    return handoff


def can_respond(handoff, user):
    receivers = {handoff.to_user_id} | _queue_leads(handoff.to_queue)
    return user.pk in receivers - {None}


@transaction.atomic
def respond_handoff(handoff, *, actor, accept, reason=""):
    issue = _lock(handoff.issue)
    handoff = Handoff.objects.select_for_update().get(pk=handoff.pk)
    if handoff.status != Handoff.PENDING:
        raise WorkflowError("This handoff is no longer pending.", code="handoff_closed")
    if not can_respond(handoff, actor):
        raise WorkflowError("Only the receiving head, backup or named recipient can "
                            "respond.", code="forbidden")
    if not accept and not (reason or "").strip():
        raise WorkflowError("Rejecting a handoff needs a reason.", code="reason_required")
    handoff.status = Handoff.ACCEPTED if accept else Handoff.REJECTED
    handoff.responded_by, handoff.responded_at = actor, timezone.now()
    handoff.response_reason = reason or ""
    handoff.save(update_fields=["status", "responded_by", "responded_at",
                                "response_reason"])
    if not accept:
        record_event(issue, "handoff_rejected", actor, handoff=handoff.pk,
                     reason=reason)
        audit.record(issue, AuditLogEntry.ACTION_UPDATE, actor=actor,
                     after={"handoff_rejected": handoff.pk}, note=reason)
        return handoff
    before = audit.snapshot(issue)
    queue = handoff.to_queue
    new_owner = handoff.to_user or (queue.head if queue else actor)
    from_department, from_person = issue.assigned_department, issue.accountable_user
    issue.queue = queue or issue.queue
    issue.assigned_department = handoff.to_department
    issue.accountable_user = new_owner
    # The acknowledgement clock and escalation sequence restart for the
    # new owner.
    issue.acknowledged_at, issue.acknowledged_by = None, None
    issue.owner_epoch += 1
    issue.owner_since = timezone.now()
    issue.save(update_fields=["queue", "assigned_department", "accountable_user",
                              "acknowledged_at", "acknowledged_by", "owner_epoch",
                              "owner_since", "updated_at"])
    IssueReassignmentLog.objects.create(
        issue=issue, from_department=from_department,
        to_department=handoff.to_department, from_person=from_person,
        to_person=new_owner, reason=f"Handoff accepted: {handoff.reason}", actor=actor)
    record_event(issue, "handoff_accepted", actor, handoff=handoff.pk,
                 accountable=new_owner.pk)
    record_event(issue, "assigned", actor, accountable=new_owner.pk,
                 queue=issue.queue_id)
    audit.record_change(issue, AuditLogEntry.ACTION_REASSIGN, before,
                        note=f"Handoff {handoff.pk} accepted", actor=actor)
    deadlines.check_issue(issue)
    return handoff


def _can_verify(issue, user):
    from access.policy import is_head_or_manager
    if user.is_test_engineer or user.is_lead_role or is_head_or_manager(user):
        return True
    return issue.participants.filter(user=user, role=IssueParticipant.ROLE_VERIFIER,
                                     removed_at__isnull=True).exists()


@transaction.atomic
def verify(issue, *, verifier, passed, what_tested="", evidence="", note=""):
    """Independent verification of the latest resolution (scenario 7). A
    fail returns the issue to investigation and keeps the resolution."""
    # Lock the row but keep working on the caller's instance, so it is not
    # left stale.
    Issue.objects.select_for_update().get(pk=issue.pk)
    issue.refresh_from_db()
    if issue.status != IssueStatus.RESOLVED:
        raise WorkflowError("Only a resolved issue can be verified.",
                            code="invalid_issue_transition")
    resolution = issue.resolutions.order_by("-at", "-id").first()
    if resolution is None:
        raise WorkflowError("No resolution is recorded for this issue.",
                            code="no_resolution")
    if settings.REQUIRE_INDEPENDENT_VERIFICATION and \
            resolution.resolved_by_id == verifier.pk:
        raise WorkflowError(
            "Verification must be performed by someone other than the person "
            "who resolved the issue.", code="independent_verification_required")
    if not _can_verify(issue, verifier):
        raise WorkflowError("Only a test engineer, a head, a manager or the assigned "
                            "verifier may verify a resolution.", code="forbidden")
    before = audit.snapshot(issue)
    v = Verification.objects.create(
        resolution=resolution, verifier=verifier,
        what_tested=what_tested or note or "(not stated)", evidence=evidence,
        result=Verification.PASS if passed else Verification.FAIL, notes=note)
    if passed:
        issue.status = IssueStatus.VERIFIED
        issue.verified_at, issue.verified_by = v.at, verifier
        record_event(issue, "verified", verifier, verification=v.pk)
    else:
        issue.status = IssueStatus.INVESTIGATING
        record_event(issue, "verification_failed", verifier, verification=v.pk)
    issue.save()
    reindex_issue(issue)
    audit.record_change(issue, AuditLogEntry.ACTION_VERIFY, before,
                        note=note or v.what_tested, actor=verifier)
    log_event(issue.fc, f"ISSUE_{issue.status}",
              f"{issue.key} → {issue.get_status_display()}", detail=note,
              stage=issue.discovered_stage, actor=verifier, issue=issue)
    for watcher in {issue.discovered_by, issue.assigned_person, issue.resolved_by}:
        if watcher and watcher.pk != verifier.pk:
            notify(watcher, "ISSUE_STATUS", issue)
    if issue.known_issue_id:
        issue.known_issue.refresh_rollup()
    _recompute_fc(issue)
    return issue


def can_reopen(issue, user):
    from access.policy import has_capability, is_head_or_manager
    from accounts.models import Capability
    allowed = set(settings.REOPEN_ALLOWED)
    return any((
        "accountable" in allowed and issue.accountable_user_id == user.pk,
        "queue_head" in allowed and issue.queue_id is not None
        and user.pk in (issue.queue.head_id, issue.queue.backup_id),
        "any_head" in allowed and is_head_or_manager(user),
        "manager" in allowed and (has_capability(user, Capability.IS_MANAGER)
                                  or user.is_manager_role),
    ))
