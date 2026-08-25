"""Seed reference data (departments, roles, FC models, checklists, software
versions) and, with --demo, a small set of realistic FCs and issues."""
import random

from django.core.management.base import BaseCommand
from django.db import transaction

from accounts.models import Department, Role, User
from fc.lifecycle import Stage
from fc.models import (ChecklistTemplate, FCModelType, ParameterProfile,
                       SoftwareVersion)

DEPARTMENTS = [
    ("Fabrication", "fabrication", Department.KIND_HARDWARE),
    ("Manual Assembly", "manual-assembly", Department.KIND_HARDWARE),
    ("Machine Assembly", "machine-assembly", Department.KIND_HARDWARE),
    ("Quality Control", "qc", Department.KIND_QUALITY),
    ("Hardware Rework", "hardware-rework", Department.KIND_HARDWARE),
    ("Firmware", "firmware", Department.KIND_FIRMWARE),
    ("Software (GCS / Configurator)", "software", Department.KIND_SOFTWARE),
    ("Mechanical Design & Assembly", "mechanical", Department.KIND_MECHANICAL),
    ("Ground & Bench Testing", "testing", Department.KIND_TESTING),
    ("Management", "management", Department.KIND_MANAGEMENT),
]

USERS = [
    ("admin", "Admin User", Role.ADMIN, "management"),
    ("mgr.rao", "Anjali Rao", Role.MANAGER, "management"),
    ("hw.lead", "Vikram Shetty", Role.DEPARTMENT_LEAD, "machine-assembly"),
    ("hw.tech1", "Priya Nair", Role.TECHNICIAN, "manual-assembly"),
    ("hw.tech2", "Rahul Menon", Role.TECHNICIAN, "machine-assembly"),
    ("qc.tech", "Sneha Iyer", Role.TECHNICIAN, "qc"),
    ("fw.lead", "Arjun Das", Role.DEPARTMENT_LEAD, "firmware"),
    ("fw.eng", "Meera Krishnan", Role.TECHNICIAN, "firmware"),
    ("sw.eng", "Karthik Reddy", Role.TECHNICIAN, "software"),
    ("mech.tech", "Divya Pillai", Role.TECHNICIAN, "mechanical"),
    ("test.eng1", "Sanjay Kumar", Role.TEST_ENGINEER, "testing"),
    ("test.eng2", "Nisha Varma", Role.TEST_ENGINEER, "testing"),
]

CHECKLISTS = {
    Stage.SENSOR_VALIDATION: [
        ("imu_detected", "IMU detected and calibrated"),
        ("baro_detected", "Barometer detected, altitude stable"),
        ("mag_detected", "Magnetometer detected, heading correct"),
        ("gps_detected", "GPS module detected"),
        ("gps_lock", "GPS 3D fix acquired (< 90 s)"),
        ("power_rails", "Power rails within tolerance"),
    ],
    Stage.BENCH_TESTING: [
        ("gcs_connect", "GCS connects over telemetry"),
        ("motor_outputs", "All motor outputs respond"),
        ("rc_link", "RC link bind and range OK"),
        ("failsafe", "Failsafe triggers correctly"),
        ("logging", "Onboard logging writes to storage"),
    ],
    Stage.GROUND_TESTING: [
        ("arming", "Arms without pre-arm errors"),
        ("attitude_hold", "Attitude hold stable"),
        ("gps_hold", "GPS position hold within 1 m"),
        ("rtl", "RTL behaves as configured"),
        ("vibration", "Vibration levels within limits"),
    ],
    Stage.FINAL_VALIDATION: [
        ("params_locked", "Parameter profile locked and matches spec"),
        ("fw_signed", "Firmware signed and version recorded"),
        ("labels", "Serial label and casing correct"),
        ("docs", "Production record complete"),
    ],
}


