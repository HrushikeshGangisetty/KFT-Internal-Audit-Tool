"""PLACEHOLDER deadline policies (IMPLEMENTATION_PLAN WP6), and history rows
for issues resolved or verified before WP7, so the new verification service
has a resolution to verify against."""
from django.db import migrations
from django.db.models import F

POLICIES = [
    # urgency, ack target, working hours?, follow-up interval, steps
    ("urgent", 30, False, 240, [
        {"after_minutes": 0, "to": "owner", "channels": "urgent"},
        {"after_minutes": 30, "to": "backup", "channels": "urgent"},
        {"after_minutes": 60, "to": "manager", "channels": "urgent"}]),
    ("normal", 240, True, 480, [
        {"after_minutes": 0, "to": "owner", "channels": "normal"},
        {"after_minutes": 240, "to": "owner", "channels": "normal"},
        {"after_minutes": 480, "to": "backup", "channels": "normal"},
        {"after_minutes": 720, "to": "manager", "channels": "normal"}]),
]


def forward(apps, schema_editor):
    DeadlinePolicy = apps.get_model("issues", "DeadlinePolicy")
    Issue = apps.get_model("issues", "Issue")
    Resolution = apps.get_model("issues", "Resolution")
    Verification = apps.get_model("issues", "Verification")
    for urgency, target, working, followup, steps in POLICIES:
        DeadlinePolicy.objects.get_or_create(urgency=urgency, defaults=dict(
            ack_target_minutes=target, ack_uses_working_hours=working,
            followup_interval_minutes=followup, escalation_steps=steps))
    Issue.objects.filter(queue__isnull=False, owner_since__isnull=True).update(
        owner_since=F("submitted_at"))
    for issue in Issue.objects.filter(resolved_by__isnull=False, resolved_at__isnull=False):
        resolution = Resolution.objects.create(
            issue=issue, resolved_by_id=issue.resolved_by_id, at=issue.resolved_at,
            change_summary=issue.resolution or "(recorded before WP7)",
            root_cause_status="confirmed" if issue.root_cause.strip() else "unknown")
        if issue.verified_by_id and issue.verified_at:
            Verification.objects.create(
                resolution=resolution, verifier_id=issue.verified_by_id,
                at=issue.verified_at, what_tested="(recorded before WP7)",
                result="pass")


def backward(apps, schema_editor):
    apps.get_model("issues", "Verification").objects.all().delete()
    apps.get_model("issues", "Resolution").objects.all().delete()
    apps.get_model("issues", "DeadlinePolicy").objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [("issues", "0006_deadlines_resolution_verification")]
    operations = [migrations.RunPython(forward, backward)]
