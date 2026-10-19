"""Alert delivery (WP3).

``dispatch_alert`` writes one ``AlertDelivery`` row per recipient and channel
and enqueues one job per new row, all in the caller's transaction. The
unique ``(alert_key, recipient, channel)`` makes repeated dispatches and job
retries harmless: a delivery already accepted is never sent again.

Out-of-app messages carry only the reference, urgency, queue and a link
(PRD §6.3); the in-app notification is a pointer rendered at read time.
"""
from dataclasses import dataclass

from django.conf import settings
from django.core.mail import send_mail
from django.db import IntegrityError, transaction

from . import jobs
from .models import AlertDelivery, Notification

URGENT = "urgent"


@dataclass
class DeliveryResult:
    status: str
    provider_ref: str = ""
    error: str = ""


class InAppChannel:
    name = "in_app"

    def send(self, recipient, message):
        note = Notification.objects.create(
            recipient=recipient, kind=message["kind"],
            target_type=message["target_type"], target_id=message["target_id"])
        return DeliveryResult(AlertDelivery.ACCEPTED, provider_ref=f"notification:{note.pk}")


class EmailChannel:
    """Django's email backend: console/file in development; the approved
    provider only after the sending decision (invariant 9)."""
    name = "email"

    def send(self, recipient, message):
        if not recipient.email:
            return DeliveryResult(AlertDelivery.FAILED, error="Recipient has no email address.")
        s = message["summary"]
        link = settings.SITE_URL.rstrip("/") + s.get("link", "")
        sent = send_mail(
            subject=f"[{s.get('urgency', 'normal')}] {s.get('ref', '')}",
            message=(f"{s.get('ref', '')} ({s.get('urgency', 'normal')}) "
                     f"in queue {s.get('queue') or 'unassigned'}.\n{link}\n"),
            from_email=None, recipient_list=[recipient.email])
        return DeliveryResult(AlertDelivery.ACCEPTED if sent else AlertDelivery.UNKNOWN)


class _Undecided:
    """SMS/WhatsApp: the after-hours channel decision is still open."""

    def __init__(self, name):
        self.name = name

    def send(self, recipient, message):
        raise NotImplementedError(f"The {self.name} channel is not decided yet.")


CHANNELS = {c.name: c for c in (InAppChannel(), EmailChannel(),
                                _Undecided("sms"), _Undecided("whatsapp"))}


def channels_for(urgency):
    return (settings.ALERT_CHANNELS_URGENT if urgency == URGENT
            else settings.ALERT_CHANNELS_NORMAL)


def dispatch_alert(alert_key, recipients, urgency, target, *, kind, summary,
                   on_failure=(), channels=None):
    """Create deliveries and their jobs. ``target`` is ``(type, id)``;
    ``summary`` holds the out-of-app fields; ``on_failure`` lists who gets an
    in-app notice if a delivery fails for good (the head and the manager).
    Returns the deliveries created by this call (none on a repeat)."""
    created = []
    for user in {u.pk: u for u in recipients if u is not None}.values():
        for channel in channels or channels_for(urgency):
            try:
                with transaction.atomic():
                    delivery = AlertDelivery.objects.create(
                        alert_key=alert_key, recipient=user, channel=channel)
            except IntegrityError:
                continue  # already dispatched: the dedup guarantee
            jobs.enqueue("alerts.deliver", {
                "delivery_id": delivery.pk, "kind": kind,
                "target_type": target[0], "target_id": target[1],
                "summary": summary,
                "on_failure": [u.pk for u in on_failure if u is not None],
            }, idempotency_key=f"alert-delivery:{delivery.pk}")
            created.append(delivery)
    return created


@jobs.job_handler("alerts.deliver")
def deliver(job):
    p = job.payload
    with transaction.atomic():
        delivery = (AlertDelivery.objects.select_for_update()
                    .select_related("recipient").get(pk=p["delivery_id"]))
        if delivery.status == AlertDelivery.ACCEPTED:
            return  # a retry after the provider already took it: no double send
        delivery.attempts += 1
        try:
            result = CHANNELS[delivery.channel].send(delivery.recipient, p)
        except Exception as exc:  # noqa: BLE001 - recorded on the delivery
            result = DeliveryResult(AlertDelivery.FAILED, error=str(exc)[:2000])
        delivery.status = result.status
        delivery.provider_ref = result.provider_ref
        delivery.error = result.error
        delivery.save(update_fields=["status", "attempts", "provider_ref", "error",
                                     "updated_at"])
    if result.status != AlertDelivery.FAILED:
        return
    if job.attempts < job.max_attempts:
        raise RuntimeError(f"Delivery {delivery.pk} failed: {result.error}")
    _notify_failure(delivery, p)


def _notify_failure(delivery, p):
    from django.contrib.auth import get_user_model
    User = get_user_model()
    dispatch_alert(
        f"{delivery.alert_key}:failed:{delivery.recipient_id}:{delivery.channel}",
        User.objects.filter(pk__in=p.get("on_failure", []), is_active=True),
        "normal", (p["target_type"], p["target_id"]), kind="ALERT_FAILED",
        summary=p["summary"], channels=[InAppChannel.name])
