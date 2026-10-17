from django.db.models import Avg, Count, F, Prefetch, Q
from django.conf import settings
from django.core.cache import cache
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
    """Manager dashboard aggregate (PRD §22).

    Fourteen distinct aggregates over four tables, each a round trip to a
    hosted database. They cannot be merged — different tables, different
    groupings — so the answer is cached briefly instead. A production overview
    does not need to be accurate to the second, and a short TTL turns repeated
    navigation into an instant page while keeping the numbers current enough to
    act on. Pass ``?fresh=1`` to bypass it.
    """

    permission_classes = [IsAuthenticated]
    CACHE_SECONDS = int(getattr(settings, "DASHBOARD_CACHE_SECONDS", 20))

    def get(self, request):
        window_days = request.query_params.get("window_days", "90")
        cache_key = f"dashboard:summary:{window_days}"
        if not request.query_params.get("fresh"):
            cached = cache.get(cache_key)
            if cached is not None:
                return Response({**cached, "cached": True})
        payload = self._build(request)
        cache.set(cache_key, payload, self.CACHE_SECONDS)
        return Response({**payload, "cached": False})

    def _build(self, request):
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
                   .prefetch_related(
                       Prefetch("issues",
                                queryset=Issue.objects.exclude(
                                    status=IssueStatus.CLOSED)))[:50])
        blocked_rows = []
        for fc in blocked:
            open_issues = list(fc.issues.all())
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

        # Averaged in the database rather than by pulling every row across the
        # network and looping in Python — the difference is a few hundred bytes
        # versus the whole table on every dashboard load.
        avg_resolution = Issue.objects.filter(
            resolved_at__isnull=False, created_at__gte=since
        ).aggregate(avg=Avg(F("resolved_at") - F("created_at")))["avg"]
        avg_resolution_hours = (round(avg_resolution.total_seconds() / 3600, 1)
                                if avg_resolution else None)

        avg_time_in_stage = [
            {"stage": row["stage"], "label": Stage(row["stage"]).label,
             "avg_hours": round(row["avg"].total_seconds() / 3600, 2)}
            for row in StageRecord.objects.filter(
                completed_at__isnull=False, started_at__isnull=False,
                completed_at__gte=since
            ).values("stage").annotate(
                avg=Avg(F("completed_at") - F("started_at"))
            ).order_by("stage")
            if row["avg"] is not None]

        rework_counts = (ReworkRecord.objects.filter(created_at__gte=since)
                         .values("fc__serial").annotate(n=Count("id")).order_by("-n")[:10])

        return {
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
        }


class HealthView(APIView):
    permission_classes = []
    authentication_classes = []

    def get(self, request):
        return Response({"status": "ok", "time": timezone.now().isoformat()})
