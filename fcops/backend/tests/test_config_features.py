"""Software release records, the firmware catalogue, manager-configurable test
checklists and FC models — including the history-preservation guarantees."""
from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import Department, Role
from core.exceptions import WorkflowError
from core.models import AuditLogEntry
from fc import config_services as cfg
from fc import services as fcsvc
from fc.lifecycle import Stage
from fc.models import (ChecklistItem, ChecklistTemplate, FCModelType,
                       FirmwareBuild, FirmwareRecord, SoftwareUpdate,
                       SoftwareVersion, TestResult)

from .factories import make_department, make_fc_model, make_user

PASSWORD = "TestPass123!"


class ConfigTestCase(TestCase):
    def setUp(self):
        self.software = make_department("software", Department.KIND_SOFTWARE)
        self.firmware = make_department("firmware", Department.KIND_FIRMWARE)
        self.hardware = make_department("assembly", Department.KIND_HARDWARE)
        self.testing = make_department("testing", Department.KIND_TESTING)
        self.mgmt = make_department("management", Department.KIND_MANAGEMENT)

        self.sw_dev = make_user("swdev", Role.TECHNICIAN, self.software)
        self.sw_lead = make_user("swlead", Role.DEPARTMENT_LEAD, self.software)
        self.fw_eng = make_user("fweng", Role.TECHNICIAN, self.firmware)
        self.fw_lead = make_user("fwlead", Role.DEPARTMENT_LEAD, self.firmware)
        self.tech = make_user("tech", Role.TECHNICIAN, self.hardware)
        self.tester = make_user("tester", Role.TEST_ENGINEER, self.testing)
        self.manager = make_user("mgr", Role.MANAGER, self.mgmt)
        self.admin = make_user("admin", Role.ADMIN, self.mgmt)
        self.model = make_fc_model()

    def client_for(self, user):
        client = APIClient()
        response = client.post("/api/auth/token/",
                               {"username": user.username, "password": PASSWORD},
                               format="json")
        assert response.status_code == 200, response.content
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access']}")
        return client


