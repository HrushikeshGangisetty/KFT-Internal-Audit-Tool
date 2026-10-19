"""Background jobs, periodic tasks and the worker heartbeat (WP3).

Domain apps register handlers with ``@job_handler("kind")`` and periodic work
with ``@periodic("name", every=...)``; this module never imports them.

Handlers must be idempotent: a job whose worker dies mid-run is returned to
the queue after ``JOB_LOCK_TIMEOUT`` and runs again.
"""
import logging
import traceback
from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, connection, transaction
from django.utils import timezone

from .models import Job, PeriodicTaskRun, WorkerHeartbeat

log = logging.getLogger(__name__)

HANDLERS = {}
PERIODIC = {}
# Arbitrary constant: the advisory lock that serialises periodic ticks.
PERIODIC_LOCK_KEY = 0x6663_6F70  # "fcop"


def job_handler(kind):
    def register(fn):
        HANDLERS[kind] = fn
        return fn
    return register


def periodic(name, *, every):
    def register(fn):
        PERIODIC[name] = (every, fn)
        return fn
    return register


def enqueue(kind, payload=None, *, run_after=None, idempotency_key=None,
            max_attempts=None):
    """Insert a job in the caller's transaction (it is visible to workers
    only once that commits, and vanishes if it rolls back). A repeated
    idempotency key returns the existing job instead of creating another."""
    fields = dict(kind=kind, payload=payload or {},
                  run_after=run_after or timezone.now(),
                  max_attempts=max_attempts or settings.JOB_MAX_ATTEMPTS)
    if idempotency_key is None:
        return Job.objects.create(**fields)
    existing = Job.objects.filter(idempotency_key=idempotency_key).first()
    if existing:
        return existing
    try:
        with transaction.atomic():
            return Job.objects.create(idempotency_key=idempotency_key, **fields)
    except IntegrityError:
        return Job.objects.get(idempotency_key=idempotency_key)


def claim(worker_id, now=None):
    """Lock the next due job for this worker, or return None. Concurrent
    workers skip each other's locked rows, so no job is claimed twice."""
    now = now or timezone.now()
    with transaction.atomic():
        job = (Job.objects.select_for_update(skip_locked=True)
               .filter(status=Job.QUEUED, run_after__lte=now)
               .order_by("run_after", "id").first())
        if job is None:
            return None
        job.status = Job.RUNNING
        job.locked_by = worker_id
        job.locked_at = now
        job.attempts += 1
        job.save(update_fields=["status", "locked_by", "locked_at", "attempts"])
    return job


def run(job):
    """Run a claimed job outside the claim transaction and record the
    outcome: success, a retry with exponential backoff, or dead."""
    handler = HANDLERS.get(job.kind)
    now = timezone.now()
    try:
        if handler is None:
            raise LookupError(f"No handler registered for job kind '{job.kind}'.")
        handler(job)
    except Exception:  # noqa: BLE001 - every failure is recorded on the job
        job.last_error = traceback.format_exc()[-4000:]
        if job.attempts >= job.max_attempts:
            job.status = Job.DEAD
            job.finished_at = now
            log.error("Job %s is dead after %s attempts", job.pk, job.attempts)
        else:
            job.status = Job.QUEUED
            job.run_after = now + timedelta(
                seconds=settings.JOB_RETRY_BASE_SECONDS * 2 ** job.attempts)
    else:
        job.status = Job.SUCCEEDED
        job.finished_at = now
        job.last_error = ""
    job.locked_by, job.locked_at = "", None
    job.save(update_fields=["status", "finished_at", "last_error", "run_after",
                            "locked_by", "locked_at"])
    return job


def recover_stale(now=None, timeout=None):
    """Return jobs whose worker vanished mid-run to the queue."""
    now = now or timezone.now()
    timeout = timeout if timeout is not None else timedelta(
        seconds=settings.JOB_LOCK_TIMEOUT_SECONDS)
    return Job.objects.filter(status=Job.RUNNING, locked_at__lt=now - timeout).update(
        status=Job.QUEUED, locked_by="", locked_at=None)


def run_periodic(now=None):
    """Run every periodic task that is due, once, under an advisory lock so
    two workers never run the same tick. A task that was missed while no
    worker ran is run once on the next tick, not once per missed interval."""
    now = now or timezone.now()
    ran = []
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_try_advisory_xact_lock(%s)", [PERIODIC_LOCK_KEY])
            if not cursor.fetchone()[0]:
                return ran
        for name, (every, fn) in PERIODIC.items():
            last = PeriodicTaskRun.objects.filter(name=name).first()
            if last and last.last_run_at + every > now:
                continue
            fn(now)
            PeriodicTaskRun.objects.update_or_create(
                name=name, defaults={"last_run_at": now})
            ran.append(name)
    return ran


def beat(worker_id, now=None):
    WorkerHeartbeat.objects.update_or_create(
        worker_id=worker_id,
        defaults={"last_seen": now or timezone.now(),
                  "version": settings.APP_VERSION})


def worker_health(now=None):
    """What the admin health endpoint reports."""
    from .models import AlertDelivery
    now = now or timezone.now()
    stale_after = timedelta(seconds=settings.WORKER_STALE_SECONDS)
    workers = [{"worker_id": hb.worker_id, "last_seen": hb.last_seen,
                "version": hb.version, "stale": now - hb.last_seen > stale_after}
               for hb in WorkerHeartbeat.objects.order_by("-last_seen")]
    return {
        "worker_stale": not any(not w["stale"] for w in workers),
        "workers": workers,
        "queued_jobs": Job.objects.filter(status=Job.QUEUED).count(),
        "dead_jobs": Job.objects.filter(status=Job.DEAD).count(),
        "failed_alerts": AlertDelivery.objects.filter(
            status=AlertDelivery.FAILED).count(),
    }
