"""Minimal customer writes, with policy and audit inside the transaction."""
from django.db import transaction
from rest_framework.exceptions import PermissionDenied
from access import policy
from accounts.models import Capability
from core import audit
from core.models import AuditLogEntry
from core.exceptions import WorkflowError
from .models import CustomerContact, Deployment


@transaction.atomic
def save_record(model, *, actor, changes, instance=None):
    if model is CustomerContact:
        allowed = policy.has_capability(actor, Capability.CAN_VIEW_CUSTOMER_CONTACTS)
    else:
        allowed = policy.can_view_fcs(actor) and policy.is_head_or_manager(actor)
    if not allowed:
        raise PermissionDenied("You cannot maintain these records.")
    if instance is not None:
        instance = model.objects.select_for_update().get(pk=instance.pk)
    before = _snapshot(instance)
    changes = dict(changes)
    units = changes.pop("units", None)
    if model is Deployment and instance is not None and "customer" in changes:
        if instance.issues.filter(customer__isnull=False).exclude(
                customer=changes["customer"]).exists():
            raise WorkflowError("Customer change conflicts with linked issues.",
                                code="customer_mismatch")
    if instance is None:
        instance = model.objects.create(**changes)
        action = AuditLogEntry.ACTION_CREATE
    else:
        for key, value in changes.items():
            setattr(instance, key, value)
        instance.save()
        action = AuditLogEntry.ACTION_UPDATE
    if units is not None and model is Deployment:
        instance.units.set(units)
    audit.record(instance, action, actor=actor, before=before,
                 after=_snapshot(instance))
    return instance


def _snapshot(instance):
    if instance is None:
        return None
    fields = [f.name for f in instance._meta.fields]
    result = audit.snapshot(instance, fields=fields)
    if isinstance(instance, Deployment):
        result["units"] = list(instance.units.values_list("pk", flat=True))
    return result


def validate_issue_context(actor, customer, deployment):
    if customer and not policy.visible_customers(actor).filter(pk=customer.pk).exists():
        raise PermissionDenied("Customer is outside your scope.")
    if deployment and not policy.visible_deployments(actor).filter(pk=deployment.pk).exists():
        raise PermissionDenied("Deployment is outside your scope.")
    if deployment:
        # Serialize customer changes against concurrent issue associations.
        deployment = Deployment.objects.select_for_update().get(pk=deployment.pk)
    if deployment and customer and deployment.customer_id != customer.pk:
        raise WorkflowError("Deployment belongs to a different customer.", code="customer_mismatch")
