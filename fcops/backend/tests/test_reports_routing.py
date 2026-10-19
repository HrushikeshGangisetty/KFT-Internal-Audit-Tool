"""WP4 (general reports, discovery facts, incidents, stage blocking) and
WP5 (routing, acknowledgement, ownership, handoffs)."""
import shutil
import tempfile
import threading

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.db import connection
from django.test import TestCase, TransactionTestCase, override_settings
from rest_framework.test import APIClient

from accounts.models import Role
from core.exceptions import WorkflowError
from core.models import AlertDelivery, Notification
from fc import services as fcsvc
from fc.models import FCStatus
from issues import services as issvc
from issues.models import (Handoff, Issue, IssueEvent, IssueKind, ProductArea,
                           Queue, RoutingRule, Severity)

from .access_fixtures import AccessWorld
from .factories import make_fc_model, make_user

MEDIA = tempfile.mkdtemp(prefix="wp4-media-")


def configure_routing(w):
    """Placeholder queues for the access-matrix world."""
    w.fw_head = make_user("fw_head", Role.DEPARTMENT_LEAD, w.firmware)
    w.coordinator = make_user("coordinator", Role.TECHNICIAN, w.service)
    w.sw_queue = Queue.objects.create(name="Software", department=w.software,
                                      head=w.sw_head, backup=w.manager)
    w.fw_queue = Queue.objects.create(name="Firmware", department=w.firmware,
                                      head=w.fw_head, backup=w.manager)
    w.fallback = Queue.objects.create(name="Fallback", head=w.coordinator,
                                      backup=w.manager, is_fallback=True)
    RoutingRule.objects.create(product_area=ProductArea.GCS, queue=w.sw_queue)
    RoutingRule.objects.create(product_area=ProductArea.FIRMWARE, queue=w.fw_queue)
    for user in (w.sw_head, w.fw_head):
        user.email = f"{user.username}@example.test"
        user.save(update_fields=["email"])


def events(issue, type=None):
    qs = IssueEvent.objects.filter(issue=issue)
    return list(qs.filter(type=type) if type else qs.values_list("type", flat=True))


