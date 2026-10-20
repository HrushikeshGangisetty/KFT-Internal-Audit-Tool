from rest_framework import serializers

from .models import (Campaign, CampaignDelivery, DeliveryAttempt, Release, ReleaseApproval,
                     ReleaseRevision)
from .services import approval_state, current_approved_revision


def _name(user):
    return (user.full_name or user.username) if user else ""


class ApprovalSerializer(serializers.ModelSerializer):
    actor_name = serializers.SerializerMethodField()

    class Meta:
        model = ReleaseApproval
        fields = ("id", "role", "decision", "actor", "actor_name", "comment", "at")

    def get_actor_name(self, obj):
        return _name(obj.actor)


class RevisionSerializer(serializers.ModelSerializer):
    approvals = ApprovalSerializer(many=True, read_only=True)
    state = serializers.SerializerMethodField()
    created_by_name = serializers.SerializerMethodField()

    class Meta:
        model = ReleaseRevision
        fields = ("id", "number", "source_ref", "artifact_ref", "artifact_sha256",
                  "internal_notes", "recipient_notes", "compatibility",
                  "known_limitations", "content_hash", "state", "approvals",
                  "created_by", "created_by_name", "created_at")

    def get_state(self, obj):
        return approval_state(obj)

    def get_created_by_name(self, obj):
        return _name(obj.created_by)


class RevisionInputSerializer(serializers.Serializer):
    source_ref = serializers.CharField(max_length=120)
    artifact_ref = serializers.CharField(max_length=500, required=False, allow_blank=True)
    artifact_sha256 = serializers.RegexField(r"^[0-9a-fA-F]{64}$", required=False,
                                             allow_blank=True)
    internal_notes = serializers.CharField(required=False, allow_blank=True)
    recipient_notes = serializers.CharField(required=False, allow_blank=True)
    compatibility = serializers.CharField(required=False, allow_blank=True)
    known_limitations = serializers.CharField(required=False, allow_blank=True)


class ReleaseCreateSerializer(RevisionInputSerializer):
    product = serializers.ChoiceField(choices=Release.PRODUCT_CHOICES, default="GCS")
    version = serializers.CharField(max_length=64)


class DecisionSerializer(serializers.Serializer):
    revision = serializers.IntegerField()
    role = serializers.ChoiceField(choices=ReleaseApproval.ROLE_CHOICES)
    decision = serializers.ChoiceField(choices=ReleaseApproval.DECISION_CHOICES)
    comment = serializers.CharField(required=False, allow_blank=True)


class ReleaseSerializer(serializers.ModelSerializer):
    product_display = serializers.CharField(source="get_product_display", read_only=True)
    revisions = RevisionSerializer(many=True, read_only=True)
    current_approved_revision = serializers.SerializerMethodField()

    class Meta:
        model = Release
        fields = ("id", "product", "product_display", "version", "legacy", "created_by",
                  "created_at", "current_approved_revision", "revisions")

    def get_current_approved_revision(self, obj):
        revision = current_approved_revision(obj)
        return revision.pk if revision else None


class AttemptSerializer(serializers.ModelSerializer):
    actor_name = serializers.SerializerMethodField()

    class Meta:
        model = DeliveryAttempt
        fields = ("kind", "outcome", "error", "actor_name", "at")

    def get_actor_name(self, obj):
        return _name(obj.actor)


class DeliverySerializer(serializers.ModelSerializer):
    history = AttemptSerializer(many=True, read_only=True)

    class Meta:
        model = CampaignDelivery
        fields = ("id", "recipient_id", "email", "status", "attempts", "provider_ref",
                  "last_error", "updated_at", "history")


class CampaignSerializer(serializers.ModelSerializer):
    """Only reachable through policy.visible_campaigns, i.e. by people
    allowed to see recipient data."""
    release = serializers.SerializerMethodField()
    revision_number = serializers.IntegerField(source="release_revision.number",
                                               read_only=True)
    synthetic = serializers.BooleanField(source="snapshot.synthetic", read_only=True)
    source = serializers.CharField(source="snapshot.source", read_only=True)
    segment = serializers.CharField(source="snapshot.segment", read_only=True)
    fetched_at = serializers.DateTimeField(source="snapshot.fetched_at", read_only=True)
    recipient_count = serializers.IntegerField(source="snapshot.count", read_only=True)
    recipients = serializers.JSONField(source="snapshot.recipients", read_only=True)
    created_by_name = serializers.SerializerMethodField()
    sent_by_name = serializers.SerializerMethodField()
    deliveries = DeliverySerializer(many=True, read_only=True)

    class Meta:
        model = Campaign
        fields = ("id", "release", "release_revision", "revision_number", "subject",
                  "body_text", "body_html", "synthetic", "source", "segment", "fetched_at",
                  "recipient_count", "recipients", "status", "created_by",
                  "created_by_name", "created_at", "sent_by", "sent_by_name", "sent_at",
                  "resend_of", "resend_reason", "deliveries")

    def get_release(self, obj):
        return {"id": obj.release_revision.release_id,
                "label": str(obj.release_revision.release)}

    def get_created_by_name(self, obj):
        return _name(obj.created_by)

    def get_sent_by_name(self, obj):
        return _name(obj.sent_by)