class Command(BaseCommand):
    help = "Seed reference data. Use --demo for sample FCs and issues."

    def add_arguments(self, parser):
        parser.add_argument("--demo", action="store_true",
                            help="Also create demo FCs, issues and history")
        parser.add_argument("--password", default="ChangeMe123!",
                            help="Password for seeded users")

    @transaction.atomic
    def handle(self, *args, **options):
        password = options["password"]
        depts = {}
        for name, code, kind in DEPARTMENTS:
            dept, _ = Department.objects.get_or_create(
                code=code, defaults={"name": name, "kind": kind})
            depts[code] = dept

        for username, full_name, role, dept_code in USERS:
            user, created = User.objects.get_or_create(
                username=username,
                defaults={"full_name": full_name, "role": role,
                          "department": depts[dept_code],
                          "email": f"{username}@example.internal"})
            if created:
                user.set_password(password)
                if role == Role.ADMIN:
                    user.is_staff = True
                    user.is_superuser = True
                user.save()

        models = {}
        for name, code in [("KFT-FC-V4", "kft-fc-v4"), ("KFT-FC-MINI", "kft-fc-mini")]:
            models[code], _ = FCModelType.objects.get_or_create(
                code=code, defaults={"name": name})

        for kind, versions in [(SoftwareVersion.KIND_GCS, ["2.4.1", "2.5.0", "2.5.1"]),
                               (SoftwareVersion.KIND_CONFIGURATOR,
                                ["1.8.0", "1.9.0", "1.9.2"])]:
            for v in versions:
                SoftwareVersion.objects.get_or_create(kind=kind, version=v)

        for name, version in [("standard-quad", "1.0"), ("standard-quad", "1.1"),
                              ("heavy-lift", "2.0")]:
            ParameterProfile.objects.get_or_create(name=name, version=version)

        for stage, items in CHECKLISTS.items():
            ChecklistTemplate.objects.get_or_create(
                stage=stage, name=f"Default {Stage(stage).label} checklist",
                fc_model=None,
                defaults={"items": [{"key": k, "label": l} for k, l in items]})

        self.stdout.write(self.style.SUCCESS(
            f"Seeded {len(depts)} departments, {User.objects.count()} users, "
            f"{FCModelType.objects.count()} FC models."))

        if options["demo"]:
            self._demo(depts, models)

    def _demo(self, depts, models):
        from fc import services as fcsvc
        from fc.models import FirmwareRecord, StageStatus
        from issues import services as issvc
        from issues.models import Category, IssueStatus, Severity

        admin = User.objects.get(username="admin")
        tech = User.objects.get(username="hw.tech1")
        qc = User.objects.get(username="qc.tech")
        fw = User.objects.get(username="fw.eng")
        fwlead = User.objects.get(username="fw.lead")
        test1 = User.objects.get(username="test.eng1")
        test2 = User.objects.get(username="test.eng2")
        mgr = User.objects.get(username="mgr.rao")

        # A handful of fully-completed historical FCs so search has material.
        histories = [
            dict(title="GPS not detected after firmware flashing",
                 symptoms="GPS module not detected in GCS after flashing firmware "
                          "4.3.7. No satellites, no fix. Serial port shows no data.",
                 stage=Stage.SENSOR_VALIDATION, category=Category.HARDWARE,
                 root_cause="GPS connector pin 3 had a cold solder joint from machine "
                            "soldering; intermittent contact only under vibration.",
                 resolution="Reflowed the connector, re-tested GPS lock in 42 s. "
                            "Added connector to QC visual inspection list.",
                 fwv="4.3.7"),
            dict(title="Barometer altitude drifting during bench test",
                 symptoms="Barometer reports altitude drift of 4-6 m over 2 minutes "
                          "on the bench with no movement. Temperature compensation "
                          "looks wrong.",
                 stage=Stage.BENCH_TESTING, category=Category.FIRMWARE,
                 root_cause="Parameter profile standard-quad 1.0 shipped with the "
                            "wrong baro temperature-compensation coefficients.",
                 resolution="Moved to parameter profile standard-quad 1.1 and "
                            "re-flashed. Drift under 0.5 m.",
                 fwv="4.3.7"),
            dict(title="GCS fails to connect to FC over USB",
                 symptoms="GCS 2.5.0 cannot connect to the flight controller over "
                          "USB. Configurator connects fine. Handshake times out.",
                 stage=Stage.BENCH_TESTING, category=Category.SOFTWARE,
                 root_cause="GCS 2.5.0 regression: serial handshake timeout reduced "
                            "to 200 ms, too short for this bootloader.",
                 resolution="Software released GCS 2.5.1 with the timeout restored. "
                            "All benches upgraded.",
                 fwv="4.4.0"),
            dict(title="Firmware flashing fails at 40 percent",
                 symptoms="Flashing aborts at around 40 percent with a checksum "
                          "error. Retry fails at the same point.",
                 stage=Stage.FIRMWARE, category=Category.FIRMWARE,
                 root_cause="Corrupted signed firmware artifact on the flashing "
                            "station; the build had been copied over a dropped "
                            "network share.",
                 resolution="Re-downloaded the signed artifact, verified SHA, "
                            "flashing completed. Added SHA verification to the "
                            "flashing SOP.",
                 fwv="4.4.0"),
        ]

        for spec in histories:
            fc = fcsvc.register_fc(fc_model=models["kft-fc-v4"],
                                   hardware_revision="rev-C", pcb_batch="B-2026-11",
                                   actor=admin)
            # Walk up to the discovery stage.
            for stage in [Stage.FABRICATION, Stage.MANUAL_ASSEMBLY,
                          Stage.MACHINE_ASSEMBLY, Stage.QC, Stage.FIRMWARE,
                          Stage.SENSOR_VALIDATION, Stage.MECHANICAL_ASSEMBLY,
                          Stage.BENCH_TESTING]:
                if stage == Stage.FIRMWARE:
                    FirmwareRecord.objects.create(
                        fc=fc, firmware_name="KFT-FC", version=spec["fwv"],
                        source_type=FirmwareRecord.SOURCE_CLOSED, is_signed=True,
                        bootloader_version="1.2.0", build_ref="a1b2c3d",
                        operator=fw)
                if stage == spec["stage"]:
                    break
                fcsvc.start_stage(fc, stage, actor=tech)
                fcsvc.complete_stage(fc, stage, passed=True, actor=tech)
            fcsvc.start_stage(fc, spec["stage"], actor=test1)
            fcsvc.complete_stage(fc, spec["stage"], passed=False, actor=test1,
                                 notes="See linked issue")
            issue = issvc.create_issue(
                fc=fc, title=spec["title"], symptoms=spec["symptoms"],
                actor=test1, discovered_stage=spec["stage"],
                category=spec["category"], severity=Severity.MAJOR,
                assigned_department=depts["firmware"]
                if spec["category"] == Category.FIRMWARE else depts["machine-assembly"],
                version_overrides={"gcs_version": "2.5.0",
                                   "configurator_version": "1.9.0"})
            issvc.add_note(issue, author=fwlead, note="Reproduced on the bench.")
            issvc.change_status(issue, IssueStatus.RESOLVED, actor=fwlead,
                                root_cause=spec["root_cause"],
                                resolution=spec["resolution"],
                                root_cause_department=depts["machine-assembly"]
                                if spec["category"] == Category.HARDWARE
                                else depts["firmware"])
            issvc.change_status(issue, IssueStatus.VERIFIED, actor=test2,
                                note="Re-tested, symptom gone.")
            issvc.change_status(issue, IssueStatus.CLOSED, actor=test2)
            issvc.promote_to_known_issue(issue, actor=fwlead)

        # Two FCs mid-production, one blocked.
        for _ in range(3):
            fc = fcsvc.register_fc(fc_model=models["kft-fc-v4"],
                                   hardware_revision="rev-C", actor=admin)
            for stage in [Stage.FABRICATION, Stage.MANUAL_ASSEMBLY,
                          Stage.MACHINE_ASSEMBLY]:
                fcsvc.start_stage(fc, stage, actor=tech)
                fcsvc.complete_stage(fc, stage, passed=True, actor=tech)

        fc = fcsvc.register_fc(fc_model=models["kft-fc-mini"],
                               hardware_revision="rev-A", actor=admin)
        for stage in [Stage.FABRICATION, Stage.MANUAL_ASSEMBLY,
                      Stage.MACHINE_ASSEMBLY]:
            fcsvc.start_stage(fc, stage, actor=tech)
            fcsvc.complete_stage(fc, stage, passed=True, actor=tech)
        fcsvc.start_stage(fc, Stage.QC, actor=qc)
        fcsvc.complete_stage(fc, Stage.QC, passed=False, actor=qc,
                             notes="Solder bridge on U7")
        issvc.create_issue(fc=fc, title="Solder bridge between U7 pins 4 and 5",
                           symptoms="Visible solder bridge on U7 under inspection "
                                    "scope. Short between pins 4 and 5.",
                           actor=qc, category=Category.HARDWARE,
                           severity=Severity.BLOCKER,
                           assigned_department=depts["machine-assembly"])

        self.stdout.write(self.style.SUCCESS("Demo data created."))
