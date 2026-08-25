from django.db.models import Avg, Count, F, Q
from django.utils import timezone
from datetime import timedelta

from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsManager
from fc.lifecycle import STAGE_ORDER, Stage
from fc.models import FlightController, FCStatus, ReworkRecord, StageRecord

from .models import AuditLogEntry, Notification
from .serializers import AuditLogEntrySerializer, NotificationSerializer


class AuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    """Append-only: read endpoints only, no create/update/delete route exists."""
    queryset = AuditLogEntry.objects.select_related("actor", "fc").all()
    serializer_class = AuditLogEntrySerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ("entity_type", "entity_id", "action", "actor", "fc")
    ordering_fields = ("created_at",)


class NotificationViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Notification.objects.filter(recipient=self.request.user)

    @action(detail=False, methods=["get"])
    def unread_count(self, request):
        return Response({"count": self.get_queryset().filter(read_at__isnull=True).count()})

    @action(detail=False, methods=["post"])
    def mark_all_read(self, request):
        self.get_queryset().filter(read_at__isnull=True).update(read_at=timezone.now())
        return Response({"status": "ok"})

    @action(detail=True, methods=["post"])
    def mark_read(self, request, pk=None):
        obj = self.get_object()
        obj.read_at = obj.read_at or timezone.now()
        obj.save(update_fields=["read_at"])
        return Response(NotificationSerializer(obj).data)


class DashboardSummaryView(APIView):
    """Manager dashboard aggregate (PRD §22)."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from issues.models import Issue, IssueStatus, Severity

        window_days = int(request.query_params.get("window_days", 90))
        since = timezone.now() - timedelta(days=window_days)

        by_stage = {s: 0 for s in STAGE_ORDER}
        for row in (FlightController.objects
                    .exclude(status__in=[FCStatus.APPROVED, FCStatus.REJECTED])
                    .values("current_stage").annotate(n=Count("id"))):
            by_stage[row["current_stage"]] = row["n"]

        by_status = {row["status"]: row["n"] for row in
                     FlightController.objects.values("status").annotate(n=Count("id"))}

        blocked = (FlightController.objects.filter(status=FCStatus.BLOCKED)
                   .prefetch_related("issues")[:50])
        blocked_rows = []
        for fc in blocked:
            open_issues = [i for i in fc.issues.all()
                           if i.status not in (IssueStatus.CLOSED,)]
            blocked_rows.append({
                "id": fc.id, "serial": fc.serial,
                "stage": Stage(fc.current_stage).label,
                "issues": [{"id": i.id, "key": i.key, "title": i.title,
                            "severity": i.severity, "status": i.status}
                           for i in open_issues],
            })

        open_issue_qs = Issue.objects.exclude(status=IssueStatus.CLOSED)
        issues_by_department = list(
            open_issue_qs.values("assigned_department__name")
            .annotate(n=Count("id")).order_by("-n"))
        issues_by_severity = list(
            open_issue_qs.values("severity").annotate(n=Count("id")).order_by())
        issues_by_category = list(
            open_issue_qs.values("category").annotate(n=Count("id")).order_by())
        issues_by_discovery_stage = list(
            Issue.objects.filter(created_at__gte=since)
            .values("discovered_stage").annotate(n=Count("id")).order_by("-n"))

        resolution_times = []
        for issue in Issue.objects.filter(resolved_at__isnull=False,
                                          created_at__gte=since):
            resolution_times.append((issue.resolved_at - issue.created_at).total_seconds())
        avg_resolution_hours = (round(sum(resolution_times) / len(resolution_times) / 3600, 1)
                                if resolution_times else None)

        stage_durations = {}
        for rec in StageRecord.objects.filter(completed_at__isnull=False,
                                              started_at__isnull=False,
                                              completed_at__gte=since):
            stage_durations.setdefault(rec.stage, []).append(
                (rec.completed_at - rec.started_at).total_seconds())
        avg_time_in_stage = [
            {"stage": s, "label": Stage(s).label,
             "avg_hours": round(sum(v) / len(v) / 3600, 2)}
            for s, v in stage_durations.items()]

        rework_counts = (ReworkRecord.objects.filter(created_at__gte=since)
                         .values("fc__serial").annotate(n=Count("id")).order_by("-n")[:10])

        return Response({
            "window_days": window_days,
            "fc_by_stage": [{"stage": s, "label": Stage(s).label, "count": by_stage[s]}
                            for s in STAGE_ORDER],
            "fc_by_status": by_status,
            "fc_total": FlightController.objects.count(),
            "blocked": blocked_rows,
            "open_issue_total": open_issue_qs.count(),
            "issues_by_department": issues_by_department,
            "issues_by_severity": issues_by_severity,
            "issues_by_category": issues_by_category,
            "issues_by_discovery_stage": issues_by_discovery_stage,
            "avg_resolution_hours": avg_resolution_hours,
            "avg_time_in_stage": avg_time_in_stage,
            "reworks_per_fc": list(rework_counts),
        })


class HealthView(APIView):
    permission_classes = []
    authentication_classes = []

    def get(self, request):
        return Response({"status": "ok", "time": timezone.now().isoformat()})
