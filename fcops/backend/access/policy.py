"""Who may see which records (WP1). The one place record scope is defined.

Every scope function returns a queryset built from subqueries rather than
joins, so it never duplicates rows: it composes with search ranking, limits,
``values().annotate(Count)`` and ``.count()`` without ``distinct()``.

Child records (notes, attachments, stage records, timeline events) are
reachable only through their parent's scope; seeing one linked object never
grants another.
"""
from django.conf import settings
from django.db.models import CharField, Q
from django.db.models.functions import Cast
from django.utils import timezone

from accounts.models import Capability, CapabilityGrant, TeamMembership


# --- who the user is --------------------------------------------------------
def active_memberships(user):
    now = timezone.now()
    return TeamMembership.objects.filter(
        Q(active_to__isnull=True) | Q(active_to__gt=now),
        user=user, active_from__lte=now)


def active_department_ids(user):
    return active_memberships(user).values("department_id")


def has_capability(user, capability):
    if not getattr(user, "is_authenticated", False):
        return False
    return CapabilityGrant.objects.filter(user=user, capability=capability,
                                          revoked_at__isnull=True).exists()


def is_head_or_manager(user):
    """Active head or backup head of any department, or a manager.

    Being an account administrator or a Django superuser is deliberately not
    enough: administering accounts grants no record access.
    """
    if not getattr(user, "is_authenticated", False):
        return False
    return (has_capability(user, Capability.IS_MANAGER)
            or active_memberships(user).filter(
                role__in=TeamMembership.HEAD_ROLES).exists())


# --- issues ------------------------------------------------------------------
def visible_issues(user):
    from issues.models import Handoff, Issue, IssueParticipant

    qs = Issue.objects.all()
    if not getattr(user, "is_authenticated", False):
        return qs.none()
    if is_head_or_manager(user):
        return qs
    departments = active_department_ids(user)
    participating = IssueParticipant.objects.filter(
        user=user, removed_at__isnull=True).values("issue_id")
    # A pending handoff lets the named recipient and the receiving queue's
    # head and backup read the issue before they accept (WP5).
    receiving = Handoff.objects.filter(
        Q(to_user=user) | Q(to_department__queue__head=user)
        | Q(to_department__queue__backup=user),
        status=Handoff.PENDING).values("issue_id")
    scope = (Q(assigned_department_id__in=departments)
             | Q(discovered_by=user) | Q(reporter=user)
             | Q(assigned_person=user) | Q(accountable_user=user)
             | Q(queue__head=user) | Q(queue__backup=user)
             | Q(pk__in=participating) | Q(pk__in=receiving))
    if settings.HANDOFF_PREVIOUS_TEAM_ACCESS == "read":
        scope |= Q(pk__in=Handoff.objects.filter(
            status=Handoff.ACCEPTED,
            from_department_id__in=departments).values("issue_id"))
    return qs.filter(scope)


def can_view_issue(user, issue):
    return visible_issues(user).filter(pk=getattr(issue, "pk", issue)).exists()


def visible_attachments(user):
    from issues.models import IssueAttachment
    return IssueAttachment.objects.filter(issue__in=visible_issues(user))


# --- knowledge ---------------------------------------------------------------
def visible_knowledge(user):
    from issues.models import KnownIssue

    qs = KnownIssue.objects.all()
    if not getattr(user, "is_authenticated", False):
        return qs.none()
    if is_head_or_manager(user):
        return qs
    audience_rows = KnownIssue.audience_departments.through.objects.filter(
        department_id__in=active_department_ids(user)).values("knownissue_id")
    return qs.filter(Q(audience=KnownIssue.AUDIENCE_ALL_STAFF)
                     | Q(audience=KnownIssue.AUDIENCE_DEPARTMENTS,
                         pk__in=audience_rows))


# --- flight controllers ------------------------------------------------------
def can_view_fcs(user):
    """PLACEHOLDER until the FC access matrix is agreed (PRD §5): heads,
    managers and members of ``settings.FC_VISIBLE_DEPARTMENT_KINDS``."""
    if is_head_or_manager(user):
        return True
    return active_memberships(user).filter(
        department__kind__in=settings.FC_VISIBLE_DEPARTMENT_KINDS).exists()


