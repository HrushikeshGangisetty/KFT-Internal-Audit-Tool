# WP7 — Status, resolution, verification, and reopening
Agent: Claude Code    Branch: wp/06-08-deadlines-verify-evidence    Date: 19 October 2026

Same authorisation and commit as WP6/WP8 (see `WP6.md`). Adapted the existing workflow rather than rebuilding it.

## Done

- **Models** (`issues/models.py`, migrations `issues/0006`, `0007`): `Resolution(issue, resolved_by, at, change_summary, root_cause_status ∈ confirmed/suspected/unknown/mitigated_only, workaround, evidence_links, affected_versions, affected_units, unresolved_risks)`; `Verification(resolution, verifier, at, what_tested, evidence, result pass/fail, notes)`; notes gain `note_type` (observation, suspected_cause, confirmed_cause, workaround, permanent_fix, general) and `supersedes`. Migration 0007 backfills a Resolution (and a passing Verification where recorded) for every issue resolved before WP7.
- **Services** (`issues/services.py`): `change_status(RESOLVED)` writes a Resolution and requires only a change summary; a root-cause description is required only when the status is `confirmed`. `change_status(VERIFIED)` delegates to the new `verify`. `verify(issue, verifier, passed, what_tested, evidence, note)`: refuses the resolver of the latest resolution, allows test engineers, heads, managers and the assigned verifier participant; a fail returns the issue to Investigating and keeps the resolution. `reopen`: authority from `REOPEN_ALLOWED` (placeholder `accountable, queue_head, any_head, manager`), only from Resolved/Verified/Closed, keeps all resolutions and verifications. `add_note(note_type, supersedes)`. Events `resolved`, `verified`, `verification_failed`, `reopened`.
- **API**: `POST /api/issues/<id>/verify/` (`result`, `what_tested`, `evidence`, `notes`); `status` accepts `root_cause_status` and resolution details; `reopen` no longer requires the legacy manager role (the service decides); `notes` accepts `note_type`, `supersedes`; `promote` accepts `audience`. Issue detail includes `resolutions` with their `verifications`. `status` and its sign-off fields are now refused by `PATCH/PUT /api/issues/<id>/` (previously writable around the allow-list).

## Acceptance

| Item | Evidence | Result |
|---|---|---|
| Scenario 7: resolving does not verify; the resolver cannot verify (API and service); a failed verification returns to Investigating with history intact | `test_scenario_7_resolve_is_not_verify_and_resolver_cannot_verify` | PASS |
| Resolving with `root_cause_status=unknown` is allowed | `test_resolving_with_unknown_root_cause_is_allowed` | PASS |
| Reopening after verification keeps the earlier resolution and verification in the timeline | `test_reopen_after_verification_keeps_history` (events `resolved, verified, reopened`; resolution and its pass still in detail) | PASS |

Also `test_confirmed_root_cause_needs_a_description`, `test_reopen_authority_is_configurable`, `test_notes_are_typed_and_corrections_keep_the_original`, `test_status_cannot_be_patched_around_the_workflow`, `test_promotion_sets_the_audience`. Existing workflow tests (`test_issues_and_search`, `test_lifecycle`) pass unchanged.

## Commands run and results

See `WP8.md`. `tests.test_resolution`: 8 tests OK. Reverse/forward of `issues 0006–0007` on a fresh seeded DB: 4 resolutions and 4 verifications rebuilt by the backfill.

## Not done / deviations from plan

- No resolution co-authorship exists, so only the resolver is excluded.
- `promote_to_known_issue` gained `audience`; `symptoms_summary` serves as the redacted summary (no separate field).
- The legacy `Issue.root_cause` / `resolution` text fields are still written (they feed search and the knowledge promotion).
- No UI for typed notes, verify pass/fail or resolution details (WP14).

## Decisions taken in this session (and why)

- `verify` locks the row but works on the caller's instance, so callers chaining status changes do not hold a stale object.
- Independent verification checks the latest Resolution's author, so re-resolving by someone else does not let the original resolver verify.

## Follow-ups (out of scope, noticed)

- Reopen from Resolved is now allowed by the service but `ISSUE_TRANSITIONS` also permits Resolved → Investigating directly; decide whether that path should require a reason too.

## Placeholders introduced

`REOPEN_ALLOWED=accountable,queue_head,any_head,manager`.
