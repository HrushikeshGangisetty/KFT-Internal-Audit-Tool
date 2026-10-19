"""Give pre-WP8 parameter files a SHA-256 and size from their stored text.
A legacy duplicate keeps a NULL hash rather than failing the migration."""
import hashlib

from django.db import migrations


def forward(apps, schema_editor):
    ParameterFile = apps.get_model("fc", "ParameterFile")
    seen = set()
    for pf in ParameterFile.objects.filter(sha256__isnull=True).order_by("pk"):
        data = pf.raw_text.encode("utf-8")
        digest = hashlib.sha256(data).hexdigest()
        pf.size = len(data)
        pf.parser_version = pf.parser_version or "legacy"
        if digest not in seen and not ParameterFile.objects.filter(sha256=digest).exists():
            pf.sha256 = digest
            seen.add(digest)
        pf.save(update_fields=["sha256", "size", "parser_version"])


class Migration(migrations.Migration):
    dependencies = [("fc", "0006_config_evidence")]
    operations = [migrations.RunPython(forward, migrations.RunPython.noop)]