def scope_by_fc(user, queryset):
    """Scope an FC or an FC child-record queryset (all-or-nothing for now)."""
    return queryset if can_view_fcs(user) else queryset.none()


def visible_fcs(user):
    from fc.models import FlightController
    return scope_by_fc(user, FlightController.objects.all())


def visible_stage_records(user):
    from fc.models import StageRecord
    return scope_by_fc(user, StageRecord.objects.all())


# --- customers (WP9) ---------------------------------------------------------
def visible_customers(user):
    from customers.models import Customer
    return scope_by_fc(user, Customer.objects.all())


def visible_deployments(user):
    from customers.models import Deployment
    return scope_by_fc(user, Deployment.objects.all())


def visible_customer_contacts(user):
    from customers.models import CustomerContact
    qs = CustomerContact.objects.all()
    return qs if has_capability(user, Capability.CAN_VIEW_CUSTOMER_CONTACTS) else qs.none()


def contact_customers(user):
    # A contact grant is independent of engineering-summary access.
    from customers.models import Customer
    qs = Customer.objects.all()
    return qs if has_capability(user, Capability.CAN_VIEW_CUSTOMER_CONTACTS) else qs.none()


# --- tasks and daily progress (WP10) -----------------------------------------
def visible_tasks(user):
    """Own and collaborative tasks; every head and the manager see all.
    Teammates see each other's tasks only when TASKS_TEAMMATES_VISIBLE
    (PLACEHOLDER until the PRD decision)."""
    from tasks.models import Task, TaskCollaborator

    qs = Task.objects.all()
    if not getattr(user, "is_authenticated", False):
        return qs.none()
    if is_head_or_manager(user):
        return qs
    collaborating = TaskCollaborator.objects.filter(user=user).values("task_id")
    scope = Q(accountable_user=user) | Q(pk__in=collaborating)
    if settings.TASKS_TEAMMATES_VISIBLE:
        scope |= Q(department_id__in=active_department_ids(user))
    return qs.filter(scope)


def visible_daily_updates(user):
    """Your own updates and updates on tasks you can see."""
    from tasks.models import DailyUpdate

    qs = DailyUpdate.objects.all()
    if not getattr(user, "is_authenticated", False):
        return qs.none()
    if is_head_or_manager(user):
        return qs
    return qs.filter(Q(author=user) | Q(task__in=visible_tasks(user)))


# --- notifications and audit ------------------------------------------------
def visible_notifications(user):
    from core.models import Notification
    return Notification.objects.filter(recipient=user)


ACCOUNT_ENTITY_TYPES = ("User", "Department", "TeamMembership", "CapabilityGrant")


def visible_audit_entries(user):
    """An audit entry is visible when the record it describes is.

    Issue and knowledge entries follow those scopes (even though issue
    entries also carry an FC), account entries need account administration,
    other entries tied to an FC follow FC scope, and the rest (catalogue and
    configuration changes) are visible to all staff.
    """
    from core.models import AuditLogEntry

    qs = AuditLogEntry.objects.all()
    if not getattr(user, "is_authenticated", False):
        return qs.none()
    # Contact snapshots contain restricted fields, including historical values.
    if not has_capability(user, Capability.CAN_VIEW_CUSTOMER_CONTACTS):
        qs = qs.exclude(entity_type="CustomerContact")
    if not can_view_fcs(user):
        qs = qs.exclude(entity_type__in=("Customer", "Deployment"))
    if has_capability(user, Capability.IS_MANAGER):
        return qs

    def ids(scope):
        return scope.annotate(sid=Cast("pk", CharField())).values("sid")

    allowed = (Q(entity_type="Issue", entity_id__in=ids(visible_issues(user)))
               | Q(entity_type="KnownIssue",
                   entity_id__in=ids(visible_knowledge(user)))
               | Q(entity_type="Task", entity_id__in=ids(visible_tasks(user))))
    if has_capability(user, Capability.CAN_ADMINISTER_ACCOUNTS):
        allowed |= Q(entity_type__in=ACCOUNT_ENTITY_TYPES)
    other = ~Q(entity_type__in=("Issue", "KnownIssue", "Task") + ACCOUNT_ENTITY_TYPES)
    if can_view_fcs(user):
        allowed |= other
    else:
        allowed |= other & Q(fc__isnull=True)
    return qs.filter(allowed)
