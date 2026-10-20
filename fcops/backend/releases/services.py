"""Release, approval and campaign writes (WP11-WP13). Policy, validation and
audit run inside the transaction; email leaves only from the worker after
commit (invariant 7)."""
import smtplib
from datetime import timedelta

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.db import transaction
from django.utils import timezone
from django.utils.html import escape, linebreaks
from rest_framework.exceptions import PermissionDenied

from access import policy
from accounts.models import Capability
from core import audit, jobs
from core.exceptions import WorkflowError
from core.models import AuditLogEntry

from . import recipients as recipient_sources
from .models import (Campaign, CampaignDelivery, DeliveryAttempt, RecipientSnapshot,
                     Release, ReleaseApproval, ReleaseRevision)

ROLE_CAPABILITY = {ReleaseApproval.SOFTWARE_HEAD: Capability.IS_SOFTWARE_HEAD,
                   ReleaseApproval.MANAGER: Capability.IS_MANAGER}
APPROVED, REJECTED, PENDING, LEGACY = "approved", "rejected", "pending", "legacy"


def _require(actor, capability, message):
    if not policy.has_capability(actor, capability):
        raise PermissionDenied(message)


# --- WP11: releases and dual approval ----------------------------------------
def approval_state(revision):
    """Approved only with an ``approve`` for both roles from two distinct
    people. Legacy rows have no approvals, so they are never approved."""
    approvals = list(revision.approvals.all())
    if any(a.decision == ReleaseApproval.REJECT for a in approvals):
        return REJECTED
    approvers = {a.role: a.actor_id for a in approvals}
    if len(approvers) == 2 and len(set(approvers.values())) == 2:
        return APPROVED
    if revision.release.legacy and revision.number == 1:
        return LEGACY
    return PENDING


def latest_revision(release):
    return release.revisions.order_by("-number").first()


def current_approved_revision(release):
    """Computed, never stored: the latest revision if it is approved."""
    latest = latest_revision(release)
    return latest if latest and approval_state(latest) == APPROVED else None


def _clean(fields):
    data = {f: (fields.get(f) or "").strip() for f in ReleaseRevision.CONTENT_FIELDS}
    if not data["source_ref"]:
        raise WorkflowError("A source reference (commit SHA or tag) is required.",
                            code="source_ref_required")
    return data


def _add_revision(release, *, actor, fields):
    latest = latest_revision(release)
    content_hash = ReleaseRevision.hash_content(release, fields)
    if latest and latest.content_hash == content_hash:
        raise WorkflowError("Nothing changed: a new revision needs different content.",
                            code="no_change")
    revision = ReleaseRevision.objects.create(
        release=release, number=(latest.number + 1) if latest else 1,
        content_hash=content_hash, created_by=actor, **fields)
    audit.record(release, AuditLogEntry.ACTION_CREATE, actor=actor,
                 after={"revision": revision.number, "content_hash": content_hash},
                 note=f"Revision {revision.number} drafted")
    return revision


@transaction.atomic
def create_release(*, actor, product, version, **fields):
    _require(actor, Capability.CAN_DRAFT_RELEASE, "Drafting a release needs the "
             "'can draft releases' capability.")
    from fc.models import SoftwareVersion

    version = (version or "").strip()
    if not version:
        raise WorkflowError("A version is required.", code="version_required")
    data = _clean(fields)
    if Release.objects.filter(product=product, version=version).exists():
        raise WorkflowError(f"{product} {version} already exists; add a revision instead.",
                            code="duplicate_version")
    release = Release.objects.create(product=product, version=version, created_by=actor)
    # Keeps the tester-facing version dropdowns in step, as pushing used to.
    SoftwareVersion.objects.get_or_create(kind=product, version=version)
    _add_revision(release, actor=actor, fields=data)
    return release


@transaction.atomic
def revise(release, *, actor, **fields):
    """An edit is a new revision; the previous revision and its approvals
    stay as they were, and the new one starts unapproved."""
    _require(actor, Capability.CAN_DRAFT_RELEASE, "Revising a release needs the "
             "'can draft releases' capability.")
    release = Release.objects.select_for_update().get(pk=release.pk)
    return _add_revision(release, actor=actor, fields=_clean(fields))


