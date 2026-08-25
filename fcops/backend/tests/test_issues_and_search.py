"""Issue workflow, knowledge search, similar-issue detection and audit log."""
from django.test import TestCase

from accounts.models import Department, Role
from core.exceptions import WorkflowError
from core.models import AuditLogEntry
from fc import services as fcsvc
from fc.lifecycle import Stage
from fc.models import FirmwareRecord
from issues import services as issvc
from issues.models import Category, Issue, IssueStatus, KnownIssue, Severity
from issues.search import find_similar, search_issues

from .factories import make_department, make_fc_model, make_user


class IssueWorkflowTests(TestCase):
    def setUp(self):
        self.hw = make_department("assembly", Department.KIND_HARDWARE)
        self.fwd = make_department("firmware", Department.KIND_FIRMWARE)
        self.testing = make_department("testing", Department.KIND_TESTING)
        self.tech = make_user("tech", Role.TECHNICIAN, self.hw)
        self.lead = make_user("lead", Role.DEPARTMENT_LEAD, self.fwd)
        self.tester = make_user("tester", Role.TEST_ENGINEER, self.testing)
        self.tester2 = make_user("tester2", Role.TEST_ENGINEER, self.testing)
        self.manager = make_user("mgr", Role.MANAGER, self.testing)
        self.model = make_fc_model()
        self.fc = fcsvc.register_fc(fc_model=self.model, actor=self.tech,
                                    hardware_revision="rev-C")

    def _issue(self, **kwargs):
        defaults = dict(fc=self.fc, title="GPS not detected after flashing",
                        symptoms="GPS module not detected, no satellites, no fix",
                        actor=self.tester, category=Category.HARDWARE,
                        severity=Severity.MAJOR, assigned_department=self.fwd)
        defaults.update(kwargs)
        return issvc.create_issue(**defaults)

    def test_issue_key_and_version_capture(self):
        FirmwareRecord.objects.create(fc=self.fc, firmware_name="KFT",
                                      version="4.3.7", operator=self.lead)
        issue = self._issue()
        self.assertRegex(issue.key, r"^ISS-\d{4}-\d{5}$")
        self.assertEqual(issue.firmware_version, "4.3.7")
        self.assertEqual(issue.hardware_revision, "rev-C")

    def test_invalid_status_transition_rejected(self):
        issue = self._issue()
        with self.assertRaises(WorkflowError):
            issvc.change_status(issue, IssueStatus.CLOSED, actor=self.tester)
        with self.assertRaises(WorkflowError):
            issvc.change_status(issue, IssueStatus.VERIFIED, actor=self.tester)

    def test_resolution_requires_root_cause_and_resolution(self):
        issue = self._issue()
        with self.assertRaises(WorkflowError):
            issvc.change_status(issue, IssueStatus.RESOLVED, actor=self.lead)
        issvc.change_status(issue, IssueStatus.RESOLVED, actor=self.lead,
                            root_cause="cold joint", resolution="reflowed")
        issue.refresh_from_db()
        self.assertEqual(issue.status, IssueStatus.RESOLVED)
        self.assertEqual(issue.resolved_by, self.lead)

    def test_verification_requires_a_different_person_and_a_role(self):
        issue = self._issue()
        issvc.change_status(issue, IssueStatus.RESOLVED, actor=self.lead,
                            root_cause="rc", resolution="res")
        with self.assertRaises(WorkflowError):
            issvc.change_status(issue, IssueStatus.VERIFIED, actor=self.lead)
        with self.assertRaises(WorkflowError):
            issvc.change_status(issue, IssueStatus.VERIFIED, actor=self.tech)
        issvc.change_status(issue, IssueStatus.VERIFIED, actor=self.tester)
        issue.refresh_from_db()
        self.assertEqual(issue.verified_by, self.tester)

    def test_reassignment_requires_reason_and_is_logged(self):
        issue = self._issue()
        with self.assertRaises(WorkflowError):
            issvc.reassign(issue, actor=self.lead, to_department=self.hw, reason="")
        issvc.reassign(issue, actor=self.lead, to_department=self.hw,
                       reason="root cause is in assembly")
        issue.refresh_from_db()
        log = issue.reassignments.last()
        self.assertEqual(log.from_department, self.fwd)
        self.assertEqual(log.to_department, self.hw)
        self.assertEqual(log.actor, self.lead)
        self.assertTrue(AuditLogEntry.objects.filter(
            entity_type="Issue", entity_id=str(issue.pk),
            action=AuditLogEntry.ACTION_REASSIGN).exists())

    def test_append_only_logs_keep_insertion_order_when_timestamps_collide(self):
        """Windows clocks have ~15 ms granularity, so two rows written in the
        same tick can share created_at. Ordering must still be insertion order,
        or an append-only log renders out of sequence.

        Regression: ordering on created_at alone made
        `issue.reassignments.last()` return the initial assignment instead of
        the most recent reassignment.
        """
        from issues.models import IssueInvestigationNote, IssueReassignmentLog

        issue = self._issue()
        issvc.reassign(issue, actor=self.lead, to_department=self.hw,
                       reason="root cause is in assembly")
        issvc.add_note(issue, author=self.tech, note="first")
        issvc.add_note(issue, author=self.lead, note="second")

        # Force every row to share a timestamp, as a coarse clock would.
        collision = issue.created_at
        IssueReassignmentLog.objects.filter(issue=issue).update(created_at=collision)
        IssueInvestigationNote.objects.filter(issue=issue).update(created_at=collision)

        logs = list(issue.reassignments.all())
        self.assertEqual([entry.pk for entry in logs],
                         sorted(entry.pk for entry in logs))
        self.assertEqual(logs[-1].from_department, self.fwd)
        self.assertEqual(logs[-1].to_department, self.hw)
        self.assertEqual(issue.reassignments.last().to_department, self.hw)

        notes = list(issue.investigation_notes.all())
        self.assertEqual([n.note for n in notes], ["first", "second"])

    def test_closed_issue_is_read_only_for_notes(self):
        issue = self._issue()
        issvc.change_status(issue, IssueStatus.RESOLVED, actor=self.lead,
                            root_cause="rc", resolution="res")
        issvc.change_status(issue, IssueStatus.VERIFIED, actor=self.tester)
        issvc.change_status(issue, IssueStatus.CLOSED, actor=self.tester)
        issue.refresh_from_db()
        with self.assertRaises(WorkflowError):
            issvc.add_note(issue, author=self.tech, note="late note")

    def test_manager_can_reopen_closed_issue_with_reason(self):
        issue = self._issue()
        issvc.change_status(issue, IssueStatus.RESOLVED, actor=self.lead,
                            root_cause="rc", resolution="res")
        issvc.change_status(issue, IssueStatus.VERIFIED, actor=self.tester)
        issvc.change_status(issue, IssueStatus.CLOSED, actor=self.tester)
        issue.refresh_from_db()
        with self.assertRaises(WorkflowError):
            issvc.reopen(issue, actor=self.tech, reason="nope")
        issvc.reopen(issue, actor=self.manager, reason="recurred on the same FC")
        issue.refresh_from_db()
        self.assertEqual(issue.status, IssueStatus.INVESTIGATING)

    def test_investigation_notes_are_append_only(self):
        issue = self._issue()
        note = issvc.add_note(issue, author=self.lead, note="checked UART")
        note.note = "edited"
        with self.assertRaises(PermissionError):
            note.save()
        with self.assertRaises(PermissionError):
            note.delete()

    def test_audit_log_is_append_only(self):
        issue = self._issue()
        entry = AuditLogEntry.objects.filter(entity_type="Issue").first()
        entry.note = "tampered"
        with self.assertRaises(PermissionError):
            entry.save()
        with self.assertRaises(PermissionError):
            entry.delete()
        # And at the database level, bypassing the model layer entirely.
        from django.db import connection, transaction
        with self.assertRaises(Exception):
            with transaction.atomic():
                with connection.cursor() as cur:
                    cur.execute("UPDATE core_auditlogentry SET note='x' WHERE id=%s",
                                [entry.pk])

    def test_promotion_requires_resolution_and_role(self):
        issue = self._issue()
        with self.assertRaises(WorkflowError):
            issvc.promote_to_known_issue(issue, actor=self.lead)
        issvc.change_status(issue, IssueStatus.RESOLVED, actor=self.lead,
                            root_cause="cold solder joint on GPS connector",
                            resolution="reflowed the joint")
        issue.refresh_from_db()
        with self.assertRaises(WorkflowError):
            issvc.promote_to_known_issue(issue, actor=self.tech)
        known = issvc.promote_to_known_issue(issue, actor=self.lead)
        issue.refresh_from_db()
        self.assertEqual(issue.known_issue, known)
        self.assertEqual(known.occurrence_count, 1)
        self.assertEqual(known.first_occurrence_issue, issue)

    def test_known_issue_rollup_counts_recurrences(self):
        issue = self._issue()
        issvc.change_status(issue, IssueStatus.RESOLVED, actor=self.lead,
                            root_cause="rc", resolution="res")
        known = issvc.promote_to_known_issue(issue, actor=self.lead)
        fc2 = fcsvc.register_fc(fc_model=self.model, actor=self.tech)
        issue2 = self._issue(fc=fc2)
        issvc.link_issue_to_known(issue2, known, actor=self.lead, reason="same symptom")
        known.refresh_from_db()
        self.assertEqual(known.occurrence_count, 2)
        issue2.refresh_from_db()
        self.assertTrue(issue2.is_recurring)


