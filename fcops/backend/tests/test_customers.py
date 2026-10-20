"""WP9: contacts never inherit issue/FC/manager access."""
import json
from django.test import TestCase, override_settings
from rest_framework.test import APIClient
from accounts.models import Capability
from accounts.services import grant_capability, revoke_capability
from customers import services
from customers.models import Customer, CustomerContact, Deployment
from issues import services as issues
from issues.models import IssueParticipant
from core.models import AuditLogEntry
from .access_fixtures import AccessWorld


class CustomerTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = AccessWorld()
        cls.customer = services.save_record(Customer, actor=cls.w.sw_head,
            changes={"name": "Engineering customer", "region": "West", "notes": "Summary"})
        cls.deployment = services.save_record(Deployment, actor=cls.w.sw_head,
            changes={"customer": cls.customer, "site_name": "Site A", "units": [cls.w.fc],
                     "gcs_version_at_handover": "1.2"})
        grant_capability(cls.w.svc_member, Capability.CAN_VIEW_CUSTOMER_CONTACTS,
                         actor=cls.w.admin)
        cls.contact = services.save_record(CustomerContact, actor=cls.w.svc_member,
            changes={"customer": cls.customer, "name": "Private Contact",
                     "email": "private@example.invalid", "phone": "555-0101", "role": "operator"})
        issues.edit_issue(cls.w.sw_issue, actor=cls.w.sw_head,
                          changes={"customer": cls.customer, "deployment": cls.deployment})

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.w.sw_member)

    def rows(self, url):
        r = self.client.get(url)
        self.assertEqual(r.status_code, 200, r.data)
        return r.data.get("results", r.data) if isinstance(r.data, dict) else r.data

    def assert_no_contacts(self, data):
        text = json.dumps(data)
        for value in ("Private Contact", "private@example.invalid", "555-0101"):
            self.assertNotIn(value, text)

    def test_summary_and_deployment_visible_without_contacts(self):
        self.assertEqual(len(self.rows("/api/customers/")), 1)
        d = self.rows("/api/deployments/")[0]
        self.assertEqual(d["units"], [self.w.fc.pk])
        self.assertEqual(d["gcs_version_at_handover"], "1.2")
        self.assertEqual(self.rows("/api/customer-contacts/"), [])
        self.assertEqual(self.client.get(f"/api/customer-contacts/{self.contact.pk}/").status_code, 404)

    def test_issue_detail_lists_search_and_audit_do_not_leak_contacts(self):
        for path in (f"/api/issues/{self.w.sw_issue.pk}/", "/api/issues/",
                     "/api/issues/?q=telemetry", "/api/issues/search/?q=telemetry",
                     f"/api/fcs/{self.w.fc.pk}/issues/",
                     f"/api/fcs/{self.w.fc.pk}/audit_log/",
                     "/api/customers/", "/api/deployments/", "/api/audit-log/"):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200, response.data)
            self.assert_no_contacts(response.data)

    def test_cross_team_sharing_does_not_expose_contacts(self):
        issues.add_participant(self.w.sw_issue, user=self.w.asm_member,
            role=IssueParticipant.ROLE_COLLABORATOR, actor=self.w.sw_head)
        self.client.force_authenticate(self.w.asm_member)
        self.assertEqual(self.client.get(f"/api/issues/{self.w.sw_issue.pk}/").status_code, 200)
        self.assertEqual(self.rows("/api/customer-contacts/"), [])
        self.assert_no_contacts(self.rows("/api/audit-log/"))

    def test_manager_and_admin_do_not_implicitly_get_contacts(self):
        for user in (self.w.manager, self.w.admin):
            self.client.force_authenticate(user)
            self.assertEqual(self.rows("/api/customer-contacts/"), [])
            self.assert_no_contacts(self.rows("/api/audit-log/"))

    def test_capability_grants_and_revokes_contacts_and_their_audit(self):
        self.client.force_authenticate(self.w.svc_member)
        self.assertEqual(self.rows("/api/customer-contacts/")[0]["email"], "private@example.invalid")
        self.assertTrue(any(x["entity_type"] == "CustomerContact" for x in self.rows("/api/audit-log/")))
        revoke_capability(self.w.svc_member, Capability.CAN_VIEW_CUSTOMER_CONTACTS, actor=self.w.admin)
        self.assertEqual(self.rows("/api/customer-contacts/"), [])
        self.assert_no_contacts(self.rows("/api/audit-log/"))

    def test_no_fc_access_hides_summaries_related_ids_and_audit(self):
        issues.add_participant(self.w.sw_issue, user=self.w.admin,
            role=IssueParticipant.ROLE_COLLABORATOR, actor=self.w.sw_head)
        self.client.force_authenticate(self.w.admin)
        for path in ("/api/customers/", "/api/deployments/"):
            self.assertEqual(self.rows(path), [])
        r = self.client.get(f"/api/issues/{self.w.sw_issue.pk}/")
        self.assertIsNone(r.data["customer"])
        self.assertIsNone(r.data["deployment"])
        for resource, pk in (("customers", self.customer.pk), ("deployments", self.deployment.pk)):
            self.assertEqual(self.client.get(f"/api/{resource}/{pk}/").status_code, 404)
        entries = self.rows("/api/audit-log/")
        self.assertFalse(any(x["entity_type"] in ("Customer", "Deployment") for x in entries))
        for entry in entries:
            if entry["entity_type"] == "Issue":
                for snapshot in (entry["before"], entry["after"]):
                    if snapshot:
                        self.assertNotIn("customer", snapshot)
                        self.assertNotIn("deployment", snapshot)
        # Sharing an issue still permits ordinary edits without summary access.
        self.assertEqual(self.client.patch(f"/api/issues/{self.w.sw_issue.pk}/",
            {"description": "Added investigation context"}, format="json").status_code, 200)
        r = self.client.patch(f"/api/issues/{self.w.sw_issue.pk}/",
            {"customer": self.customer.pk}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_post_submission_links_nullable_audited_and_customer_consistent(self):
        self.client.force_authenticate(self.w.sw_head)
        url = f"/api/issues/{self.w.sw_verify.pk}/"
        self.assertIsNone(self.client.get(url).data["customer"])
        r = self.client.patch(url, {"customer": self.customer.pk, "deployment": self.deployment.pk}, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data["deployment"], self.deployment.pk)
        other = services.save_record(Customer, actor=self.w.sw_head, changes={"name": "Other"})
        r = self.client.patch(url, {"customer": other.pk}, format="json")
        self.assertEqual(r.status_code, 409, r.data)
        r = self.client.patch(url, {"customer": None, "deployment": None}, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertTrue(AuditLogEntry.objects.filter(entity_type="Issue", entity_id=str(self.w.sw_verify.pk),
            after__has_key="deployment").exists())

    def test_summary_writes_are_head_only_and_contact_writes_require_capability(self):
        self.assertEqual(self.client.post("/api/customers/", {"name": "Denied"}).status_code, 403)
        self.assertEqual(self.client.post("/api/customer-contacts/", {
            "customer": self.customer.pk, "name": "Denied"}).status_code, 400)
        self.client.force_authenticate(self.w.sw_head)
        r = self.client.post("/api/customers/", {"name": "Created"})
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(self.client.delete(f"/api/customers/{r.data['id']}/").status_code, 405)
        r = self.client.post("/api/deployments/", {"customer": self.customer.pk,
            "site_name": "Site B", "units": [self.w.fc.pk]}, format="json")
        self.assertEqual(r.status_code, 201, r.data)
        self.client.force_authenticate(self.w.svc_member)
        r = self.client.patch(f"/api/customer-contacts/{self.contact.pk}/",
            {"phone": "555-0102"}, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        self.client.force_authenticate(self.w.manager)
        self.assert_no_contacts(self.rows("/api/audit-log/"))

    def test_contact_grant_is_independent_of_fc_visibility(self):
        grant_capability(self.w.admin, Capability.CAN_VIEW_CUSTOMER_CONTACTS, actor=self.w.manager)
        self.client.force_authenticate(self.w.admin)
        self.assertEqual(self.rows("/api/customers/"), [])
        self.assertEqual(len(self.rows("/api/customer-contacts/")), 1)
        r = self.client.post("/api/customer-contacts/", {"customer": self.customer.pk,
            "name": "Another private contact"})
        self.assertEqual(r.status_code, 201, r.data)

    def test_summary_scope_tracks_fc_policy_configuration(self):
        with override_settings(FC_VISIBLE_DEPARTMENT_KINDS=[]):
            self.assertEqual(self.rows("/api/customers/"), [])
            self.assertEqual(self.rows("/api/deployments/"), [])
            self.client.force_authenticate(self.w.sw_head)
            self.assertEqual(len(self.rows("/api/customers/")), 1)

    def test_deployment_customer_change_cannot_invalidate_issue_context(self):
        self.client.force_authenticate(self.w.sw_head)
        other = services.save_record(Customer, actor=self.w.sw_head, changes={"name": "Other"})
        r = self.client.patch(f"/api/deployments/{self.deployment.pk}/",
            {"customer": other.pk}, format="json")
        self.assertEqual(r.status_code, 409, r.data)
        self.deployment.refresh_from_db()
        self.assertEqual(self.deployment.customer_id, self.customer.pk)

    def test_related_ids_are_scoped_for_deployment_and_contact_writes(self):
        self.client.force_authenticate(self.w.sw_head)
        for data in ({"site_name": "Invalid", "customer": 999999},
                     {"site_name": "Invalid", "customer": self.customer.pk, "units": [999999]}):
            self.assertEqual(self.client.post("/api/deployments/", data, format="json").status_code, 400)
        self.client.force_authenticate(self.w.svc_member)
        self.assertEqual(self.client.patch(f"/api/customer-contacts/{self.contact.pk}/",
            {"customer": 999999}, format="json").status_code, 400)
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get("/api/customer-contacts/").status_code, 401)
