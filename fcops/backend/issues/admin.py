from django.contrib import admin

from .models import (Issue, IssueAttachment, IssueInvestigationNote,
                     IssueReassignmentLog, KnownIssue)


@admin.register(Issue)
class IssueAdmin(admin.ModelAdmin):
    list_display = ("key", "fc", "title", "severity", "status",
                    "assigned_department", "created_at")
    list_filter = ("status", "severity", "category", "discovered_stage")
    search_fields = ("key", "title", "symptoms", "root_cause", "resolution")


admin.site.register([KnownIssue, IssueInvestigationNote, IssueReassignmentLog,
                     IssueAttachment])