class SearchTests(TestCase):
    def setUp(self):
        self.hw = make_department("assembly", Department.KIND_HARDWARE)
        self.fwd = make_department("firmware", Department.KIND_FIRMWARE)
        self.tech = make_user("tech", Role.TECHNICIAN, self.hw)
        self.lead = make_user("lead", Role.DEPARTMENT_LEAD, self.fwd)
        self.model = make_fc_model()
        self.fc = fcsvc.register_fc(fc_model=self.model, actor=self.tech,
                                    hardware_revision="rev-C")

        self.gps = issvc.create_issue(
            fc=self.fc, title="GPS not detected after firmware flashing",
            symptoms="GPS module not detected in GCS after flashing. No satellites.",
            actor=self.tech, category=Category.HARDWARE,
            assigned_department=self.hw,
            version_overrides={"firmware_version": "4.3.7",
                               "hardware_revision": "rev-C"})
        issvc.change_status(self.gps, IssueStatus.RESOLVED, actor=self.lead,
                            root_cause="Cold solder joint on the GPS connector",
                            resolution="Reflowed the connector; GPS locks in 40 s")

        self.baro = issvc.create_issue(
            fc=self.fc, title="Barometer altitude drift on bench",
            symptoms="Barometer altitude drifts several metres while stationary",
            actor=self.tech, category=Category.FIRMWARE,
            discovered_stage=Stage.FABRICATION,
            assigned_department=self.fwd,
            version_overrides={"firmware_version": "4.4.0"})

    def test_full_text_search_finds_by_symptom_keyword(self):
        results = list(search_issues(Issue.objects.all(), text="GPS not detected"))
        self.assertIn(self.gps, results)
        self.assertNotIn(self.baro, results)

    def test_full_text_search_matches_root_cause_and_resolution(self):
        results = list(search_issues(Issue.objects.all(), text="cold solder joint"))
        self.assertIn(self.gps, results)

    def test_structured_filter_search(self):
        results = list(search_issues(Issue.objects.all(),
                                     filters={"firmware_version": "4.4.0"}))
        self.assertEqual(results, [self.baro])

    def test_similar_issues_ranks_matching_versions_higher(self):
        scored, known = find_similar(
            text="GPS not detected after flashing firmware",
            firmware_version="4.3.7", hardware_revision="rev-C",
            category=Category.HARDWARE)
        self.assertTrue(scored)
        top_score, matched_on, top_issue = scored[0]
        self.assertEqual(top_issue, self.gps)
        self.assertIn("firmware_version", matched_on)
        self.assertIn("hardware_revision", matched_on)

    def test_similar_issues_surface_known_issues(self):
        issvc.promote_to_known_issue(self.gps, actor=self.lead)
        scored, known = find_similar(text="GPS not detected")
        self.assertTrue(known)
        self.assertIn("GPS", known[0].title)

    def test_similar_falls_back_to_structured_matching(self):
        scored, _ = find_similar(text="zzzz-nonsense-token",
                                 firmware_version="4.4.0")
        self.assertTrue(any(i.pk == self.baro.pk for _, _, i in scored))

    def test_search_tolerates_arbitrary_user_input(self):
        for text in ["a & b |", "!!!", "'quoted", "a:b:c", ""]:
            list(search_issues(Issue.objects.all(), text=text))
