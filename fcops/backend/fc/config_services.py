"""Services for the configuration and catalogue features: software release
records, the firmware build catalogue, test-checklist configuration and FC
models.

Same rules as the lifecycle engine in :mod:`fc.services` — every write goes
through here so authorisation, validation and audit logging cannot be bypassed
by adding an endpoint, and nothing that has been used in production history is
ever hard-deleted.
"""
from django.db import transaction
from django.utils import timezone

from core import audit
from core.exceptions import WorkflowError
from core.models import AuditLogEntry

from .lifecycle import Stage
from .models import (ChecklistItem, ChecklistTemplate, FCModelType, FirmwareBuild,
                     FirmwareRecord)


# --------------------------------------------------------------------------
# Firmware catalogue
# --------------------------------------------------------------------------
def _require_firmware_authority(actor):
    if not actor or not actor.can_manage_firmware:
        raise WorkflowError(
            "Only the Firmware department (or an admin) may manage the firmware "
            "catalogue.", code="forbidden")


@transaction.atomic
def create_firmware_build(*, actor, **fields):
    _require_firmware_authority(actor)
    name = (fields.get("name") or "").strip()
    version = (fields.get("version") or "").strip()
    if not name or not version:
        raise WorkflowError("A firmware build needs a name and a version.",
                            code="name_and_version_required")
    if FirmwareBuild.objects.filter(name=name, version=version).exists():
        raise WorkflowError(f"Firmware '{name} {version}' already exists.",
                            code="duplicate_build")
    fc_models = fields.pop("fc_models", None)
    build = FirmwareBuild.objects.create(created_by=actor, **fields)
    if fc_models:
        build.fc_models.set(fc_models)
    audit.record(build, AuditLogEntry.ACTION_CREATE, actor=actor,
                 after=audit.snapshot(build),
                 note=f"Firmware build {build} added to the catalogue")
    return build


@transaction.atomic
def update_firmware_build(build, *, actor, **fields):
    _require_firmware_authority(actor)
    before = audit.snapshot(build)
    fc_models = fields.pop("fc_models", None)
    for key, value in fields.items():
        setattr(build, key, value)
    build.save()
    if fc_models is not None:
        build.fc_models.set(fc_models)
    audit.record_change(build, AuditLogEntry.ACTION_UPDATE, before,
                        note="Firmware build updated", actor=actor)
    return build


@transaction.atomic
def set_firmware_build_active(build, *, actor, is_active):
    """Retire or restore a build.

    Deactivating only removes it from the pick-list for *new* flashes. Every
    FirmwareRecord already written keeps its own copy of the fields, so an FC's
    history still shows exactly what was flashed onto it.
    """
    _require_firmware_authority(actor)
    if build.is_active == is_active:
        return build
    before = audit.snapshot(build)
    build.is_active = is_active
    build.save(update_fields=["is_active", "updated_at"])
    audit.record_change(
        build, AuditLogEntry.ACTION_CONFIG, before, actor=actor,
        note=("Firmware build activated" if is_active else
              f"Firmware build deactivated ({build.flash_count} historical "
              f"flash record(s) preserved)"))
    return build


def delete_firmware_build(build, *, actor):
    _require_firmware_authority(actor)
    if build.is_in_use:
        raise WorkflowError(
            f"'{build}' has been flashed onto {build.flash_count} FC(s) and "
            "cannot be deleted. Deactivate it instead so the history stays "
            "intact.", code="build_in_use")
    audit.record(build, AuditLogEntry.ACTION_CONFIG, actor=actor,
                 before=audit.snapshot(build),
                 note="Unused firmware build deleted")
    build.delete()


