"""GCS releases, dual approval, recipients and announcement campaigns
(WP11-WP13).

Revisions and approvals are immutable rows: editing a release creates
revision N+1, which has no approvals. Whether a revision is approved is
computed from its approval rows (``services.approval_state``), never stored.
"""
from django.conf import settings
from django.db import models

from .legacy import CONTENT_FIELDS, content_hash


class _Immutable(models.Model):
    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise PermissionError(f"{type(self).__name__} rows are immutable.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionError(f"{type(self).__name__} rows cannot be deleted.")


class Release(models.Model):
    PRODUCT_CHOICES = [("GCS", "GCS"), ("CONFIGURATOR", "Configurator")]

    product = models.CharField(max_length=24, choices=PRODUCT_CHOICES, default="GCS")
    version = models.CharField(max_length=64)
    # Migrated from the old named-approver records (fc.SoftwareUpdate). Never
    # shown as approved under the current process (PRD §8.1).
    legacy = models.BooleanField(default=False)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True,
                                   on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at", "-id")
        constraints = [models.UniqueConstraint(fields=["product", "version"],
                                               name="one_release_per_product_version")]

    def __str__(self):
        return f"{self.get_product_display()} {self.version}"


class ReleaseRevision(_Immutable):
    CONTENT_FIELDS = CONTENT_FIELDS

    release = models.ForeignKey(Release, on_delete=models.PROTECT, related_name="revisions")
    number = models.PositiveIntegerField()
    source_ref = models.CharField(max_length=120, help_text="Commit SHA or tag (required)")
    artifact_ref = models.CharField(max_length=500, blank=True)
    artifact_sha256 = models.CharField(max_length=64, blank=True)
    internal_notes = models.TextField(blank=True)
    recipient_notes = models.TextField(blank=True)
    compatibility = models.TextField(blank=True)
    known_limitations = models.TextField(blank=True)
    content_hash = models.CharField(max_length=64)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True,
                                   on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("release_id", "-number")
        constraints = [models.UniqueConstraint(fields=["release", "number"],
                                               name="one_revision_number_per_release")]

    def __str__(self):
        return f"{self.release} r{self.number}"

    @classmethod
    def hash_content(cls, release, fields):
        return content_hash(release.product, release.version, fields)


class ReleaseApproval(_Immutable):
    SOFTWARE_HEAD, MANAGER = "software_head", "manager"
    ROLE_CHOICES = [(SOFTWARE_HEAD, "Software head"), (MANAGER, "Manager")]
    APPROVE, REJECT = "approve", "reject"
    DECISION_CHOICES = [(APPROVE, "Approve"), (REJECT, "Reject")]

    revision = models.ForeignKey(ReleaseRevision, on_delete=models.PROTECT,
                                 related_name="approvals")
    role = models.CharField(max_length=16, choices=ROLE_CHOICES)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                              related_name="release_decisions")
    decision = models.CharField(max_length=8, choices=DECISION_CHOICES)
    comment = models.TextField(blank=True)
    at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("at", "id")
        constraints = [models.UniqueConstraint(fields=["revision", "role"],
                                               name="one_decision_per_revision_role")]


class RecipientSnapshot(_Immutable):
    """The frozen recipient list a campaign is built from (WP12)."""
    source = models.CharField(max_length=32)
    synthetic = models.BooleanField()
    segment = models.CharField(max_length=64)
    fetched_at = models.DateTimeField()
    fetched_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                                   related_name="+")
    recipients = models.JSONField()
    count = models.PositiveIntegerField()

    class Meta:
        ordering = ("-fetched_at", "-id")


class Campaign(models.Model):
    DRAFT, QUEUED, SENDING, COMPLETED, COMPLETED_WITH_FAILURES = (
        "draft", "queued", "sending", "completed", "completed_with_failures")
    STATUS_CHOICES = [(s, s.replace("_", " ")) for s in (
        DRAFT, QUEUED, SENDING, COMPLETED, COMPLETED_WITH_FAILURES)]

    release_revision = models.ForeignKey(ReleaseRevision, on_delete=models.PROTECT,
                                         related_name="campaigns")
    subject = models.CharField(max_length=255)
    body_text = models.TextField()
    body_html = models.TextField()
    snapshot = models.ForeignKey(RecipientSnapshot, on_delete=models.PROTECT,
                                 related_name="campaigns")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                                   related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    idempotency_key = models.CharField(max_length=64, null=True, blank=True, unique=True)
    status = models.CharField(max_length=24, choices=STATUS_CHOICES, default=DRAFT)
    sent_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                on_delete=models.PROTECT, related_name="+")
    sent_at = models.DateTimeField(null=True, blank=True)
    resend_of = models.ForeignKey("self", null=True, blank=True, on_delete=models.PROTECT,
                                  related_name="resends")
    resend_reason = models.TextField(blank=True)

    class Meta:
        ordering = ("-created_at", "-id")

    def __str__(self):
        return f"Campaign {self.pk}: {self.subject}"


class CampaignDelivery(models.Model):
    QUEUED, ACCEPTED, FAILED, UNKNOWN = "queued", "accepted", "failed", "unknown"
    STATUS_CHOICES = [(s, s) for s in (QUEUED, ACCEPTED, FAILED, UNKNOWN)]

    campaign = models.ForeignKey(Campaign, on_delete=models.PROTECT,
                                 related_name="deliveries")
    recipient_id = models.CharField(max_length=128)
    email = models.EmailField()
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=QUEUED)
    attempts = models.PositiveIntegerField(default=0)
    provider_ref = models.CharField(max_length=255, blank=True)
    last_error = models.TextField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("id",)
        constraints = [models.UniqueConstraint(fields=["campaign", "recipient_id"],
                                               name="one_delivery_per_campaign_recipient")]


class DeliveryAttempt(_Immutable):
    """Per-recipient history: every send attempt and every reconciliation
    is a row, so retries never overwrite what happened before."""
    delivery = models.ForeignKey(CampaignDelivery, on_delete=models.PROTECT,
                                 related_name="history")
    kind = models.CharField(max_length=16)  # send | reconcile | retry
    outcome = models.CharField(max_length=16)
    provider_ref = models.CharField(max_length=255, blank=True)
    error = models.TextField(blank=True)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                              on_delete=models.PROTECT, related_name="+")
    at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("at", "id")
