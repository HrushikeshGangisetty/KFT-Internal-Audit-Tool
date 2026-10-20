from rest_framework import serializers

from access import policy
from access.mixins import ScopedPrimaryKeyRelatedField
from accounts.models import Department, User

from .models import DailyUpdate, Task
from .services import today


class TaskSerializer(serializers.ModelSerializer):
    accountable_user = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.filter(is_active=True), required=False)
    department = serializers.PrimaryKeyRelatedField(
        queryset=Department.objects.filter(is_active=True), required=False, allow_null=True)
    issue = ScopedPrimaryKeyRelatedField(policy.visible_issues, required=False, allow_null=True)
    fc = ScopedPrimaryKeyRelatedField(policy.visible_fcs, required=False, allow_null=True)
    accountable_user_name = serializers.CharField(source="accountable_user.full_name",
                                                  read_only=True)
    department_name = serializers.CharField(source="department.name", read_only=True,
                                            default="")
    collaborators = serializers.SerializerMethodField()
    is_overdue = serializers.SerializerMethodField()

    class Meta:
        model = Task
        fields = ("id", "title", "description", "accountable_user", "accountable_user_name",
                  "department", "department_name", "priority", "due_date", "status",
                  "issue", "fc", "collaborators", "is_overdue", "created_by",
                  "created_at", "updated_at")
        read_only_fields = ("created_by",)

    def get_collaborators(self, obj):
        return [{"id": c.user_id, "name": c.user.full_name or c.user.username}
                for c in obj.collaborators.all()]

    def get_is_overdue(self, obj):
        return bool(obj.due_date and obj.status in Task.OPEN_STATUSES
                    and obj.due_date < today())

    def to_representation(self, obj):
        # A readable task does not open its linked issue or FC (WP1).
        data = super().to_representation(obj)
        user = self.context["request"].user
        if obj.issue_id and not policy.can_view_issue(user, obj.issue_id):
            data["issue"] = None
        if obj.fc_id and not policy.can_view_fcs(user):
            data["fc"] = None
        return data


class DailyUpdateSerializer(serializers.ModelSerializer):
    task = ScopedPrimaryKeyRelatedField(policy.visible_tasks, required=False, allow_null=True)
    supersedes = ScopedPrimaryKeyRelatedField(policy.visible_daily_updates, required=False,
                                              allow_null=True)
    author_name = serializers.CharField(source="author.full_name", read_only=True)
    task_title = serializers.SerializerMethodField()
    is_current = serializers.SerializerMethodField()

    class Meta:
        model = DailyUpdate
        fields = ("id", "task", "task_title", "author", "author_name", "date", "progress",
                  "next_step", "blockers", "supersedes", "is_current", "created_at")
        read_only_fields = ("author", "date")

    def to_representation(self, obj):
        # Your own update on a task you no longer see keeps its text, not the task.
        data = super().to_representation(obj)
        if obj.task_id and not policy.visible_tasks(
                self.context["request"].user).filter(pk=obj.task_id).exists():
            data["task"] = None
        return data

    def get_task_title(self, obj):
        user = self.context["request"].user
        if obj.task_id and policy.visible_tasks(user).filter(pk=obj.task_id).exists():
            return obj.task.title
        return ""

    def get_is_current(self, obj):
        return not hasattr(obj, "superseded_by")
