"""API-level tests: authentication, RBAC enforcement on writes, universal read
access, and the endpoints the frontend depends on."""
from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import Department, Role
from fc import services as fcsvc
from fc.lifecycle import Stage
from issues import services as issvc
from issues.models import Category, IssueStatus, Severity

from .factories import make_department, make_fc_model, make_user

PASSWORD = "TestPass123!"


class ApiTestCase(TestCase):
    def setUp(self):
        self.hw = make_department("assembly", Department.KIND_HARDWARE)
        self.fwd = make_department("firmware", Department.KIND_FIRMWARE)
        self.testing = make_department("testing", Department.KIND_TESTING)
        self.tech = make_user("tech", Role.TECHNICIAN, self.hw)
        self.lead = make_user("lead", Role.DEPARTMENT_LEAD, self.fwd)
        self.tester = make_user("tester", Role.TEST_ENGINEER, self.testing)
        self.manager = make_user("mgr", Role.MANAGER, self.testing)
        self.admin = make_user("admin", Role.ADMIN, self.testing)
        self.model = make_fc_model()

    def client_for(self, user):
        client = APIClient()
        response = client.post("/api/auth/token/",
                               {"username": user.username, "password": PASSWORD},
                               format="json")
        assert response.status_code == 200, response.content
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access']}")
        return client


class AuthTests(ApiTestCase):
    def test_unauthenticated_requests_are_rejected(self):
        self.assertEqual(APIClient().get("/api/fcs/").status_code, 401)

    def test_bad_credentials_rejected(self):
        response = APIClient().post("/api/auth/token/",
                                    {"username": "tech", "password": "wrong"},
                                    format="json")
        self.assertEqual(response.status_code, 401)

    def test_me_endpoint_exposes_permissions(self):
        response = self.client_for(self.manager).get("/api/users/me/")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["permissions"]["can_approve"])
        response = self.client_for(self.tech).get("/api/users/me/")
        self.assertFalse(response.data["permissions"]["can_approve"])

    def test_health_is_public(self):
        self.assertEqual(APIClient().get("/api/health/").status_code, 200)


class RbacTests(ApiTestCase):
    def test_everyone_can_read_everything(self):
        fc = fcsvc.register_fc(fc_model=self.model, actor=self.tech)
        for user in (self.tech, self.lead, self.tester, self.manager, self.admin):
            client = self.client_for(user)
            self.assertEqual(client.get("/api/fcs/").status_code, 200)
            self.assertEqual(client.get(f"/api/fcs/{fc.id}/timeline/").status_code, 200)
            self.assertEqual(client.get("/api/issues/").status_code, 200)
            self.assertEqual(client.get("/api/known-issues/").status_code, 200)
            self.assertEqual(client.get("/api/audit-log/").status_code, 200)

    def test_only_admin_manages_users_and_departments(self):
        payload = {"name": "New Dept", "code": "new-dept", "kind": "HARDWARE"}
        self.assertEqual(
            self.client_for(self.tech).post("/api/departments/", payload,
                                            format="json").status_code, 403)
        self.assertEqual(
            self.client_for(self.manager).post("/api/departments/", payload,
                                               format="json").status_code, 403)
        self.assertEqual(
            self.client_for(self.admin).post("/api/departments/", payload,
                                             format="json").status_code, 201)

    def test_technician_cannot_approve_fc(self):
        fc = fcsvc.register_fc(fc_model=self.model, actor=self.tech)
        response = self.client_for(self.tech).post(
            f"/api/fcs/{fc.id}/approve/", {"approve": True}, format="json")
        self.assertEqual(response.status_code, 403)

    def test_manager_approval_path(self):
        fc = fcsvc.register_fc(fc_model=self.model, actor=self.tech)
        while fc.current_stage != Stage.MANAGER_APPROVAL:
            fcsvc.start_stage(fc, actor=self.tech)
            fcsvc.complete_stage(fc, passed=True, actor=self.tech)
            fc.refresh_from_db()
        response = self.client_for(self.manager).post(
            f"/api/fcs/{fc.id}/approve/", {"approve": True, "note": "ok"},
            format="json")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.data["status"], "APPROVED")

    def test_technician_cannot_promote_known_issue(self):
        fc = fcsvc.register_fc(fc_model=self.model, actor=self.tech)
        issue = issvc.create_issue(fc=fc, title="t", symptoms="s", actor=self.tech,
                                   assigned_department=self.fwd)
        issvc.change_status(issue, IssueStatus.RESOLVED, actor=self.lead,
                            root_cause="rc", resolution="res")
        self.assertEqual(
            self.client_for(self.tech).post(f"/api/issues/{issue.id}/promote/", {},
                                            format="json").status_code, 403)
        self.assertEqual(
            self.client_for(self.lead).post(f"/api/issues/{issue.id}/promote/", {},
                                            format="json").status_code, 201)

    def test_fcs_and_issues_cannot_be_deleted(self):
        fc = fcsvc.register_fc(fc_model=self.model, actor=self.tech)
        self.assertEqual(
            self.client_for(self.admin).delete(f"/api/fcs/{fc.id}/").status_code, 405)


