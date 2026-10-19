"""WP6: acknowledgement deadlines, reminders, waiting and escalation, with
frozen time."""
from contextlib import contextmanager
from datetime import datetime, timedelta
from unittest import mock
from zoneinfo import ZoneInfo

from django.test import TestCase, override_settings

from accounts.models import Role
from core.exceptions import WorkflowError
from core.models import AlertDelivery, Job
from issues import deadlines
from issues import services as issvc
from issues.models import IssueEvent, ProductArea

from .access_fixtures import AccessWorld
from .factories import make_user
from .test_reports_routing import configure_routing

IST = ZoneInfo("Asia/Kolkata")
CALENDAR = dict(WORKING_DAYS=[0, 1, 2, 3, 4], WORKING_HOURS=(10, 18),
                WORKING_TIMEZONE="Asia/Kolkata", DUTY_CONTACT_USER_ID=None)


def at(d, h, mi=0):
    """November 2026, day ``d - 10`` (dates after the fixtures exist):
    at(14) is Wednesday 4 November, at(16) Friday 6, at(19) Monday 9."""
    return datetime(2026, 11, d - 10, h, mi, tzinfo=IST)


@contextmanager
def frozen(when):
    with mock.patch("django.utils.timezone.now", return_value=when):
        yield


def keys(prefix):
    return list(AlertDelivery.objects.filter(alert_key__startswith=prefix)
                .order_by("id").values_list("alert_key", "recipient__username",
                                            "channel"))


