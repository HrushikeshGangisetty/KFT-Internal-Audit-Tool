"""Tasks and daily progress (WP10).

Daily updates are append-only: a correction made the same day is a new row
that ``supersedes`` the earlier one, and earlier days cannot be superseded,
so yesterday's text never changes.
"""
from django.conf import settings
from django.db import models

from core.models import TimeStampedModel


class Task(TimeStampedModel):
    PLANNED, IN_PROGRESS, BLOCKED, DONE, CANCELLED = (
        "planned", "in_progress", "blocked", "done", "cancelled")
    STATUS_CHOICES = [(PLANNED, "Planned"), (IN_PROGRESS, "In progress"),
                      (BLOCKED, "Blocked"), (DONE, "Done"), (CANCELLED, "Cancelled")]
    OPEN_STATUSES = (PLANNED, IN_PROGRESS, BLOCKED)
    PRIORITY_CHOICES = [("low", "Low"), ("normal", "Normal"), ("high", "High")]

    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    accountable_user = models.ForeignKey(settings.AUTH_USER_MODEL,
                                         on_delete=models.PROTECT,
                                         related_name="accountable_tasks")
    department = models.ForeignKey("accounts.Department", null=True, blank=True,
                                   on_delete=models.PROTECT, related_name="tasks")
    priority = models.CharField(max_length=8, choices=PRIORITY_CHOICES, default="normal")
    due_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=PLANNED,
                              db_index=True)
    # Release link waits for WP11's release model.
    issue = models.ForeignKey("issues.Issue", null=True, blank=True,
                              on_delete=models.PROTECT, related_name="tasks")
    fc = models.ForeignKey("fc.FlightController", null=True, blank=True,
                           on_delete=models.PROTECT, related_name="tasks")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True,
                                   on_delete=models.SET_NULL, related_name="+")

    class Meta:
        ordering = ("due_date", "id")

    def __str__(self):
        return self.title


class TaskCollaborator(models.Model):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="collaborators")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                             related_name="task_collaborations")
    added_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True,
                                 on_delete=models.SET_NULL, related_name="+")
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["task", "user"],
                                               name="one_collaborator_row_per_task")]


class DailyUpdate(models.Model):
    task = models.ForeignKey(Task, null=True, blank=True, on_delete=models.PROTECT,
                             related_name="updates")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                               related_name="daily_updates")
    date = models.DateField(db_index=True)
    progress = models.TextField()
    next_step = models.TextField(blank=True)
    blockers = models.TextField(blank=True)
    supersedes = models.OneToOneField("self", null=True, blank=True,
                                      on_delete=models.PROTECT,
                                      related_name="superseded_by")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-date", "-created_at", "-id")

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise PermissionError("Daily updates are append-only.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionError("Daily updates cannot be deleted.")
