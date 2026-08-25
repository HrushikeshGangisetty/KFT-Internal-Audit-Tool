"""Audit helper. Call :func:`record` from services, never from serializers."""
from django.forms.models import model_to_dict

from .middleware import resolve_actor
from .models import AuditLogEntry


def snapshot(instance, fields=None):
    """JSON-safe dict of a model instance, for before/after capture."""
    if instance is None:
        return None
    data = model_to_dict(instance, fields=fields)
    out = {}
    for key, value in data.items():
        if hasattr(value, "isoformat"):
            out[key] = value.isoformat()
        elif isinstance(value, (str, int, float, bool, type(None), list, dict)):
            out[key] = value
        else:
            out[key] = str(value)
    return out


def diff(before, after):
    """Only the fields that actually changed (keeps the log readable)."""
    before = before or {}
    after = after or {}
    changed_before, changed_after = {}, {}
    for key in set(before) | set(after):
        if before.get(key) != after.get(key):
            changed_before[key] = before.get(key)
            changed_after[key] = after.get(key)
    return changed_before, changed_after


def record(entity, action, *, actor=None, before=None, after=None, note="",
           fc=None, entity_label=None):
    actor = actor or resolve_actor()
    entity_type = entity.__class__.__name__
    if fc is None:
        fc = getattr(entity, "fc", None)
        if fc is None and entity_type == "FlightController":
            fc = entity
    entry = AuditLogEntry(
        entity_type=entity_type,
        entity_id=str(getattr(entity, "pk", "")),
        entity_label=entity_label or str(entity)[:255],
        actor=actor if getattr(actor, "pk", None) else None,
        actor_label=(getattr(actor, "username", "") or "system"),
        action=action,
        before=before,
        after=after,
        note=note,
        fc=fc,
    )
    entry.save()
    return entry


def record_change(entity, action, before_snapshot, *, note="", fields=None, actor=None):
    """Record only what changed between ``before_snapshot`` and the entity now."""
    after_snapshot = snapshot(entity, fields=fields)
    b, a = diff(before_snapshot, after_snapshot)
    if not b and not a and action == AuditLogEntry.ACTION_UPDATE:
        return None
    return record(entity, action, before=b, after=a, note=note, actor=actor)
