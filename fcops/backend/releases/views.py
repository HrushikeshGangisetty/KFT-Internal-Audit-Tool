from django.db.models import Prefetch
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.generics import get_object_or_404
from rest_framework.response import Response

from access import policy
from access.mixins import ScopedViewSetMixin
from accounts.models import Capability

from . import recipients, services
from .models import CampaignDelivery, ReleaseApproval, ReleaseRevision
from .serializers import (CampaignSerializer, DecisionSerializer, ReleaseCreateSerializer,
                          ReleaseSerializer, RevisionInputSerializer)


class ReleaseViewSet(ScopedViewSetMixin, mixins.RetrieveModelMixin, mixins.ListModelMixin,
                     viewsets.GenericViewSet):
    """No update or delete: an edit is a new revision (``revise``)."""
    serializer_class = ReleaseSerializer
    filterset_fields = ("product", "legacy")

    def get_scoped_queryset(self):
        return policy.visible_releases(self.request.user).prefetch_related(Prefetch(
            "revisions", queryset=ReleaseRevision.objects.select_related(
                "release", "created_by").prefetch_related(Prefetch(
                    "approvals", queryset=ReleaseApproval.objects.select_related("actor")))))

    def _respond(self, release, code=status.HTTP_200_OK):
        return Response(self.get_serializer(self.get_queryset().get(pk=release.pk)).data,
                        status=code)

    def create(self, request):
        s = ReleaseCreateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        release = services.create_release(actor=request.user, **s.validated_data)
        return self._respond(release, status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def revise(self, request, pk=None):
        s = RevisionInputSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        release = self.get_object()
        services.revise(release, actor=request.user, **s.validated_data)
        return self._respond(release, status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def decide(self, request, pk=None):
        s = DecisionSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        release = self.get_object()
        revision = get_object_or_404(release.revisions.all(), pk=s.validated_data["revision"])
        services.decide(revision, actor=request.user, role=s.validated_data["role"],
                        decision=s.validated_data["decision"],
                        comment=s.validated_data.get("comment", ""))
        return self._respond(release)


class CampaignViewSet(ScopedViewSetMixin, mixins.RetrieveModelMixin, mixins.ListModelMixin,
                      viewsets.GenericViewSet):
    """Preview, send, retry, reconcile and resend. Every write rechecks the
    sender capability and the approval in the service."""
    serializer_class = CampaignSerializer
    filterset_fields = ("status", "release_revision")

    def get_scoped_queryset(self):
        qs = policy.visible_campaigns(self.request.user).select_related(
            "snapshot", "release_revision__release", "created_by", "sent_by"
        ).prefetch_related("deliveries__history__actor")
        release = self.request.query_params.get("release")
        return qs.filter(release_revision__release=release) if release else qs

    def _respond(self, campaign, code=status.HTTP_200_OK):
        return Response(self.get_serializer(self.get_queryset().get(pk=campaign.pk)).data,
                        status=code)

    @action(detail=False, methods=["get"])
    def segments(self, request):
        if not policy.has_capability(request.user, Capability.CAN_SEND_ANNOUNCEMENTS):
            raise PermissionDenied("Announcements need the 'can send announcements' "
                                   "capability.")
        source = recipients.get_source()
        return Response({"source": source.name,
                         "synthetic": isinstance(source, recipients.SyntheticRecipientSource),
                         "segments": source.segments()})

    @action(detail=False, methods=["post"])
    def preview(self, request):
        revision = get_object_or_404(ReleaseRevision.objects.filter(
            release__in=policy.visible_releases(request.user)),
            pk=request.data.get("release_revision"))
        campaign = services.preview(actor=request.user, revision=revision,
                                    segment=str(request.data.get("segment") or ""))
        return self._respond(campaign, status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def send(self, request, pk=None):
        campaign = services.send(self.get_object(), actor=request.user,
                                 idempotency_key=str(request.data.get("idempotency_key") or ""))
        return self._respond(campaign)

    @action(detail=True, methods=["post"])
    def retry(self, request, pk=None):
        campaign = self.get_object()
        services.retry_failed(campaign, actor=request.user)
        return self._respond(campaign)

    @action(detail=True, methods=["post"])
    def resend(self, request, pk=None):
        new = services.resend(self.get_object(), actor=request.user,
                              reason=str(request.data.get("reason") or ""))
        return self._respond(new, status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def reconcile(self, request, pk=None):
        campaign = self.get_object()
        delivery = get_object_or_404(CampaignDelivery.objects.filter(campaign=campaign),
                                     pk=request.data.get("delivery"))
        services.reconcile(delivery, actor=request.user,
                           outcome=str(request.data.get("outcome") or ""),
                           note=str(request.data.get("note") or ""))
        return self._respond(campaign)
