from django.apps import AppConfig


class ReleasesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "releases"

    def ready(self):
        from . import services  # noqa: F401 - registers the delivery job handler
