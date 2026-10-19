"""``python manage.py run_worker``: the always-on second process (WP3).

Each loop: heartbeat, return stale jobs to the queue, run due periodic
tasks (at most every PERIODIC_INTERVAL_SECONDS), then drain due jobs.
"""
import os
import socket
import time

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import close_old_connections
from django.utils import timezone

from core import jobs


class Command(BaseCommand):
    help = "Run background jobs and periodic tasks."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true",
                            help="Run one loop and exit (tests, cron fallback).")
        parser.add_argument("--sleep", type=float, default=2.0)

    def handle(self, *args, once=False, sleep=2.0, **options):
        worker_id = f"{socket.gethostname()}:{os.getpid()}"
        last_periodic = None
        while True:
            now = timezone.now()
            jobs.beat(worker_id, now)
            jobs.recover_stale(now)
            if last_periodic is None or (now - last_periodic).total_seconds() >= \
                    settings.PERIODIC_INTERVAL_SECONDS:
                jobs.run_periodic(now)
                last_periodic = now
            while (job := jobs.claim(worker_id)) is not None:
                jobs.run(job)
            if once:
                return
            time.sleep(sleep)
            close_old_connections()
