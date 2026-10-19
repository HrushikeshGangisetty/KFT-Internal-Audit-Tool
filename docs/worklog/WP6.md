# WP6 — Deadlines, reminders, waiting, and escalation
Agent: Claude Code    Branch: wp/06-08-deadlines-verify-evidence    Date: 19 October 2026

Authorised by the user in chat ("Can u do the next three tasks as well same like before … keep changes local for now, we shall merge once im back"): WP6–WP8 in one local commit. Branched from `wp/03-05-jobs-issues-routing` (unmerged; WP6 depends on WP3 and WP5). Not pushed.

## Done

- **Policy as data** (`issues/models.py::DeadlinePolicy`, migrations `issues/0006`, `0007`): urgency, ack target, working-hours flag, follow-up interval, `escalation_steps` (`after_minutes`, `to` ∈ owner/backup/manager, `channels`). Placeholders seeded: urgent 30 min wall clock (0 owner, 30 backup, 60 manager; in-app + email); normal 4 working hours (0 owner, 240 owner reminder, 480 backup, 720 manager; in-app). Unknown urgency → normal.
- **Owner epochs** (`Issue.owner_epoch`, `owner_since`): set on routing; incremented on accepted ownership and accepted handoff, so a new owner starts a fresh sequence while re-runs never resend a step.
- **Engine** (`issues/deadlines.py`): `check_issue`, `check_handoff`, `check_followup`, `check_waiting`, `ack_due_at`; periodic task `issues.check_deadlines` (every minute, registered in `IssuesConfig.ready`). Keys `ack:<issue>:<epoch>:<step>`, `handoff:<id>:<step>`, `followup:<issue>:<epoch>:<last activity>`, `waiting:<issue>:<date>:<step>`, `coverage:<what>:<date>`. `notified` / `reminder_sent` / `escalated` events are written only when a step actually created deliveries.
- **WP5 alerts now go through the engine**: routing, accepted ownership, proposed and accepted handoffs call `check_issue`/`check_handoff` (step 0 immediately) instead of ad-hoc alerts, so step 0 and later reminders share one key space.
- **Waiting** (`services.set_waiting`, `POST /api/issues/<id>/waiting/`): reason and `next_followup_at` required, within `WAITING_MAX_DAYS` (14); `dependency_owner` recorded. Waiting pauses follow-ups, never acknowledgement escalation; on the date it reminds the owner, then the queue head one ack target later, then managers.
- **Coverage gaps**: a queue whose head and backup are both inactive, an inactive recipient, or an urgent alert after hours with no `DUTY_CONTACT_USER_ID` → in-app `COVERAGE_GAP` to managers (once per day per gap; after-hours per issue) and a `coverage_gap` event. With a duty contact configured, they are added to step 0 and named in the summary (`on_duty`); otherwise nothing names anyone on duty.
- `core/calendar.py::is_working_time`; issue detail exposes `ack_due_at`, waiting fields, `owner_epoch`. `IssueEvent` and `Handoff` timestamps are now written from `timezone.now()` explicitly.

## Acceptance

| Item | Evidence | Result |
|---|---|---|
| Scenario 2 second half: urgent unacknowledged → head now, backup at 30, manager at 60; ten runs at one instant send each step once | `test_scenario_2_urgent_escalates_head_backup_manager_once_each` (frozen time; 6 deliveries = 3 steps × 2 channels; events `notified, escalated, escalated`) | PASS |
| Normal report Friday 17:30 IST reaches its 4-working-hour target Monday 13:30 | `test_normal_report_friday_1730_is_due_monday_1330` (`ack_due_at`, and the reminder fires at 13:30 not 13:29) | PASS |
| Acknowledging stops escalation; accepting a handoff starts a new sequence | `test_acknowledging_stops_escalation`, `test_accepted_handoff_starts_a_new_sequence` | PASS |
| Waiting past `next_followup_at` reminds, then escalates | `test_waiting_reminds_then_escalates_and_pauses_followups` (also: missing date and >14 days refused, follow-ups paused) | PASS |
| After-hours urgent names a duty contact only if configured; otherwise reaches the head and shows the gap | `test_after_hours_urgent_without_duty_contact_shows_the_gap`, `test_after_hours_urgent_with_duty_contact_names_them` | PASS |

Also: `test_unknown_urgency_follows_the_normal_policy`, `test_pending_handoff_escalates_receiver_then_backup_then_manager`, `test_waiting_never_pauses_acknowledgement_escalation`, `test_quiet_acknowledged_issue_gets_one_followup_per_quiet_period`, `test_queue_without_active_head_or_backup_is_a_coverage_gap`.

## Commands run and results

See `WP8.md` for the shared full-suite run. `tests.test_deadlines`: 12 tests OK.

## Not done / deviations from plan

- Time is frozen with `unittest.mock.patch("django.utils.timezone.now")`, not `time-machine` (not installed; no new dependency).
- Follow-ups remind the owner only; stale acknowledged issues do not escalate further (the plan lists escalation only for unacknowledged reports, handoffs and waiting).
- "No deliverable channel": an inactive recipient is a coverage gap; a missing email address is a failed delivery, which WP3 already reports to the head and managers.
- No UI for policies, waiting or `ack_due_at` (WP14). Policies are edited as rows.

## Decisions taken in this session (and why)

- Step 0 lives in the policy rather than in routing, so "alert the head now" and later steps can never duplicate each other.
- After-hours gaps are keyed per issue per day so every unattended urgent report is visible; queue gaps per queue per day.

## Follow-ups (out of scope, noticed)

- `check_deadlines` loops in Python over all active issues each minute; fine at pilot volume, index or batch later.
- Real holiday calendar and duty rota.

## Placeholders introduced

The two seeded `DeadlinePolicy` rows; `DUTY_CONTACT_USER_ID` unset; `WAITING_MAX_DAYS=14`.
