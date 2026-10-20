from django.http import FileResponse
from django.shortcuts import get_object_or_404
from rest_framework import status as http_status
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from django.db.models import Q
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from access import policy
from access.mixins import ScopedViewSetMixin
from accounts.models import Department, User
from accounts.permissions import CanWriteIssues, IsLeadOrAbove, IsManager
from core import audit
from core.exceptions import WorkflowError
from core.models import AuditLogEntry
from fc.models import StageRecord

from . import services
from .models import (Category, Handoff, Impact, Issue, IssueAttachment, IssueKind,
                     IssueStatus, KnownIssue, ProductArea, Severity, Urgency)
from .search import find_similar, search_issues, search_known_issues
from .serializers import (HandoffProposeSerializer, HandoffRespondSerializer,
                          HandoffSerializer, InvestigationNoteSerializer,
                          IssueAttachmentSerializer, IssueCreateSerializer,
                          IssueDetailSerializer, IssueListSerializer,
                          KnownIssueSerializer, ParticipantAddSerializer,
                          ReassignSerializer, ReportSerializer,
                          SimilarQuerySerializer, StatusChangeSerializer,
                          VerifySerializer, WaitingSerializer)


class IssueViewSet(ScopedViewSetMixin, viewsets.ModelViewSet):
    permission_classes = [CanWriteIssues]
    filterset_fields = ("fc", "status", "severity", "category", "discovered_stage",
                        "assigned_department", "discovering_department",
                        "assigned_person", "known_issue", "is_recurring",
                        "product_area", "urgency", "kind", "parent", "queue",
                        "accountable_user")
    ordering_fields = ("created_at", "updated_at", "severity")

    def get_serializer_class(self):
        if self.action == "list":
            return IssueListSerializer
        if self.action == "create":
            return IssueCreateSerializer
        return IssueDetailSerializer

    def get_scoped_queryset(self):
        return policy.visible_issues(self.request.user).select_related(
            "fc", "discovered_by", "discovering_department", "assigned_department",
            "assigned_person", "root_cause_department", "known_issue", "queue",
            "accountable_user", "reporter", "parent")

    def get_queryset(self):
        # Scope first, then search: a hidden match can neither take a ranked
        # slot nor appear in a count.
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
        fc = (get_object_or_404(policy.visible_fcs(request.user), pk=data["fc"])
              if data.get("fc") else None)
        stage_record = None
        if fc and data.get("discovered_stage_record"):
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
        return Response(IssueDetailSerializer(
            issue, context=self.get_serializer_context()).data,
            status=http_status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        issue = self.get_object()
        if issue.status == IssueStatus.CLOSED and not request.user.is_admin_role:
            raise WorkflowError("Closed issues are read-only (admin correction only).",
                                code="issue_closed")
        # Refuse, rather than silently drop, attempts to rewrite discovery
        # facts or routing state (WP4).
        refused = sorted(set(request.data) & set(
            services.IMMUTABLE_FIELDS + services.SERVICE_OWNED_FIELDS))
        if refused:
            raise WorkflowError(f"These fields cannot be edited: {', '.join(refused)}.",
                                code="immutable_field")
        s = IssueDetailSerializer(issue, data=request.data, partial=True,
                                  context=self.get_serializer_context())
        s.is_valid(raise_exception=True)
        issue = services.edit_issue(issue, actor=request.user,
                                    changes=s.validated_data)
        return Response(IssueDetailSerializer(
            issue, context=self.get_serializer_context()).data)

    def destroy(self, request, *args, **kwargs):
        return Response({"detail": "Issues are never deleted; close them instead."},
                        status=http_status.HTTP_405_METHOD_NOT_ALLOWED)

    # --- WP4/WP5: report, routing, acknowledgement, handoffs --------------
    @action(detail=False, methods=["post"],
            parser_classes=[JSONParser, MultiPartParser, FormParser])
    def report(self, request):
        """Scenario 1: returns the ID and the queue. Attachment failures are
        listed but never fail the report."""
        s = ReportSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = dict(s.validated_data)
        user = request.user
        fc_id, parent_id = d.pop("fc", None), d.pop("parent", None)
        issue = services.submit_report(
            reporter=user, title=d.pop("title"), symptom=d.pop("symptom"),
            urgency=d.pop("urgency"),
            fc=get_object_or_404(policy.visible_fcs(user), pk=fc_id) if fc_id else None,
            parent=get_object_or_404(policy.visible_issues(user), pk=parent_id)
            if parent_id else None, **d)
        failed = []
        for upload in request.FILES.getlist("files"):
            try:
                services.add_attachment(issue, upload=upload, actor=user)
            except Exception as exc:  # noqa: BLE001 - reported per file
                failed.append({"name": upload.name,
                               "error": getattr(exc, "message", str(exc))})
        data = IssueDetailSerializer(issue, context=self.get_serializer_context()).data
        return Response({**data, "failed_attachments": failed},
                        status=http_status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def acknowledge(self, request, pk=None):
        issue = services.acknowledge(self.get_object(), user=request.user)
        return Response(IssueDetailSerializer(
            issue, context=self.get_serializer_context()).data)

    @action(detail=True, methods=["post"], url_path="accept-ownership")
    def accept_ownership(self, request, pk=None):
        member = get_object_or_404(User, pk=request.data.get("member") or request.user.pk,
                                   is_active=True)
        issue = services.accept_ownership(self.get_object(), actor=request.user,
                                          member=member)
        return Response(IssueDetailSerializer(
            issue, context=self.get_serializer_context()).data)

    @action(detail=True, methods=["post"])
    def handoffs(self, request, pk=None):
        issue = self.get_object()
        s = HandoffProposeSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        handoff = services.propose_handoff(
            issue, actor=request.user,
            to_department=get_object_or_404(Department, pk=d["to_department"]),
            to_user=get_object_or_404(User, pk=d["to_user"], is_active=True)
            if d.get("to_user") else None,
            reason=d["reason"])
        return Response(HandoffSerializer(handoff).data,
                        status=http_status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="units")
    def link_unit(self, request, pk=None):
        issue = self.get_object()
        fc = get_object_or_404(policy.visible_fcs(request.user), pk=request.data.get("fc"))
        services.link_unit(issue, fc=fc, actor=request.user,
                           reason=request.data.get("reason", ""))
        return Response(IssueDetailSerializer(
            issue, context=self.get_serializer_context()).data,
            status=http_status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def evidence(self, request, pk=None):
        from fc.evidence import link_evidence
        from fc.models import ConfigEvidence
        issue = self.get_object()
        evidence = get_object_or_404(
            policy.scope_by_fc(request.user, ConfigEvidence.objects.all()),
            pk=request.data.get("evidence"))
        link_evidence(issue, evidence, actor=request.user)
        return Response(IssueDetailSerializer(
            issue, context=self.get_serializer_context()).data,
            status=http_status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="blocks-stage")
    def blocks_stage(self, request, pk=None):
        issue = services.set_blocks_stage(
            self.get_object(), actor=request.user,
            blocks=bool(request.data.get("blocks")),
            reason=request.data.get("reason", ""))
        return Response(IssueDetailSerializer(
            issue, context=self.get_serializer_context()).data)

    @action(detail=True, methods=["post"])
    def notes(self, request, pk=None):
        issue = self.get_object()
        note = (request.data.get("note") or "").strip()
        if not note:
            raise WorkflowError("Note text is required.", code="note_required")
        supersedes = (get_object_or_404(issue.investigation_notes,
                                        pk=request.data["supersedes"])
                      if request.data.get("supersedes") else None)
        entry = services.add_note(issue, author=request.user, note=note,
                                  note_type=request.data.get("note_type") or "general",
                                  supersedes=supersedes)
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
        return Response(self.get_serializer(issue).data)

    @action(detail=True, methods=["post"], url_path="status")
    def change_status(self, request, pk=None):
        issue = self.get_object()
        s = StatusChangeSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        details = {k: d[k] for k in ("workaround", "affected_versions",
                                     "affected_units", "unresolved_risks",
                                     "evidence_links") if k in d}
        issue = services.change_status(
            issue, d["status"], actor=request.user, note=d.get("note", ""),
            root_cause=d.get("root_cause"), resolution=d.get("resolution"),
            root_cause_department=Department.objects.filter(
                pk=d.get("root_cause_department")).first()
            if d.get("root_cause_department") else None,
            root_cause_status=d.get("root_cause_status"),
            resolution_details=details,
            verification_details={k: d[k] for k in ("what_tested", "evidence")
                                  if k in d})
        return Response(self.get_serializer(issue).data)

    @action(detail=True, methods=["post"])
    def verify(self, request, pk=None):
        """Record a pass or fail; a fail returns the issue to investigating."""
        s = VerifySerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        issue = services.verify(self.get_object(), verifier=request.user,
                                passed=d["result"] == "pass",
                                what_tested=d["what_tested"], evidence=d["evidence"],
                                note=d["notes"])
        return Response(self.get_serializer(issue).data)

    @action(detail=True, methods=["post"])
    def reopen(self, request, pk=None):
        issue = self.get_object()
        issue = services.reopen(issue, actor=request.user,
                                reason=request.data.get("reason", ""))
        return Response(self.get_serializer(issue).data)

    @action(detail=True, methods=["post"])
    def waiting(self, request, pk=None):
        s = WaitingSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        issue = services.set_waiting(self.get_object(), actor=request.user,
                                     waiting=d["waiting"], reason=d["reason"],
                                     dependency_owner=d["dependency_owner"],
                                     next_followup_at=d.get("next_followup_at"))
        return Response(self.get_serializer(issue).data)

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
            affected_software=request.data.get("affected_software"),
            audience=request.data.get("audience"))
        return Response(KnownIssueSerializer(
            known, context=self.get_serializer_context()).data,
            status=http_status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="link-known-issue")
    def link_known_issue(self, request, pk=None):
        issue = self.get_object()
        known = get_object_or_404(policy.visible_knowledge(request.user),
                                  pk=request.data.get("known_issue"))
        issue = services.link_issue_to_known(issue, known, actor=request.user,
                                             reason=request.data.get("reason", ""))
        return Response(self.get_serializer(issue).data)

    @action(detail=True, methods=["post"])
    def participants(self, request, pk=None):
        """Add a collaborator or verifier. PLACEHOLDER rule until WP5/WP7:
        heads, managers and the issue's assigned person may add."""
        issue = self.get_object()
        if not (policy.is_head_or_manager(request.user)
                or issue.assigned_person_id == request.user.pk):
            raise PermissionDenied("Only a head, a manager or the assigned person "
                                   "may add participants.")
        s = ParticipantAddSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        services.add_participant(
            issue, user=get_object_or_404(User, pk=s.validated_data["user"],
                                          is_active=True),
            role=s.validated_data["role"], actor=request.user)
        return Response(self.get_serializer(issue).data,
                        status=http_status.HTTP_201_CREATED)

    def _similar(self, **kwargs):
        user = self.request.user
        scored, known = find_similar(
            issues=policy.visible_issues(user).select_related(
                "fc", "assigned_department", "discovering_department", "known_issue"),
            known_issues=policy.visible_knowledge(user), **kwargs)
        context = self.get_serializer_context()
        return Response({
            "similar_issues": [
                {"score": round(score, 4), "matched_on": matched,
                 **IssueListSerializer(issue, context=context).data}
                for score, matched, issue in scored],
            "known_issues": KnownIssueSerializer(known, many=True,
                                                 context=context).data,
        })

    @action(detail=True, methods=["get"])
    def similar(self, request, pk=None):
        issue = self.get_object()
        return self._similar(
            text=f"{issue.title} {issue.symptoms}",
            stage=issue.discovered_stage, category=issue.category,
            hardware_revision=issue.hardware_revision,
            firmware_version=issue.firmware_version,
            gcs_version=issue.gcs_version,
            configurator_version=issue.configurator_version,
            parameter_profile=issue.parameter_profile,
            exclude_issue_id=issue.pk)

    @action(detail=False, methods=["get", "post"], url_path="similar-search")
    def similar_search(self, request):
        payload = request.data if request.method == "POST" else request.query_params
        s = SimilarQuerySerializer(data=payload)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        return self._similar(
            text=d.get("text", ""), stage=d.get("stage") or None,
            category=d.get("category") or None,
            hardware_revision=d.get("hardware_revision") or None,
            firmware_version=d.get("firmware_version") or None,
            gcs_version=d.get("gcs_version") or None,
            configurator_version=d.get("configurator_version") or None,
            parameter_profile=d.get("parameter_profile") or None,
            exclude_issue_id=d.get("exclude_issue_id"),
            limit=d.get("limit", 10))

    @action(detail=False, methods=["get"])
    def search(self, request):
        params = request.query_params
        qs = search_issues(self.get_scoped_queryset(), text=params.get("q"),
                           filters={k: params.get(k) for k in params.keys()})
        page = self.paginate_queryset(qs)
        data = IssueListSerializer(page if page is not None else qs, many=True, context=self.get_serializer_context()).data
        return self.get_paginated_response(data) if page is not None else Response(data)

    @action(detail=False, methods=["get"])
    def meta(self, request):
        return Response({
            "statuses": [{"value": v, "label": l} for v, l in IssueStatus.choices],
            "severities": [{"value": v, "label": l} for v, l in Severity.choices],
            "categories": [{"value": v, "label": l} for v, l in Category.choices],
            "product_areas": [{"value": v, "label": l} for v, l in ProductArea.choices],
            "impacts": [{"value": v, "label": l} for v, l in Impact.choices],
            "urgencies": [{"value": v, "label": l} for v, l in Urgency.choices],
            "kinds": [{"value": v, "label": l} for v, l in IssueKind.choices],
        })


class HandoffViewSet(ScopedViewSetMixin, viewsets.ReadOnlyModelViewSet):
    """Handoffs on issues the reader can see; responding is a service call."""
    serializer_class = HandoffSerializer
    filterset_fields = ("issue", "status")

    def get_scoped_queryset(self):
        return Handoff.objects.filter(
            issue__in=policy.visible_issues(self.request.user)).select_related(
            "issue", "to_department")

    @action(detail=True, methods=["post"])
    def respond(self, request, pk=None):
        s = HandoffRespondSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        handoff = services.respond_handoff(
            self.get_object(), actor=request.user, accept=s.validated_data["accept"],
            reason=s.validated_data["reason"])
        return Response(HandoffSerializer(handoff).data)


class MyQueueView(APIView):
    """What I am accountable for, what awaits my acknowledgement, and the
    handoffs awaiting my response. Built from access.policy scopes."""

    def get(self, request):
        user = request.user
        issues = policy.visible_issues(user).exclude(status=IssueStatus.CLOSED)
        mine = issues.filter(accountable_user=user)
        awaiting = issues.filter(acknowledged_at__isnull=True).filter(
            Q(accountable_user=user) | Q(queue__head=user) | Q(queue__backup=user))
        handoffs = [h for h in Handoff.objects.filter(
            status=Handoff.PENDING, issue__in=policy.visible_issues(user))
            .select_related("issue", "to_department")
            if services.can_respond(h, user)]
        ctx = {"request": request}
        return Response({
            "accountable": IssueListSerializer(mine, many=True, context=ctx).data,
            "awaiting_acknowledgement": IssueListSerializer(awaiting, many=True,
                                                            context=ctx).data,
            "handoffs_awaiting_response": HandoffSerializer(handoffs, many=True).data,
        })


class KnownIssueViewSet(ScopedViewSetMixin, viewsets.ModelViewSet):
    serializer_class = KnownIssueSerializer
    filterset_fields = ("category", "status", "owning_department")

    def get_permissions(self):
        if self.request.method in ("GET", "HEAD", "OPTIONS"):
            return [IsAuthenticated()]
        return [IsLeadOrAbove()]

    def get_scoped_queryset(self):
        return policy.visible_knowledge(self.request.user).select_related(
            "promoted_by", "owning_department")

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
        qs = policy.visible_issues(request.user).filter(known_issue=known)
        return Response(IssueListSerializer(qs, many=True, context=self.get_serializer_context()).data)


class IssueAttachmentViewSet(ScopedViewSetMixin, viewsets.ModelViewSet):
    serializer_class = IssueAttachmentSerializer
    permission_classes = [CanWriteIssues]
    parser_classes = [MultiPartParser, FormParser]
    filterset_fields = ("issue",)

    def get_scoped_queryset(self):
        return policy.visible_attachments(self.request.user).select_related(
            "issue", "uploaded_by")

    @action(detail=True, methods=["get"])
    def download(self, request, pk=None):
        """Stream the file after a scope check through the parent issue; an
        attachment outside scope is a 404 like any other record."""
        attachment = self.get_object()
        response = FileResponse(attachment.file.open("rb"), as_attachment=True,
                                filename=attachment.original_name or None)
        response["X-Content-Type-Options"] = "nosniff"
        return response

    def perform_create(self, serializer):
        upload = self.request.FILES.get("file")
        obj = serializer.save(uploaded_by=self.request.user,
                              original_name=getattr(upload, "name", ""),
                              content_type=getattr(upload, "content_type", ""),
                              size=getattr(upload, "size", 0))
        audit.record(obj.issue, AuditLogEntry.ACTION_UPDATE, actor=self.request.user,
                     after={"attachment": obj.original_name},
                     note="Attachment added", fc=obj.issue.fc)
