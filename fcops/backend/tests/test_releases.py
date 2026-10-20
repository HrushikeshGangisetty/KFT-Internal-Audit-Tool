"""WP11-WP13: dual authenticated release approval, synthetic recipients and
announcement campaigns."""
import smtplib
import threading
from datetime import timedelta
from unittest import mock

from django.core import mail
from django.db import connection
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import Capability, Role, User
from accounts.services import grant_capability, revoke_capability
from core.models import AuditLogEntry
from fc.models import SoftwareUpdate
from releases import services
from releases.legacy import convert_software_updates
from releases.models import (Campaign, CampaignDelivery, RecipientSnapshot, Release,
                             ReleaseApproval, ReleaseRevision)

from .access_fixtures import AccessWorld
from .factories import make_user
from .test_jobs_alerts import drain

SENTINEL = "INTERNAL-SENTINEL-7f3a do not ship"
FIELDS = {"source_ref": "9f2c1ab4d7e5", "recipient_notes": "Faster telemetry reconnect.",
          "internal_notes": SENTINEL, "compatibility": "FC firmware 4.5+"}


def client_for(user):
    client = APIClient()
    client.force_authenticate(user)
    return client


def approve_both(revision, head, manager):
    services.decide(revision, actor=head, role="software_head", decision="approve")
    services.decide(revision, actor=manager, role="manager", decision="approve")


class ReleaseWorld:
    def __init__(self):
        self.w = AccessWorld()
        self.sender = make_user("sender", Role.TECHNICIAN, self.w.software)
        grant_capability(self.sender, Capability.CAN_SEND_ANNOUNCEMENTS, actor=self.w.admin)
        self.release = services.create_release(actor=self.w.sw_member, product="GCS",
                                               version="2.6.0", **FIELDS)
        self.r1 = self.release.revisions.get()


class ApprovalTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.rw = ReleaseWorld()
        cls.w = cls.rw.w

    def state(self, revision=None):
        return services.approval_state(revision or self.rw.r1)

    def test_scenario_9_dual_approval_and_edit_invalidates(self):
        r1 = self.rw.r1
        services.decide(r1, actor=self.w.sw_head, role="software_head", decision="approve")
        self.assertEqual(self.state(), services.PENDING)  # one approval does not approve
        self.assertIsNone(services.current_approved_revision(self.rw.release))
        services.decide(r1, actor=self.w.manager, role="manager", decision="approve")
        self.assertEqual(self.state(), services.APPROVED)
        self.assertEqual(services.current_approved_revision(self.rw.release), r1)

        r2 = services.revise(self.rw.release, actor=self.w.sw_member,
                             **{**FIELDS, "recipient_notes": "Changed after approval."})
        self.assertEqual(r2.number, 2)
        self.assertEqual(self.state(r2), services.PENDING)
        self.assertIsNone(services.current_approved_revision(self.rw.release))
        # The earlier revision and its approvals are kept as they were.
        self.assertEqual(self.state(r1), services.APPROVED)
        with self.assertRaisesMessage(Exception, "latest revision"):
            services.decide(r1, actor=self.w.manager, role="manager", decision="approve")
        r = client_for(self.rw.sender).post("/api/campaigns/preview/", {
            "release_revision": r1.pk, "segment": "pilot-testers"}, format="json")
        self.assertEqual(r.status_code, 409, r.data)
        self.assertEqual(r.data["code"], "not_approved")

    def test_same_person_cannot_approve_in_both_roles(self):
        grant_capability(self.w.sw_head, Capability.IS_MANAGER, actor=self.w.admin)
        services.decide(self.rw.r1, actor=self.w.sw_head, role="software_head",
                        decision="approve")
        r = client_for(self.w.sw_head).post(f"/api/releases/{self.rw.release.pk}/decide/", {
            "revision": self.rw.r1.pk, "role": "manager", "decision": "approve"},
            format="json")
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.data["code"], "same_approver")
        self.assertEqual(self.state(), services.PENDING)

    def test_administrator_without_capability_cannot_approve(self):
        for role in ("software_head", "manager"):
            r = client_for(self.w.admin).post(f"/api/releases/{self.rw.release.pk}/decide/", {
                "revision": self.rw.r1.pk, "role": role, "decision": "approve"},
                format="json")
            self.assertEqual(r.status_code, 403, role)
        # A head of another department is not the Software head either.
        with self.assertRaises(Exception):
            services.decide(self.rw.r1, actor=self.w.asm_head, role="software_head",
                            decision="approve")
        self.assertFalse(ReleaseApproval.objects.exists())

    def test_capability_is_checked_at_decision_time(self):
        revoke_capability(self.w.manager, Capability.IS_MANAGER, actor=self.w.admin)
        with self.assertRaises(Exception):
            services.decide(self.rw.r1, actor=self.w.manager, role="manager",
                            decision="approve")

    def test_rejection_needs_reason_and_a_new_revision(self):
        with self.assertRaisesMessage(Exception, "needs a reason"):
            services.decide(self.rw.r1, actor=self.w.manager, role="manager",
                            decision="reject")
        services.decide(self.rw.r1, actor=self.w.manager, role="manager",
                        decision="reject", comment="Missing compatibility notes.")
        self.assertEqual(self.state(), services.REJECTED)
        with self.assertRaisesMessage(Exception, "new revision"):
            services.decide(self.rw.r1, actor=self.w.sw_head, role="software_head",
                            decision="approve")
        r2 = services.revise(self.rw.release, actor=self.w.sw_member,
                             **{**FIELDS, "compatibility": "FC firmware 4.5 and 4.6"})
        approve_both(r2, self.w.sw_head, self.w.manager)
        self.assertEqual(services.current_approved_revision(self.rw.release), r2)

    def test_drafting_needs_capability_and_revisions_are_immutable(self):
        r = client_for(self.w.asm_member).post("/api/releases/", {
            "version": "3.0", **FIELDS}, format="json")
        self.assertEqual(r.status_code, 403)
        r = client_for(self.w.sw_member).post("/api/releases/", {
            "version": "3.0", "source_ref": ""}, format="json")
        self.assertEqual(r.status_code, 400)
        with self.assertRaisesMessage(Exception, "Nothing changed"):
            services.revise(self.rw.release, actor=self.w.sw_member, **FIELDS)
        with self.assertRaises(PermissionError):
            self.rw.r1.save()
        client = client_for(self.w.sw_member)
        self.assertEqual(client.patch(f"/api/releases/{self.rw.release.pk}/",
                                      {"version": "9"}, format="json").status_code, 405)
        self.assertEqual(client.delete(f"/api/releases/{self.rw.release.pk}/").status_code,
                         405)

    def test_release_api_shows_state_and_is_readable_by_staff(self):
        approve_both(self.rw.r1, self.w.sw_head, self.w.manager)
        data = client_for(self.w.asm_member).get(f"/api/releases/{self.rw.release.pk}/").data
        self.assertEqual(data["current_approved_revision"], self.rw.r1.pk)
        self.assertEqual(data["revisions"][0]["state"], "approved")
        self.assertEqual({a["role"] for a in data["revisions"][0]["approvals"]},
                         {"software_head", "manager"})
        decisions = AuditLogEntry.objects.filter(entity_type="Release",
                                                 action="RELEASE_DECISION")
        self.assertEqual(decisions.count(), 2)

    def test_me_flags(self):
        perms = client_for(self.w.sw_head).get("/api/auth/me/").data["permissions"]
        self.assertEqual(perms["release_approval_roles"], ["software_head"])
        self.assertTrue(perms["can_draft_release"])
        self.assertFalse(perms["can_send_announcements"])
        perms = client_for(self.w.admin).get("/api/auth/me/").data["permissions"]
        self.assertEqual(perms["release_approval_roles"], [])


