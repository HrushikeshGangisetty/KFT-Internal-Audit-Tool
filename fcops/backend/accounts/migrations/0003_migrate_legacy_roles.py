"""WP1: derive memberships and capability grants from legacy role/department.

Mapping (kept in step with accounts.services.legacy_capabilities):
- every user with a department -> open membership in it, as ``head`` when
  role is DEPARTMENT_LEAD, otherwise ``member``; active from date_joined;
- MANAGER -> is_manager;
- ADMIN -> can_administer_accounts (no record access by itself);
- member of a SOFTWARE-kind department -> can_draft_release, and when
  DEPARTMENT_LEAD also is_software_head.

Reversal deletes only the rows this migration created (marked by note).
"""
from django.db import migrations

NOTE = "Migrated from legacy role/department (WP1)"


def forwards(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    TeamMembership = apps.get_model("accounts", "TeamMembership")
    CapabilityGrant = apps.get_model("accounts", "CapabilityGrant")
    for user in User.objects.select_related("department"):
        dept = user.department
        if dept is not None:
            TeamMembership.objects.create(
                user=user, department=dept, active_from=user.date_joined,
                role="head" if user.role == "DEPARTMENT_LEAD" else "member")
        caps = set()
        if user.role == "MANAGER":
            caps.add("is_manager")
        if user.role == "ADMIN":
            caps.add("can_administer_accounts")
        if dept is not None and dept.kind == "SOFTWARE":
            caps.add("can_draft_release")
            if user.role == "DEPARTMENT_LEAD":
                caps.add("is_software_head")
        for cap in sorted(caps):
            CapabilityGrant.objects.create(user=user, capability=cap, note=NOTE)


def backwards(apps, schema_editor):
    apps.get_model("accounts", "CapabilityGrant").objects.filter(note=NOTE).delete()
    # Memberships carry no marker; at this point in history every one was
    # created by forwards().
    apps.get_model("accounts", "TeamMembership").objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0002_access_scope"),
    ]

    operations = [migrations.RunPython(forwards, backwards)]