@transaction.atomic
def flash_build_onto_fc(*, fc, build, actor, stage_record=None,
                        flashing_result=FirmwareRecord.RESULT_SUCCESS,
                        config_result=FirmwareRecord.RESULT_SUCCESS, notes=""):
    """Create the per-FC firmware record by copying a catalogue build.

    The copy is the point: the FC's record must not change later just because
    someone edited the catalogue entry.
    """
    from . import services as lifecycle

    if not build.is_active:
        raise WorkflowError(
            f"'{build}' is inactive and cannot be flashed onto a new FC.",
            code="build_inactive")

    record = FirmwareRecord.objects.create(
        fc=fc, stage_record=stage_record, build=build,
        firmware_name=build.name, version=build.version,
        source_type=build.source_type, is_signed=build.is_signed,
        is_locked=build.is_locked, bootloader_version=build.bootloader_version,
        build_ref=build.git_sha, parameter_profile=build.parameter_profile,
        script_name=build.script_name if build.includes_scripts else "",
        script_version=build.script_version if build.includes_scripts else "",
        flashing_result=flashing_result, config_result=config_result,
        operator=actor, notes=notes)
    audit.record(record, AuditLogEntry.ACTION_CREATE, actor=actor,
                 after=audit.snapshot(record), fc=fc,
                 note=f"Flashed catalogue build {build}")
    lifecycle.log_event(
        fc, "FIRMWARE_RECORDED",
        f"Firmware {build.name} {build.version} flashed "
        f"({record.get_flashing_result_display()})",
        detail=notes, stage=Stage.FIRMWARE, actor=actor)
    return record


# --------------------------------------------------------------------------
# Test checklist configuration (manager)
# --------------------------------------------------------------------------
def _require_manager(actor, what):
    if not actor or not actor.is_manager_role:
        raise WorkflowError(f"Only a manager or admin may {what}.",
                            code="forbidden")


@transaction.atomic
def create_checklist_template(*, actor, stage, name, fc_model=None):
    _require_manager(actor, "configure test checklists")
    template = ChecklistTemplate.objects.create(stage=stage, name=name,
                                                fc_model=fc_model)
    audit.record(template, AuditLogEntry.ACTION_CONFIG, actor=actor,
                 after=audit.snapshot(template), note="Checklist template created")
    return template


@transaction.atomic
def add_checklist_item(template, *, actor, key, label, description="",
                       is_mandatory=True, order=None):
    _require_manager(actor, "configure test checklists")
    key = (key or "").strip()
    label = (label or "").strip()
    if not label:
        raise WorkflowError("A test needs a label.", code="label_required")
    if not key:
        from django.utils.text import slugify
        key = slugify(label)[:64]
    if template.checklist_items.filter(key=key).exists():
        raise WorkflowError(f"A test with the key '{key}' already exists in this "
                            "checklist.", code="duplicate_key")
    if order is None:
        order = (template.checklist_items.count() + 1) * 10
    item = ChecklistItem.objects.create(
        template=template, key=key, label=label, description=description,
        is_mandatory=is_mandatory, order=order)
    version = template.bump_version()
    audit.record(item, AuditLogEntry.ACTION_CONFIG, actor=actor,
                 after=audit.snapshot(item),
                 note=f"Test '{label}' added to {template.name} (v{version})")
    return item


@transaction.atomic
def update_checklist_item(item, *, actor, **fields):
    _require_manager(actor, "configure test checklists")
    if "key" in fields and fields["key"] != item.key and item.is_in_use:
        raise WorkflowError(
            "This test has already been answered on historical FC records, so "
            "its key cannot change — past results are stored against it. "
            "Change the label instead.", code="key_locked")
    before = audit.snapshot(item)
    for key, value in fields.items():
        setattr(item, key, value)
    item.save()
    version = item.template.bump_version()
    audit.record_change(item, AuditLogEntry.ACTION_CONFIG, before, actor=actor,
                        note=f"Test updated in {item.template.name} (v{version})")
    return item