# ---------------------------------------------------------------------------
# 1. Software "Push Update"
# ---------------------------------------------------------------------------
class SoftwareUpdateTests(ConfigTestCase):
    PAYLOAD = {
        "kind": "GCS", "version": "2.6.0", "git_sha": "9f2c1ab4d7e5",
        "release_notes": "Restored the serial handshake timeout to 500 ms and "
                         "fixed the telemetry reconnect loop.",
    }

    def _payload(self, **overrides):
        data = dict(self.PAYLOAD, approved_by=self.sw_lead.id)
        data.update(overrides)
        return data

    def test_software_user_can_push_an_update(self):
        response = self.client_for(self.sw_dev).post(
            "/api/software-updates/", self._payload(), format="json")
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.data["version"], "2.6.0")
        self.assertEqual(response.data["pushed_by"], self.sw_dev.id)
        self.assertEqual(response.data["approved_by"], self.sw_lead.id)
        self.assertIsNotNone(response.data["approved_at"])

    def test_non_software_user_cannot_push_an_update(self):
        for user in (self.tech, self.tester, self.fw_eng, self.manager):
            with self.subTest(user=user.username):
                response = self.client_for(user).post(
                    "/api/software-updates/", self._payload(), format="json")
                self.assertEqual(response.status_code, 403, response.content)
        self.assertFalse(SoftwareUpdate.objects.exists())

    def test_admin_can_push_an_update(self):
        response = self.client_for(self.admin).post(
            "/api/software-updates/", self._payload(), format="json")
        self.assertEqual(response.status_code, 201, response.content)

    def test_git_sha_is_required(self):
        response = self.client_for(self.sw_dev).post(
            "/api/software-updates/", self._payload(git_sha=""), format="json")
        self.assertEqual(response.status_code, 400)
        with self.assertRaises(WorkflowError) as ctx:
            cfg.push_software_update(actor=self.sw_dev, kind="GCS", version="9.9",
                                     git_sha="   ", release_notes="x",
                                     approved_by=self.sw_lead)
        self.assertEqual(ctx.exception.code, "git_sha_required")

    def test_release_notes_are_required(self):
        response = self.client_for(self.sw_dev).post(
            "/api/software-updates/", self._payload(release_notes=""),
            format="json")
        self.assertEqual(response.status_code, 400)
        with self.assertRaises(WorkflowError) as ctx:
            cfg.push_software_update(actor=self.sw_dev, kind="GCS", version="9.9",
                                     git_sha="abc", release_notes="  ",
                                     approved_by=self.sw_lead)
        self.assertEqual(ctx.exception.code, "release_notes_required")

    def test_approver_is_required_and_must_be_authorised(self):
        response = self.client_for(self.sw_dev).post(
            "/api/software-updates/", self._payload(approved_by=None),
            format="json")
        self.assertEqual(response.status_code, 400)

        with self.assertRaises(WorkflowError) as ctx:
            cfg.push_software_update(actor=self.sw_dev, kind="GCS", version="9.9",
                                     git_sha="abc", release_notes="notes",
                                     approved_by=None)
        self.assertEqual(ctx.exception.code, "approver_required")

        # A technician cannot sign off a release.
        with self.assertRaises(WorkflowError) as ctx:
            cfg.push_software_update(actor=self.sw_dev, kind="GCS", version="9.9",
                                     git_sha="abc", release_notes="notes",
                                     approved_by=self.tech)
        self.assertEqual(ctx.exception.code, "approver_not_authorised")

    def test_duplicate_version_is_rejected(self):
        client = self.client_for(self.sw_dev)
        client.post("/api/software-updates/", self._payload(), format="json")
        response = client.post("/api/software-updates/", self._payload(),
                               format="json")
        self.assertEqual(response.status_code, 409, response.content)

    def test_history_is_retrievable_by_everyone(self):
        self.client_for(self.sw_dev).post("/api/software-updates/",
                                          self._payload(), format="json")
        self.client_for(self.sw_dev).post(
            "/api/software-updates/",
            self._payload(kind="CONFIGURATOR", version="1.10.0"), format="json")
        for user in (self.tech, self.tester, self.manager):
            with self.subTest(user=user.username):
                response = self.client_for(user).get("/api/software-updates/")
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.data["count"], 2)
        row = response.data["results"][0]
        for field in ("version", "git_sha", "short_sha", "pushed_by_name",
                      "approved_by_name", "created_at", "release_notes"):
            self.assertIn(field, row)

    def test_pushing_registers_the_version_for_test_records(self):
        """The release history and the tester-facing version list must not
        drift apart."""
        self.client_for(self.sw_dev).post("/api/software-updates/",
                                          self._payload(), format="json")
        self.assertTrue(
            SoftwareVersion.objects.filter(kind="GCS", version="2.6.0").exists())

    def test_release_records_are_immutable(self):
        client = self.client_for(self.sw_dev)
        created = client.post("/api/software-updates/", self._payload(),
                              format="json")
        update_id = created.data["id"]
        self.assertEqual(
            client.patch(f"/api/software-updates/{update_id}/",
                         {"version": "9.9.9"}, format="json").status_code, 405)
        self.assertEqual(
            client.delete(f"/api/software-updates/{update_id}/").status_code, 405)

    def test_push_and_approval_are_audited(self):
        self.client_for(self.sw_dev).post("/api/software-updates/",
                                          self._payload(), format="json")
        entries = AuditLogEntry.objects.filter(entity_type="SoftwareUpdate")
        actions = set(entries.values_list("action", flat=True))
        self.assertIn(AuditLogEntry.ACTION_SOFTWARE_PUSH, actions)
        self.assertIn(AuditLogEntry.ACTION_APPROVE, actions)
        self.assertEqual(entries.first().actor, self.sw_dev)

    def test_approvers_endpoint_lists_only_authorised_users(self):
        response = self.client_for(self.sw_dev).get(
            "/api/software-updates/approvers/")
        self.assertEqual(response.status_code, 200)
        usernames = {row["username"] for row in response.data}
        self.assertIn("swlead", usernames)
        self.assertIn("mgr", usernames)
        self.assertNotIn("tech", usernames)
        self.assertNotIn("swdev", usernames)


