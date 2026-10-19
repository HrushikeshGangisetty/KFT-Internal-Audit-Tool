"""WP3: job queue, worker, heartbeat, working calendar and alert delivery."""
import threading
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from django.core import mail
from django.core.management import call_command
from django.db import connection, transaction
from django.test import SimpleTestCase, TestCase, TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import Role
from core import alerts, jobs
from core.calendar import add_working_minutes, working_minutes_between
from core.models import AlertDelivery, Job, Notification, PeriodicTaskRun

from .factories import make_department, make_user

IST = ZoneInfo("Asia/Kolkata")
CALENDAR = dict(WORKING_DAYS=[0, 1, 2, 3, 4], WORKING_HOURS=(10, 18),
                WORKING_TIMEZONE="Asia/Kolkata")


def at(y, m, d, h, mi=0):
    return datetime(y, m, d, h, mi, tzinfo=IST)


def drain(worker="test-worker"):
    while (job := jobs.claim(worker)) is not None:
        jobs.run(job)


class JobQueueTests(TestCase):
    def setUp(self):
        self.calls = []
        jobs.HANDLERS["test.record"] = lambda job: self.calls.append(job.payload)

    def tearDown(self):
        jobs.HANDLERS.pop("test.record", None)
        jobs.HANDLERS.pop("test.boom", None)

    def test_job_enqueued_in_rolled_back_transaction_never_runs(self):
        try:
            with transaction.atomic():
                jobs.enqueue("test.record", {"n": 1})
                raise RuntimeError("roll back")
        except RuntimeError:
            pass
        drain()
        self.assertEqual(Job.objects.count(), 0)
        self.assertEqual(self.calls, [])

    def test_idempotency_key_returns_existing_job(self):
        a = jobs.enqueue("test.record", {"n": 1}, idempotency_key="k1")
        b = jobs.enqueue("test.record", {"n": 2}, idempotency_key="k1")
        self.assertEqual(a.pk, b.pk)
        drain()
        self.assertEqual(self.calls, [{"n": 1}])

    def test_failure_retries_with_backoff_then_dies(self):
        jobs.HANDLERS["test.boom"] = lambda job: 1 / 0
        job = jobs.enqueue("test.boom", max_attempts=2)
        jobs.run(jobs.claim("w"))
        job.refresh_from_db()
        self.assertEqual(job.status, Job.QUEUED)
        self.assertGreater(job.run_after, timezone.now())
        self.assertIn("ZeroDivisionError", job.last_error)
        jobs.run(jobs.claim("w", now=job.run_after))
        job.refresh_from_db()
        self.assertEqual((job.status, job.attempts), (Job.DEAD, 2))

    def test_job_not_due_is_not_claimed(self):
        jobs.enqueue("test.record", run_after=timezone.now() + timedelta(hours=1))
        self.assertIsNone(jobs.claim("w"))


class ConcurrentClaimTests(TransactionTestCase):
    def test_two_workers_never_run_the_same_job(self):
        for n in range(20):
            jobs.enqueue("test.noop", {"n": n})
        barrier = threading.Barrier(2)
        claimed = {"a": [], "b": []}

        def work(name):
            try:
                barrier.wait()
                while (job := jobs.claim(name)) is not None:
                    claimed[name].append(job.pk)
            finally:
                connection.close()

        threads = [threading.Thread(target=work, args=(n,)) for n in claimed]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        a, b = set(claimed["a"]), set(claimed["b"])
        self.assertEqual(a & b, set())
        self.assertEqual(len(a | b), 20)
        self.assertEqual(len(claimed["a"]) + len(claimed["b"]), 20)


