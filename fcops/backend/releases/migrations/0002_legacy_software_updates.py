"""Copy fc.SoftwareUpdate rows into legacy releases (WP11). The old table is
left in place, unchanged, as the source record."""
from django.db import migrations

from releases.legacy import convert_software_updates


def forwards(apps, schema_editor):
    convert_software_updates(apps.get_model("fc", "SoftwareUpdate"),
                             apps.get_model("releases", "Release"),
                             apps.get_model("releases", "ReleaseRevision"),
                             apps.get_model("accounts", "User"))


def backwards(apps, schema_editor):
    Release = apps.get_model("releases", "Release")
    apps.get_model("releases", "ReleaseRevision").objects.filter(
        release__legacy=True).delete()
    Release.objects.filter(legacy=True).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("releases", "0001_initial"),
        ("fc", "0007_backfill_parameter_file_hashes"),
    ]

    operations = [migrations.RunPython(forwards, backwards)]
