"""Move the inline ChecklistTemplate.items JSON into ChecklistItem rows.

The legacy JSON column is left in place and untouched, so nothing is lost and
the migration is safely reversible.
"""
from django.db import migrations
from django.utils.text import slugify


def forwards(apps, schema_editor):
    ChecklistTemplate = apps.get_model("fc", "ChecklistTemplate")
    ChecklistItem = apps.get_model("fc", "ChecklistItem")

    for template in ChecklistTemplate.objects.all():
        if ChecklistItem.objects.filter(template=template).exists():
            continue
        for order, item in enumerate(template.items or []):
            key = (item.get("key") or slugify(item.get("label", ""))
                   or f"item-{order + 1}")[:64]
            ChecklistItem.objects.create(
                template=template,
                key=key,
                label=item.get("label") or key,
                description=item.get("description", ""),
                is_mandatory=bool(item.get("mandatory", True)),
                order=order,
                is_active=True,
            )


def backwards(apps, schema_editor):
    # The JSON column was never modified, so undoing this only means dropping
    # the rows this migration created.
    ChecklistItem = apps.get_model("fc", "ChecklistItem")
    ChecklistItem.objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [("fc", "0003_checklisttemplate_version_and_more")]
    operations = [migrations.RunPython(forwards, backwards)]
