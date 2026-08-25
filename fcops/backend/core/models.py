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
    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                  related_name="notifications")
    verb = models.CharField(max_length=64)
    message = models.CharField(max_length=500)
    link = models.CharField(max_length=255, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return f"{self.recipient_id}: {self.verb}"
