"""WP1 access matrix: every actor x every surface, through the API.

Replaces the prototype's universal-read test (test_everyone_can_read_everything).
"""
import shutil
import tempfile

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import TeamMembership
from accounts.services import close_membership
from core.serializers import NO_ACCESS
from issues.models import KnownIssue

from .access_fixtures import AccessWorld

MEDIA = tempfile.mkdtemp(prefix="wp1-media-")
SEARCH_WORDS = "intermittent dropout"


@override_settings(MEDIA_ROOT=MEDIA)
class AccessMatrixTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def setUp(self):
        self.w = AccessWorld()

    def client_for(self, user):
        client = APIClient()
        client.force_authenticate(user)
        return client

    def each_actor(self):
        for name in AccessWorld.ACTORS:
            with self.subTest(actor=name):
                yield name, self.client_for(self.w.actor(name)), {
                    i.pk for i in self.w.expected_issues(name)}

    def test_issue_list_and_detail(self):
        all_issues = (self.w.sw_issue, self.w.asm_issue, self.w.sw_verify)
        for name, client, expected in self.each_actor():
            r = client.get("/api/issues/", {"page_size": 100})
            self.assertEqual({row["id"] for row in r.data["results"]}, expected)
            self.assertEqual(r.data["count"], len(expected))
            for issue in all_issues:
                code = client.get(f"/api/issues/{issue.pk}/").status_code
                self.assertEqual(code, 200 if issue.pk in expected else 404, issue.key)

    def test_search_and_list_text_query(self):
        for name, client, expected in self.each_actor():
            r = client.get("/api/issues/search/", {"q": SEARCH_WORDS})
            self.assertEqual({row["id"] for row in r.data["results"]}, expected)
            self.assertEqual(r.data["count"], len(expected))
            r = client.get("/api/issues/", {"q": SEARCH_WORDS})
            self.assertEqual(r.data["count"], len(expected))

    def test_similar_results_rank_only_visible_issues(self):
        for name, client, expected in self.each_actor():
            r = client.get("/api/issues/similar-search/",
                           {"text": SEARCH_WORDS, "limit": 1})
            got = {row["id"] for row in r.data["similar_issues"]}
            # limit=1: a hidden match must not take the only slot.
            self.assertEqual(len(got), min(1, len(expected)))
            self.assertTrue(got <= expected)
            if expected:
                own = next(iter(expected))
                r = client.get(f"/api/issues/{own}/similar/")
                self.assertTrue({row["id"] for row in r.data["similar_issues"]}
                                <= expected - {own})

    def test_dashboard_counts(self):
        for name, client, expected in self.each_actor():
            r = client.get("/api/dashboard/summary/")
            self.assertEqual(r.status_code, 200)
            self.assertEqual(r.data["open_issue_total"], len(expected))
            shown = {i["id"] for fc in r.data["blocked"] for i in fc["issues"]}
            self.assertTrue(shown <= expected)

    def test_attachment_download(self):
        url = f"/api/issue-attachments/{self.w.attachment.pk}/download/"
        for name, client, expected in self.each_actor():
            r = client.get(url)
            if self.w.sw_issue.pk in expected:
                self.assertEqual(r.status_code, 200)
                self.assertEqual(b"".join(r.streaming_content), b"hello")
                self.assertIn("attachment", r["Content-Disposition"])
                self.assertEqual(r["X-Content-Type-Options"], "nosniff")
            else:
                self.assertEqual(r.status_code, 404)

    def test_attachments_are_not_publicly_fetchable(self):
        self.assertEqual(APIClient().get(
            f"/api/issue-attachments/{self.w.attachment.pk}/download/").status_code, 401)
        self.assertEqual(APIClient().get(
            "/media/" + self.w.attachment.file.name).status_code, 404)
        r = self.client_for(self.w.sw_head).get(f"/api/issues/{self.w.sw_issue.pk}/")
        self.assertEqual(r.data["attachments"][0]["url"],
                         f"/api/issue-attachments/{self.w.attachment.pk}/download/")
        self.assertNotIn("file", r.data["attachments"][0])

    def test_fc_timeline_and_issue_lists_hide_unseen_issues(self):
        client = self.client_for(self.w.asm_member)
        events = client.get(f"/api/fcs/{self.w.fc.pk}/timeline/").data
        self.assertEqual({e["issue"] for e in events if e["issue"]},
                         {self.w.asm_issue.pk})
        rows = client.get(f"/api/fcs/{self.w.fc.pk}/issues/").data
        self.assertEqual({row["id"] for row in rows}, {self.w.asm_issue.pk})
        audit = client.get(f"/api/fcs/{self.w.fc.pk}/audit_log/").data
        issue_ids = {e["entity_id"] for e in audit if e["entity_type"] == "Issue"}
        self.assertEqual(issue_ids, {str(self.w.asm_issue.pk)})

    def test_audit_log_scope(self):
        for name, client, expected in self.each_actor():
            r = client.get("/api/audit-log/", {"entity_type": "Issue",
                                               "page_size": 500})
            self.assertEqual({int(e["entity_id"]) for e in r.data["results"]},
                             expected)
        accounts = self.client_for(self.w.admin).get(
            "/api/audit-log/", {"entity_type": "TeamMembership"}).data
        self.assertTrue(accounts["count"] >= 1)
        hidden = self.client_for(self.w.sw_member).get(
            "/api/audit-log/", {"entity_type": "TeamMembership"}).data
        self.assertEqual(hidden["count"], 0)

    # --- named acceptance items -------------------------------------------
    def test_scenario_5_software_issue_hidden_from_assembly(self):
        sw = self.client_for(self.w.sw_member)
        asm = self.client_for(self.w.asm_member)
        self.assertEqual(sw.get(f"/api/issues/{self.w.sw_issue.pk}/").status_code, 200)
        self.assertEqual(asm.get(f"/api/issues/{self.w.sw_issue.pk}/").status_code, 404)
        for name in ("sw_head", "asm_head", "manager"):
            self.assertEqual(self.w.expected_issues(name),
                             {self.w.sw_issue, self.w.asm_issue, self.w.sw_verify})

    def test_verifier_sees_only_the_assigned_software_issue(self):
        client = self.client_for(self.w.verifier)
        self.assertEqual(client.get(f"/api/issues/{self.w.sw_verify.pk}/").status_code, 200)
        self.assertEqual(client.get(f"/api/issues/{self.w.sw_issue.pk}/").status_code, 404)

    def test_membership_closure_removes_access_immediately(self):
        client = self.client_for(self.w.sw_member)
        url = f"/api/issues/{self.w.sw_issue.pk}/"
        self.assertEqual(client.get(url).status_code, 200)
        close_membership(TeamMembership.objects.get(user=self.w.sw_member,
                                                    active_to__isnull=True),
                         actor=self.w.admin)
        self.assertEqual(client.get(url).status_code, 404)
        # ex_member's membership was closed yesterday.
        self.assertEqual(self.client_for(self.w.ex_member).get(url).status_code, 404)

    def test_admin_sees_no_issues_by_being_admin(self):
        self.assertTrue(self.w.admin.is_superuser)
        r = self.client_for(self.w.admin).get("/api/issues/")
        self.assertEqual(r.data["count"], 0)

    def test_notification_renders_without_detail_after_access_lost(self):
        client = self.client_for(self.w.sw_member)
        rows = client.get("/api/notifications/").data["results"]
        mine = [n for n in rows if n["target_id"] == self.w.sw_issue.pk]
        self.assertTrue(mine)
        self.assertIn(self.w.sw_issue.key, mine[0]["message"])
        close_membership(TeamMembership.objects.get(user=self.w.sw_member,
                                                    active_to__isnull=True),
                         actor=self.w.admin)
        rows = client.get("/api/notifications/").data["results"]
        lost = [n for n in rows if n["target_id"] == self.w.sw_issue.pk]
        self.assertEqual(lost[0]["message"], NO_ACCESS)
        self.assertEqual(lost[0]["link"], "")
        self.assertNotIn(self.w.sw_issue.key, str(rows))

    # --- relationship validation ------------------------------------------
    def test_cannot_attach_to_or_link_an_unseen_issue(self):
        client = self.client_for(self.w.asm_member)
        r = client.post("/api/issue-attachments/",
                        {"issue": self.w.sw_issue.pk, "file": _upload()},
                        format="multipart")
        self.assertEqual(r.status_code, 400)
        self.assertIn("issue", r.data)
        stage_record = self.w.fc.stage_records.first()
        r = client.post("/api/test-results/", {
            "fc": self.w.fc.pk, "stage_record": stage_record.pk,
            "test_type": stage_record.stage, "linked_issue": self.w.sw_issue.pk,
            "checklist_results": []}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("linked_issue", r.data)

    def test_fc_records_follow_fc_scope(self):
        # Assembly is an FC-visible department kind; Management is not.
        from accounts.models import Department, Role
        from .factories import make_department, make_user
        mgmt = make_department("management", Department.KIND_MANAGEMENT)
        office = make_user("office", Role.TECHNICIAN, mgmt)
        self.assertEqual(self.client_for(self.w.asm_member).get(
            f"/api/fcs/{self.w.fc.pk}/").status_code, 200)
        client = self.client_for(office)
        self.assertEqual(client.get(f"/api/fcs/{self.w.fc.pk}/").status_code, 404)
        self.assertEqual(client.get("/api/stage-records/").data["count"], 0)

    # --- knowledge ---------------------------------------------------------
    def test_knowledge_audience_and_scoped_occurrences(self):
        known = KnownIssue.objects.create(
            title="Telemetry dropout", symptoms_summary="s", root_cause="r",
            resolution="x")
        for issue in (self.w.sw_issue, self.w.asm_issue):
            issue.known_issue = known
            issue.save(update_fields=["known_issue"])
        member = self.client_for(self.w.asm_member)
        self.assertEqual(member.get(f"/api/known-issues/{known.pk}/").status_code, 404)
        known.audience = KnownIssue.AUDIENCE_ALL_STAFF
        known.save(update_fields=["audience"])
        r = member.get(f"/api/known-issues/{known.pk}/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["occurrence_count"], 1)
        self.assertEqual(r.data["first_occurrence_issue"], self.w.asm_issue.pk)
        occurrences = member.get(f"/api/known-issues/{known.pk}/occurrences/").data
        self.assertEqual([row["id"] for row in occurrences], [self.w.asm_issue.pk])
        head = self.client_for(self.w.sw_head).get(f"/api/known-issues/{known.pk}/")
        self.assertEqual(head.data["occurrence_count"], 2)
        known.audience = KnownIssue.AUDIENCE_DEPARTMENTS
        known.save(update_fields=["audience"])
        known.audience_departments.set([self.w.firmware])
        self.assertEqual(member.get(f"/api/known-issues/{known.pk}/").status_code, 404)
        self.assertEqual(self.client_for(self.w.fw_member).get(
            f"/api/known-issues/{known.pk}/").status_code, 200)


def _upload():
    from django.core.files.uploadedfile import SimpleUploadedFile
    return SimpleUploadedFile("x.txt", b"x")