@override_settings(**CALENDAR)
class DeadlineTests(TestCase):
    def setUp(self):
        self.w = AccessWorld()
        configure_routing(self.w)
        self.backup = make_user("sw_backup", Role.TECHNICIAN, self.w.software)
        self.w.sw_queue.backup = self.backup
        self.w.sw_queue.save()

    def report(self, when, urgency="urgent", area=ProductArea.GCS):
        with frozen(when):
            return issvc.submit_report(reporter=self.w.svc_member, title="Link lost",
                                       symptom="GCS loses link", urgency=urgency,
                                       product_area=area)

    def run_checks(self, when, times=1):
        with frozen(when):
            for _ in range(times):
                deadlines.check_deadlines(when)

    def escalation_events(self, issue):
        return list(IssueEvent.objects.filter(
            issue=issue, type__in=["notified", "reminder_sent", "escalated"])
            .values_list("type", flat=True))

    def test_scenario_2_urgent_escalates_head_backup_manager_once_each(self):
        issue = self.report(at(14, 11))
        prefix = f"ack:{issue.pk}:0:"
        self.assertEqual({(k, u) for k, u, _ in keys(prefix)},
                         {(prefix + "0", "sw_head")})
        self.run_checks(at(14, 11, 29), times=10)
        self.assertEqual(len(keys(prefix)), 2)  # nothing new before 30 min
        self.run_checks(at(14, 11, 30), times=10)
        self.assertIn((prefix + "1", "sw_backup"), {(k, u) for k, u, _ in keys(prefix)})
        self.run_checks(at(14, 12, 0), times=10)
        self.assertIn((prefix + "2", "manager"), {(k, u) for k, u, _ in keys(prefix)})
        # urgent channels: in-app + email, one row per recipient and channel
        self.assertEqual(len(keys(prefix)), 6)
        self.assertEqual(self.escalation_events(issue),
                         ["notified", "escalated", "escalated"])

    def test_normal_report_friday_1730_is_due_monday_1330(self):
        issue = self.report(at(16, 17, 30), urgency="normal")
        self.assertEqual(deadlines.ack_due_at(issue), at(19, 13, 30))
        self.run_checks(at(19, 13, 29))
        self.assertEqual(self.escalation_events(issue), ["notified"])
        self.run_checks(at(19, 13, 30))
        self.assertEqual(self.escalation_events(issue), ["notified", "reminder_sent"])

    def test_unknown_urgency_follows_the_normal_policy(self):
        issue = self.report(at(14, 11), urgency="unknown")
        self.assertEqual(deadlines.ack_due_at(issue), at(14, 15))

    def test_acknowledging_stops_escalation(self):
        issue = self.report(at(14, 11))
        with frozen(at(14, 11, 10)):
            issvc.acknowledge(issue, user=self.w.sw_head)
        self.run_checks(at(14, 13), times=3)
        self.assertEqual(self.escalation_events(issue), ["notified"])

    def test_accepted_handoff_starts_a_new_sequence(self):
        issue = self.report(at(14, 11))
        with frozen(at(14, 11, 5)):
            handoff = issvc.propose_handoff(issue, actor=self.w.sw_head,
                                            to_department=self.w.firmware, reason="fw")
            issvc.respond_handoff(handoff, actor=self.w.fw_head, accept=True)
        issue.refresh_from_db()
        self.assertEqual(issue.owner_epoch, 1)
        self.assertEqual({u for _, u, _ in keys(f"ack:{issue.pk}:1:0")}, {"fw_head"})
        self.run_checks(at(14, 11, 34))  # 30 min after the first owner only
        self.assertEqual(keys(f"ack:{issue.pk}:0:1"), [])
        self.run_checks(at(14, 11, 35))
        self.assertEqual({u for _, u, _ in keys(f"ack:{issue.pk}:1:1")}, {"manager"})

    def test_pending_handoff_escalates_receiver_then_backup_then_manager(self):
        issue = self.report(at(14, 11), urgency="normal")
        with frozen(at(14, 11)):
            issvc.acknowledge(issue, user=self.w.sw_head)
            handoff = issvc.propose_handoff(issue, actor=self.w.sw_head,
                                            to_department=self.w.firmware, reason="fw")
        prefix = f"handoff:{handoff.pk}:"
        self.assertEqual({u for _, u, _ in keys(prefix + "0")}, {"fw_head"})
        self.run_checks(at(15, 11), times=5)       # 480 working minutes later
        self.assertEqual({u for _, u, _ in keys(prefix + "2")}, {"manager"})
        self.run_checks(at(15, 15), times=5)       # 720
        self.assertEqual({u for _, u, _ in keys(prefix + "3")}, {"manager"})
        self.assertEqual(len(keys(prefix + "3")), 1)

    def test_waiting_reminds_then_escalates_and_pauses_followups(self):
        issue = self.report(at(14, 11), urgency="normal")
        with frozen(at(14, 11)):
            issvc.accept_ownership(issue, actor=self.w.sw_head, member=self.w.sw_member)
            issvc.acknowledge(issue, user=self.w.sw_member)
            with self.assertRaises(WorkflowError):
                issvc.set_waiting(issue, actor=self.w.sw_member, waiting=True,
                                  reason="parts")
            with self.assertRaises(WorkflowError):
                issvc.set_waiting(issue, actor=self.w.sw_member, waiting=True,
                                  reason="parts", next_followup_at=at(30, 11))
            issvc.set_waiting(issue, actor=self.w.sw_member, waiting=True,
                              reason="waiting for radio module",
                              dependency_owner="Vendor X", next_followup_at=at(15, 11))
        self.run_checks(at(15, 10, 59))
        self.assertEqual(keys(f"waiting:{issue.pk}"), [])
        self.assertEqual(keys(f"followup:{issue.pk}"), [])  # paused while waiting
        self.run_checks(at(15, 11), times=5)
        self.assertEqual({u for _, u, _ in keys(f"waiting:{issue.pk}")}, {"sw_member"})
        self.run_checks(at(15, 15), times=5)       # one ack target later
        self.assertIn("sw_head", {u for _, u, _ in keys(f"waiting:{issue.pk}")})
        self.run_checks(at(16, 11), times=5)
        self.assertIn("manager", {u for _, u, _ in keys(f"waiting:{issue.pk}")})

    def test_waiting_never_pauses_acknowledgement_escalation(self):
        issue = self.report(at(14, 11))
        with frozen(at(14, 11, 1)):
            issvc.set_waiting(issue, actor=self.w.sw_head, waiting=True, reason="r",
                              next_followup_at=at(16, 11))
        self.run_checks(at(14, 11, 30))
        self.assertEqual({u for _, u, _ in keys(f"ack:{issue.pk}:0:1")}, {"sw_backup"})

    def test_quiet_acknowledged_issue_gets_one_followup_per_quiet_period(self):
        issue = self.report(at(14, 11), urgency="normal")
        with frozen(at(14, 11)):
            issvc.acknowledge(issue, user=self.w.sw_head)
        self.run_checks(at(15, 10, 59))
        self.assertEqual(keys(f"followup:{issue.pk}"), [])
        self.run_checks(at(15, 11), times=10)
        self.assertEqual({u for _, u, _ in keys(f"followup:{issue.pk}")}, {"sw_head"})
        self.assertEqual(len(keys(f"followup:{issue.pk}")), 1)

    def test_after_hours_urgent_without_duty_contact_shows_the_gap(self):
        issue = self.report(at(14, 21))
        self.assertEqual({u for _, u, _ in keys(f"ack:{issue.pk}:0:0")}, {"sw_head"})
        self.assertEqual({u for _, u, _ in keys("coverage:after-hours")}, {"manager"})
        job = Job.objects.filter(kind="alerts.deliver",
                                 payload__summary__ref=issue.key).first()
        self.assertNotIn("on_duty", job.payload["summary"])

    def test_after_hours_urgent_with_duty_contact_names_them(self):
        duty = make_user("duty", Role.TECHNICIAN, self.w.software)
        with override_settings(DUTY_CONTACT_USER_ID=duty.pk):
            issue = self.report(at(14, 21))
        self.assertEqual({u for _, u, _ in keys(f"ack:{issue.pk}:0:0")},
                         {"sw_head", "duty"})
        self.assertEqual(keys("coverage:after-hours"), [])
        job = Job.objects.filter(kind="alerts.deliver",
                                 payload__summary__ref=issue.key).first()
        self.assertEqual(job.payload["summary"]["on_duty"], "duty")

    def test_queue_without_active_head_or_backup_is_a_coverage_gap(self):
        for user in (self.w.sw_head, self.backup):
            user.is_active = False
            user.save(update_fields=["is_active"])
        issue = self.report(at(14, 11))
        self.run_checks(at(14, 11, 1), times=3)
        self.assertEqual(len(keys(f"coverage:queue:{self.w.sw_queue.pk}")), 1)
        self.assertTrue(IssueEvent.objects.filter(issue=issue, type="coverage_gap").exists())
