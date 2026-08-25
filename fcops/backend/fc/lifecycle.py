"""The FC production lifecycle and its state machine (PRD §7, §8).

The sequence is mostly linear. Backward movement is *not* arbitrary: it is
limited to an explicit allow-list of rework routes, so "jump anywhere" can
never be introduced accidentally by a UI change. Anything outside the
allow-list requires an admin/manager override, which is itself audited.
"""
from django.db import models


class Stage(models.TextChoices):
    FABRICATION = "FABRICATION", "Fabrication"
    MANUAL_ASSEMBLY = "MANUAL_ASSEMBLY", "Manual Assembly"
    MACHINE_ASSEMBLY = "MACHINE_ASSEMBLY", "Machine Assembly / Soldering"
    QC = "QC", "QC"
    FIRMWARE = "FIRMWARE", "Firmware"
    SENSOR_VALIDATION = "SENSOR_VALIDATION", "Sensor / Functional Validation"
    MECHANICAL_ASSEMBLY = "MECHANICAL_ASSEMBLY", "Mechanical Assembly"
    BENCH_TESTING = "BENCH_TESTING", "Bench Testing"
    GROUND_TESTING = "GROUND_TESTING", "Ground Testing"
    FINAL_VALIDATION = "FINAL_VALIDATION", "Final Validation"
    MANAGER_APPROVAL = "MANAGER_APPROVAL", "Manager Approval"


STAGE_ORDER = [
    Stage.FABRICATION,
    Stage.MANUAL_ASSEMBLY,
    Stage.MACHINE_ASSEMBLY,
    Stage.QC,
    Stage.FIRMWARE,
    Stage.SENSOR_VALIDATION,
    Stage.MECHANICAL_ASSEMBLY,
    Stage.BENCH_TESTING,
    Stage.GROUND_TESTING,
    Stage.FINAL_VALIDATION,
    Stage.MANAGER_APPROVAL,
]

STAGE_INDEX = {stage: i for i, stage in enumerate(STAGE_ORDER)}

# Which department kind normally owns a stage. Used to pre-fill the assigned
# department on an issue and to suggest a root-cause owner — never to block.
STAGE_OWNER_KIND = {
    Stage.FABRICATION: "HARDWARE",
    Stage.MANUAL_ASSEMBLY: "HARDWARE",
    Stage.MACHINE_ASSEMBLY: "HARDWARE",
    Stage.QC: "QUALITY",
    Stage.FIRMWARE: "FIRMWARE",
    Stage.SENSOR_VALIDATION: "TESTING",
    Stage.MECHANICAL_ASSEMBLY: "MECHANICAL",
    Stage.BENCH_TESTING: "TESTING",
    Stage.GROUND_TESTING: "TESTING",
    Stage.FINAL_VALIDATION: "TESTING",
    Stage.MANAGER_APPROVAL: "MANAGEMENT",
}

# Stages that produce a structured Test Result / checklist (PRD §15).
TEST_STAGES = {
    Stage.SENSOR_VALIDATION,
    Stage.BENCH_TESTING,
    Stage.GROUND_TESTING,
    Stage.FINAL_VALIDATION,
}

# Explicit backward (rework) routes. PRD §8 requires these be enumerated
# rather than allowing arbitrary jumps. ASSUMPTION (see IMPLEMENTATION_NOTES):
# a late hardware defect routes back to Manual/Machine Assembly; a firmware
# defect routes back to Firmware; a mechanical defect back to Mechanical
# Assembly. Confirm with Hardware/Firmware/Testing leads.
ALLOWED_REWORK_TARGETS = {
    Stage.QC: [Stage.MANUAL_ASSEMBLY, Stage.MACHINE_ASSEMBLY],
    Stage.FIRMWARE: [Stage.QC, Stage.MANUAL_ASSEMBLY, Stage.MACHINE_ASSEMBLY],
    Stage.SENSOR_VALIDATION: [Stage.FIRMWARE, Stage.QC, Stage.MACHINE_ASSEMBLY,
                              Stage.MANUAL_ASSEMBLY],
    Stage.MECHANICAL_ASSEMBLY: [Stage.MECHANICAL_ASSEMBLY, Stage.QC],
    Stage.BENCH_TESTING: [Stage.FIRMWARE, Stage.MECHANICAL_ASSEMBLY, Stage.QC,
                          Stage.MACHINE_ASSEMBLY, Stage.MANUAL_ASSEMBLY],
    Stage.GROUND_TESTING: [Stage.FIRMWARE, Stage.MECHANICAL_ASSEMBLY,
                           Stage.BENCH_TESTING, Stage.QC, Stage.MACHINE_ASSEMBLY,
                           Stage.MANUAL_ASSEMBLY],
    Stage.FINAL_VALIDATION: [Stage.GROUND_TESTING, Stage.BENCH_TESTING,
                             Stage.FIRMWARE, Stage.MECHANICAL_ASSEMBLY],
    Stage.MANAGER_APPROVAL: [Stage.FINAL_VALIDATION, Stage.GROUND_TESTING,
                             Stage.FIRMWARE, Stage.MECHANICAL_ASSEMBLY],
}


def next_stage(stage):
    idx = STAGE_INDEX[stage]
    if idx + 1 >= len(STAGE_ORDER):
        return None
    return STAGE_ORDER[idx + 1]


def previous_stage(stage):
    idx = STAGE_INDEX[stage]
    return STAGE_ORDER[idx - 1] if idx else None


def is_forward(from_stage, to_stage):
    return STAGE_INDEX[to_stage] == STAGE_INDEX[from_stage] + 1


def rework_targets(failed_stage):
    return list(ALLOWED_REWORK_TARGETS.get(failed_stage, []))


def is_allowed_rework(failed_stage, target_stage):
    return target_stage in ALLOWED_REWORK_TARGETS.get(failed_stage, [])


def stages_between(from_stage, to_stage):
    """Stages strictly after ``from_stage`` up to and including ``to_stage``."""
    lo, hi = STAGE_INDEX[from_stage], STAGE_INDEX[to_stage]
    if hi <= lo:
        return []
    return STAGE_ORDER[lo + 1:hi + 1]
