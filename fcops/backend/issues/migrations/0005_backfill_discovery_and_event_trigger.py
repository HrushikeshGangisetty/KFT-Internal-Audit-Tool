"""Backfill WP4 discovery facts on existing issues, keep their stage-blocking
behaviour, and make the issue event log append-only in the database."""
from django.db import migrations
from django.db.models import F

TRIGGER = """
CREATE OR REPLACE FUNCTION issues_issueevent_append_only() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'issues_issueevent is append-only (attempted %)', TG_OP;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS issues_issueevent_no_update ON issues_issueevent;
CREATE TRIGGER issues_issueevent_no_update
    BEFORE UPDATE OR DELETE ON issues_issueevent
    FOR EACH ROW EXECUTE FUNCTION issues_issueevent_append_only();
"""

DROP_TRIGGER = """
DROP TRIGGER IF EXISTS issues_issueevent_no_update ON issues_issueevent;
DROP FUNCTION IF EXISTS issues_issueevent_append_only();
"""


def backfill(apps, schema_editor):
    Issue = apps.get_model("issues", "Issue")
    # Every pre-WP4 issue is FC-anchored and blocked its stage; keep that.
    Issue.objects.filter(fc__isnull=False).update(blocks_stage=True)
    Issue.objects.update(reporter=F("discovered_by"), submitted_at=F("created_at"))


class Migration(migrations.Migration):
    dependencies = [("issues", "0004_reports_routing_handoffs")]
    operations = [
        # Reversing leaves the backfilled columns to be dropped by 0004.
        migrations.RunPython(backfill, migrations.RunPython.noop),
        migrations.RunSQL(TRIGGER, DROP_TRIGGER),
    ]
