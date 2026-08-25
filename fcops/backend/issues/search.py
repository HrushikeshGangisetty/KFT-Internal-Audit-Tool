"""PostgreSQL full-text + structured search and similar-issue detection
(PRD §21). No AI — weighted tsvector plus structured-field boosts."""
from django.contrib.postgres.search import (SearchHeadline, SearchQuery,
                                            SearchRank, SearchVector)
from django.db.models import F, FloatField, Q, Value
from django.db.models.functions import Coalesce, Greatest

ISSUE_VECTOR = (
    SearchVector("title", weight="A", config="english")
    + SearchVector("symptoms", weight="A", config="english")
    + SearchVector("root_cause", weight="B", config="english")
    + SearchVector("resolution", weight="B", config="english")
    + SearchVector("description", weight="C", config="english")
)

KNOWN_ISSUE_VECTOR = (
    SearchVector("title", weight="A", config="english")
    + SearchVector("symptoms_summary", weight="A", config="english")
    + SearchVector("root_cause", weight="B", config="english")
    + SearchVector("resolution", weight="B", config="english")
)


def reindex_issue(issue):
    from .models import Issue
    Issue.objects.filter(pk=issue.pk).update(search_vector=ISSUE_VECTOR)


def reindex_known_issue(known):
    from .models import KnownIssue
    KnownIssue.objects.filter(pk=known.pk).update(search_vector=KNOWN_ISSUE_VECTOR)


def reindex_all():
    from .models import Issue, KnownIssue
    Issue.objects.update(search_vector=ISSUE_VECTOR)
    KnownIssue.objects.update(search_vector=KNOWN_ISSUE_VECTOR)


def _query(text):
    text = (text or "").strip()
    if not text:
        return None
    # websearch_to_tsquery tolerates arbitrary user input (no syntax errors).
    return SearchQuery(text, search_type="websearch", config="english")


def search_issues(queryset, *, text=None, filters=None):
    filters = filters or {}
    field_map = {
        "fc": "fc__serial__iexact",
        "stage": "discovered_stage",
        "category": "category",
        "severity": "severity",
        "status": "status",
        "discovering_department": "discovering_department_id",
        "assigned_department": "assigned_department_id",
        "root_cause_department": "root_cause_department_id",
        "hardware_revision": "hardware_revision__iexact",
        "firmware_version": "firmware_version__iexact",
        "gcs_version": "gcs_version__iexact",
        "configurator_version": "configurator_version__iexact",
        "parameter_profile": "parameter_profile__iexact",
        "known_issue": "known_issue_id",
        "created_after": "created_at__gte",
        "created_before": "created_at__lte",
    }
    for key, lookup in field_map.items():
        value = filters.get(key)
        if value not in (None, "", []):
            queryset = queryset.filter(**{lookup: value})

    query = _query(text)
    if query is not None:
        queryset = (queryset.filter(search_vector=query)
                    .annotate(rank=SearchRank(F("search_vector"), query))
                    .order_by("-rank", "-created_at"))
    else:
        queryset = queryset.annotate(rank=Value(0.0, output_field=FloatField()))
    return queryset


def search_known_issues(queryset, *, text=None, filters=None):
    filters = filters or {}
    if filters.get("category"):
        queryset = queryset.filter(category=filters["category"])
    if filters.get("status"):
        queryset = queryset.filter(status=filters["status"])
    query = _query(text)
    if query is not None:
        queryset = (queryset.filter(search_vector=query)
                    .annotate(rank=SearchRank(F("search_vector"), query))
                    .order_by("-rank", "-updated_at"))
    else:
        queryset = queryset.annotate(rank=Value(0.0, output_field=FloatField()))
    return queryset


STRUCTURED_BOOSTS = [
    ("firmware_version", 0.35),
    ("hardware_revision", 0.30),
    ("gcs_version", 0.20),
    ("configurator_version", 0.20),
    ("parameter_profile", 0.15),
    ("discovered_stage", 0.25),
    ("category", 0.20),
]


def find_similar(*, text, stage=None, category=None, hardware_revision=None,
                 firmware_version=None, gcs_version=None,
                 configurator_version=None, parameter_profile=None,
                 exclude_issue_id=None, limit=10):
    """Ranked historical issues that look like the one being described.

    Score = full-text rank + structured-field overlap bonuses. Resolved and
    known issues are boosted because a resolved match is what the searcher
    actually needs (PRD §21).
    """
    from .models import Issue, IssueStatus, KnownIssue

    qs = Issue.objects.select_related("fc", "assigned_department",
                                      "discovering_department", "known_issue")
    if exclude_issue_id:
        qs = qs.exclude(pk=exclude_issue_id)

    query = _query(text)
    candidates = []
    if query is not None:
        matched = (qs.filter(search_vector=query)
                   .annotate(rank=SearchRank(F("search_vector"), query))
                   .order_by("-rank")[:100])
        candidates = list(matched)
    if not candidates:
        # Fall back to structured matching alone so the panel is still useful
        # for terse symptom text.
        structured = Q()
        if firmware_version:
            structured |= Q(firmware_version__iexact=firmware_version)
        if hardware_revision:
            structured |= Q(hardware_revision__iexact=hardware_revision)
        if stage:
            structured |= Q(discovered_stage=stage)
        if category:
            structured |= Q(category=category)
        if structured:
            candidates = list(qs.filter(structured).order_by("-created_at")[:50])
            for c in candidates:
                c.rank = 0.0

    wanted = {
        "firmware_version": firmware_version,
        "hardware_revision": hardware_revision,
        "gcs_version": gcs_version,
        "configurator_version": configurator_version,
        "parameter_profile": parameter_profile,
        "discovered_stage": stage,
        "category": category,
    }
    scored = []
    for issue in candidates:
        score = float(getattr(issue, "rank", 0.0) or 0.0)
        matched_on = []
        for field, boost in STRUCTURED_BOOSTS:
            expected = wanted.get(field)
            actual = getattr(issue, field, None)
            if expected and actual and str(expected).lower() == str(actual).lower():
                score += boost
                matched_on.append(field)
        if issue.status in (IssueStatus.RESOLVED, IssueStatus.VERIFIED,
                            IssueStatus.CLOSED):
            score += 0.25
        if issue.known_issue_id:
            score += 0.30
        scored.append((score, matched_on, issue))
    scored.sort(key=lambda row: row[0], reverse=True)

    known = []
    if query is not None:
        known = list(
            KnownIssue.objects.filter(search_vector=query, status="ACTIVE")
            .annotate(rank=SearchRank(F("search_vector"), query))
            .order_by("-rank")[:5])

    return scored[:limit], known
