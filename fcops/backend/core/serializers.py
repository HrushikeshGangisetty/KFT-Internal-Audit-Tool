from rest_framework import serializers

from .models import AuditLogEntry, Notification


class AuditLogEntrySerializer(serializers.ModelSerializer):
    actor_name = serializers.SerializerMethodField()
    fc_serial = serializers.CharField(source="fc.serial", read_only=True, default="")

    class Meta:
        model = AuditLogEntry
        fields = ("id", "entity_type", "entity_id", "entity_label", "actor",
                  "actor_name", "action", "before", "after", "note", "fc",
                  "fc_serial", "created_at")

    def get_actor_name(self, obj):
        return (obj.actor.full_name if obj.actor and obj.actor.full_name
                else obj.actor_label)


NO_ACCESS = "You no longer have access to this item"


class NotificationSerializer(serializers.ModelSerializer):
    """Renders the text now, from the target, for this recipient only."""

    message = serializers.SerializerMethodField()
    link = serializers.SerializerMethodField()

    class Meta:
        model = Notification
        fields = ("id", "kind", "target_type", "target_id", "message", "link",
                  "read_at", "created_at")

    def _target(self, obj):
        if obj.target_type != "issue":
            return None
        if "_issues" not in self.context:
            from access.policy import visible_issues
            self.context["_issues"] = visible_issues(obj.recipient).select_related("fc")
        # ponytail: one query per rendered notification; batch per page if
        # the list grows beyond a few dozen per request.
        return self.context["_issues"].filter(pk=obj.target_id).first()

    def to_representation(self, obj):
        self._issue = self._target(obj)
        return super().to_representation(obj)

    def get_message(self, obj):
        issue = self._issue
        if issue is None:
            return NO_ACCESS
        if obj.kind == "HIGH_SEVERITY_ISSUE":
            return (f"{issue.get_severity_display()} issue {issue.key} opened on "
                    f"{issue.fc.serial}")
        if obj.kind == "ISSUE_STATUS":
            return f"{issue.key} is now {issue.get_status_display()}"
        return f"{issue.key}: {issue.title}"

    def get_link(self, obj):
        return f"/issues/{self._issue.pk}" if self._issue is not None else ""