class AlertTests(TestCase):
    def setUp(self):
        dept = make_department("software")
        self.head = make_user("head", Role.DEPARTMENT_LEAD, dept)
        self.head.email = "head@example.test"
        self.head.save(update_fields=["email"])
        self.manager = make_user("boss", Role.MANAGER)
        self.summary = {"ref": "ISS-2026-00001", "urgency": "urgent",
                        "queue": "Software", "link": "/issues/1"}

    def dispatch(self, key="issue:1:routed", recipients=None, urgency="urgent"):
        return alerts.dispatch_alert(key, recipients or [self.head], urgency,
                                     ("issue", 1), kind="ISSUE_ALERT",
                                     summary=self.summary,
                                     on_failure=[self.manager])

    def test_dispatch_twice_gives_one_delivery_per_recipient_and_channel(self):
        first = self.dispatch()
        second = self.dispatch()
        self.assertEqual({d.channel for d in first}, {"in_app", "email"})
        self.assertEqual(second, [])
        self.assertEqual(AlertDelivery.objects.count(), 2)
        self.assertEqual(Job.objects.count(), 2)

    def test_normal_alert_is_in_app_only(self):
        self.assertEqual([d.channel for d in self.dispatch(urgency="normal")],
                         ["in_app"])

    def test_out_of_app_message_carries_reference_and_link_only(self):
        self.dispatch()
        drain()
        self.assertEqual(len(mail.outbox), 1)
        body = mail.outbox[0].subject + mail.outbox[0].body
        self.assertIn("ISS-2026-00001", body)
        self.assertIn("/issues/1", body)
        self.assertEqual(Notification.objects.filter(recipient=self.head).count(), 1)

    def test_crash_mid_handler_is_retried_without_a_double_send(self):
        # Email only, so the external effect is countable.
        alerts.dispatch_alert("k-crash", [self.head], "urgent", ("issue", 1),
                              kind="ISSUE_ALERT", summary=self.summary,
                              channels=["email"])
        job = jobs.claim("dying-worker")
        alerts.deliver(job)  # the effect happens, then the worker dies
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(Job.objects.get(pk=job.pk).status, Job.RUNNING)
        self.assertEqual(jobs.recover_stale(timeout=timedelta(0)), 1)
        drain("second-worker")
        self.assertEqual(len(mail.outbox), 1)  # idempotent: no double send
        self.assertEqual(Job.objects.get(pk=job.pk).status, Job.SUCCEEDED)

    def test_failed_delivery_notifies_head_and_manager_once(self):
        self.head.email = ""
        self.head.save(update_fields=["email"])
        delivery = alerts.dispatch_alert(
            "k-fail", [self.head], "urgent", ("issue", 1), kind="ISSUE_ALERT",
            summary=self.summary, channels=["email"], on_failure=[self.manager])[0]
        Job.objects.update(max_attempts=1)
        drain()
        delivery.refresh_from_db()
        self.assertEqual(delivery.status, AlertDelivery.FAILED)
        notices = Notification.objects.filter(kind="ALERT_FAILED")
        self.assertEqual(list(notices.values_list("recipient", flat=True)),
                         [self.manager.pk])


class WorkerHealthTests(TestCase):
    def setUp(self):
        self.manager = make_user("boss", Role.MANAGER)
        self.member = make_user("tech", Role.TECHNICIAN, make_department("assembly"))
        self.runs = []
        jobs.PERIODIC["test.tick"] = (timedelta(minutes=1),
                                      lambda now: self.runs.append(now))

    def tearDown(self):
        jobs.PERIODIC.pop("test.tick", None)

    def get_health(self, user):
        client = APIClient()
        client.force_authenticate(user)
        return client.get("/api/admin/health/")

    def test_scenario_13_stale_heartbeat_then_restart_runs_overdue_work_once(self):
        now = timezone.now()
        jobs.beat("old-worker", now - timedelta(minutes=10))
        PeriodicTaskRun.objects.create(name="test.tick",
                                       last_run_at=now - timedelta(minutes=30))
        r = self.get_health(self.manager)
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.data["worker_stale"])
        self.assertEqual(self.get_health(self.member).status_code, 403)

        call_command("run_worker", "--once")  # the restart
        self.assertEqual(len(self.runs), 1)   # thirty missed ticks, run once
        self.assertFalse(self.get_health(self.manager).data["worker_stale"])
        jobs.run_periodic(timezone.now())
        self.assertEqual(len(self.runs), 1)   # not due again yet


@override_settings(**CALENDAR)
class WorkingCalendarTests(SimpleTestCase):
    # 16 Oct 2026 is a Friday.
    def test_across_a_weekend(self):
        self.assertEqual(add_working_minutes(at(2026, 10, 16, 17), 120, holidays=[]),
                         at(2026, 10, 19, 11))
        self.assertEqual(working_minutes_between(at(2026, 10, 16, 17),
                                                 at(2026, 10, 19, 11), holidays=[]), 120)

    def test_across_a_holiday(self):
        monday = date(2026, 10, 19)
        self.assertEqual(add_working_minutes(at(2026, 10, 16, 17), 120,
                                             holidays=[monday]),
                         at(2026, 10, 20, 11))
        self.assertEqual(working_minutes_between(at(2026, 10, 16, 17),
                                                 at(2026, 10, 20, 11),
                                                 holidays=[monday]), 120)

    def test_starting_after_hours(self):
        self.assertEqual(add_working_minutes(at(2026, 10, 14, 20), 30, holidays=[]),
                         at(2026, 10, 15, 10, 30))

    def test_starting_before_hours(self):
        self.assertEqual(add_working_minutes(at(2026, 10, 14, 8), 30, holidays=[]),
                         at(2026, 10, 14, 10, 30))
        self.assertEqual(working_minutes_between(at(2026, 10, 14, 8),
                                                 at(2026, 10, 14, 10, 30),
                                                 holidays=[]), 30)

    def test_utc_input_is_converted(self):
        start = datetime(2026, 10, 14, 4, 30, tzinfo=ZoneInfo("UTC"))  # 10:00 IST
        self.assertEqual(add_working_minutes(start, 60, holidays=[]),
                         at(2026, 10, 14, 11))

    def test_exactly_a_full_day_ends_at_closing(self):
        self.assertEqual(add_working_minutes(at(2026, 10, 14, 10), 480, holidays=[]),
                         at(2026, 10, 14, 18))