@transaction.atomic
def decide(revision, *, actor, role, decision, comment=""):
    release = Release.objects.select_for_update().get(pk=revision.release_id)
    if role not in ROLE_CAPABILITY:
        raise WorkflowError(f"Unknown approval role '{role}'.", code="invalid_role")
    if decision not in (ReleaseApproval.APPROVE, ReleaseApproval.REJECT):
        raise WorkflowError(f"Unknown decision '{decision}'.", code="invalid_decision")
    # Checked now, at the time of the decision; being an administrator is not enough.
    _require(actor, ROLE_CAPABILITY[role],
             f"Only a holder of the {role.replace('_', ' ')} capability can decide "
             "in that role.")
    if release.legacy and revision.number == 1:
        raise WorkflowError("A legacy record is not approved retroactively; draft a new "
                            "revision and approve that.", code="legacy_revision")
    if latest_revision(release).pk != revision.pk:
        raise WorkflowError("Only the latest revision can be approved or rejected.",
                            code="not_latest")
    comment = (comment or "").strip()
    if decision == ReleaseApproval.REJECT and not comment:
        raise WorkflowError("A rejection needs a reason.", code="reason_required")
    existing = list(revision.approvals.all())
    if any(a.decision == ReleaseApproval.REJECT for a in existing):
        raise WorkflowError("This revision was rejected; the release needs a new revision.",
                            code="revision_rejected")
    if any(a.role == role for a in existing):
        raise WorkflowError(f"The {role.replace('_', ' ')} decision is already recorded.",
                            code="already_decided")
    if decision == ReleaseApproval.APPROVE and any(a.actor_id == actor.pk for a in existing):
        raise WorkflowError("The two approvals must come from two different people.",
                            code="same_approver")
    approval = ReleaseApproval.objects.create(revision=revision, role=role, actor=actor,
                                              decision=decision, comment=comment)
    audit.record(release, "RELEASE_DECISION", actor=actor, note=comment,
                 after={"revision": revision.number, "role": role, "decision": decision})
    return approval


# --- WP12: recipient snapshots ----------------------------------------------
def take_snapshot(*, actor, segment):
    _require(actor, Capability.CAN_SEND_ANNOUNCEMENTS, "Selecting recipients needs the "
             "'can send announcements' capability.")
    fetch = recipient_sources.validate(recipient_sources.get_source().fetch_eligible(segment))
    if fetch.errors:
        # No snapshot at all: a partial list must never look complete.
        raise WorkflowError("Recipients could not be loaded: " + " ".join(fetch.errors),
                            code="recipient_source_failed")
    return RecipientSnapshot.objects.create(
        source=fetch.source, synthetic=fetch.synthetic, segment=segment,
        fetched_at=fetch.fetched_at, fetched_by=actor, recipients=fetch.recipients,
        count=len(fetch.recipients))


# --- WP13: campaigns ----------------------------------------------------------
def render(revision):
    """Recipient-facing text comes from ``recipient_notes`` only; internal
    notes are never in the template context."""
    release = revision.release
    ctx = {"product": release.get_product_display(), "version": release.version,
           "notes": revision.recipient_notes}
    subject = f"{ctx['product']} {ctx['version']} is available"
    body = (f"{ctx['product']} {ctx['version']} has been released.\n\n{ctx['notes']}\n\n"
            "This message announces a release; it does not install anything.\n")
    html = (f"<p>{escape(ctx['product'])} {escape(ctx['version'])} has been released.</p>"
            f"{linebreaks(escape(ctx['notes']))}"
            "<p>This message announces a release; it does not install anything.</p>")
    return subject, body, html


def _require_current_approved(revision):
    if current_approved_revision(revision.release) != revision:
        raise WorkflowError("This revision is not the current approved revision of the "
                            "release, so it cannot be announced.", code="not_approved")