@transaction.atomic
def set_checklist_item_active(item, *, actor, is_active):
    """Retire a test without destroying the record of past answers."""
    _require_manager(actor, "configure test checklists")
    if item.is_active == is_active:
        return item
    before = audit.snapshot(item)
    item.is_active = is_active
    item.save(update_fields=["is_active", "updated_at"])
    version = item.template.bump_version()
    audit.record_change(
        item, AuditLogEntry.ACTION_CONFIG, before, actor=actor,
        note=(f"Test '{item.label}' enabled (v{version})" if is_active else
              f"Test '{item.label}' disabled (v{version}); historical results "
              f"keep their answers"))
    return item


@transaction.atomic
def reorder_checklist_items(template, *, actor, ordered_ids):
    _require_manager(actor, "configure test checklists")
    items = {item.pk: item for item in template.checklist_items.all()}
    unknown = [i for i in ordered_ids if i not in items]
    if unknown:
        raise WorkflowError(f"Unknown checklist item(s): {unknown}.",
                            code="unknown_item")
    before = [items[pk].label for pk in
              sorted(items, key=lambda k: (items[k].order, k))]
    for position, pk in enumerate(ordered_ids):
        item = items[pk]
        item.order = (position + 1) * 10
        item.save(update_fields=["order", "updated_at"])
    version = template.bump_version()
    after = [items[pk].label for pk in ordered_ids]
    audit.record(template, AuditLogEntry.ACTION_CONFIG, actor=actor,
                 before={"order": before}, after={"order": after},
                 note=f"Tests reordered in {template.name} (v{version})")
    return template.active_items()


@transaction.atomic
def delete_checklist_item(item, *, actor):
    _require_manager(actor, "configure test checklists")
    if item.is_in_use:
        raise WorkflowError(
            "This test has already been answered on historical FC records and "
            "cannot be deleted — that would destroy audit history. Disable it "
            "instead.", code="item_in_use")
    template = item.template
    audit.record(item, AuditLogEntry.ACTION_CONFIG, actor=actor,
                 before=audit.snapshot(item),
                 note=f"Unused test '{item.label}' removed from {template.name}")
    item.delete()
    template.bump_version()


# --------------------------------------------------------------------------
# FC models (manager)
# --------------------------------------------------------------------------
@transaction.atomic
def create_fc_model(*, actor, name, code, description=""):
    _require_manager(actor, "manage FC models")
    model = FCModelType.objects.create(name=name, code=code,
                                       description=description)
    audit.record(model, AuditLogEntry.ACTION_CONFIG, actor=actor,
                 after=audit.snapshot(model), note=f"FC model '{name}' created")
    return model


@transaction.atomic
def update_fc_model(model, *, actor, **fields):
    _require_manager(actor, "manage FC models")
    before = audit.snapshot(model)
    for key, value in fields.items():
        setattr(model, key, value)
    model.save()
    audit.record_change(model, AuditLogEntry.ACTION_CONFIG, before, actor=actor,
                        note="FC model updated")
    return model


@transaction.atomic
def set_fc_model_active(model, *, actor, is_active):
    """Archive a model instead of deleting it, so FCs already built against it
    keep a valid reference."""
    _require_manager(actor, "manage FC models")
    if model.is_active == is_active:
        return model
    before = audit.snapshot(model)
    model.is_active = is_active
    model.save(update_fields=["is_active"])
    in_use = model.units.count()
    audit.record_change(
        model, AuditLogEntry.ACTION_CONFIG, before, actor=actor,
        note=(f"FC model '{model.name}' activated" if is_active else
              f"FC model '{model.name}' archived ({in_use} existing FC(s) keep "
              f"this model)"))
    return model


def delete_fc_model(model, *, actor):
    _require_manager(actor, "manage FC models")
    if model.units.exists():
        raise WorkflowError(
            f"'{model.name}' is used by {model.units.count()} FC(s) and cannot "
            "be deleted. Archive it instead.", code="model_in_use")
    audit.record(model, AuditLogEntry.ACTION_CONFIG, actor=actor,
                 before=audit.snapshot(model), note="Unused FC model deleted")
    model.delete()
