"""Acknowledgement deadlines, reminders, waiting follow-ups and escalation
(WP6). ``check_deadlines`` runs every minute in the worker; it is safe to run
any number of times at the same instant because every alert is keyed by its
step and ``dispatch_alert`` sends each key once per recipient and channel.

Keys:
  ack:<issue>:<owner_epoch>:<step>          unacknowledged issue
  handoff:<handoff>:<step>                  pending handoff
  followup:<issue>:<epoch>:<last activity>  acknowledged but quiet issue
  waiting:<issue>:<follow-up at>:<step>     waiting issue past its date
  coverage:<what>:<date>                    a gap, once per day
"""
from datetime import timedelta

from django.conf import settings
from django.db.models import Max
from django.utils import timezone

from core import alerts, jobs
from core.calendar import add_working_minutes, is_working_time, working_minutes_between

from .models import DeadlinePolicy, Handoff, Issue, IssueEvent, IssueStatus, Urgency

ACTIVE = (IssueStatus.OPEN, IssueStatus.INVESTIGATING)
DEFAULT_POLICY = {"ack_target_minutes": 240, "ack_uses_working_hours": True,
                  "followup_interval_minutes": 480, "escalation_steps": [
                      {"after_minutes": 0, "to": "owner", "channels": "normal"}]}


def policy_for(urgency):
    """Unknown urgency is treated as normal."""
    key = Urgency.URGENT if urgency == Urgency.URGENT else Urgency.NORMAL
    policy = DeadlinePolicy.objects.filter(urgency=key).first()
    return policy or DeadlinePolicy(urgency=key, **DEFAULT_POLICY)


