from django.shortcuts import get_object_or_404
from rest_framework import status as http_status
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from accounts.models import Department, User
from accounts.permissions import CanWriteIssues, IsLeadOrAbove, IsManager
from core import audit
from core.exceptions import WorkflowError
from core.models import AuditLogEntry
from fc.models import FlightController, StageRecord

from . import services
from .models import (Category, Issue, IssueAttachment, IssueStatus, KnownIssue,
                     Severity)
from .search import find_similar, search_issues, search_known_issues
from .serializers import (InvestigationNoteSerializer, IssueAttachmentSerializer,
                          IssueCreateSerializer, IssueDetailSerializer,
                          IssueListSerializer, KnownIssueSerializer,
                          ReassignSerializer, SimilarQuerySerializer,
                          StatusChangeSerializer)


class IssueViewSet(viewsets.ModelViewSet):
    queryset = (Issue.objects.select_related(
        "fc", "discovered_by", "discovering_department", "assigned_department",
        "assigned_person", "root_cause_department", "known_issue").all())
    permission_classes = [CanWriteIssues]
    filterset_fields = ("fc", "status", "severity", "category", "discovered_stage",
                        "assigned_department", "discovering_department",
                        "assigned_person", "known_issue", "is_recurring")
    ordering_fields = ("created_at", "updated_at", "severity")

    def get_serializer_class(self):
        if self.action == "list":
            return IssueListSerializer
        if self.action == "create":
            return IssueCreateSerializer
        return IssueDetailSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        text = params.get("q") or params.get("search")
        if text or any(params.get(k) for k in
                       ("hardware_revision", "firmware_version", "gcs_version",
                        "configurator_version", "parameter_profile", "stage",
                        "created_after", "created_before")):
            qs = search_issues(qs, text=text, filters={
                k: params.get(k) for k in params.keys()})
        return qs

    def create(self, request, *args, **kwargs):
        s = IssueCreateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        data = s.validated_data
        fc = get_object_or_404(FlightController, pk=data["fc"])
        stage_record = None
        if data.get("discovered_stage_record"):
            stage_record = StageRecord.objects.filter(
                pk=data["discovered_stage_record"], fc=fc).first()
        issue = services.create_issue(
            fc=fc,
            title=data["title"],
            symptoms=data["symptoms"],
            description=data.get("description", ""),
            discovered_stage=data.get("discovered_stage"),
            discovered_stage_record=stage_record,
            category=data.get("category"),
            severity=data.get("severity", Severity.MAJOR),
            assigned_department=Department.objects.filter(
                pk=data.get("assigned_department")).first(),
            assigned_person=User.objects.filter(pk=data.get("assigned_person")).first(),
            symptom_tags=data.get("symptom_tags", []),
            version_overrides={
                "firmware_version": data.get("firmware_version"),
                "hardware_revision": data.get("hardware_revision"),
                "gcs_version": data.get("gcs_version"),
                "configurator_version": data.get("configurator_version"),
                "parameter_profile": data.get("parameter_profile"),
            },
            actor=request.user)
        return Response(IssueDetailSerializer(issue).data,
                        status=http_status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        issue = self.get_object()
        if issue.status == IssueStatus.CLOSED and not request.user.is_admin_role:
            raise WorkflowError("Closed issues are read-only (admin correction only).",
                                code="issue_closed")
        before = audit.snapshot(issue)
        response = super().update(request, *args, **kwargs)
        issue.refresh_from_db()
        from .search import reindex_issue
        reindex_issue(issue)
        audit.record_change(issue, AuditLogEntry.ACTION_UPDATE, before,
                            note="Issue edited", actor=request.user)
        return response

    def destroy(self, request, *args, **kwargs):
        return Response({"detail": "Issues are never deleted; close them instead."},
                        status=http_status.HTTP_405_METHOD_NOT_ALLOWED)

    @action(detail=True, methods=["post"])
    def notes(self, request, pk=None):
        issue = self.get_object()
        note = (request.data.get("note") or "").strip()
        if not note:
            raise WorkflowError("Note text is required.", code="note_required")
        entry = services.add_note(issue, author=request.user, note=note)
        return Response(InvestigationNoteSerializer(entry).data,
                        status=http_status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def reassign(self, request, pk=None):
        issue = self.get_object()
        s = ReassignSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        issue = services.reassign(
            issue, actor=request.user,
            to_department=Department.objects.filter(
                pk=s.validated_data.get("to_department")).first(),
            to_person=User.objects.filter(
                pk=s.validated_data.get("to_person")).first(),
            reason=s.validated_data["reason"])
        return Response(IssueDetailSerializer(issue).data)

    @action(detail=True, methods=["post"], url_path="status")
    def change_status(self, request, pk=None):
        issue = self.get_object()
        s = StatusChangeSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        issue = services.change_status(
            issue, d["status"], actor=request.user, note=d.get("note", ""),
            root_cause=d.get("root_cause"), resolution=d.get("resolution"),
            root_cause_department=Department.objects.filter(
                pk=d.get("root_cause_department")).first()
            if d.get("root_cause_department") else None)
        return Response(IssueDetailSerializer(issue).data)

    @action(detail=True, methods=["post"], permission_classes=[IsManager])
    def reopen(self, request, pk=None):
        issue = self.get_object()
        issue = services.reopen(issue, actor=request.user,
                                reason=request.data.get("reason", ""))
        return Response(IssueDetailSerializer(issue).data)

    @action(detail=True, methods=["post"])
    def waiting(self, request, pk=None):
        issue = self.get_object()
        issue = services.set_waiting(issue, actor=request.user,
                                     waiting=bool(request.data.get("waiting")),
                                     reason=request.data.get("reason", ""))
        return Response(IssueDetailSerializer(issue).data)

    @action(detail=True, methods=["post"], permission_classes=[IsLeadOrAbove])
    def promote(self, request, pk=None):
        issue = self.get_object()
        known = services.promote_to_known_issue(
            issue, actor=request.user,
            title=request.data.get("title"),
            symptoms_summary=request.data.get("symptoms_summary"),
            root_cause=request.data.get("root_cause"),
            resolution=request.data.get("resolution"),
            affected_revisions=request.data.get("affected_revisions"),
            affected_firmware=request.data.get("affected_firmware"),
            affected_software=request.data.get("affected_software"))
        return Response(KnownIssueSerializer(known).data,
                        status=http_status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="link-known-issue")
    def link_known_issue(self, request, pk=None):
        issue = self.get_object()
        known = get_object_or_404(KnownIssue, pk=request.data.get("known_issue"))
        issue = services.link_issue_to_known(issue, known, actor=request.user,
                                             reason=request.data.get("reason", ""))
        return Response(IssueDetailSerializer(issue).data)

    @action(detail=True, methods=["get"])
    def similar(self, request, pk=None):
        issue = self.get_object()
        scored, known = find_similar(
            text=f"{issue.title} {issue.symptoms}",
            stage=issue.discovered_stage, category=issue.category,
            hardware_revision=issue.hardware_revision,
            firmware_version=issue.firmware_version,
            gcs_version=issue.gcs_version,
            configurator_version=issue.configurator_version,
            parameter_profile=issue.parameter_profile,
            exclude_issue_id=issue.pk)
        return Response(_similar_payload(scored, known))

    @action(detail=False, methods=["get", "post"], url_path="similar-search")
    def similar_search(self, request):
        payload = request.data if request.method == "POST" else request.query_params
        s = SimilarQuerySerializer(data=payload)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        scored, known = find_similar(
            text=d.get("text", ""), stage=d.get("stage") or None,
            category=d.get("category") or None,
            hardware_revision=d.get("hardware_revision") or None,
            firmware_version=d.get("firmware_version") or None,
            gcs_version=d.get("gcs_version") or None,
            configurator_version=d.get("configurator_version") or None,
            parameter_profile=d.get("parameter_profile") or None,
            exclude_issue_id=d.get("exclude_issue_id"),
            limit=d.get("limit", 10))
        return Response(_similar_payload(scored, known))

    @action(detail=False, methods=["get"])
    def search(self, request):
        params = request.query_params
        qs = search_issues(self.queryset, text=params.get("q"),
                           filters={k: params.get(k) for k in params.keys()})
        page = self.paginate_queryset(qs)
        data = IssueListSerializer(page if page is not None else qs, many=True).data
        return self.get_paginated_response(data) if page is not None else Response(data)

    @action(detail=False, methods=["get"])
    def meta(self, request):
        return Response({
            "statuses": [{"value": v, "label": l} for v, l in IssueStatus.choices],
            "severities": [{"value": v, "label": l} for v, l in Severity.choices],
            "categories": [{"value": v, "label": l} for v, l in Category.choices],
        })


def _similar_payload(scored, known):
    return {
        "similar_issues": [
            {"score": round(score, 4), "matched_on": matched,
             **IssueListSerializer(issue).data}
            for score, matched, issue in scored],
        "known_issues": KnownIssueSerializer(known, many=True).data,
    }


class KnownIssueViewSet(viewsets.ModelViewSet):
    queryset = KnownIssue.objects.select_related("promoted_by",
                                                 "owning_department").all()
    serializer_class = KnownIssueSerializer
    filterset_fields = ("category", "status", "owning_department")

    def get_permissions(self):
        if self.request.method in ("GET", "HEAD", "OPTIONS"):
            return [IsAuthenticated()]
        return [IsLeadOrAbove()]

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        text = params.get("q") or params.get("search")
        if text:
            qs = search_known_issues(qs, text=text, filters={})
        return qs

    def perform_update(self, serializer):
        before = audit.snapshot(serializer.instance)
        obj = serializer.save()
        from .search import reindex_known_issue
        reindex_known_issue(obj)
        audit.record_change(obj, AuditLogEntry.ACTION_UPDATE, before,
                            note="Known issue updated", actor=self.request.user)

    @action(detail=True, methods=["get"])
    def occurrences(self, request, pk=None):
        known = self.get_object()
        return Response(IssueListSerializer(known.linked_issues.all(), many=True).data)


class IssueAttachmentViewSet(viewsets.ModelViewSet):
    queryset = IssueAttachment.objects.select_related("issue", "uploaded_by").all()
    serializer_class = IssueAttachmentSerializer
    permission_classes = [CanWriteIssues]
    parser_classes = [MultiPartParser, FormParser]
    filterset_fields = ("issue",)

    def perform_create(self, serializer):
        upload = self.request.FILES.get("file")
        obj = serializer.save(uploaded_by=self.request.user,
                              original_name=getattr(upload, "name", ""),
                              content_type=getattr(upload, "content_type", ""),
                              size=getattr(upload, "size", 0))
        audit.record(obj.issue, AuditLogEntry.ACTION_UPDATE, actor=self.request.user,
                     after={"attachment": obj.original_name},
                     note="Attachment added", fc=obj.issue.fc)