class LegacyTests(TestCase):
    def test_legacy_releases_are_never_dual_approved(self):
        pusher = make_user("pusher")
        lead = make_user("lead", Role.DEPARTMENT_LEAD)
        SoftwareUpdate.objects.create(kind="GCS", version="1.0", git_sha="abc123",
                                      release_notes="Old notes", approved_by=lead,
                                      approved_at=timezone.now(), pushed_by=pusher)
        self.assertEqual(convert_software_updates(SoftwareUpdate, Release, ReleaseRevision,
                                                  User), 1)
        self.assertEqual(convert_software_updates(SoftwareUpdate, Release, ReleaseRevision,
                                                  User), 0)  # re-running is harmless
        release = Release.objects.get(version="1.0")
        revision = release.revisions.get()
        self.assertTrue(release.legacy)
        self.assertIn("Legacy approver field: lead", revision.internal_notes)
        self.assertEqual(revision.recipient_notes, "")
        self.assertFalse(ReleaseApproval.objects.exists())
        self.assertEqual(services.approval_state(revision), services.LEGACY)
        self.assertIsNone(services.current_approved_revision(release))
        head = make_user("head")
        grant_capability(head, Capability.IS_SOFTWARE_HEAD, actor=None)
        with self.assertRaisesMessage(Exception, "legacy"):
            services.decide(revision, actor=head, role="software_head", decision="approve")


class RecipientTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.rw = ReleaseWorld()
        approve_both(cls.rw.r1, cls.rw.w.sw_head, cls.rw.w.manager)

    def test_only_synthetic_recipients_while_api_disabled(self):
        client = client_for(self.rw.sender)
        seg = client.get("/api/campaigns/segments/").data
        self.assertTrue(seg["synthetic"])
        r = client.post("/api/campaigns/preview/", {
            "release_revision": self.rw.r1.pk, "segment": "pilot-testers"}, format="json")
        self.assertEqual(r.status_code, 201, r.data)
        self.assertTrue(r.data["synthetic"])
        self.assertEqual(r.data["source"], "synthetic")
        self.assertTrue(all(x["email"].endswith("@example.invalid")
                            for x in r.data["recipients"]))

    def test_source_failure_is_an_error_not_an_empty_list(self):
        r = client_for(self.rw.sender).post("/api/campaigns/preview/", {
            "release_revision": self.rw.r1.pk, "segment": "simulate-failure"},
            format="json")
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.data["code"], "recipient_source_failed")
        self.assertFalse(RecipientSnapshot.objects.exists())
        self.assertFalse(Campaign.objects.exists())

    def test_one_invalid_row_fails_the_whole_fetch(self):
        from releases.recipients import RecipientFetch
        bad = RecipientFetch("synthetic", True, timezone.now(), recipients=[
            {"id": "a", "email": "ok@example.invalid"}, {"id": "b", "email": "nope"}])
        with mock.patch("releases.recipients.SyntheticRecipientSource.fetch_eligible",
                        return_value=bad):
            with self.assertRaises(Exception):
                services.take_snapshot(actor=self.rw.sender, segment="pilot-testers")
        self.assertFalse(RecipientSnapshot.objects.exists())

    @override_settings(SIGNUP_API_ENABLED=True)
    def test_enabled_signup_api_without_contract_fails_visibly(self):
        r = client_for(self.rw.sender).post("/api/campaigns/preview/", {
            "release_revision": self.rw.r1.pk, "segment": "all-gcs-users"}, format="json")
        self.assertEqual(r.status_code, 409)
        self.assertIn("contract is pending", r.data["detail"])

    def test_recipient_data_needs_capability(self):
        services.preview(actor=self.rw.sender, revision=self.rw.r1, segment="pilot-testers")
        for name in ("manager", "sw_head", "admin", "sw_member"):
            client = client_for(self.rw.w.actor(name))
            self.assertEqual(client.get("/api/campaigns/").data["results"], [], name)
            self.assertEqual(client.post("/api/campaigns/preview/", {
                "release_revision": self.rw.r1.pk, "segment": "pilot-testers"},
                format="json").status_code, 403, name)
            self.assertEqual(client.get("/api/campaigns/segments/").status_code, 403)
            self.assertEqual(client.get(
                "/api/audit-log/?entity_type=Campaign").data["results"], [], name)
        contacts = make_user("contacts")
        grant_capability(contacts, Capability.CAN_VIEW_CUSTOMER_CONTACTS, actor=None)
        self.assertEqual(len(client_for(contacts).get("/api/campaigns/").data["results"]), 1)


class CampaignTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.rw = ReleaseWorld()
        approve_both(cls.rw.r1, cls.rw.w.sw_head, cls.rw.w.manager)

    def setUp(self):
        self.client = client_for(self.rw.sender)

    def preview(self, segment="pilot-testers"):
        r = self.client.post("/api/campaigns/preview/", {
            "release_revision": self.rw.r1.pk, "segment": segment}, format="json")
        self.assertEqual(r.status_code, 201, r.data)
        return r.data

    def send(self, campaign_id, key="key-1"):
        return self.client.post(f"/api/campaigns/{campaign_id}/send/",
                                {"idempotency_key": key}, format="json")

    def test_preview_shows_exact_message_and_has_no_side_effects(self):
        data = self.preview()
        self.assertEqual(data["recipient_count"], 3)
        self.assertEqual(len(data["recipients"]), 3)
        self.assertEqual(data["status"], "draft")
        self.assertEqual(data["subject"], "GCS 2.6.0 is available")
        self.assertIn("Faster telemetry reconnect.", data["body_text"])
        self.assertFalse(CampaignDelivery.objects.exists())
        self.assertEqual(len(mail.outbox), 0)

    def test_internal_notes_never_rendered(self):
        data = self.preview()
        self.send(data["id"])
        drain()
        campaign = Campaign.objects.get(pk=data["id"])
        for text in (campaign.subject, campaign.body_text, campaign.body_html):
            self.assertNotIn(SENTINEL, text)
        self.assertEqual(len(mail.outbox), 3)
        for message in mail.outbox:
            self.assertNotIn(SENTINEL, message.body)
            self.assertNotIn(SENTINEL, message.alternatives[0][0])
            self.assertEqual(len(message.to), 1)  # one message per recipient
            self.assertEqual(message.cc, [])

    def test_send_is_idempotent_and_completed_campaign_is_not_resent(self):
        data = self.preview()
        first = self.send(data["id"])
        again = self.send(data["id"])
        self.assertEqual(first.status_code, 200, first.data)
        self.assertEqual(again.data["id"], first.data["id"])
        self.assertEqual(CampaignDelivery.objects.count(), 3)
        drain()
        self.assertEqual(Campaign.objects.get(pk=data["id"]).status, Campaign.COMPLETED)
        self.assertEqual(len(mail.outbox), 3)
        other = self.send(data["id"], key="key-2")
        self.assertEqual(other.status_code, 409)
        self.assertEqual(other.data["code"], "already_sent")
        r = self.client.post(f"/api/campaigns/{data['id']}/resend/", {}, format="json")
        self.assertEqual(r.status_code, 409)
        r = self.client.post(f"/api/campaigns/{data['id']}/resend/",
                             {"reason": "Two testers missed it."}, format="json")
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data["resend_of"], data["id"])
        self.assertEqual(r.data["status"], "draft")

    def test_editing_after_approval_blocks_the_existing_draft(self):
        data = self.preview()
        services.revise(self.rw.release, actor=self.rw.w.sw_member,
                        **{**FIELDS, "recipient_notes": "New text"})
        r = self.send(data["id"])
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.data["code"], "not_approved")
        self.assertFalse(CampaignDelivery.objects.exists())

    def test_stale_snapshot_and_missing_capability_block_send(self):
        data = self.preview()
        r = client_for(self.rw.w.manager).post(f"/api/campaigns/{data['id']}/send/",
                                               {"idempotency_key": "k"}, format="json")
        self.assertEqual(r.status_code, 404)  # not even visible without the capability
        RecipientSnapshot.objects.filter(campaigns__pk=data["id"]).update(
            fetched_at=timezone.now() - timedelta(hours=2))
        r = self.send(data["id"])
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.data["code"], "snapshot_stale")

    def test_scenario_10_failed_and_unknown_listed_retry_touches_failed_only(self):
        data = self.preview()
        self.send(data["id"])
        outcomes = iter([smtplib.SMTPRecipientsRefused({}), TimeoutError("timed out"), 1])

        def fake_send(message, *args, **kwargs):
            outcome = next(outcomes)
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

        with mock.patch("django.core.mail.EmailMultiAlternatives.send", fake_send):
            drain()
        rows = {d["recipient_id"]: d for d in self.client.get(
            f"/api/campaigns/{data['id']}/").data["deliveries"]}
        self.assertEqual([rows[k]["status"] for k in sorted(rows)],
                         ["failed", "unknown", "accepted"])
        self.assertEqual(Campaign.objects.get(pk=data["id"]).status,
                         Campaign.COMPLETED_WITH_FAILURES)

        r = self.client.post(f"/api/campaigns/{data['id']}/retry/", {}, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        drain()
        rows = {d["recipient_id"]: d for d in self.client.get(
            f"/api/campaigns/{data['id']}/").data["deliveries"]}
        self.assertEqual(rows["synthetic-001"]["status"], "accepted")
        self.assertEqual(rows["synthetic-001"]["attempts"], 2)
        self.assertEqual([h["kind"] for h in rows["synthetic-001"]["history"]],
                         ["send", "retry", "send"])
        self.assertEqual(rows["synthetic-002"]["status"], "unknown")  # untouched
        self.assertEqual(rows["synthetic-002"]["attempts"], 1)
        self.assertEqual(rows["synthetic-003"]["attempts"], 1)
        self.assertEqual(len(mail.outbox), 1)

        unknown = CampaignDelivery.objects.get(recipient_id="synthetic-002")
        r = self.client.post(f"/api/campaigns/{data['id']}/reconcile/", {
            "delivery": unknown.pk, "outcome": "not_sent"}, format="json")
        self.assertEqual(r.status_code, 409)  # a note of what was checked is required
        r = self.client.post(f"/api/campaigns/{data['id']}/reconcile/", {
            "delivery": unknown.pk, "outcome": "not_sent",
            "note": "Console backend log shows nothing sent."}, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        self.client.post(f"/api/campaigns/{data['id']}/retry/", {}, format="json")
        drain()
        self.assertEqual(Campaign.objects.get(pk=data["id"]).status, Campaign.COMPLETED)
        self.assertEqual(len(mail.outbox), 2)

    def test_retried_job_does_not_send_twice(self):
        from core import jobs
        data = self.preview()
        self.send(data["id"])
        drain()
        delivery = CampaignDelivery.objects.first()
        jobs.HANDLERS["campaigns.deliver"](mock.Mock(payload={"delivery_id": delivery.pk}))
        self.assertEqual(len(mail.outbox), 3)


class ConcurrentSendTests(TransactionTestCase):
    def test_double_click_creates_one_campaign_and_one_set_of_deliveries(self):
        rw = ReleaseWorld()
        approve_both(rw.r1, rw.w.sw_head, rw.w.manager)
        campaign = services.preview(actor=rw.sender, revision=rw.r1, segment="pilot-testers")
        barrier = threading.Barrier(2)
        results = []

        def click():
            try:
                barrier.wait()
                results.append(services.send(campaign, actor=rw.sender,
                                             idempotency_key="same-click").pk)
            finally:
                connection.close()

        threads = [threading.Thread(target=click) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(results, [campaign.pk, campaign.pk])
        self.assertEqual(Campaign.objects.count(), 1)
        self.assertEqual(CampaignDelivery.objects.count(), 3)
        from core.models import Job
        self.assertEqual(Job.objects.filter(kind="campaigns.deliver").count(), 3)
