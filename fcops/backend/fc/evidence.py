"""Configuration evidence (WP8): parameter files, approved baselines, flashed
records and read-backs, and comparisons between them.

Original bytes are stored once (by SHA-256) in private storage and served
only through the scoped download endpoint. Evidence rows are never edited:
newer evidence for the same unit and kind supersedes the older row, and
associating an unknown unit later writes a new row that supersedes the
unassociated one.
"""
import hashlib

from django.core.files.base import ContentFile
from django.db import IntegrityError, transaction
from django.utils import timezone

from core import audit
from core.exceptions import WorkflowError
from core.models import AuditLogEntry

from . import parameters as param_parser
from .models import (BaselineApproval, ConfigEvidence, IssueEvidenceLink,
                     ParameterComparison, ParameterFile)
from .services import log_event

PARSER_VERSION = "fc.parameters/1"


def decode(raw):
    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise WorkflowError("That file could not be read as text.", code="undecodable_file")


def parse_upload(upload):
    """Parse an upload without storing it (quick comparisons)."""
    upload.seek(0)
    parameters, skipped = param_parser.parse(decode(upload.read()))
    if not parameters:
        raise WorkflowError(f"No parameters could be read from {upload.name}. A .param "
                            "file has one NAME,VALUE pair per line.",
                            code="empty_param_file")
    return parameters, skipped


@transaction.atomic
def store_parameter_file(upload, *, actor, label="", fc=None, parameter_profile=None):
    """Store an upload once. Returns ``(file, created, skipped_lines)``; a
    second upload of the same bytes returns the existing row."""
    upload.seek(0)
    raw = upload.read()
    digest = hashlib.sha256(raw).hexdigest()
    existing = ParameterFile.objects.filter(sha256=digest).first()
    if existing:
        return existing, False, existing.parse_warnings
    text = decode(raw)
    parameters, skipped = param_parser.parse(text)
    if not parameters:
        raise WorkflowError(
            "No parameters could be read from that file. A .param file has "
            "one NAME,VALUE pair per line.", code="empty_param_file")
    pf = ParameterFile(
        name=upload.name[:160], label=(label or "")[:160], fc=fc,
        parameter_profile=parameter_profile, parameters=parameters, raw_text=text,
        parameter_count=len(parameters), uploaded_by=actor, sha256=digest,
        size=len(raw), parser_version=PARSER_VERSION, parse_warnings=skipped)
    pf.file.save(f"{digest}.param", ContentFile(raw), save=False)
    try:
        with transaction.atomic():
            pf.save()
    except IntegrityError:  # a concurrent upload of the same bytes won
        pf.file.delete(save=False)
        existing = ParameterFile.objects.get(sha256=digest)
        return existing, False, existing.parse_warnings
    audit.record(pf, AuditLogEntry.ACTION_CREATE, actor=actor,
                 after={"name": pf.name, "parameters": len(parameters),
                        "sha256": digest},
                 note=f"Parameter file uploaded ({len(parameters)} parameters)", fc=fc)
    return pf, True, skipped


def current_evidence(fc, kind):
    return (ConfigEvidence.objects.filter(fc=fc, kind=kind, superseded_by__isnull=True)
            .order_by("-captured_at", "-id").first())


@transaction.atomic
def record_evidence(*, kind, file, actor, fc=None, captured_at=None,
                    unit_identity_confidence=None, **fields):
    if kind not in dict(ConfigEvidence.KIND_CHOICES):
        raise WorkflowError("Unknown evidence kind.", code="invalid_kind")
    confidence = unit_identity_confidence or (
        ConfigEvidence.CONFIRMED if fc else ConfigEvidence.UNKNOWN)
    if fc is None and confidence != ConfigEvidence.UNKNOWN:
        raise WorkflowError("Evidence without a unit must have unknown identity.",
                            code="invalid_confidence")
    previous = current_evidence(fc, kind) if fc else None
    evidence = ConfigEvidence.objects.create(
        kind=kind, file=file, fc=fc, unit_identity_confidence=confidence,
        captured_at=captured_at or timezone.now(), recorded_by=actor,
        supersedes=previous, **fields)
    audit.record(evidence, AuditLogEntry.ACTION_CREATE, actor=actor,
                 after={"kind": kind, "file": file.pk, "fc": getattr(fc, "pk", None),
                        "supersedes": getattr(previous, "pk", None)},
                 note=f"{evidence.get_kind_display()} recorded", fc=fc)
    log_event(fc, "CONFIG_EVIDENCE", f"{evidence.get_kind_display()} recorded",
              detail=f"{file.name} captured {evidence.captured_at:%Y-%m-%d %H:%M}",
              actor=actor, payload={"evidence": evidence.pk, "kind": kind})
    return evidence