class WorkflowApiTests(ApiTestCase):
    def test_full_flow_through_the_api(self):
        client = self.client_for(self.tech)
        response = client.post("/api/fcs/", {"fc_model": self.model.id,
                                             "hardware_revision": "rev-C"},
                               format="json")
        self.assertEqual(response.status_code, 201, response.content)
        fc_id = response.data["id"]

        # Progress through to QC.
        for _ in range(3):
            client.post(f"/api/fcs/{fc_id}/start_stage/", {}, format="json")
            r = client.post(f"/api/fcs/{fc_id}/pass_stage/", {}, format="json")
            self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.data["fc"]["current_stage"], Stage.QC)

        # Fail QC and raise an issue.
        client.post(f"/api/fcs/{fc_id}/start_stage/", {}, format="json")
        r = client.post(f"/api/fcs/{fc_id}/fail_stage/",
                        {"notes": "solder bridge"}, format="json")
        stage_record_id = r.data["stage_record"]["id"]

        r = client.post("/api/issues/", {
            "fc": fc_id, "title": "Solder bridge on U7",
            "symptoms": "Visible solder bridge between U7 pins 4 and 5",
            "severity": Severity.BLOCKER, "category": Category.HARDWARE,
            "assigned_department": self.hw.id,
            "discovered_stage_record": stage_record_id}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        issue_id = r.data["id"]
        self.assertEqual(r.data["discovering_department"], self.hw.id)

        # FC is blocked.
        r = client.get(f"/api/fcs/{fc_id}/")
        self.assertEqual(r.data["status"], "BLOCKED")

        # Invalid transition is rejected server-side with 409.
        r = client.post(f"/api/issues/{issue_id}/status/",
                        {"status": IssueStatus.CLOSED}, format="json")
        self.assertEqual(r.status_code, 409, r.content)

        # Notes, reassignment, resolution.
        r = client.post(f"/api/issues/{issue_id}/notes/",
                        {"note": "Confirmed under the scope"}, format="json")
        self.assertEqual(r.status_code, 201)
        lead_client = self.client_for(self.lead)
        r = lead_client.post(f"/api/issues/{issue_id}/reassign/",
                             {"to_department": self.fwd.id, "reason": "check config"},
                             format="json")
        self.assertEqual(r.status_code, 200, r.content)
        r = lead_client.post(f"/api/issues/{issue_id}/reassign/",
                             {"to_department": self.hw.id}, format="json")
        self.assertEqual(r.status_code, 400)

        r = lead_client.post(f"/api/issues/{issue_id}/status/",
                             {"status": IssueStatus.RESOLVED,
                              "root_cause": "Solder bridge from machine soldering",
                              "resolution": "Reworked the joint"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)

        # Rework.
        r = client.post("/api/rework-records/",
                        {"stage_record": stage_record_id,
                         "description": "Reflowed U7",
                         "return_to_stage": Stage.MACHINE_ASSEMBLY,
                         "originating_issue": issue_id}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        rework_id = r.data["id"]
        r = client.post(f"/api/rework-records/{rework_id}/complete/",
                        {"outcome": "COMPLETED"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)

        # Verification by a different person.
        tester_client = self.client_for(self.tester)
        r = tester_client.post(f"/api/issues/{issue_id}/status/",
                               {"status": IssueStatus.VERIFIED}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        r = tester_client.post(f"/api/issues/{issue_id}/status/",
                               {"status": IssueStatus.CLOSED}, format="json")
        self.assertEqual(r.status_code, 200)

        # Timeline records the whole history.
        r = client.get(f"/api/fcs/{fc_id}/timeline/")
        kinds = [e["kind"] for e in r.data]
        for expected in ("FC_REGISTERED", "STAGE_FAILED", "ISSUE_OPENED",
                         "ISSUE_REASSIGNED", "REWORK_OPENED", "ISSUE_VERIFIED"):
            self.assertIn(expected, kinds)

        # Audit log for the FC is populated.
        r = client.get(f"/api/fcs/{fc_id}/audit_log/")
        self.assertTrue(len(r.data) > 5)

    def test_similar_issues_endpoint(self):
        fc = fcsvc.register_fc(fc_model=self.model, actor=self.tech)
        issue = issvc.create_issue(
            fc=fc, title="GPS not detected after firmware flashing",
            symptoms="GPS module not detected, no satellites",
            actor=self.tech, assigned_department=self.hw,
            version_overrides={"firmware_version": "4.3.7"})
        issvc.change_status(issue, IssueStatus.RESOLVED, actor=self.lead,
                            root_cause="cold joint", resolution="reflow")
        client = self.client_for(self.tester)
        r = client.get("/api/issues/similar-search/",
                       {"text": "GPS not detected after flashing",
                        "firmware_version": "4.3.7"})
        self.assertEqual(r.status_code, 200, r.content)
        self.assertTrue(r.data["similar_issues"])
        self.assertEqual(r.data["similar_issues"][0]["key"], issue.key)

    def test_search_endpoint_with_filters(self):
        fc = fcsvc.register_fc(fc_model=self.model, actor=self.tech)
        issvc.create_issue(fc=fc, title="Baro drift", symptoms="altitude drifts",
                           actor=self.tech, assigned_department=self.fwd,
                           version_overrides={"firmware_version": "4.4.0"})
        client = self.client_for(self.tech)
        r = client.get("/api/issues/search/", {"q": "altitude drifts"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["count"], 1)
        r = client.get("/api/issues/search/", {"firmware_version": "9.9.9"})
        self.assertEqual(r.data["count"], 0)

    def test_dashboard_summary(self):
        fc = fcsvc.register_fc(fc_model=self.model, actor=self.tech)
        issvc.create_issue(fc=fc, title="t", symptoms="s", actor=self.tech,
                           severity=Severity.BLOCKER, assigned_department=self.hw)
        r = self.client_for(self.manager).get("/api/dashboard/summary/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["fc_total"], 1)
        self.assertEqual(r.data["open_issue_total"], 1)
        self.assertTrue(r.data["blocked"])

    def test_notifications_created_for_assigned_department(self):
        fc = fcsvc.register_fc(fc_model=self.model, actor=self.tech)
        issvc.create_issue(fc=fc, title="t", symptoms="s", actor=self.tester,
                           severity=Severity.BLOCKER, assigned_department=self.fwd)
        r = self.client_for(self.lead).get("/api/notifications/unread_count/")
        self.assertGreaterEqual(r.data["count"], 1)
        r = self.client_for(self.manager).get("/api/notifications/")
        self.assertTrue(any("BLOCKER" in n["message"] or "Blocker" in n["message"]
                            for n in r.data["results"]))

    def test_lifecycle_metadata_endpoint(self):
        r = self.client_for(self.tech).get("/api/lifecycle/")
        self.assertEqual(len(r.data["stages"]), 11)
        self.assertIn(Stage.GROUND_TESTING, r.data["rework_targets"])

    def test_firmware_and_test_result_records(self):
        client = self.client_for(self.lead)
        fc = fcsvc.register_fc(fc_model=self.model, actor=self.tech)
        r = client.post("/api/firmware-records/",
                        {"fc": fc.id, "firmware_name": "KFT-FC", "version": "4.4.0",
                         "source_type": "CLOSED_SOURCE", "is_signed": True,
                         "bootloader_version": "1.2.0", "build_ref": "abc123"},
                        format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertTrue(r.data["is_current"])

        stage_record = fc.stage_records.first()
        r = client.post("/api/test-results/",
                        {"fc": fc.id, "stage_record": stage_record.id,
                         "test_type": Stage.SENSOR_VALIDATION,
                         "checklist_results": [
                             {"key": "gps_lock", "label": "GPS lock", "passed": False},
                             {"key": "imu", "label": "IMU", "passed": True}]},
                        format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertFalse(r.data["overall_passed"])
