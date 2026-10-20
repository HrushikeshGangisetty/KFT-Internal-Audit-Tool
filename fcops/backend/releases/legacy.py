"""Content hashing and the legacy conversion (WP11). Model classes are passed
in, so the data migration can use historical models and tests the real ones."""
import hashlib
import json

CONTENT_FIELDS = ("source_ref", "artifact_ref", "artifact_sha256", "internal_notes",
                  "recipient_notes", "compatibility", "known_limitations")


def content_hash(product, version, fields):
    payload = {"product": product, "version": version,
               **{f: fields.get(f) or "" for f in CONTENT_FIELDS}}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def convert_software_updates(SoftwareUpdate, Release, ReleaseRevision, User):
    """Each old named-approver record becomes ``Release(legacy=True)`` with one
    revision. The named approver goes into internal notes as text; no
    approval rows are created, so legacy releases are never dual-approved."""
    converted = 0
    for old in SoftwareUpdate.objects.order_by("created_at", "id"):
        if Release.objects.filter(product=old.kind, version=old.version).exists():
            continue
        approver = User.objects.filter(pk=old.approved_by_id).first()
        name = (approver.full_name or approver.username) if approver else "unknown"
        approved_at = old.approved_at.isoformat() if old.approved_at else "no time recorded"
        fields = {
            "source_ref": old.git_sha,
            "internal_notes": (f"{old.release_notes}\n\nLegacy approver field: {name} "
                               f"({approved_at}). Migrated from SoftwareUpdate #{old.pk}; "
                               "not an authenticated approval."),
        }
        release = Release.objects.create(product=old.kind, version=old.version,
                                         legacy=True, created_by_id=old.pushed_by_id)
        Release.objects.filter(pk=release.pk).update(created_at=old.created_at)
        ReleaseRevision.objects.create(
            release=release, number=1, created_by_id=old.pushed_by_id,
            content_hash=content_hash(old.kind, old.version, fields), **fields)
        converted += 1
    return converted
