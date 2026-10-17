"""WP1: notifications store a pointer to their target, not copied text.

Existing rows are converted from their ``/issues/<id>`` link. Rows whose link
cannot be parsed point at nothing renderable and are deleted (they could only
ever have rendered stale copied text). Reversal restores ``verb`` and ``link``
from the pointer; the copied ``message`` text is not recoverable and comes
back empty.
"""
import re

from django.db import migrations, models

ISSUE_LINK = re.compile(r"^/issues/(\d+)/?$")


def forwards(apps, schema_editor):
    Notification = apps.get_model("core", "Notification")
    for n in Notification.objects.all():
        match = ISSUE_LINK.match(n.link or "")
        if not match:
            n.delete()
            continue
        n.target_type = "issue"
        n.target_id = int(match.group(1))
        n.save(update_fields=["target_type", "target_id"])


def backwards(apps, schema_editor):
    Notification = apps.get_model("core", "Notification")
    for n in Notification.objects.all():
        n.link = f"/issues/{n.target_id}" if n.target_type == "issue" else ""
        n.save(update_fields=["link"])


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0003_audit_append_only"),
    ]

    operations = [
        migrations.RenameField("notification", "verb", "kind"),
        migrations.AddField("notification", "target_type",
                            models.CharField(default="", max_length=32),
                            preserve_default=False),
        migrations.AddField("notification", "target_id",
                            models.PositiveBigIntegerField(default=0),
                            preserve_default=False),
        migrations.AlterField("notification", "message",
                              models.CharField(blank=True, default="", max_length=500)),
        migrations.RunPython(forwards, backwards),
        migrations.RemoveField("notification", "message"),
        migrations.RemoveField("notification", "link"),
    ]
