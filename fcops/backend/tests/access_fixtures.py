"""The access-matrix world (WP1), reused by later work packages.

Actors (IMPLEMENTATION_PLAN.md WP1):
  sw_member, sw_head (also is_software_head), asm_member, asm_head, fw_member,
  svc_member (reporter), manager (no department), admin (account admin, no
  department, not a head), verifier (Assembly member assigned as verifier on
  one Software issue), ex_member (Software membership closed yesterday).

Issues (all share the words "intermittent dropout" so one search hits all):
  sw_issue      Software, reported by svc_member, has an attachment
  asm_issue     Assembly, reported by asm_member
  sw_verify     Software, reported by sw_member, verifier assigned
"""
from datetime import timedelta

from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from accounts.models import Department, Role, TeamMembership
from accounts.services import close_membership
from fc import services as fcsvc
from issues import services as issvc
from issues.models import IssueAttachment, IssueParticipant

from .factories import make_department, make_fc_model, make_user


class AccessWorld:
    ACTORS = ("sw_member", "sw_head", "asm_member", "asm_head", "fw_member",
              "svc_member", "manager", "admin", "verifier", "ex_member")

    def __init__(self):
        self.software = make_department("software", Department.KIND_SOFTWARE)
        self.assembly = make_department("assembly", Department.KIND_HARDWARE)
        self.firmware = make_department("firmware", Department.KIND_FIRMWARE)
        self.service = make_department("service", Department.KIND_SERVICE)

        self.sw_member = make_user("sw_member", Role.TECHNICIAN, self.software)
        self.sw_head = make_user("sw_head", Role.DEPARTMENT_LEAD, self.software)
        self.asm_member = make_user("asm_member", Role.TECHNICIAN, self.assembly)
        self.asm_head = make_user("asm_head", Role.DEPARTMENT_LEAD, self.assembly)
        self.fw_member = make_user("fw_member", Role.TECHNICIAN, self.firmware)
        self.svc_member = make_user("svc_member", Role.TECHNICIAN, self.service)
        self.manager = make_user("manager", Role.MANAGER, None)
        self.admin = make_user("admin", Role.ADMIN, None)
        self.verifier = make_user("verifier", Role.TECHNICIAN, self.assembly)
        self.ex_member = make_user("ex_member", Role.TECHNICIAN, self.software)
        membership = TeamMembership.objects.get(user=self.ex_member)
        membership.active_from = timezone.now() - timedelta(days=30)
        membership.save(update_fields=["active_from"])
        close_membership(membership, actor=self.admin,
                         at=timezone.now() - timedelta(days=1))

        self.fc = fcsvc.register_fc(fc_model=make_fc_model(), actor=self.asm_head)
        self.sw_issue = issvc.create_issue(
            fc=self.fc, title="GCS telemetry stalls", actor=self.svc_member,
            symptoms="intermittent dropout of the telemetry link",
            assigned_department=self.software)
        self.asm_issue = issvc.create_issue(
            fc=self.fc, title="Loose battery connector", actor=self.asm_member,
            symptoms="intermittent dropout of power under vibration",
            assigned_department=self.assembly)
        self.sw_verify = issvc.create_issue(
            fc=self.fc, title="Configurator write fails", actor=self.sw_member,
            symptoms="intermittent dropout while writing parameters",
            assigned_department=self.software)
        issvc.add_participant(self.sw_verify, user=self.verifier,
                              role=IssueParticipant.ROLE_VERIFIER, actor=self.sw_head)
        self.attachment = IssueAttachment.objects.create(
            issue=self.sw_issue, uploaded_by=self.svc_member,
            original_name="log.txt", content_type="text/plain", size=5,
            file=SimpleUploadedFile("log.txt", b"hello"))

    def actor(self, name):
        return getattr(self, name)

    def expected_issues(self, name):
        """Which issues each actor may read — the matrix under test."""
        everything = {self.sw_issue, self.asm_issue, self.sw_verify}
        return {
            "sw_member": {self.sw_issue, self.sw_verify},
            "sw_head": everything,
            "asm_member": {self.asm_issue},
            "asm_head": everything,
            "fw_member": set(),
            "svc_member": {self.sw_issue},
            "manager": everything,
            "admin": set(),
            # An Assembly member, so the Assembly issue too; of the Software
            # issues only the one they verify.
            "verifier": {self.asm_issue, self.sw_verify},
            "ex_member": set(),
        }[name]
