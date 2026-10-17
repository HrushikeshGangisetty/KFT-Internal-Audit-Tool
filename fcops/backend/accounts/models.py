"""Users, departments and roles.

Departments are first-class configurable rows (PRD §6) rather than an enum, so
the org chart can change without a migration. Roles are a fixed enum because
they drive server-side permission checks (PRD §18).
"""
from django.contrib.auth.models import AbstractUser
from django.db import models


class Department(models.Model):
    """A configurable organisational unit.

    ``kind`` groups departments coarsely so workflow rules (e.g. "which
    department owns the Firmware stage") can be expressed without hardcoding
    specific department names.
    """

    KIND_HARDWARE = "HARDWARE"
    KIND_FIRMWARE = "FIRMWARE"
    KIND_SOFTWARE = "SOFTWARE"
    KIND_MECHANICAL = "MECHANICAL"
    KIND_TESTING = "TESTING"
    KIND_QUALITY = "QUALITY"
    KIND_MANAGEMENT = "MANAGEMENT"
    KIND_SERVICE = "SERVICE"
    KIND_OTHER = "OTHER"
    KIND_CHOICES = [
        (KIND_HARDWARE, "Hardware"),
        (KIND_FIRMWARE, "Firmware"),
        (KIND_SOFTWARE, "Software"),
        (KIND_MECHANICAL, "Mechanical"),
        (KIND_TESTING, "Testing"),
        (KIND_QUALITY, "Quality"),
        (KIND_MANAGEMENT, "Management"),
        (KIND_SERVICE, "Service"),
        (KIND_OTHER, "Other"),
    ]

    name = models.CharField(max_length=120, unique=True)
    code = models.SlugField(max_length=48, unique=True)
    kind = models.CharField(max_length=24, choices=KIND_CHOICES, default=KIND_OTHER)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("name",)

    def __str__(self):
        return self.name


class Role(models.TextChoices):
    TECHNICIAN = "TECHNICIAN", "Technician"
    DEPARTMENT_LEAD = "DEPARTMENT_LEAD", "Department Lead"
    TEST_ENGINEER = "TEST_ENGINEER", "Test Engineer"
    MANAGER = "MANAGER", "Manager"
    ADMIN = "ADMIN", "Admin"


class User(AbstractUser):
    department = models.ForeignKey(Department, null=True, blank=True,
                                   on_delete=models.PROTECT, related_name="members")
    role = models.CharField(max_length=32, choices=Role.choices, default=Role.TECHNICIAN)
    full_name = models.CharField(max_length=150, blank=True)
    is_active_employee = models.BooleanField(default=True)

    def __str__(self):
        return self.full_name or self.username

    # --- role helpers used by permission classes -------------------------
    @property
    def is_admin_role(self):
        return self.role == Role.ADMIN or self.is_superuser

    @property
    def is_manager_role(self):
        return self.role == Role.MANAGER or self.is_admin_role

    @property
    def is_lead_role(self):
        return self.role == Role.DEPARTMENT_LEAD or self.is_manager_role

    @property
    def is_test_engineer(self):
        return self.role == Role.TEST_ENGINEER or self.is_manager_role

    def in_department(self, department):
        if department is None:
            return False
        dept_id = getattr(department, "pk", department)
        return self.department_id == dept_id

    def in_department_kind(self, kind):
        """True when this user belongs to a department of the given kind.

        Departments are configurable rows, so capability is derived from the
        department's ``kind`` rather than from its name — a second Firmware
        team can be created without touching permission code.
        """
        return bool(self.department_id and self.department.kind == kind)

    @property
    def can_push_software_update(self):
        return self.is_admin_role or self.in_department_kind(Department.KIND_SOFTWARE)

    @property
    def can_manage_firmware(self):
        return self.is_admin_role or self.in_department_kind(Department.KIND_FIRMWARE)

    @property
    def can_approve_software_update(self):
        """Sign-off needs authority, not just membership: a department lead,
        a manager or an admin."""
        return self.is_lead_role


class TeamMembership(models.Model):
    """Which departments a user belongs to, and in what role (WP1).

    This, not ``User.department``, is what record access is scoped on. A user
    may belong to several departments. Leaving is recorded by setting
    ``active_to``; rows are never deleted, so history survives.
    """

    ROLE_MEMBER = "member"
    ROLE_HEAD = "head"
    ROLE_BACKUP_HEAD = "backup_head"
    ROLE_CHOICES = [(ROLE_MEMBER, "Member"), (ROLE_HEAD, "Head"),
                    (ROLE_BACKUP_HEAD, "Backup head")]
    HEAD_ROLES = (ROLE_HEAD, ROLE_BACKUP_HEAD)

    user = models.ForeignKey(User, on_delete=models.PROTECT,
                             related_name="memberships")
    department = models.ForeignKey(Department, on_delete=models.PROTECT,
                                   related_name="memberships")
    role = models.CharField(max_length=16, choices=ROLE_CHOICES, default=ROLE_MEMBER)
    active_from = models.DateTimeField()
    active_to = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(User, null=True, blank=True,
                                   on_delete=models.SET_NULL,
                                   related_name="+")

    class Meta:
        ordering = ("user_id", "-active_from", "id")
        constraints = [
            models.UniqueConstraint(fields=["user", "department"],
                                    condition=models.Q(active_to__isnull=True),
                                    name="one_open_membership_per_department"),
        ]

    def __str__(self):
        return f"{self.user} · {self.department} ({self.role})"


class Capability(models.TextChoices):
    """What a user may do, kept separate from which records they may see."""
    IS_MANAGER = "is_manager", "Manager"
    IS_SOFTWARE_HEAD = "is_software_head", "Software head"
    CAN_DRAFT_RELEASE = "can_draft_release", "Can draft releases"
    CAN_SEND_ANNOUNCEMENTS = "can_send_announcements", "Can send announcements"
    CAN_VIEW_CUSTOMER_CONTACTS = "can_view_customer_contacts", "Can view customer contacts"
    CAN_ADMINISTER_ACCOUNTS = "can_administer_accounts", "Can administer accounts"


class CapabilityGrant(models.Model):
    """An audited grant of one capability. Revoking sets ``revoked_at``."""

    user = models.ForeignKey(User, on_delete=models.PROTECT,
                             related_name="capability_grants")
    capability = models.CharField(max_length=48, choices=Capability.choices)
    granted_by = models.ForeignKey(User, null=True, blank=True,
                                   on_delete=models.SET_NULL, related_name="+")
    granted_at = models.DateTimeField(auto_now_add=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    revoked_by = models.ForeignKey(User, null=True, blank=True,
                                   on_delete=models.SET_NULL, related_name="+")
    note = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ("user_id", "capability", "-granted_at")
        constraints = [
            models.UniqueConstraint(fields=["user", "capability"],
                                    condition=models.Q(revoked_at__isnull=True),
                                    name="one_active_grant_per_capability"),
        ]

    def __str__(self):
        return f"{self.user} · {self.capability}"
