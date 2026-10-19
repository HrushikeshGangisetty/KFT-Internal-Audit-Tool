# WP5 — Routing, acknowledgement, ownership, and handoffs
Agent: Claude Code    Branch: wp/03-05-jobs-issues-routing    Date: 19 October 2026

Same authorisation and commit as WP3/WP4 (see `WP3.md`).

## Done

- **Models** (`issues/models.py`, migrations `issues/0004`, `0005`): `Queue(name, department one-to-one, head, backup, is_fallback)` — head and backup are NOT NULL, at most one fallback (partial unique constraint); `RoutingRule(product_area, queue, priority)`; on `Issue`: `queue`, `accountable_user`, `acknowledged_at`, `acknowledged_by`; `IssueEvent(issue, type, actor, at, data)` append-only in Python and by a database trigger (same pattern as the audit log); `Handoff` with at most one `pending` per issue (partial unique index). `IssueParticipant` already existed from WP1.
- **Services** (`issues/services.py`, each locks the issue with `select_for_update`): `route` (rule by product area, else fallback; accountable = queue head; responsible department = queue department; `routed`/`assigned`/`notified` events; alert to the head — urgent: in-app + email, otherwise in-app; failure notices to the head and managers); `acknowledge` (accountable person, queue head or backup only; idempotent; reading never acknowledges); `accept_ownership` (queue head/backup names an active member of the queue's team); `propose_handoff` (reason required; accountability unchanged; one pending; alert to the named recipient or receiving head); `respond_handoff` (receiving head, backup or named recipient; rejection needs a reason; acceptance moves queue, department and accountable person in one transaction, resets acknowledgement, writes a reassignment-log row); `set_waiting` now writes `waiting_set`/`waiting_cleared` events.
- **Access** (`access/policy.py::visible_issues`): adds reporter, accountable person, queue head/backup, pending-handoff recipients (named user, receiving queue head/backup), and — when `HANDOFF_PREVIOUS_TEAM_ACCESS=read` (default) — members of a department that handed the issue off.
- **API**: `POST /api/issues/report/`, `POST /api/issues/<id>/acknowledge/`, `POST /api/issues/<id>/accept-ownership/` (`{"member": id}`), `POST /api/issues/<id>/handoffs/`, `GET /api/handoffs/` (scoped via the issue), `POST /api/handoffs/<id>/respond/`, `GET /api/me/queue/` (accountable, awaiting acknowledgement, handoffs awaiting my response). `MyQueueView` is allowlisted in the route-coverage test (built from `visible_issues`); `HandoffViewSet` uses the scoped mixin.
- **Placeholder configuration**: `python manage.py seed_pilot_config` (DEBUG only, refuses `PRODUCTION=1`): fallback queue with the first manager as coordinator and backup, one queue per department kind that has a head, routing rules per product area. Idempotent.

## Acceptance

| Item | Evidence | Result |
|---|---|---|
| Scenario 1: response includes ID and queue name; unknown area → fallback | `test_scenario_1_minimal_report_gets_an_id_and_the_fallback_queue` | PASS |
| Scenario 2 (first half): Software head alerted; acknowledgement records actor and time; opening does not acknowledge | `test_scenario_2_head_alerted_and_viewing_does_not_acknowledge` (in-app + email deliveries, `run_worker --once` creates the notification, GET leaves `acknowledged_at` null, non-accountable member refused, second acknowledge adds no event) | PASS |
| Scenario 3: Firmware handoff gives read access, keeps Software accountable until acceptance, rejection needs a reason, every step is an event | `test_scenario_3_handoff_to_firmware` | PASS |
| Two simultaneous proposals → one pending handoff and one clean error | `ConcurrentHandoffTests.test_two_simultaneous_proposals_give_one_pending_handoff` (TransactionTestCase, 2 threads, barrier) | PASS |
| `routed` and `acknowledged` events give submission→routing and submission→acknowledgement times | `test_events_give_routing_and_acknowledgement_times` (`seconds_since_submission` on both) | PASS |

Also: `test_issue_events_are_append_only` (Python and trigger), `test_previous_team_access_can_be_withdrawn`, `test_head_assigns_ownership_to_a_team_member`, `test_seed_pilot_config_is_idempotent`.

## Commands run and results

Disposable environment from WP0 (Python 3.12 venv, portable PostgreSQL 16 on 127.0.0.1:55432 started with `pg_ctl`; TEST_POSTGRES_* unset; remote URLs blanked by the runner script).

- `manage.py check`: no issues. `makemigrations --check --dry-run`: no changes.
- `manage.py test tests.test_jobs_alerts`: 17 tests OK. `manage.py test tests.test_reports_routing`: 16 tests OK.
- Full suite `manage.py test tests --noinput`: **186 tests in 411.689s, OK** (153 before this branch + 17 WP3 + 16 WP4/WP5).
- `npm run build`: OK.
- Fresh DB `fcops_wp35`: migrate, `seed --demo`, `seed_pilot_config` (demo data has a head only in Firmware, so Software/Hardware/Service queues were skipped and printed as such), urgent GCS report → fallback queue, `run_worker --once` → both deliveries accepted.
- Not run: the E2E walkthrough (no UI for these flows yet).

## Not done / deviations from plan

- No "offer ownership" step: only the queue head or backup assigns a member; a member cannot self-accept.
- No withdraw endpoint for a pending handoff (the `withdrawn` status exists).
- A handoff to a department with no queue makes the named recipient (or, failing that, the accepting actor) accountable and keeps the old queue.
- Workflow refusals (wrong person acknowledging, responding, proposing) return 409 with `code: forbidden`, matching the existing `WorkflowError` convention, not 403.
- No UI for queues, acknowledgement or handoffs (WP14). Queues and rules are managed through `seed_pilot_config` and the Django admin is not registered for them.

## Decisions taken in this session (and why)

- `accountable_user` is a separate field from the legacy `assigned_person`, as the plan specifies; WP6 escalation targets it.
- With no fallback queue configured, a report stays unrouted rather than failing, so reporting never breaks on missing configuration.
- An accepted handoff also writes an `IssueReassignmentLog` row, so the existing reassignment history stays complete.

## Follow-ups (out of scope, noticed)

- Admin/API to manage queues, heads, backups and routing rules.
- `create_issue` still notifies managers for Major/Blocker severity; reports default to Major, so every report notifies managers. Decide with WP6 whether urgency replaces this.
- `MyQueueView` computes handoff responders in Python; fine at pilot scale.

## Placeholders introduced

Queue heads/backups/coordinator and the product-area → queue mapping in `seed_pilot_config`; `HANDOFF_PREVIOUS_TEAM_ACCESS=read`.
