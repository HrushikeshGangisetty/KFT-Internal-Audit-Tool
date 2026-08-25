"""Rebuild the full-text search vectors for every issue and known issue.

Needed after a bulk data load, a restore into a new database, or any write path
that bypassed the service layer.
"""
from django.core.management.base import BaseCommand

from issues.models import Issue, KnownIssue
from issues.search import reindex_all


class Command(BaseCommand):
    help = "Rebuild search_vector for all issues and known issues."

    def handle(self, *args, **options):
        reindex_all()
        self.stdout.write(self.style.SUCCESS(
            f"Reindexed {Issue.objects.count()} issue(s) and "
            f"{KnownIssue.objects.count()} known issue(s)."))
