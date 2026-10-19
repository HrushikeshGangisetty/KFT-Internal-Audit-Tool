from django.apps import AppConfig


class IssuesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "issues"

    def ready(self):
        from . import deadlines  # noqa: F401 - registers the periodic check