@transaction.atomic
def preview(*, actor, revision, segment):
    """Stores a draft only; nothing is queued or sent."""
    _require(actor, Capability.CAN_SEND_ANNOUNCEMENTS, "Announcements need the "
             "'can send announcements' capability.")
    _require_current_approved(revision)
    snapshot = take_snapshot(actor=actor, segment=segment)
    subject, body, html = render(revision)
    campaign = Campaign.objects.create(release_revision=revision, subject=subject,
                                       body_text=body, body_html=html, snapshot=snapshot,
                                       created_by=actor)
    audit.record(campaign, AuditLogEntry.ACTION_CREATE, actor=actor,
                 after={"revision": revision.pk, "recipients": snapshot.count,
                        "synthetic": snapshot.synthetic}, note="Campaign previewed")
    return campaign


def _enqueue(delivery):
    jobs.enqueue("campaigns.deliver", {"delivery_id": delivery.pk},
                 idempotency_key=f"campaign-delivery:{delivery.pk}:{delivery.attempts}")


@transaction.atomic
def send(campaign, *, actor, idempotency_key):
    key = (idempotency_key or "").strip()
    if not key:
        raise WorkflowError("A send needs an idempotency key.", code="key_required")
    campaign = Campaign.objects.select_for_update().get(pk=campaign.pk)
    if campaign.status != Campaign.DRAFT:
        if campaign.idempotency_key == key:
            return campaign  # the same click again: the same campaign, no new sends
        raise WorkflowError("This campaign was already sent. A deliberate resend needs "
                            "the resend action and a reason.", code="already_sent")
    _require(actor, Capability.CAN_SEND_ANNOUNCEMENTS, "Sending needs the "
             "'can send announcements' capability.")
    _require_current_approved(campaign.release_revision)
    age = timezone.now() - campaign.snapshot.fetched_at
    if age > timedelta(minutes=settings.CAMPAIGN_SNAPSHOT_MAX_AGE_MINUTES):
        raise WorkflowError("The recipient list is too old; preview again to refresh it.",
                            code="snapshot_stale")
    if Campaign.objects.filter(idempotency_key=key).exists():
        raise WorkflowError("This idempotency key belongs to another campaign.",
                            code="key_reused")
    campaign.status = Campaign.QUEUED
    campaign.idempotency_key = key
    campaign.sent_by, campaign.sent_at = actor, timezone.now()
    campaign.save(update_fields=["status", "idempotency_key", "sent_by", "sent_at"])
    for row in campaign.snapshot.recipients:
        _enqueue(CampaignDelivery.objects.create(campaign=campaign, recipient_id=row["id"],
                                                 email=row["email"]))
    audit.record(campaign, "CAMPAIGN_SENT", actor=actor,
                 after={"deliveries": campaign.snapshot.count,
                        "synthetic": campaign.snapshot.synthetic})
    return campaign


@transaction.atomic
def resend(campaign, *, actor, reason):
    """A deliberate resend is a new linked draft with a fresh recipient list."""
    reason = (reason or "").strip()
    if not reason:
        raise WorkflowError("A resend needs a reason.", code="reason_required")
    if campaign.status == Campaign.DRAFT:
        raise WorkflowError("A draft has not been sent; send it instead.", code="not_sent")
    new = preview(actor=actor, revision=campaign.release_revision,
                  segment=campaign.snapshot.segment)
    new.resend_of, new.resend_reason = campaign, reason
    new.save(update_fields=["resend_of", "resend_reason"])
    return new


@transaction.atomic
def retry_failed(campaign, *, actor):
    """Retries only ``failed`` deliveries; ``unknown`` needs reconciliation first."""
    campaign = Campaign.objects.select_for_update().get(pk=campaign.pk)
    _require(actor, Capability.CAN_SEND_ANNOUNCEMENTS, "Retrying needs the "
             "'can send announcements' capability.")
    _require_current_approved(campaign.release_revision)
    failed = list(campaign.deliveries.select_for_update().filter(
        status=CampaignDelivery.FAILED))
    for delivery in failed:
        delivery.status = CampaignDelivery.QUEUED
        delivery.save(update_fields=["status", "updated_at"])
        DeliveryAttempt.objects.create(delivery=delivery, kind="retry",
                                       outcome=CampaignDelivery.QUEUED, actor=actor)
        _enqueue(delivery)
    if failed:
        campaign.status = Campaign.SENDING
        campaign.save(update_fields=["status"])
        audit.record(campaign, "CAMPAIGN_RETRY", actor=actor, after={"retried": len(failed)})
    return len(failed)


