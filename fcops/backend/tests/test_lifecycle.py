"""End-to-end lifecycle: registration → stage progression → failure → issue →
investigation → rework → re-run → resolution → verification → approval."""
from django.test import TestCase

from accounts.models import Department, Role
from core.exceptions import WorkflowError
from core.models import AuditLogEntry
from fc import services as fcsvc
from fc.lifecycle import Stage
from fc.models import FCStatus, ReworkRecord, StageStatus
from issues import services as issvc
from issues.models import Category, IssueStatus, Severity

from .factories import make_department, make_fc_model, make_user


class LifecycleTests(TestCase):
    def setUp(self):
        self.hw = make_department("assembly", Department.KIND_HARDWARE)
        self.fwd = make_department("firmware", Department.KIND_FIRMWARE)
        self.testing = make_department("testing", Department.KIND_TESTING)
        self.mgmt = make_department("management", Department.KIND_MANAGEMENT)
        self.tech = make_user("tech", Role.TECHNICIAN, self.hw)
        self.fw_eng = make_user("fweng", Role.TECHNICIAN, self.fwd)
        self.fw_lead = make_user("fwlead", Role.DEPARTMENT_LEAD, self.fwd)
        self.tester = make_user("tester", Role.TEST_ENGINEER, self.testing)
        self.tester2 = make_user("tester2", Role.TEST_ENGINEER, self.testing)
        self.manager = make_user("manager", Role.MANAGER, self.mgmt)
        self.model = make_fc_model()

    def _advance(self, fc, upto, actor=None):
        actor = actor or self.tech
        while fc.current_stage != upto:
            fcsvc.start_stage(fc, actor=actor)
            fcsvc.complete_stage(fc, passed=True, actor=actor)
            fc.refresh_from_db()

    def test_serial_generation_and_registration(self):
        fc = fcsvc.register_fc(fc_model=self.model, actor=self.tech)
        self.assertRegex(fc.serial, r"^FC-\d{4}-\d{5}$")
        self.assertEqual(fc.current_stage, Stage.FABRICATION)
        self.assertEqual(fc.status, FCStatus.IN_PRODUCTION)
        fc2 = fcsvc.register_fc(fc_model=self.model, actor=self.tech)
        self.assertNotEqual(fc.serial, fc2.serial)
        self.assertTrue(AuditLogEntry.objects.filter(
            entity_type="FlightController", entity_id=str(fc.pk),
            action=AuditLogEntry.ACTION_CREATE).exists())

    def test_cannot_complete_a_stage_that_is_not_current(self):
        fc = fcsvc.register_fc(fc_model=self.model, actor=self.tech)
        with self.assertRaises(WorkflowError):
            fcsvc.complete_stage(fc, Stage.GROUND_TESTING, passed=True,
                                 actor=self.tech)

    def test_full_happy_path_to_approval(self):
        fc = fcsvc.register_fc(fc_model=self.model, actor=self.tech)
        self._advance(fc, Stage.MANAGER_APPROVAL)
        fc.refresh_from_db()
        self.assertEqual(fc.status, FCStatus.PENDING_APPROVAL)
        blockers, warnings = fcsvc.approval_blockers(fc)
        self.assertEqual(blockers, [])
        fc = fcsvc.manager_approve(fc, actor=self.manager, approve=True,
                                   note="Looks good")
        self.assertEqual(fc.status, FCStatus.APPROVED)

    def test_technician_cannot_approve_via_service_blockers(self):
        """Approval is gated by role in the API layer; the service still refuses
        to approve an FC that has not reached the approval stage."""
        fc = fcsvc.register_fc(fc_model=self.model, actor=self.tech)
        with self.assertRaises(WorkflowError):
            fcsvc.manager_approve(fc, actor=self.manager, approve=True)

    def test_failure_issue_rework_rerun_resolution_verification(self):
        fc = fcsvc.register_fc(fc_model=self.model, actor=self.tech)
        self._advance(fc, Stage.GROUND_TESTING)
        fcsvc.start_stage(fc, actor=self.tester)
        record = fcsvc.complete_stage(fc, passed=False, actor=self.tester,
                                      notes="No GPS fix")
        fc.refresh_from_db()
        self.assertEqual(record.status, StageStatus.FAILED)

        issue = issvc.create_issue(
            fc=fc, title="GPS not detected in ground test",
            symptoms="No satellites, no fix, serial silent",
            actor=self.tester, category=Category.HARDWARE,
            severity=Severity.BLOCKER, assigned_department=self.fwd)
        fc.refresh_from_db()
        self.assertEqual(fc.status, FCStatus.BLOCKED)
        self.assertEqual(issue.discovering_department, self.testing)
        self.assertEqual(issue.assigned_department, self.fwd)

        # Investigation reveals a hardware root cause → reassign with a reason.
        issvc.add_note(issue, author=self.fw_eng,
                       note="Firmware sees no data on the GPS UART.")
        issue.refresh_from_db()
        self.assertEqual(issue.status, IssueStatus.INVESTIGATING)
        issvc.reassign(issue, actor=self.fw_lead, to_department=self.hw,
                       reason="UART is silent at the connector; hardware fault.")
        issue.refresh_from_db()
        self.assertEqual(issue.assigned_department, self.hw)
        self.assertEqual(issue.reassignments.count(), 2)  # initial + reassign
        self.assertIn("hardware fault", issue.reassignments.last().reason)

        # Discovery data is preserved and distinct from root cause.
        self.assertEqual(issue.discovered_stage, Stage.GROUND_TESTING)
        self.assertEqual(issue.discovering_department, self.testing)

        # Rework routes the FC back to an allowed earlier stage.
        rework = fcsvc.create_rework(stage_record=record,
                                     description="Reflow GPS connector",
                                     return_to_stage=Stage.MECHANICAL_ASSEMBLY,
                                     originating_issue=issue, actor=self.tech)
        fc.refresh_from_db()
        self.assertEqual(fc.current_stage, Stage.MECHANICAL_ASSEMBLY)
        fcsvc.complete_rework(rework, outcome=ReworkRecord.OUTCOME_COMPLETED,
                              actor=self.tech)

        # The failed attempt is preserved, not overwritten.
        self.assertEqual(
            fc.stage_records.filter(stage=Stage.GROUND_TESTING,
                                    status=StageStatus.FAILED).count(), 1)

        issvc.change_status(issue, IssueStatus.RESOLVED, actor=self.tech,
                            root_cause="Cold solder joint on GPS connector pin 3",
                            resolution="Reflowed joint, verified continuity",
                            root_cause_department=self.hw)
        issue.refresh_from_db()
        self.assertEqual(issue.root_cause_department, self.hw)

        # Same person cannot verify their own fix.
        with self.assertRaises(WorkflowError):
            issvc.change_status(issue, IssueStatus.VERIFIED, actor=self.tech)
        issvc.change_status(issue, IssueStatus.VERIFIED, actor=self.tester2,
                            note="GPS fix in 40 s")
        issvc.change_status(issue, IssueStatus.CLOSED, actor=self.tester2)
        issue.refresh_from_db()
        self.assertEqual(issue.status, IssueStatus.CLOSED)

        # Stage must be explicitly re-run and re-passed; it does not auto-pass.
        fc.refresh_from_db()
        self._advance(fc, Stage.GROUND_TESTING, actor=self.tester)
        fcsvc.start_stage(fc, actor=self.tester)
        rerun = fcsvc.complete_stage(fc, passed=True, actor=self.tester)
        self.assertEqual(rerun.attempt, 2)
        fc.refresh_from_db()
        self._advance(fc, Stage.MANAGER_APPROVAL, actor=self.tester)
        fc = fcsvc.manager_approve(fc, actor=self.manager, approve=True)
        self.assertEqual(fc.status, FCStatus.APPROVED)

    def test_rework_target_must_be_allowed(self):
        fc = fcsvc.register_fc(fc_model=self.model, actor=self.tech)
        self._advance(fc, Stage.QC)
        fcsvc.start_stage(fc, actor=self.tech)
        record = fcsvc.complete_stage(fc, passed=False, actor=self.tech)
        with self.assertRaises(WorkflowError):
            fcsvc.create_rework(stage_record=record, description="x",
                                return_to_stage=Stage.GROUND_TESTING,
                                actor=self.tech)
        rework = fcsvc.create_rework(stage_record=record, description="ok",
                                     return_to_stage=Stage.MANUAL_ASSEMBLY,
                                     actor=self.tech)
        self.assertIsNotNone(rework.pk)

    def test_cannot_rework_a_passed_stage(self):
        fc = fcsvc.register_fc(fc_model=self.model, actor=self.tech)
        fcsvc.start_stage(fc, actor=self.tech)
        record = fcsvc.complete_stage(fc, passed=True, actor=self.tech)
        with self.assertRaises(WorkflowError):
            fcsvc.create_rework(stage_record=record, description="x",
                                return_to_stage=Stage.FABRICATION, actor=self.tech)

    def test_cannot_pass_stage_with_open_issue(self):
        fc = fcsvc.register_fc(fc_model=self.model, actor=self.tech)
        self._advance(fc, Stage.QC)
        fcsvc.start_stage(fc, actor=self.tech)
        fcsvc.complete_stage(fc, passed=False, actor=self.tech)
        issvc.create_issue(fc=fc, title="short", symptoms="short circuit",
                           actor=self.tech, assigned_department=self.hw)
        fc.refresh_from_db()
        with self.assertRaises(WorkflowError):
            fcsvc.complete_stage(fc, passed=True, actor=self.tech)

    def test_blocking_message_names_the_issue_and_its_actual_state(self):
        """A resolved-but-unverified issue still blocks the stage. The message
        must say so, rather than calling the issue 'unresolved' — which
        contradicts what the timeline shows the user."""
        fc = fcsvc.register_fc(fc_model=self.model, actor=self.tech)
        self._advance(fc, Stage.QC)
        fcsvc.start_stage(fc, actor=self.tech)
        fcsvc.complete_stage(fc, passed=False, actor=self.tech)
        issue = issvc.create_issue(fc=fc, title="solder bridge",
                                   symptoms="short between pins",
                                   actor=self.tech, assigned_department=self.hw)
        fc.refresh_from_db()

        # While the issue is open.
        reasons = fcsvc.stage_blockers(fc, Stage.QC)
        self.assertEqual(len(reasons), 1)
        self.assertIn(issue.key, reasons[0])
        self.assertIn("open", reasons[0].lower())

        # After it is resolved but before anyone has verified it.
        issvc.change_status(issue, IssueStatus.RESOLVED, actor=self.tech,
                            root_cause="bridge from soldering",
                            resolution="reflowed")
        fc.refresh_from_db()
        reasons = fcsvc.stage_blockers(fc, Stage.QC)
        self.assertEqual(len(reasons), 1)
        self.assertIn(issue.key, reasons[0])
        self.assertIn("resolved but not yet verified", reasons[0])
        self.assertNotIn("unresolved", reasons[0])
        self.assertIn("someone else must verify", reasons[0])

        with self.assertRaises(WorkflowError) as ctx:
            fcsvc.complete_stage(fc, passed=True, actor=self.tech)
        self.assertIn("resolved but not yet verified", str(ctx.exception))

        # Once verified by a second person the stage is free to pass.
        issvc.change_status(issue, IssueStatus.VERIFIED, actor=self.tester)
        fc.refresh_from_db()
        self.assertEqual(fcsvc.stage_blockers(fc, Stage.QC), [])
        record = fcsvc.complete_stage(fc, passed=True, actor=self.tech)
        self.assertEqual(record.status, StageStatus.PASSED)

    def test_approval_blocked_by_open_issue(self):
        fc = fcsvc.register_fc(fc_model=self.model, actor=self.tech)
        self._advance(fc, Stage.FINAL_VALIDATION)
        fcsvc.start_stage(fc, actor=self.tester)
        fcsvc.complete_stage(fc, passed=False, actor=self.tester)
        issue = issvc.create_issue(fc=fc, title="param mismatch",
                                   symptoms="parameter profile does not match spec",
                                   actor=self.tester, severity=Severity.MAJOR,
                                   assigned_department=self.fwd)
        fc.refresh_from_db()
        blockers, _ = fcsvc.approval_blockers(fc)
        self.assertTrue(any("unresolved" in b for b in blockers))
        with self.assertRaises(WorkflowError):
            fcsvc.manager_approve(fc, actor=self.manager, approve=True)

    def test_override_transition_requires_reason_and_is_audited(self):
        fc = fcsvc.register_fc(fc_model=self.model, actor=self.tech)
        with self.assertRaises(WorkflowError):
            fcsvc.override_transition(fc, Stage.QC, actor=self.manager, reason="")
        fcsvc.override_transition(fc, Stage.QC, actor=self.manager,
                                  reason="Pilot line exception")
        fc.refresh_from_db()
        self.assertEqual(fc.current_stage, Stage.QC)
        self.assertTrue(fc.events.filter(kind="STAGE_TRANSITION",
                                         detail__icontains="OVERRIDE").exists())

    def test_timeline_is_chronological_and_complete(self):
        fc = fcsvc.register_fc(fc_model=self.model, actor=self.tech)
        self._advance(fc, Stage.QC)
        kinds = list(fc.events.values_list("kind", flat=True))
        self.assertEqual(kinds[0], "FC_REGISTERED")
        self.assertIn("STAGE_PASSED", kinds)
        self.assertIn("STAGE_TRANSITION", kinds)