@override_settings(MEDIA_ROOT=MEDIA)
class ReportAndRoutingTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def setUp(self):
        self.w = AccessWorld()
        configure_routing(self.w)

    def client_for(self, user):
        client = APIClient()
        client.force_authenticate(user)
        return client

    def report(self, user, **fields):
        data = {"title": "GCS map freezes", "symptom": "map stops updating",
                "urgency": "unknown", **fields}
        r = self.client_for(user).post("/api/issues/report/", data, format="json")
        self.assertEqual(r.status_code, 201, r.data)
        return r.data

    # --- WP4 -------------------------------------------------------------
    def test_scenario_1_minimal_report_gets_an_id_and_the_fallback_queue(self):
        data = self.report(self.w.svc_member)
        self.assertTrue(data["key"].startswith("ISS-"))
        self.assertEqual(data["queue_name"], "Fallback")
        self.assertIsNone(data["fc"])
        issue = Issue.objects.get(pk=data["id"])
        self.assertEqual((issue.reporter, issue.product_area, issue.urgency),
                         (self.w.svc_member, ProductArea.UNKNOWN, "unknown"))
        self.assertEqual(issue.accountable_user, self.w.coordinator)

    def test_report_requires_title_symptom_and_urgency(self):
        r = self.client_for(self.w.svc_member).post(
            "/api/issues/report/", {"title": "x", "symptom": "y"}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("urgency", r.data)

    def test_scenario_8_general_issue_shows_in_list_search_and_dashboard(self):
        data = self.report(self.w.svc_member, title="Rover beacon silent",
                           symptom="no beacon after boot", product_area="GCS")
        client = self.client_for(self.w.sw_member)
        ids = {i["id"] for i in client.get("/api/issues/", {"page_size": 100})
               .data["results"]}
        self.assertIn(data["id"], ids)
        hits = client.get("/api/issues/", {"q": "beacon"}).data["results"]
        self.assertEqual([h["id"] for h in hits], [data["id"]])
        self.assertEqual(hits[0]["stage_label"], "")
        self.assertEqual(client.get(f"/api/issues/{data['id']}/similar/").status_code, 200)
        dash = self.client_for(self.w.manager).get("/api/dashboard/summary/").data
        self.assertEqual(dash["open_issue_total"], 4)  # 3 FC issues + this one

    def test_discovery_facts_cannot_change_through_the_api(self):
        issue = self.w.sw_issue
        client = self.client_for(self.w.sw_head)
        for field, value in (("discovered_by", self.w.sw_head.pk),
                             ("reporter", self.w.sw_head.pk), ("fc", None),
                             ("discovered_stage", "QC_INSPECTION"),
                             ("accountable_user", self.w.sw_head.pk)):
            with self.subTest(field=field):
                r = client.patch(f"/api/issues/{issue.pk}/", {field: value},
                                 format="json")
                self.assertEqual(r.status_code, 409)
                self.assertEqual(r.data["code"], "immutable_field")
        issue.refresh_from_db()
        self.assertEqual((issue.discovered_by, issue.reporter, issue.fc_id),
                         (self.w.svc_member, self.w.svc_member, self.w.fc.pk))
        r = client.patch(f"/api/issues/{issue.pk}/", {"description": "more"},
                         format="json")
        self.assertEqual(r.status_code, 200)

    def test_discovery_facts_cannot_change_through_services(self):
        with self.assertRaises(WorkflowError):
            issvc.edit_issue(self.w.sw_issue, actor=self.w.manager,
                             changes={"discovered_by": self.w.manager})
        with self.assertRaises(WorkflowError):
            issvc.edit_issue(self.w.sw_issue, actor=self.w.manager,
                             changes={"submitted_at": None})

    def test_incident_workstreams_are_scoped_separately(self):
        incident = issvc.submit_report(
            reporter=self.w.manager, title="Field outage at site A",
            symptom="rovers lost link", urgency="urgent", kind=IssueKind.INCIDENT)
        sw = issvc.submit_report(
            reporter=self.w.manager, title="GCS side", symptom="GCS drops link",
            urgency="urgent", product_area=ProductArea.GCS,
            kind=IssueKind.WORKSTREAM, parent=incident)
        fw = issvc.submit_report(
            reporter=self.w.manager, title="Firmware side", symptom="radio resets",
            urgency="urgent", product_area=ProductArea.FIRMWARE,
            kind=IssueKind.WORKSTREAM, parent=incident)
        issvc.add_note(sw, author=self.w.sw_head, note="GCS heap trace attached")
        client = self.client_for(self.w.fw_member)
        r = client.get(f"/api/issues/{fw.pk}/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["parent_summary"]["key"], incident.key)
        self.assertNotIn("GCS heap trace", str(r.data))
        self.assertEqual(client.get(f"/api/issues/{sw.pk}/").status_code, 404)
        self.assertEqual(client.get(f"/api/issues/{incident.pk}/").status_code, 404)
        with self.assertRaises(WorkflowError):
            issvc.submit_report(reporter=self.w.manager, title="t", symptom="s",
                                urgency="normal", kind=IssueKind.WORKSTREAM,
                                parent=fw)

    def test_linking_a_severe_issue_does_not_block_without_the_decision(self):
        fc = fcsvc.register_fc(fc_model=make_fc_model("other"), actor=self.w.asm_head)
        issue = issvc.submit_report(reporter=self.w.asm_member, title="Cracked frame",
                                    symptom="crack near mount", urgency="urgent",
                                    fc=fc, severity=Severity.BLOCKER)
        other = fcsvc.register_fc(fc_model=make_fc_model("other"), actor=self.w.asm_head)
        issvc.link_unit(issue, fc=other, actor=self.w.asm_head, reason="same batch")
        for unit in (fc, other):
            unit.refresh_from_db()
            self.assertNotEqual(unit.status, FCStatus.BLOCKED)
            self.assertEqual(fcsvc.stage_blockers(unit), [])
        with self.assertRaises(WorkflowError):
            issvc.set_blocks_stage(issue, actor=self.w.asm_member, blocks=True,
                                   reason="x")
        r = self.client_for(self.w.asm_head).post(
            f"/api/issues/{issue.pk}/blocks-stage/",
            {"blocks": True, "reason": "unsafe to test"}, format="json")
        self.assertEqual(r.status_code, 200)
        fc.refresh_from_db()
        self.assertEqual(fc.status, FCStatus.BLOCKED)
        self.assertTrue(fcsvc.stage_blockers(fc))
        self.assertEqual(len(events(issue, "blocks_stage_set")), 1)

    @override_settings(ATTACHMENT_MAX_BYTES=10)
    def test_attachment_failure_does_not_fail_the_report(self):
        r = self.client_for(self.w.svc_member).post("/api/issues/report/", {
            "title": "Photo of damage", "symptom": "bent arm", "urgency": "normal",
            "files": [SimpleUploadedFile("ok.txt", b"small"),
                      SimpleUploadedFile("big.txt", b"x" * 100)]},
            format="multipart")
        self.assertEqual(r.status_code, 201)
        self.assertEqual([f["name"] for f in r.data["failed_attachments"]], ["big.txt"])
        self.assertEqual([a["original_name"] for a in r.data["attachments"]], ["ok.txt"])

    # --- WP5 -------------------------------------------------------------
    def test_scenario_2_head_alerted_and_viewing_does_not_acknowledge(self):
        data = self.report(self.w.svc_member, product_area="GCS", urgency="urgent")
        issue = Issue.objects.get(pk=data["id"])
        self.assertEqual(data["queue_name"], "Software")
        self.assertEqual(issue.accountable_user, self.w.sw_head)
        self.assertEqual(set(AlertDelivery.objects.filter(recipient=self.w.sw_head)
                             .values_list("channel", flat=True)), {"in_app", "email"})
        call_command("run_worker", "--once")
        self.assertTrue(Notification.objects.filter(
            recipient=self.w.sw_head, kind="ISSUE_ALERT", target_id=issue.pk).exists())

        head = self.client_for(self.w.sw_head)
        self.assertEqual(head.get(f"/api/issues/{issue.pk}/").status_code, 200)
        issue.refresh_from_db()
        self.assertIsNone(issue.acknowledged_at)

        r = self.client_for(self.w.sw_member).post(f"/api/issues/{issue.pk}/acknowledge/")
        self.assertEqual(r.status_code, 409)
        r = head.post(f"/api/issues/{issue.pk}/acknowledge/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["acknowledged_by"], self.w.sw_head.pk)
        head.post(f"/api/issues/{issue.pk}/acknowledge/")
        self.assertEqual(len(events(issue, "acknowledged")), 1)

    def test_events_give_routing_and_acknowledgement_times(self):
        issue = issvc.submit_report(reporter=self.w.svc_member, title="t",
                                    symptom="s", urgency="normal",
                                    product_area=ProductArea.GCS)
        issvc.acknowledge(issue, user=self.w.sw_head)
        self.assertEqual(events(issue)[:3], ["submitted", "routed", "assigned"])
        routed = events(issue, "routed")[0]
        acked = events(issue, "acknowledged")[0]
        self.assertGreaterEqual(routed.data["seconds_since_submission"], 0)
        self.assertGreaterEqual(acked.data["seconds_since_submission"],
                                routed.data["seconds_since_submission"])
        self.assertEqual(acked.actor, self.w.sw_head)

    def test_issue_events_are_append_only(self):
        issue = issvc.submit_report(reporter=self.w.svc_member, title="t",
                                    symptom="s", urgency="normal")
        event = IssueEvent.objects.filter(issue=issue).first()
        with self.assertRaises(PermissionError):
            event.save()
        from django.db import DatabaseError, transaction
        with self.assertRaises(DatabaseError), transaction.atomic():
            IssueEvent.objects.filter(pk=event.pk).update(type="escalated")

    def test_scenario_3_handoff_to_firmware(self):
        issue = issvc.submit_report(reporter=self.w.svc_member, title="Param reset",
                                    symptom="params revert after flight",
                                    urgency="normal", product_area=ProductArea.GCS)
        fw_member = self.client_for(self.w.fw_member)
        self.assertEqual(fw_member.get(f"/api/issues/{issue.pk}/").status_code, 404)

        r = self.client_for(self.w.sw_head).post(
            f"/api/issues/{issue.pk}/handoffs/",
            {"to_department": self.w.firmware.pk, "to_user": self.w.fw_member.pk,
             "reason": ""}, format="json")
        self.assertEqual(r.status_code, 409)  # a reason is required
        r = self.client_for(self.w.sw_head).post(
            f"/api/issues/{issue.pk}/handoffs/",
            {"to_department": self.w.firmware.pk, "to_user": self.w.fw_member.pk,
             "reason": "looks like a firmware parameter default"}, format="json")
        self.assertEqual(r.status_code, 201)
        handoff_id = r.data["id"]
        # While pending: the recipient and the Firmware head can read it, and
        # Software stays accountable.
        self.assertEqual(fw_member.get(f"/api/issues/{issue.pk}/").status_code, 200)
        self.assertEqual(self.client_for(self.w.fw_head)
                         .get(f"/api/issues/{issue.pk}/").status_code, 200)
        issue.refresh_from_db()
        self.assertEqual(issue.accountable_user, self.w.sw_head)
        queue = fw_member.get("/api/me/queue/").data
        self.assertEqual([h["id"] for h in queue["handoffs_awaiting_response"]],
                         [handoff_id])

        self.assertEqual(self.client_for(self.w.sw_member).post(
            f"/api/handoffs/{handoff_id}/respond/", {"accept": True},
            format="json").status_code, 409)  # not a receiver
        r = fw_member.post(f"/api/handoffs/{handoff_id}/respond/",
                           {"accept": False}, format="json")
        self.assertEqual((r.status_code, r.data["code"]), (409, "reason_required"))
        r = fw_member.post(f"/api/handoffs/{handoff_id}/respond/",
                           {"accept": False, "reason": "it is the GCS writer"},
                           format="json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(fw_member.get(f"/api/issues/{issue.pk}/").status_code, 404)

        handoff = issvc.propose_handoff(issue, actor=self.w.sw_head,
                                        to_department=self.w.firmware,
                                        reason="trace shows firmware write")
        issvc.respond_handoff(handoff, actor=self.w.fw_head, accept=True)
        issue.refresh_from_db()
        self.assertEqual((issue.accountable_user, issue.queue, issue.assigned_department),
                         (self.w.fw_head, self.w.fw_queue, self.w.firmware))
        self.assertIsNone(issue.acknowledged_at)
        self.assertEqual(issue.reassignments.last().to_department, self.w.firmware)
        self.assertEqual(
            [t for t in events(issue) if t.startswith("handoff")],
            ["handoff_proposed", "handoff_rejected", "handoff_proposed",
             "handoff_accepted"])
        # Previous team keeps read access (placeholder default "read").
        self.assertEqual(self.client_for(self.w.sw_member)
                         .get(f"/api/issues/{issue.pk}/").status_code, 200)

    @override_settings(HANDOFF_PREVIOUS_TEAM_ACCESS="none")
    def test_previous_team_access_can_be_withdrawn(self):
        issue = issvc.submit_report(reporter=self.w.svc_member, title="t",
                                    symptom="s", urgency="normal",
                                    product_area=ProductArea.GCS)
        issvc.respond_handoff(
            issvc.propose_handoff(issue, actor=self.w.sw_head,
                                  to_department=self.w.firmware, reason="r"),
            actor=self.w.fw_head, accept=True)
        self.assertEqual(self.client_for(self.w.sw_member)
                         .get(f"/api/issues/{issue.pk}/").status_code, 404)

    def test_head_assigns_ownership_to_a_team_member(self):
        issue = issvc.submit_report(reporter=self.w.svc_member, title="t",
                                    symptom="s", urgency="normal",
                                    product_area=ProductArea.GCS)
        with self.assertRaises(WorkflowError):
            issvc.accept_ownership(issue, actor=self.w.sw_member, member=self.w.sw_member)
        with self.assertRaises(WorkflowError):
            issvc.accept_ownership(issue, actor=self.w.sw_head, member=self.w.fw_member)
        r = self.client_for(self.w.sw_head).post(
            f"/api/issues/{issue.pk}/accept-ownership/",
            {"member": self.w.sw_member.pk}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["accountable_user"], self.w.sw_member.pk)
        mine = self.client_for(self.w.sw_member).get("/api/me/queue/").data
        self.assertEqual([i["id"] for i in mine["accountable"]], [issue.pk])

    @override_settings(DEBUG=True)
    def test_seed_pilot_config_is_idempotent(self):
        call_command("seed_pilot_config")
        call_command("seed_pilot_config")
        self.assertEqual(Queue.objects.filter(is_fallback=True).count(), 1)


class ConcurrentHandoffTests(TransactionTestCase):
    def test_two_simultaneous_proposals_give_one_pending_handoff(self):
        w = AccessWorld()
        configure_routing(w)
        issue = issvc.submit_report(reporter=w.svc_member, title="t", symptom="s",
                                    urgency="normal", product_area=ProductArea.GCS)
        barrier = threading.Barrier(2)
        outcomes = []

        def propose(actor):
            try:
                barrier.wait()
                issvc.propose_handoff(issue, actor=actor, to_department=w.firmware,
                                      reason="race")
                outcomes.append("ok")
            except WorkflowError as exc:
                outcomes.append(exc.code)
            finally:
                connection.close()

        threads = [threading.Thread(target=propose, args=(a,))
                   for a in (w.sw_head, w.manager)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(sorted(outcomes), ["handoff_pending", "ok"])
        self.assertEqual(Handoff.objects.filter(issue=issue,
                                                status=Handoff.PENDING).count(), 1)
