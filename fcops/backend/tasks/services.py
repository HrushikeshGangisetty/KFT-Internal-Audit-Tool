"""Task and daily-update writes, with policy and audit inside the transaction."""
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied

from access import policy
from core import audit
from core.exceptions import WorkflowError
from core.models import AuditLogEntry

from .models import DailyUpdate, Task, TaskCollaborator

TASK_FIELDS = ("title", "description", "accountable_user", "department", "priority",
               "due_date", "status", "issue", "fc")


def today():
    """'Today' is the working-calendar date, not the server's UTC date."""
    return timezone.localdate(timezone=ZoneInfo(settings.WORKING_TIMEZONE))


def can_manage(actor, task):
    return policy.is_head_or_manager(actor) or task.accountable_user_id == actor.pk


def is_participant(actor, task):
    return (task.accountable_user_id == actor.pk
            or task.collaborators.filter(user=actor).exists())


@transaction.atomic
def create_task(*, actor, changes):
    owner = changes.get("accountable_user") or actor
    if owner != actor and not policy.is_head_or_manager(actor):
        raise PermissionDenied("Only a head or the manager can assign tasks to others.")
    task = Task.objects.create(**{**changes, "accountable_user": owner,
                                  "created_by": actor})
    audit.record(task, AuditLogEntry.ACTION_CREATE, actor=actor,
                 after=audit.snapshot(task, fields=TASK_FIELDS))
    return task


@transaction.atomic
def update_task(task, *, actor, changes):
    task = Task.objects.select_for_update().get(pk=task.pk)
    if not can_manage(actor, task):
        raise PermissionDenied("Only the accountable person, a head or the manager "
                               "can change this task.")
    if ("accountable_user" in changes and changes["accountable_user"] != task.accountable_user
            and not policy.is_head_or_manager(actor)):
        raise PermissionDenied("Only a head or the manager can reassign a task.")
    before = audit.snapshot(task, fields=TASK_FIELDS)
    for key, value in changes.items():
        setattr(task, key, value)
    task.save()
    audit.record_change(task, AuditLogEntry.ACTION_UPDATE, before, fields=TASK_FIELDS,
                        actor=actor)
    return task


@transaction.atomic
def add_collaborator(task, *, actor, user):
    task = Task.objects.select_for_update().get(pk=task.pk)
    if not can_manage(actor, task):
        raise PermissionDenied("You cannot change collaborators on this task.")
    _, created = TaskCollaborator.objects.get_or_create(
        task=task, user=user, defaults={"added_by": actor})
    if created:
        audit.record(task, AuditLogEntry.ACTION_UPDATE, actor=actor,
                     after={"collaborator_added": user.pk})
    return task


@transaction.atomic
def post_update(*, actor, task=None, progress, next_step="", blockers="", supersedes=None):
    if task is not None and not is_participant(actor, task):
        raise PermissionDenied("Only the accountable person or a collaborator can post "
                               "updates on this task.")
    date = today()
    if supersedes is not None:
        supersedes = DailyUpdate.objects.select_for_update().get(pk=supersedes.pk)
        if supersedes.author_id != actor.pk:
            raise PermissionDenied("You can only correct your own update.")
        if supersedes.date != date:
            raise WorkflowError("Only today's update can be corrected; earlier days "
                                "are kept as written.", code="update_locked")
        if supersedes.task_id != getattr(task, "pk", None):
            raise WorkflowError("A correction must be for the same task.",
                                code="task_mismatch")
        if DailyUpdate.objects.filter(supersedes=supersedes).exists():
            raise WorkflowError("This update has already been corrected.",
                                code="already_superseded")
    return DailyUpdate.objects.create(task=task, author=actor, date=date,
                                      progress=progress, next_step=next_step,
                                      blockers=blockers, supersedes=supersedes)