@transaction.atomic
def associate_unit(evidence, *, fc, actor, reason,
                   confidence=ConfigEvidence.PROBABLE):
    """Attach evidence captured from an unknown unit to an FC, as a new row
    that supersedes the unassociated one, so the association is recorded."""
    if evidence.fc_id is not None:
        raise WorkflowError("This evidence already belongs to a unit.",
                            code="already_associated")
    if not (reason or "").strip():
        raise WorkflowError("Associating a unit needs a reason.", code="reason_required")
    evidence = ConfigEvidence.objects.select_for_update().get(pk=evidence.pk)
    if hasattr(evidence, "superseded_by"):
        raise WorkflowError("This evidence has already been superseded.",
                            code="superseded")
    new = ConfigEvidence.objects.create(
        kind=evidence.kind, file=evidence.file, fc=fc,
        unit_identity_confidence=confidence, firmware_version=evidence.firmware_version,
        firmware_build=evidence.firmware_build, gcs_version=evidence.gcs_version,
        hardware_revision=evidence.hardware_revision, captured_at=evidence.captured_at,
        recorded_by=actor, tool=evidence.tool,
        source_note=f"Associated with {fc.serial}: {reason}", supersedes=evidence)
    audit.record(new, AuditLogEntry.ACTION_UPDATE, actor=actor,
                 after={"associated_from": evidence.pk, "fc": fc.pk,
                        "confidence": confidence}, note=reason, fc=fc)
    log_event(fc, "CONFIG_EVIDENCE", f"{new.get_kind_display()} associated",
              detail=reason, actor=actor, payload={"evidence": new.pk})
    return new


def can_approve_baseline(user):
    """PLACEHOLDER authority: a Firmware lead or a manager."""
    from access.policy import has_capability
    from accounts.models import Capability
    return (has_capability(user, Capability.IS_MANAGER)
            or (user.is_lead_role and user.can_manage_firmware))


@transaction.atomic
def approve_baseline(evidence, *, actor, revision, compatibility="", scope=""):
    if evidence.kind != ConfigEvidence.BASELINE:
        raise WorkflowError("Only a baseline can be approved.", code="not_a_baseline")
    if not can_approve_baseline(actor):
        raise WorkflowError("Only a Firmware lead or a manager may approve a baseline.",
                            code="forbidden")
    if not (revision or "").strip():
        raise WorkflowError("A baseline approval needs a revision.",
                            code="revision_required")
    if BaselineApproval.objects.filter(evidence=evidence).exists():
        raise WorkflowError("This baseline is already approved; record a new revision.",
                            code="already_approved")
    approval = BaselineApproval.objects.create(
        evidence=evidence, revision=revision, approved_by=actor,
        compatibility=compatibility, scope=scope)
    audit.record(evidence, AuditLogEntry.ACTION_APPROVE, actor=actor,
                 after={"revision": revision}, note="Baseline approved", fc=evidence.fc)
    return approval


@transaction.atomic
def compare_evidence(left, right, *, actor, tolerance=0.0):
    """Differences and parser warnings only; no safety verdict."""
    result = param_parser.compare(left.file.parameters, right.file.parameters,
                                  tolerance=tolerance)
    result["warnings"] = {"left": left.file.parse_warnings,
                          "right": right.file.parse_warnings}
    return ParameterComparison.objects.create(
        left_evidence=left, right_evidence=right, tolerance={"relative": tolerance},
        result=result, created_by=actor,
        parser_versions={"left": left.file.parser_version,
                         "right": right.file.parser_version})


@transaction.atomic
def link_evidence(issue, evidence, *, actor):
    from issues.services import record_event
    link, created = IssueEvidenceLink.objects.get_or_create(
        issue=issue, evidence=evidence, defaults={"linked_by": actor})
    if created:
        record_event(issue, "evidence_linked", actor, evidence=evidence.pk,
                     kind=evidence.kind)
        audit.record(issue, AuditLogEntry.ACTION_UPDATE, actor=actor,
                     after={"evidence_linked": evidence.pk}, note="Evidence linked")
    return link


def _version_row(evidence, source):
    return {"evidence": evidence.pk, "kind": evidence.kind, "source": source,
            "captured_at": evidence.captured_at,
            "firmware_version": evidence.firmware_version,
            "gcs_version": evidence.gcs_version,
            "hardware_revision": evidence.hardware_revision}


def versions_at_time(issue, user):
    """Versions from evidence linked to the issue, or else the latest
    evidence of each kind captured before the report, always labelled with
    its capture time. Never the FC's latest version silently."""
    from access.policy import can_view_fcs
    if not can_view_fcs(user):
        return []
    linked = [link.evidence for link in
              issue.evidence_links.select_related("evidence").all()]
    if linked:
        return [_version_row(e, "linked") for e in linked]
    if issue.fc_id is None:
        return []
    rows = []
    for kind, _ in ConfigEvidence.KIND_CHOICES:
        e = (ConfigEvidence.objects.filter(fc_id=issue.fc_id, kind=kind,
                                           captured_at__lte=issue.submitted_at)
             .order_by("-captured_at", "-id").first())
        if e:
            rows.append(_version_row(e, "nearest_before_report"))
    return rows