# ---------------------------------------------------------------------------
# 2. Firmware catalogue
# ---------------------------------------------------------------------------
class FirmwareCatalogueTests(ConfigTestCase):
    BUILD = {
        "name": "KFT-FC", "firmware_type": "APJ", "version": "4.5.0",
        "git_sha": "c0ffee123456", "source_type": "CLOSED_SOURCE",
        "description": "Adds dual-GPS blending and a new baro driver.",
        "includes_scripts": True, "script_name": "prearm.lua",
        "script_version": "1.2", "is_signed": True, "is_locked": True,
        "bootloader_version": "1.3.0",
    }

    def test_firmware_user_can_create_a_build(self):
        response = self.client_for(self.fw_eng).post(
            "/api/firmware-builds/", self.BUILD, format="json")
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.data["created_by"], self.fw_eng.id)
        self.assertTrue(response.data["is_active"])
        self.assertEqual(response.data["firmware_type"], "APJ")

    def test_non_firmware_user_cannot_manage_the_catalogue(self):
        for user in (self.tech, self.tester, self.sw_dev, self.manager):
            with self.subTest(user=user.username):
                response = self.client_for(user).post(
                    "/api/firmware-builds/", self.BUILD, format="json")
                self.assertEqual(response.status_code, 403)
        self.assertFalse(FirmwareBuild.objects.exists())

    def test_everyone_can_read_the_catalogue(self):
        cfg.create_firmware_build(actor=self.fw_eng, **self.BUILD)
        for user in (self.tech, self.tester, self.manager):
            with self.subTest(user=user.username):
                self.assertEqual(
                    self.client_for(user).get("/api/firmware-builds/").status_code,
                    200)

    def test_firmware_type_is_extensible_without_a_migration(self):
        build = cfg.create_firmware_build(
            actor=self.fw_eng, **dict(self.BUILD, firmware_type="FUTURE-FORMAT"))
        self.assertEqual(build.firmware_type, "FUTURE-FORMAT")

    def test_build_can_be_edited_and_is_audited(self):
        build = cfg.create_firmware_build(actor=self.fw_eng, **self.BUILD)
        client = self.client_for(self.fw_lead)
        response = client.patch(f"/api/firmware-builds/{build.id}/",
                                {"description": "Updated notes"}, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(AuditLogEntry.objects.filter(
            entity_type="FirmwareBuild", action=AuditLogEntry.ACTION_UPDATE).exists())

    def test_build_can_be_activated_and_deactivated(self):
        build = cfg.create_firmware_build(actor=self.fw_eng, **self.BUILD)
        client = self.client_for(self.fw_eng)
        response = client.post(f"/api/firmware-builds/{build.id}/set-active/",
                               {"is_active": False}, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertFalse(response.data["is_active"])
        response = client.post(f"/api/firmware-builds/{build.id}/set-active/",
                               {"is_active": True}, format="json")
        self.assertTrue(response.data["is_active"])
        self.assertTrue(AuditLogEntry.objects.filter(
            entity_type="FirmwareBuild",
            action=AuditLogEntry.ACTION_CONFIG).exists())

    def test_flashing_copies_the_build_onto_the_fc(self):
        build = cfg.create_firmware_build(actor=self.fw_eng, **self.BUILD)
        fc = fcsvc.register_fc(fc_model=self.model, actor=self.tech)
        record = cfg.flash_build_onto_fc(fc=fc, build=build, actor=self.fw_eng)
        self.assertEqual(record.firmware_name, "KFT-FC")
        self.assertEqual(record.version, "4.5.0")
        self.assertEqual(record.build_ref, "c0ffee123456")
        self.assertTrue(record.is_signed)
        self.assertEqual(record.script_name, "prearm.lua")
        self.assertEqual(record.build, build)

    def test_inactive_build_cannot_be_flashed_onto_a_new_fc(self):
        build = cfg.create_firmware_build(actor=self.fw_eng, **self.BUILD)
        cfg.set_firmware_build_active(build, actor=self.fw_eng, is_active=False)
        fc = fcsvc.register_fc(fc_model=self.model, actor=self.tech)
        with self.assertRaises(WorkflowError) as ctx:
            cfg.flash_build_onto_fc(fc=fc, build=build, actor=self.fw_eng)
        self.assertEqual(ctx.exception.code, "build_inactive")

    def test_historical_firmware_survives_deactivation_and_editing(self):
        """An FC's record must keep showing exactly what was flashed onto it."""
        build = cfg.create_firmware_build(actor=self.fw_eng, **self.BUILD)
        fc = fcsvc.register_fc(fc_model=self.model, actor=self.tech)
        record = cfg.flash_build_onto_fc(fc=fc, build=build, actor=self.fw_eng)

        cfg.update_firmware_build(build, actor=self.fw_eng, version="4.9.9",
                                  is_signed=False, bootloader_version="9.9.9")
        cfg.set_firmware_build_active(build, actor=self.fw_eng, is_active=False)

        record.refresh_from_db()
        self.assertEqual(record.version, "4.5.0")
        self.assertTrue(record.is_signed)
        self.assertEqual(record.bootloader_version, "1.3.0")
        self.assertEqual(record.build_id, build.id)
        # And it is still reachable from the FC's own history.
        self.assertIn(record, fc.firmware_records.all())

    def test_used_build_cannot_be_deleted(self):
        build = cfg.create_firmware_build(actor=self.fw_eng, **self.BUILD)
        fc = fcsvc.register_fc(fc_model=self.model, actor=self.tech)
        cfg.flash_build_onto_fc(fc=fc, build=build, actor=self.fw_eng)
        response = self.client_for(self.fw_eng).delete(
            f"/api/firmware-builds/{build.id}/")
        self.assertEqual(response.status_code, 409, response.content)
        self.assertTrue(FirmwareBuild.objects.filter(pk=build.pk).exists())

    def test_unused_build_can_be_deleted(self):
        build = cfg.create_firmware_build(actor=self.fw_eng, **self.BUILD)
        response = self.client_for(self.fw_eng).delete(
            f"/api/firmware-builds/{build.id}/")
        self.assertEqual(response.status_code, 204)

    def test_flashes_endpoint_lists_every_fc_using_a_build(self):
        build = cfg.create_firmware_build(actor=self.fw_eng, **self.BUILD)
        for _ in range(2):
            fc = fcsvc.register_fc(fc_model=self.model, actor=self.tech)
            cfg.flash_build_onto_fc(fc=fc, build=build, actor=self.fw_eng)
        response = self.client_for(self.tech).get(
            f"/api/firmware-builds/{build.id}/flashes/")
        self.assertEqual(len(response.data), 2)


# ---------------------------------------------------------------------------
# 3. Manager-configurable test checklists
# ---------------------------------------------------------------------------
class TestConfigurationTests(ConfigTestCase):
    def setUp(self):
        super().setUp()
        self.template = ChecklistTemplate.objects.create(
            stage=Stage.GROUND_TESTING, name="Ground Testing checklist")
        self.item = cfg.add_checklist_item(
            self.template, actor=self.manager, key="gps_hold",
            label="GPS position hold within 1 m")

    def test_manager_can_add_edit_and_disable_tests(self):
        client = self.client_for(self.manager)
        response = client.post("/api/checklist-items/",
                               {"template": self.template.id, "key": "rtl",
                                "label": "RTL behaves as configured",
                                "description": "Trigger RTL from 20 m.",
                                "is_mandatory": True}, format="json")
        self.assertEqual(response.status_code, 201, response.content)
        item_id = response.data["id"]

        response = client.patch(f"/api/checklist-items/{item_id}/",
                                {"label": "RTL returns and lands"}, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.data["label"], "RTL returns and lands")

        response = client.post(f"/api/checklist-items/{item_id}/set-active/",
                               {"is_active": False}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["is_active"])

    def test_non_manager_cannot_modify_test_configuration(self):
        for user in (self.tech, self.tester, self.fw_lead, self.sw_lead):
            with self.subTest(user=user.username):
                client = self.client_for(user)
                self.assertEqual(
                    client.post("/api/checklist-items/",
                                {"template": self.template.id, "key": "x",
                                 "label": "Nope"}, format="json").status_code, 403)
                self.assertEqual(
                    client.patch(f"/api/checklist-items/{self.item.id}/",
                                 {"label": "Hacked"}, format="json").status_code,
                    403)
                self.assertEqual(
                    client.post(f"/api/checklist-items/{self.item.id}/set-active/",
                                {"is_active": False}, format="json").status_code,
                    403)
        self.item.refresh_from_db()
        self.assertEqual(self.item.label, "GPS position hold within 1 m")

    def test_testers_can_read_the_current_checklist(self):
        response = self.client_for(self.tester).get(
            f"/api/checklist-templates/{self.template.id}/current/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["version"], self.template.version)
        self.assertEqual(response.data["items"][0]["key"], "gps_hold")

    def test_version_is_bumped_on_every_change(self):
        start = ChecklistTemplate.objects.get(pk=self.template.pk).version
        cfg.add_checklist_item(self.template, actor=self.manager, key="rtl",
                               label="RTL")
        after_add = ChecklistTemplate.objects.get(pk=self.template.pk).version
        self.assertGreater(after_add, start)
        cfg.set_checklist_item_active(self.item, actor=self.manager, is_active=False)
        self.assertGreater(
            ChecklistTemplate.objects.get(pk=self.template.pk).version, after_add)

    def test_reordering_changes_presentation_order_only(self):
        second = cfg.add_checklist_item(self.template, actor=self.manager,
                                        key="rtl", label="RTL")
        client = self.client_for(self.manager)
        response = client.post(f"/api/checklist-templates/{self.template.id}/reorder/",
                               {"ordered_ids": [second.id, self.item.id]},
                               format="json")
        self.assertEqual(response.status_code, 200, response.content)
        keys = [i["key"] for i in
                self.template.as_checklist()]
        self.assertEqual(keys, ["rtl", "gps_hold"])

    def test_non_manager_cannot_reorder(self):
        self.assertEqual(
            self.client_for(self.tester).post(
                f"/api/checklist-templates/{self.template.id}/reorder/",
                {"ordered_ids": [self.item.id]}, format="json").status_code, 403)

    def test_historical_test_records_are_not_changed_by_checklist_edits(self):
        """The heart of the requirement: a manager editing the checklist must
        never alter what a past tester recorded."""
        fc = fcsvc.register_fc(fc_model=self.model, actor=self.tech)
        stage_record = fc.stage_records.first()
        answered = [{"key": "gps_hold", "label": "GPS position hold within 1 m",
                     "passed": False, "note": "drifted 3 m"}]
        result = TestResult.objects.create(
            fc=fc, stage_record=stage_record, test_type=Stage.GROUND_TESTING,
            template=self.template, template_version=self.template.version,
            checklist_results=answered, overall_passed=False, tester=self.tester)
        original_version = result.template_version

        # The manager now renames the test, disables it and adds another.
        cfg.update_checklist_item(self.item, actor=self.manager,
                                  label="GPS hold within 0.5 m")
        cfg.set_checklist_item_active(self.item, actor=self.manager,
                                      is_active=False)
        cfg.add_checklist_item(self.template, actor=self.manager, key="vibe",
                               label="Vibration within limits")

        result.refresh_from_db()
        self.assertEqual(result.checklist_results, answered)
        self.assertEqual(result.checklist_results[0]["label"],
                         "GPS position hold within 1 m")
        self.assertFalse(result.overall_passed)
        self.assertEqual(result.template_version, original_version)
        self.assertLess(result.template_version, self.template.version)

        # The live checklist has moved on, as it should have.
        self.assertEqual([i["key"] for i in self.template.as_checklist()], ["vibe"])

    def test_used_test_cannot_be_deleted_or_rekeyed(self):
        fc = fcsvc.register_fc(fc_model=self.model, actor=self.tech)
        TestResult.objects.create(
            fc=fc, stage_record=fc.stage_records.first(),
            test_type=Stage.GROUND_TESTING, template=self.template,
            checklist_results=[{"key": "gps_hold", "label": "GPS", "passed": True}],
            tester=self.tester)
        self.assertTrue(self.item.is_in_use)

        with self.assertRaises(WorkflowError) as ctx:
            cfg.delete_checklist_item(self.item, actor=self.manager)
        self.assertEqual(ctx.exception.code, "item_in_use")

        with self.assertRaises(WorkflowError) as ctx:
            cfg.update_checklist_item(self.item, actor=self.manager, key="renamed")
        self.assertEqual(ctx.exception.code, "key_locked")

    def test_unused_test_can_be_deleted(self):
        self.assertEqual(
            self.client_for(self.manager).delete(
                f"/api/checklist-items/{self.item.id}/").status_code, 204)

    def test_configuration_changes_are_audited(self):
        cfg.add_checklist_item(self.template, actor=self.manager, key="rtl",
                               label="RTL")
        cfg.set_checklist_item_active(self.item, actor=self.manager,
                                      is_active=False)
        cfg.reorder_checklist_items(self.template, actor=self.manager,
                                    ordered_ids=[self.item.id])
        actions = AuditLogEntry.objects.filter(
            action=AuditLogEntry.ACTION_CONFIG).values_list("entity_type", flat=True)
        self.assertIn("ChecklistItem", set(actions))
        self.assertIn("ChecklistTemplate", set(actions))


# ---------------------------------------------------------------------------
# 4. Manager-managed FC models
# ---------------------------------------------------------------------------
class FCModelManagementTests(ConfigTestCase):
    def test_manager_can_add_edit_and_archive_a_model(self):
        client = self.client_for(self.manager)
        response = client.post("/api/fc-models/",
                               {"name": "KFT-FC-PRO", "code": "kft-fc-pro",
                                "description": "High-payload variant"},
                               format="json")
        self.assertEqual(response.status_code, 201, response.content)
        model_id = response.data["id"]

        response = client.patch(f"/api/fc-models/{model_id}/",
                                {"description": "Heavy-lift variant"},
                                format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["description"], "Heavy-lift variant")

        response = client.post(f"/api/fc-models/{model_id}/set-active/",
                               {"is_active": False}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["is_active"])

    def test_non_manager_cannot_manage_models(self):
        for user in (self.tech, self.tester, self.fw_lead, self.sw_lead):
            with self.subTest(user=user.username):
                response = self.client_for(user).post(
                    "/api/fc-models/", {"name": "X", "code": "x"}, format="json")
                self.assertEqual(response.status_code, 403)

    def test_everyone_can_read_models_for_registration(self):
        for user in (self.tech, self.tester):
            self.assertEqual(
                self.client_for(user).get("/api/fc-models/").status_code, 200)

    def test_historical_fcs_survive_model_archiving(self):
        fc = fcsvc.register_fc(fc_model=self.model, actor=self.tech)
        cfg.set_fc_model_active(self.model, actor=self.manager, is_active=False)
        fc.refresh_from_db()
        self.assertEqual(fc.fc_model, self.model)
        response = self.client_for(self.tech).get(f"/api/fcs/{fc.id}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["fc_model_name"], self.model.name)
        # And the FC can still move through its lifecycle.
        fcsvc.start_stage(fc, actor=self.tech)
        record = fcsvc.complete_stage(fc, passed=True, actor=self.tech)
        self.assertEqual(record.status, "PASSED")

    def test_model_in_use_cannot_be_deleted(self):
        fcsvc.register_fc(fc_model=self.model, actor=self.tech)
        response = self.client_for(self.manager).delete(
            f"/api/fc-models/{self.model.id}/")
        self.assertEqual(response.status_code, 409, response.content)
        self.assertTrue(FCModelType.objects.filter(pk=self.model.pk).exists())

    def test_serial_generation_is_unaffected(self):
        first = fcsvc.register_fc(fc_model=self.model, actor=self.tech)
        new_model = cfg.create_fc_model(actor=self.manager, name="KFT-FC-NANO",
                                        code="kft-fc-nano")
        second = fcsvc.register_fc(fc_model=new_model, actor=self.tech)
        self.assertRegex(second.serial, r"^FC-\d{4}-\d{5}$")
        self.assertNotEqual(first.serial, second.serial)
        self.assertEqual(int(second.serial.split("-")[-1]),
                         int(first.serial.split("-")[-1]) + 1)

    def test_model_changes_are_audited(self):
        model = cfg.create_fc_model(actor=self.manager, name="KFT-FC-X",
                                    code="kft-fc-x")
        cfg.set_fc_model_active(model, actor=self.manager, is_active=False)
        entries = AuditLogEntry.objects.filter(entity_type="FCModelType",
                                               action=AuditLogEntry.ACTION_CONFIG)
        self.assertGreaterEqual(entries.count(), 2)
        self.assertEqual(entries.last().actor, self.manager)


class CapabilityFlagTests(ConfigTestCase):
    """The frontend hides what a user cannot do; these flags are what it reads.
    The backend enforces the same rules independently."""

    def test_flags_match_the_enforced_permissions(self):
        expectations = {
            self.sw_dev: {"can_push_software_update": True,
                          "can_manage_firmware": False,
                          "can_configure_tests": False},
            self.fw_eng: {"can_push_software_update": False,
                          "can_manage_firmware": True,
                          "can_configure_tests": False},
            self.manager: {"can_push_software_update": False,
                           "can_manage_firmware": False,
                           "can_configure_tests": True,
                           "can_manage_fc_models": True},
            self.admin: {"can_push_software_update": True,
                         "can_manage_firmware": True,
                         "can_configure_tests": True},
            self.tech: {"can_push_software_update": False,
                        "can_manage_firmware": False,
                        "can_configure_tests": False},
        }
        for user, expected in expectations.items():
            with self.subTest(user=user.username):
                response = self.client_for(user).get("/api/users/me/")
                for flag, value in expected.items():
                    self.assertEqual(response.data["permissions"][flag], value,
                                     f"{user.username}.{flag}")
