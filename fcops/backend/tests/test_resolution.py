"""WP7: typed notes, resolution, independent verification, reopening."""
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from core.exceptions import WorkflowError
from issues import services as issvc
from issues.models import (IssueEvent, IssueInvestigationNote, IssueStatus, KnownIssue,
                           Resolution, Verification)

from .access_fixtures import AccessWorld


class ResolutionTests(TestCase):
    def setUp(self):
        self.w = AccessWorld()
        self.issue = self.w.sw_verify  # Software; `verifier` is assigned verifier

    def client_for(self, user):
        client = APIClient()
        client.force_authenticate(user)
        return client

    def resolve(self, user, **extra):
        r = self.client_for(user).post(
            f"/api/issues/{self.issue.pk}/status/",
            {"status": "RESOLVED", "resolution": "retry the write", **extra},
            format="json")
        self.assertEqual(r.status_code, 200, r.data)
        return r

    def test_scenario_7_resolve_is_not_verify_and_resolver_cannot_verify(self):
        r = self.resolve(self.w.sw_head, root_cause="race in writer",
                         root_cause_status="confirmed")
        self.assertEqual(r.data["status"], "RESOLVED")
        self.assertIsNone(r.data["verified_by"])
        # the resolver is refused through the API and the service
        r = self.client_for(self.w.sw_head).post(
            f"/api/issues/{self.issue.pk}/verify/",
            {"result": "pass", "what_tested": "ran it"}, format="json")
        self.assertEqual((r.status_code, r.data["code"]),
                         (409, "independent_verification_required"))
        with self.assertRaises(WorkflowError):
            issvc.verify(self.issue, verifier=self.w.sw_head, passed=True,
                         what_tested="x")
        # the assigned verifier fails it: back to investigating, history kept
        r = self.client_for(self.w.verifier).post(
            f"/api/issues/{self.issue.pk}/verify/",
            {"result": "fail", "what_tested": "wrote 200 params", "notes": "2 failed"},
            format="json")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data["status"], "INVESTIGATING")
        self.assertEqual(len(r.data["resolutions"]), 1)
        self.assertEqual(r.data["resolutions"][0]["verifications"][0]["result"], "fail")
        # a second resolution then passes
        self.resolve(self.w.sw_head, resolution="serialise writes")
        r = self.client_for(self.w.verifier).post(
            f"/api/issues/{self.issue.pk}/verify/",
            {"result": "pass", "what_tested": "wrote 1000 params"}, format="json")
        self.assertEqual(r.data["status"], "VERIFIED")
        self.assertEqual([len(x["verifications"]) for x in r.data["resolutions"]], [1, 1])

    def test_resolving_with_unknown_root_cause_is_allowed(self):
        r = self.resolve(self.w.sw_head, root_cause_status="unknown",
                         unresolved_risks="may recur on slow links")
        res = Resolution.objects.get(issue=self.issue)
        self.assertEqual((res.root_cause_status, res.unresolved_risks),
                         ("unknown", "may recur on slow links"))
        self.assertEqual(r.data["root_cause"], "")

    def test_confirmed_root_cause_needs_a_description(self):
        r = self.client_for(self.w.sw_head).post(
            f"/api/issues/{self.issue.pk}/status/",
            {"status": "RESOLVED", "resolution": "x", "root_cause_status": "confirmed"},
            format="json")
        self.assertEqual(r.status_code, 409)

    def test_reopen_after_verification_keeps_history(self):
        self.resolve(self.w.sw_head, root_cause_status="suspected")
        issvc.verify(self.issue, verifier=self.w.verifier, passed=True, what_tested="t")
        self.issue.refresh_from_db()
        with self.assertRaises(WorkflowError):
            issvc.reopen(self.issue, actor=self.w.sw_member, reason="saw it again")
        r = self.client_for(self.w.sw_head).post(
            f"/api/issues/{self.issue.pk}/reopen/", {"reason": "seen again in field"},
            format="json")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data["status"], "INVESTIGATING")
        self.assertEqual(r.data["resolutions"][0]["verifications"][0]["result"], "pass")
        types = list(IssueEvent.objects.filter(issue=self.issue)
                     .values_list("type", flat=True))
        self.assertEqual([t for t in types if t in ("resolved", "verified", "reopened")],
                         ["resolved", "verified", "reopened"])

    @override_settings(REOPEN_ALLOWED=["manager"])
    def test_reopen_authority_is_configurable(self):
        self.resolve(self.w.sw_head)
        self.issue.refresh_from_db()
        with self.assertRaises(WorkflowError):
            issvc.reopen(self.issue, actor=self.w.sw_head, reason="r")
        issvc.reopen(self.issue, actor=self.w.manager, reason="r")

    def test_notes_are_typed_and_corrections_keep_the_original(self):
        client = self.client_for(self.w.sw_member)
        first = client.post(f"/api/issues/{self.issue.pk}/notes/",
                            {"note": "looks like a race", "note_type": "suspected_cause"},
                            format="json").data
        second = client.post(f"/api/issues/{self.issue.pk}/notes/",
                             {"note": "confirmed race in writer",
                              "note_type": "confirmed_cause",
                              "supersedes": first["id"]}, format="json").data
        self.assertEqual(second["supersedes"], first["id"])
        self.assertEqual(IssueInvestigationNote.objects.get(pk=first["id"]).note,
                         "looks like a race")
        r = client.post(f"/api/issues/{self.issue.pk}/notes/",
                        {"note": "x", "note_type": "gossip"}, format="json")
        self.assertEqual(r.status_code, 409)

    def test_status_cannot_be_patched_around_the_workflow(self):
        r = self.client_for(self.w.sw_head).patch(
            f"/api/issues/{self.issue.pk}/", {"status": "CLOSED"}, format="json")
        self.assertEqual((r.status_code, r.data["code"]), (409, "immutable_field"))

    def test_promotion_sets_the_audience(self):
        self.resolve(self.w.sw_head)
        r = self.client_for(self.w.sw_head).post(
            f"/api/issues/{self.issue.pk}/promote/",
            {"audience": "all_staff", "symptoms_summary": "writes fail (redacted)"},
            format="json")
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(KnownIssue.objects.get().audience, "all_staff")
        self.assertEqual(Verification.objects.count(), 0)
        self.assertEqual(IssueStatus.RESOLVED, self.issue.__class__.objects.get(
            pk=self.issue.pk).status)