def elapsed_minutes(policy, since, now):
    if policy.ack_uses_working_hours:
        return working_minutes_between(since, now)
    return int((now - since).total_seconds() // 60)


def due_at(policy, since, minutes):
    if policy.ack_uses_working_hours:
        return add_working_minutes(since, minutes)
    return since + timedelta(minutes=minutes)


def ack_due_at(issue):
    if issue.owner_since is None:
        return None
    policy = policy_for(issue.urgency)
    return due_at(policy, issue.owner_since, policy.ack_target_minutes)


def _managers():
    from accounts.models import Capability, User
    return list(User.objects.filter(
        is_active=True, capability_grants__capability=Capability.IS_MANAGER,
        capability_grants__revoked_at__isnull=True))


def _summary(issue, urgency, **extra):
    return {"ref": issue.key, "urgency": urgency,
            "queue": issue.queue.name if issue.queue_id else "",
            "link": f"/issues/{issue.pk}", **extra}


def _event(issue, type, **data):
    IssueEvent.objects.create(issue=issue, type=type, at=timezone.now(), data=data)


def coverage_gap(issue, what, detail, now):
    """Tell the managers once per day; never claim coverage that is absent."""
    created = alerts.dispatch_alert(
        f"coverage:{what}:{now.date().isoformat()}", _managers(), "normal",
        ("issue", issue.pk), kind="COVERAGE_GAP",
        summary=_summary(issue, "normal", gap=detail), channels=["in_app"])
    if created:
        _event(issue, "coverage_gap", what=what, detail=detail)


def _deliverable(user):
    """A missing email address is a failed delivery (WP3 notices the head
    and managers); an inactive person cannot be reached at all."""
    return user is not None and user.is_active


def _send_step(issue, key, step_index, recipients, channel_class, now, *,
               reminder):
    urgency = alerts.URGENT if channel_class == "urgent" else "normal"
    extra = {}
    if step_index == 0 and urgency == alerts.URGENT and not is_working_time(now):
        duty = _duty_contact()
        if duty is None:
            coverage_gap(issue, f"after-hours:{issue.pk}", "Urgent alert after hours and no duty "
                         "contact is configured; it was sent to the owner only.", now)
        else:
            recipients = [*recipients, duty]
            extra["on_duty"] = duty.full_name or duty.username
    targets = [u for u in recipients if _deliverable(u)]
    for user in recipients:
        if user is not None and user not in targets:
            coverage_gap(issue, f"user:{user.pk}",
                         f"{user} cannot receive alerts (inactive or no address).", now)
    if not targets:
        return
    created = alerts.dispatch_alert(
        key, targets, urgency, ("issue", issue.pk), kind="ISSUE_ALERT",
        summary=_summary(issue, urgency, **extra),
        on_failure=[issue.queue.head if issue.queue_id else None, *_managers()])
    if created:
        type = "notified" if step_index == 0 else (
            "reminder_sent" if reminder else "escalated")
        _event(issue, type, key=key, step=step_index,
               recipients=sorted({d.recipient_id for d in created}))


def _duty_contact():
    if not settings.DUTY_CONTACT_USER_ID:
        return None
    from accounts.models import User
    return User.objects.filter(pk=settings.DUTY_CONTACT_USER_ID, is_active=True).first()


def _step_recipients(to, owner, queue):
    if to == "owner":
        return [owner]
    if to == "backup":
        return [queue.backup if queue else None]
    return _managers()


def check_issue(issue, now=None):
    """Due acknowledgement steps for one unacknowledged, routed issue."""
    now = now or timezone.now()
    if issue.acknowledged_at or issue.owner_since is None or issue.status not in ACTIVE:
        return
    queue = issue.queue
    if queue and not (queue.head.is_active or queue.backup.is_active):
        coverage_gap(issue, f"queue:{queue.pk}",
                     f"Queue {queue.name} has no active head or backup.", now)
    policy = policy_for(issue.urgency)
    elapsed = elapsed_minutes(policy, issue.owner_since, now)
    for i, step in enumerate(policy.escalation_steps):
        if elapsed < step["after_minutes"]:
            continue
        _send_step(issue, f"ack:{issue.pk}:{issue.owner_epoch}:{i}", i,
                   _step_recipients(step["to"], issue.accountable_user, queue),
                   step["channels"], now, reminder=step["to"] == "owner")


def check_handoff(handoff, now=None):
    """Pending handoffs follow the normal policy from ``proposed_at``,
    escalating to the receiver, then its backup, then the manager."""
    now = now or timezone.now()
    if handoff.status != Handoff.PENDING:
        return
    issue = handoff.issue
    queue = handoff.to_queue
    receiver = handoff.to_user or (queue.head if queue else None)
    policy = policy_for(Urgency.NORMAL)
    elapsed = elapsed_minutes(policy, handoff.proposed_at, now)
    for i, step in enumerate(policy.escalation_steps):
        if elapsed >= step["after_minutes"]:
            _send_step(issue, f"handoff:{handoff.pk}:{i}", i,
                       _step_recipients(step["to"], receiver, queue), "normal", now,
                       reminder=step["to"] == "owner")


def check_followup(issue, now=None):
    """An acknowledged issue with no activity for the follow-up interval
    reminds its owner, once per quiet period. Waiting issues are paused."""
    now = now or timezone.now()
    if not issue.acknowledged_at or issue.is_waiting or issue.status not in ACTIVE:
        return
    policy = policy_for(issue.urgency)
    last_event = issue.events.aggregate(at=Max("at"))["at"]
    last = max(filter(None, [issue.updated_at, last_event, issue.acknowledged_at]))
    if elapsed_minutes(policy, last, now) < policy.followup_interval_minutes:
        return
    _send_step(issue, f"followup:{issue.pk}:{issue.owner_epoch}:{int(last.timestamp())}",
               1, [issue.accountable_user], "normal", now, reminder=True)


def check_waiting(issue, now=None):
    """On the follow-up date remind the owner; if it is still waiting on the
    same date one acknowledgement target later, the queue head; then the
    manager."""
    now = now or timezone.now()
    when = issue.waiting_next_followup_at
    if not issue.is_waiting or when is None or now < when:
        return
    policy = policy_for(issue.urgency)
    elapsed = elapsed_minutes(policy, when, now)
    target = policy.ack_target_minutes
    ladder = [(0, [issue.accountable_user]),
              (target, [issue.queue.head if issue.queue_id else None]),
              (2 * target, _managers())]
    for i, (after, recipients) in enumerate(ladder):
        if elapsed >= after:
            _send_step(issue, f"waiting:{issue.pk}:{int(when.timestamp())}:{i}",
                       max(i, 1), recipients, "normal", now, reminder=i == 0)


@jobs.periodic("issues.check_deadlines", every=timedelta(minutes=1))
def check_deadlines(now=None):
    now = now or timezone.now()
    issues = Issue.objects.filter(status__in=ACTIVE).select_related(
        "queue__head", "queue__backup", "accountable_user")
    for issue in issues.filter(acknowledged_at__isnull=True, owner_since__isnull=False):
        check_issue(issue, now)
    for issue in issues.filter(acknowledged_at__isnull=False):
        check_followup(issue, now)
        check_waiting(issue, now)
    for issue in issues.filter(acknowledged_at__isnull=True, is_waiting=True):
        check_waiting(issue, now)
    for handoff in Handoff.objects.filter(status=Handoff.PENDING).select_related(
            "issue", "to_user", "to_department"):
        check_handoff(handoff, now)