RECONCILE_OUTCOMES = {"accepted": CampaignDelivery.ACCEPTED,
                      "not_sent": CampaignDelivery.FAILED}


@transaction.atomic
def reconcile(delivery, *, actor, outcome, note):
    """Settle an ``unknown`` delivery from the provider log: it was accepted,
    or it was confirmed not sent (it then becomes ``failed`` and retryable)."""
    _require(actor, Capability.CAN_SEND_ANNOUNCEMENTS, "Reconciling needs the "
             "'can send announcements' capability.")
    delivery = CampaignDelivery.objects.select_for_update().get(pk=delivery.pk)
    if delivery.status != CampaignDelivery.UNKNOWN:
        raise WorkflowError("Only deliveries with an unknown outcome are reconciled.",
                            code="not_unknown")
    if outcome not in RECONCILE_OUTCOMES or not (note or "").strip():
        raise WorkflowError("Choose 'accepted' or 'not_sent' and say what you checked.",
                            code="invalid_reconciliation")
    delivery.status = RECONCILE_OUTCOMES[outcome]
    delivery.last_error = f"Reconciled ({outcome}): {note.strip()}"
    delivery.save(update_fields=["status", "last_error", "updated_at"])
    DeliveryAttempt.objects.create(delivery=delivery, kind="reconcile",
                                   outcome=delivery.status, error=note.strip(), actor=actor)
    _settle(delivery.campaign_id)
    return delivery


def _settle(campaign_id):
    campaign = Campaign.objects.select_for_update().get(pk=campaign_id)
    statuses = set(campaign.deliveries.values_list("status", flat=True))
    if CampaignDelivery.QUEUED in statuses:
        new = Campaign.SENDING
    elif statuses & {CampaignDelivery.FAILED, CampaignDelivery.UNKNOWN}:
        new = Campaign.COMPLETED_WITH_FAILURES
    else:
        new = Campaign.COMPLETED
    if campaign.status != new:
        campaign.status = new
        campaign.save(update_fields=["status"])


# Definite rejections by the provider; anything else (timeouts, dropped
# connections) leaves the outcome unknown.
DEFINITE_FAILURES = (smtplib.SMTPRecipientsRefused, smtplib.SMTPSenderRefused,
                     smtplib.SMTPDataError)


@jobs.job_handler("campaigns.deliver")
def deliver(job):
    """One message per recipient (no shared To/CC). Never raises, so the job
    is not retried automatically: a retry is an explicit action."""
    with transaction.atomic():
        delivery = (CampaignDelivery.objects.select_for_update()
                    .select_related("campaign").get(pk=job.payload["delivery_id"]))
        if delivery.status != CampaignDelivery.QUEUED:
            return  # already handled: a retried job must not send twice
        campaign = delivery.campaign
        delivery.attempts += 1
        error = ""
        try:
            message = EmailMultiAlternatives(campaign.subject, campaign.body_text,
                                             to=[delivery.email])
            message.attach_alternative(campaign.body_html, "text/html")
            sent = message.send()
            status = CampaignDelivery.ACCEPTED if sent else CampaignDelivery.UNKNOWN
        except DEFINITE_FAILURES as exc:
            status, error = CampaignDelivery.FAILED, str(exc)[:2000]
        except Exception as exc:  # noqa: BLE001 - ambiguous: needs reconciliation
            status, error = CampaignDelivery.UNKNOWN, str(exc)[:2000]
        delivery.status, delivery.last_error = status, error
        delivery.save(update_fields=["status", "attempts", "last_error", "updated_at"])
        DeliveryAttempt.objects.create(delivery=delivery, kind="send", outcome=status,
                                       error=error)
        _settle(campaign.pk)
