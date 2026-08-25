"""Enforce append-only-ness of the audit log at the database level, so that a
compromised or careless application path cannot rewrite history (PRD §30)."""
from django.db import migrations

FORWARD = """
CREATE OR REPLACE FUNCTION core_auditlog_append_only() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'core_auditlogentry is append-only (attempted %)', TG_OP;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS core_auditlog_no_update ON core_auditlogentry;
CREATE TRIGGER core_auditlog_no_update
    BEFORE UPDATE OR DELETE ON core_auditlogentry
    FOR EACH ROW EXECUTE FUNCTION core_auditlog_append_only();
"""

REVERSE = """
DROP TRIGGER IF EXISTS core_auditlog_no_update ON core_auditlogentry;
DROP FUNCTION IF EXISTS core_auditlog_append_only();
"""


class Migration(migrations.Migration):
    dependencies = [("core", "0002_initial")]
    operations = [migrations.RunSQL(FORWARD, REVERSE)]
