from django.db.models import Exists, OuterRef, Q
from django.utils import timezone
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.generics import get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

from access import policy
from access.mixins import ScopedViewSetMixin
from accounts.models import Department, TeamMembership, User

from . import services
from .models import Task, TaskCollaborator
from .serializers import DailyUpdateSerializer, TaskSerializer


def my_tasks(user):
    """Open tasks the user is accountable for or collaborates on."""
    return policy.visible_tasks(user).filter(
        Q(accountable_user=user)
        | Q(pk__in=TaskCollaborator.objects.filter(user=user).values("task_id")),
        status__in=Task.OPEN_STATUSES)


class TaskViewSet(ScopedViewSetMixin, mixins.CreateModelMixin, mixins.UpdateModelMixin,
                  mixins.RetrieveModelMixin, mixins.ListModelMixin,
                  viewsets.GenericViewSet):
    # No delete: cancel a task instead, so its updates keep their context.
    serializer_class = TaskSerializer
    filterset_fields = ("status", "accountable_user", "department", "issue", "fc", "release")

    def get_scoped_queryset(self):
        user = self.request.user
        qs = policy.visible_tasks(user)
        if self.request.query_params.get("mine"):
            qs = qs.filter(Q(accountable_user=user) | Q(
                pk__in=TaskCollaborator.objects.filter(user=user).values("task_id")))
        if self.request.query_params.get("open"):
            qs = qs.filter(status__in=Task.OPEN_STATUSES)
        return qs.select_related("accountable_user", "department").prefetch_related(
            "collaborators__user")

    def perform_create(self, serializer):
        serializer.instance = services.create_task(actor=self.request.user,
                                                   changes=serializer.validated_data)

    def perform_update(self, serializer):
        serializer.instance = services.update_task(serializer.instance,
                                                   actor=self.request.user,
                                                   changes=serializer.validated_data)

    @action(detail=True, methods=["post"])
    def collaborators(self, request, pk=None):
        user = get_object_or_404(User.objects.filter(is_active=True),
                                 pk=request.data.get("user"))
        task = services.add_collaborator(self.get_object(), actor=request.user, user=user)
        return Response(self.get_serializer(task).data)


class DailyUpdateViewSet(ScopedViewSetMixin, mixins.CreateModelMixin,
                         mixins.RetrieveModelMixin, mixins.ListModelMixin,
                         viewsets.GenericViewSet):
    """Append-only: no update or delete route. Correct the current day's
    entry by posting a new one with ``supersedes``."""
    serializer_class = DailyUpdateSerializer
    filterset_fields = ("task", "author", "date")

    def get_scoped_queryset(self):
        qs = policy.visible_daily_updates(self.request.user).select_related(
            "author", "task", "superseded_by")
        if self.request.query_params.get("current"):
            qs = qs.filter(superseded_by__isnull=True)
        if self.request.query_params.get("mine"):
            qs = qs.filter(author=self.request.user)
        return qs

    def perform_create(self, serializer):
        data = serializer.validated_data
        serializer.instance = services.post_update(
            actor=self.request.user, task=data.get("task"), progress=data["progress"],
            next_step=data.get("next_step", ""), blockers=data.get("blockers", ""),
            supersedes=data.get("supersedes"))


def _person(user):
    return {"id": user.pk, "name": user.full_name or user.username}


def _issue_row(issue, **extra):
    return {"id": issue.pk, "key": issue.key, "title": issue.title,
            "urgency": issue.urgency, "status": issue.status,
            "queue_name": issue.queue.name if issue.queue_id else "",
            "accountable_user_name": (issue.accountable_user.full_name
                                      if issue.accountable_user_id else ""),
            "owner_since": issue.owner_since, "submitted_at": issue.submitted_at, **extra}


class ProgressView(APIView):
    """Head view (WP10): assigned work, missing updates, overdue and blocked
    tasks, next steps, and issues needing attention. Plain lists only: no
    activity counts or rankings (PRD §3). Built from access.policy scopes."""

    def get(self, request):
        from issues.deadlines import ACTIVE, ack_due_at
        from issues.models import IssueEvent

        user = request.user
        if not policy.is_head_or_manager(user):
            raise PermissionDenied("The progress view is for heads and the manager.")
        now = timezone.now()
        memberships = TeamMembership.objects.filter(
            Q(active_to__isnull=True) | Q(active_to__gt=now),
            active_from__lte=now, user__is_active=True)
        department = request.query_params.get("department")
        if department:
            department = get_object_or_404(Department, pk=department)
            memberships = memberships.filter(department=department)
        members = list(User.objects.filter(
            pk__in=memberships.values("user_id")).order_by("full_name", "username"))
        member_ids = {m.pk for m in members}

        date = services.today()
        tasks = policy.visible_tasks(user).filter(status__in=Task.OPEN_STATUSES)
        if department:
            tasks = tasks.filter(Q(department=department) | Q(accountable_user__in=members))
        tasks = list(tasks.select_related("accountable_user", "department")
                     .prefetch_related("collaborators__user"))
        ctx = {"request": request}
        rows = {t.pk: TaskSerializer(t, context=ctx).data for t in tasks}
        updates = [u for u in policy.visible_daily_updates(user).filter(
            date=date, superseded_by__isnull=True).select_related("author", "task")
            if not department or u.author_id in member_ids]
        updated = {u.author_id for u in updates}

        issues = policy.visible_issues(user).filter(
            status__in=ACTIVE, acknowledged_at__isnull=True).select_related(
            "queue", "accountable_user")
        if department:
            issues = issues.filter(Q(queue__department=department)
                                   | Q(assigned_department=department))
        escalated = issues.filter(Exists(IssueEvent.objects.filter(
            issue=OuterRef("pk"), type="escalated", at__gte=OuterRef("owner_since"))))
        # ponytail: per-issue due computation in Python; fine at pilot volume.
        past_target = []
        for issue in issues:
            due = ack_due_at(issue)
            if due and due < now:
                past_target.append(_issue_row(issue, ack_due_at=due))

        return Response({
            "date": date,
            "department": department.pk if department else None,
            "assigned_work": [{**_person(m), "tasks": [
                rows[t.pk] for t in tasks if t.accountable_user_id == m.pk]}
                for m in members],
            "no_update_today": [_person(m) for m in members if m.pk not in updated],
            "overdue": [rows[t.pk] for t in tasks if t.due_date and t.due_date < date],
            "blocked": [rows[t.pk] for t in tasks if t.status == Task.BLOCKED],
            "updates_today": DailyUpdateSerializer(updates, many=True, context=ctx).data,
            "unacknowledged_past_target": past_target,
            "escalated": [_issue_row(i) for i in escalated],
        })
