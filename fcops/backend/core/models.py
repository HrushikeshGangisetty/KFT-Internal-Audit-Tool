"""Cross-cutting infrastructure models: append-only audit log and in-app
notifications."""
from django.conf import settings
from django.db import models


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class AuditLogEntry(models.Model):
    """Append-only record of every meaningful write.

    Rows are never updated or deleted: ``save()`` refuses updates and
    ``delete()`` raises. A database trigger enforces the same rule so that
    even raw SQL from an admin account cannot rewrite history silently.
    """

    ACTION_CREATE = "CREATE"
    ACTION_UPDATE = "UPDATE"
    ACTION_TRANSITION = "TRANSITION"
    ACTION_REASSIGN = "REASSIGN"
    ACTION_STATUS = "STATUS_CHANGE"
    ACTION_PROMOTE = "PROMOTE_KNOWN_ISSUE"
    ACTION_APPROVE = "MANAGER_APPROVAL"
    ACTION_REJECT = "MANAGER_REJECTION"
    ACTION_VERIFY = "VERIFICATION"
    ACTION_LOGIN = "LOGIN"
    ACTION_PERMISSION = "PERMISSION_CHANGE"
    ACTION_CONFIG = "CONFIG_CHANGE"
    ACTION_SOFTWARE_PUSH = "SOFTWARE_UPDATE_PUSHED"

    entity_type = models.CharField(max_length=64, db_index=True)
    entity_id = models.CharField(max_length=64, db_index=True)
    entity_label = models.CharField(max_length=255, blank=True)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                              on_delete=models.SET_NULL, related_name="audit_entries")
    actor_label = models.CharField(max_length=255, blank=True)
    action = models.CharField(max_length=48, db_index=True)
    before = models.JSONField(null=True, blank=True)
    after = models.JSONField(null=True, blank=True)
    note = models.TextField(blank=True)
    fc = models.ForeignKey("fc.FlightController", null=True, blank=True,
                           on_delete=models.SET_NULL, related_name="audit_entries")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ("-created_at", "-id")
        indexes = [models.Index(fields=["entity_type", "entity_id"])]

    def __str__(self):
        return f"{self.action} {self.entity_type}#{self.entity_id}"

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise PermissionError("Audit log entries are append-only.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionError("Audit log entries cannot be deleted.")


class Notification(models.Model):
    """A pointer to something that happened, never a copy of its content.

    The text is rendered when read, from the target, and only if the
    recipient can still see the target (WP1). That way a notification cannot
    leak a title after access is lost.
    """

    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                  related_name="notifications")
    kind = models.CharField(max_length=64)
    target_type = models.CharField(max_length=32)
    target_id = models.PositiveBigIntegerField()
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return f"{self.recipient_id}: {self.kind}"


# --- WP3: background jobs, worker heartbeat, working calendar, alerts -------
class Job(models.Model):
    """A unit of deferred work. Rows are written inside the caller's
    transaction, so a rolled-back transaction leaves no job behind."""

    QUEUED, RUNNING, SUCCEEDED, FAILED, DEAD = (
        "queued", "running", "succeeded", "failed", "dead")
    STATUS_CHOICES = [(s, s) for s in (QUEUED, RUNNING, SUCCEEDED, FAILED, DEAD)]

    kind = models.CharField(max_length=64, db_index=True)
    payload = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=QUEUED)
    run_after = models.DateTimeField(db_index=True)
    attempts = models.PositiveIntegerField(default=0)
    max_attempts = models.PositiveIntegerField(default=5)
    last_error = models.TextField(blank=True)
    locked_by = models.CharField(max_length=128, blank=True)
    locked_at = models.DateTimeField(null=True, blank=True)
    idempotency_key = models.CharField(max_length=255, null=True, blank=True,
                                       unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("run_after", "id")
        indexes = [models.Index(fields=["status", "run_after"])]

    def __str__(self):
        return f"{self.kind}#{self.pk} {self.status}"


class PeriodicTaskRun(models.Model):
    """When each registered periodic task last ran (survives restarts)."""

    name = models.CharField(max_length=64, primary_key=True)
    last_run_at = models.DateTimeField()


class WorkerHeartbeat(models.Model):
    worker_id = models.CharField(max_length=128, primary_key=True)
    last_seen = models.DateTimeField()
    version = models.CharField(max_length=64, blank=True)


class Holiday(models.Model):
    date = models.DateField(unique=True)
    name = models.CharField(max_length=120)

    class Meta:
        ordering = ("date",)

    def __str__(self):
        return f"{self.date} {self.name}"


class AlertDelivery(models.Model):
    """One alert to one person on one channel. The unique key is the
    deduplication guarantee: a step can never alert the same person twice on
    the same channel, however often it is dispatched or retried."""

    PENDING, ACCEPTED, FAILED, UNKNOWN = "pending", "accepted", "failed", "unknown"
    STATUS_CHOICES = [(s, s) for s in (PENDING, ACCEPTED, FAILED, UNKNOWN)]

    alert_key = models.CharField(max_length=255)
    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                  related_name="alert_deliveries")
    channel = models.CharField(max_length=16)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=PENDING)
    attempts = models.PositiveIntegerField(default=0)
    provider_ref = models.CharField(max_length=255, blank=True)
    error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at", "-id")
        constraints = [models.UniqueConstraint(
            fields=["alert_key", "recipient", "channel"],
            name="one_delivery_per_alert_recipient_channel")]
