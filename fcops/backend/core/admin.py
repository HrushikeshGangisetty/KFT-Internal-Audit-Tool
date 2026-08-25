from django.contrib import admin

from .models import AuditLogEntry, Notification


@admin.register(AuditLogEntry)
class AuditLogEntryAdmin(admin.ModelAdmin):
    list_display = ("created_at", "action", "entity_type", "entity_label",
                    "actor_label")
    list_filter = ("action", "entity_type")
    search_fields = ("entity_label", "actor_label", "note")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


admin.site.register(Notification)
