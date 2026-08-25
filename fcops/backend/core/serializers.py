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


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ("id", "verb", "message", "link", "read_at", "created_at")
