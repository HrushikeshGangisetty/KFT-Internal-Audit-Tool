# WP3 — Job queue, scheduler, and alert delivery
Agent: Claude Code    Branch: wp/03-05-jobs-issues-routing    Date: 19 October 2026

Authorised by the user in chat ("Continue with the next 3 tasks in the same commit", confirmed as WP3–WP5 in one commit on a new branch from `main`). Built on `main` (`c9f0aab`, WP2). WP3, WP4 and WP5 share one branch and one commit at the user's request, against the plan's one-WP-one-branch rule.

## Done

- **Models** (`core/models.py`, migration `core/0005_jobs_alerts_calendar.py`): `Job` (plan fields; unique nullable `idempotency_key`), `PeriodicTaskRun(name, last_run_at)`, `WorkerHeartbeat(worker_id, last_seen, version)`, `Holiday(date, name)`, `AlertDelivery` with unique `(alert_key, recipient, channel)`.
- **Job queue** (`core/jobs.py`): `enqueue` (idempotency key returns the existing job), `claim` (`select_for_update(skip_locked=True)`, short transaction, sets running/locked_by/locked_at), `run` (handler outside the claim transaction; retry with `JOB_RETRY_BASE_SECONDS * 2^attempts`; `dead` after `max_attempts`), `recover_stale`, `@job_handler`, `@periodic`, `run_periodic` (under `pg_try_advisory_xact_lock`; an overdue task runs once, not once per missed tick), `beat`, `worker_health`.
- **Worker** (`core/management/commands/run_worker.py`): heartbeat → stale recovery → periodic tasks every `PERIODIC_INTERVAL_SECONDS` → drain jobs; `--once` for tests and manual runs.
- **Health endpoint** `GET /api/admin/health/` (`core/views.py::WorkerHealthView`): managers and account administrators only (403 otherwise); reports `worker_stale`, workers, queued/dead job counts, failed alert count. Allowlisted in the route-coverage test (counts only).
- **Working calendar** (`core/calendar.py`): `add_working_minutes`, `working_minutes_between`; settings `WORKING_DAYS`, `WORKING_HOURS`, `WORKING_TIMEZONE`; holidays from `core.Holiday` or an explicit set.
- **Alerts** (`core/alerts.py`): `InAppChannel` (notification pointer), `EmailChannel` (Django email backend; message carries only reference, urgency, queue and link), SMS/WhatsApp stubs that raise. `dispatch_alert(alert_key, recipients, urgency, target, *, kind, summary, on_failure, channels)` creates delivery rows and one job each; `alerts.deliver` handler skips an already-accepted delivery; a delivery that fails on its last attempt sends a keyed in-app `ALERT_FAILED` notice to the `on_failure` users (WP5 passes the queue head and managers). Registered in `CoreConfig.ready`.
- **Settings** (`config/settings.py`): job/worker knobs, `EMAIL_BACKEND` defaults to the console backend, `SITE_URL`, `ALERT_CHANNELS_URGENT=in_app,email`, `ALERT_CHANNELS_NORMAL=in_app`, calendar placeholders.
- **Notifications** (`core/serializers.py`): render `ISSUE_ALERT` and `ALERT_FAILED`; the high-severity message no longer assumes an FC.

## Acceptance

| Item | Evidence | Result |
|---|---|---|
| A job enqueued in a rolled-back transaction never runs | `JobQueueTests.test_job_enqueued_in_rolled_back_transaction_never_runs` | PASS |
| Two concurrent workers never run the same job | `ConcurrentClaimTests.test_two_workers_never_run_the_same_job` (TransactionTestCase, 2 threads, barrier, 20 jobs) | PASS |
| Crash mid-handler is retried after lock timeout; idempotency prevents a double effect | `AlertTests.test_crash_mid_handler_is_retried_without_a_double_send` (email sent, worker "dies", `recover_stale`, second worker: still one email, job succeeded) | PASS |
| `dispatch_alert` twice with the same key → one delivery per recipient and channel | `AlertTests.test_dispatch_twice_gives_one_delivery_per_recipient_and_channel` | PASS |
| Scenario 13: stale heartbeat reported; after restart overdue periodic work runs once | `WorkerHealthTests.test_scenario_13_stale_heartbeat_then_restart_runs_overdue_work_once` | PASS |
| Working calendar: weekends, holidays, after-hours and before-hours starts | `WorkingCalendarTests` (6 tests) | PASS |

Also: retry/backoff then dead (`test_failure_retries_with_backoff_then_dies`), normal alerts in-app only, failed delivery notifies the manager once.

## Commands run and results

See `WP5.md` for the shared full-suite run. WP3-only: `manage.py test tests.test_jobs_alerts` → 17 tests OK. Manual on a fresh disposable DB (`fcops_wp35`, loopback PostgreSQL 16): an urgent report dispatched in-app + email; `run_worker --once` printed the console email (reference, urgency, queue, link only) and both jobs/deliveries ended `succeeded`/`accepted`.

## Not done / deviations from plan

- **Jobs are inserted in the caller's transaction rather than via `transaction.on_commit`.** Same guarantee (a rolled-back transaction leaves no job; workers only see committed rows), and `enqueue` can return the job and honour the idempotency key synchronously.
- `core/jobs.py`, `core/alerts.py` are modules, not packages.
- No administrator/manager banner for a stale heartbeat in the UI; the endpoint exists (UI is WP14).
- No per-user "email for normal alerts" preference: normal alerts follow `ALERT_CHANNELS_NORMAL`.
- No process-manager configuration for the worker (WP15).
- Time tests pass explicit instants instead of using `time-machine` (not installed; no new dependency).

## Decisions taken in this session (and why)

- A delivery that fails is retried by its job; only the last failure raises the in-app notice, so heads are not told about transient failures.
- `EmailChannel` reports `failed` for a user without an email address rather than raising.

## Follow-ups (out of scope, noticed)

- The email is sent while the delivery row is locked; if the provider call hangs, that row stays locked until it returns. Add a provider timeout with the real provider.
- Dead jobs have no admin UI; only counted on the health endpoint.

## Placeholders introduced

`WORKING_DAYS=0,1,2,3,4` (Mon–Fri; Mon–Sat is still a decision), `WORKING_HOURS=10,18`, `WORKING_TIMEZONE=Asia/Kolkata`, `ALERT_CHANNELS_URGENT=in_app,email`, `ALERT_CHANNELS_NORMAL=in_app`, `WORKER_STALE_SECONDS=180`, `JOB_LOCK_TIMEOUT_SECONDS=600`.
