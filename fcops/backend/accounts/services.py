"""Membership and capability changes (WP1). Every change is audited."""
from django.contrib.sessions.models import Session
from django.db import transaction
from django.utils import timezone

from core import audit
from core.models import AuditLogEntry

from .models import Capability, CapabilityGrant, Department, Role, TeamMembership


def legacy_membership_role(role):
    return (TeamMembership.ROLE_HEAD if role == Role.DEPARTMENT_LEAD
            else TeamMembership.ROLE_MEMBER)


def legacy_capabilities(role, department):
    """Capabilities implied by the legacy ``User.role`` / ``User.department``.

    Same mapping as accounts migration 0003. Admin is deliberately *not* a
    manager here: administering accounts grants no record access.
    """
    caps = set()
    if role == Role.MANAGER:
        caps.add(Capability.IS_MANAGER)
    if role == Role.ADMIN:
        caps.add(Capability.CAN_ADMINISTER_ACCOUNTS)
    if department is not None and department.kind == Department.KIND_SOFTWARE:
        caps.add(Capability.CAN_DRAFT_RELEASE)
        if role == Role.DEPARTMENT_LEAD:
            caps.add(Capability.IS_SOFTWARE_HEAD)
    return caps


@transaction.atomic
def add_membership(user, department, role=TeamMembership.ROLE_MEMBER, *, actor,
                   active_from=None):
    membership = TeamMembership.objects.create(
        user=user, department=department, role=role,
        active_from=active_from or timezone.now(),
        created_by=actor if getattr(actor, "pk", None) else None)
    audit.record(membership, AuditLogEntry.ACTION_PERMISSION, actor=actor,
                 after=audit.snapshot(membership), note="Membership opened")
    return membership


@transaction.atomic
def close_membership(membership, *, actor, at=None):
    if membership.active_to is not None:
        return membership
    membership.active_to = at or timezone.now()
    membership.save(update_fields=["active_to"])
    audit.record(membership, AuditLogEntry.ACTION_PERMISSION, actor=actor,
                 after={"active_to": membership.active_to.isoformat()},
                 note="Membership closed")
    return membership


@transaction.atomic
def grant_capability(user, capability, *, actor, note=""):
    existing = CapabilityGrant.objects.filter(user=user, capability=capability,
                                              revoked_at__isnull=True).first()
    if existing:
        return existing
    grant = CapabilityGrant.objects.create(
        user=user, capability=capability, note=note,
        granted_by=actor if getattr(actor, "pk", None) else None)
    audit.record(grant, AuditLogEntry.ACTION_PERMISSION, actor=actor,
                 after={"user": user.pk, "capability": capability},
                 note="Capability granted")
    return grant


@transaction.atomic
def revoke_capability(user, capability, *, actor):
    for grant in CapabilityGrant.objects.filter(user=user, capability=capability,
                                                revoked_at__isnull=True):
        grant.revoked_at = timezone.now()
        grant.revoked_by = actor if getattr(actor, "pk", None) else None
        grant.save(update_fields=["revoked_at", "revoked_by"])
        audit.record(grant, AuditLogEntry.ACTION_PERMISSION, actor=actor,
                     after={"user": user.pk, "capability": capability},
                     note="Capability revoked")


@transaction.atomic
def sync_legacy_fields(user, *, actor, old_department=None, old_role=None):
    """Keep memberships and grants in step when ``User.department`` or
    ``User.role`` is changed through the user admin API.

    Only the delta is applied, so memberships in other departments and grants
    made directly through this module are left alone. ``old_role=None`` means
    the user is new.
    """
    old_key = (old_department, legacy_membership_role(old_role)) if old_role else None
    new_key = (user.department, legacy_membership_role(user.role))
    if old_key != new_key:
        if old_department is not None:
            for m in TeamMembership.objects.filter(user=user, department=old_department,
                                                   active_to__isnull=True):
                close_membership(m, actor=actor)
        if user.department is not None:
            add_membership(user, user.department, new_key[1], actor=actor)

    old_caps = legacy_capabilities(old_role, old_department) if old_role else set()
    new_caps = legacy_capabilities(user.role, user.department)
    for cap in old_caps - new_caps:
        revoke_capability(user, cap, actor=actor)
    for cap in new_caps - old_caps:
        grant_capability(user, cap, actor=actor, note="Derived from role/department")


def end_sessions(user, *, actor):
    """Delete every live session of ``user`` (on deactivation, WP2).

    Django already treats an inactive user's session as anonymous; deleting
    the rows makes that explicit and survives a later reactivation.
    ponytail: decodes every live session; index sessions by user if the
    table grows large.
    """
    ended = 0
    for session in Session.objects.filter(expire_date__gt=timezone.now()):
        if session.get_decoded().get("_auth_user_id") == str(user.pk):
            session.delete()
            ended += 1
    audit.record(user, AuditLogEntry.ACTION_PERMISSION, actor=actor,
                 after={"sessions_ended": ended}, note="Sessions ended on deactivation")
    return ended
