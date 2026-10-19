# WP4 — Decouple issues from FCs; incidents and workstreams
Agent: Claude Code    Branch: wp/03-05-jobs-issues-routing    Date: 19 October 2026

Same authorisation and commit as WP3/WP5 (see `WP3.md`).

## Done

- **Model** (`issues/models.py`, migrations `issues/0004_reports_routing_handoffs.py`, `0005_backfill_discovery_and_event_trigger.py`): `Issue.fc` nullable, `discovered_stage` blank-able; new `reporter`, `submitted_at`, `product_area` (default Unknown), `impact` (default Unknown), `urgency` (urgent/normal/unknown), `occurred_at_approx`, `location_context`, `reproduction_notes`, `kind` (standalone/incident/workstream), `parent`, `blocks_stage`. New `IssueUnitLink(issue, fc, linked_by, linked_at, reason)`. Backfill: `blocks_stage=True` for every existing FC-anchored issue, `reporter=discovered_by`, `submitted_at=created_at`.
- **Stage blocking gated** (`fc/models.py::recompute_status`, `open_blocking_issues`; `fc/services.py::stage_blockers`, `approval_blockers`): only `blocks_stage=True` issues count. `create_issue` with an FC (the lifecycle path) defaults to `blocks_stage=True`, so existing behaviour is unchanged; general reports and unit links never block. `set_blocks_stage` (`POST /api/issues/<id>/blocks-stage/`) records the decision with a reason, event and audit entry.
- **Services** (`issues/services.py`): `create_issue` accepts `fc=None`; `submit_report` validates only title, symptom and urgency (workstream needs an incident parent; only workstreams have parents), writes a `submitted` event, routes (WP5) and returns the issue; `add_attachment` (size limit `ATTACHMENT_MAX_BYTES`); `link_unit`; `edit_issue` refuses `IMMUTABLE_FIELDS` (fc, discovered_stage, discovered_stage_record, discovering_department, discovered_by, reporter, submitted_at) and service-owned routing fields. `fc.services.log_event` is a no-op without an FC; FC status recompute only when there is one.
- **API** (`issues/views.py`, `issues/serializers.py`): `POST /api/issues/report/` (JSON or multipart `files[]`; response = issue detail + `queue_name` + `failed_attachments`); `POST /api/issues/<id>/units/`; `POST /api/issues/` accepts no FC; `PUT/PATCH /api/issues/<id>/` goes through `edit_issue` and returns 409 `immutable_field` for discovery or routing fields. Serializers expose the new fields, `parent_summary` (key, title, status, urgency only), events, handoffs, unit links; `fc_serial`/`stage_label` are empty for FC-less issues. FC issues tab includes linked units. New filters on the issue list; `meta` lists product areas, impacts, urgencies, kinds.
- **Frontend**: `FcLink` renders "—" when there is no FC (`frontend/src/components/ui.jsx`). No quick-report screen (WP14).

## Acceptance

| Item | Evidence | Result |
|---|---|---|
| Scenario 1 backend: title, symptom, urgency=Unknown succeeds and returns an ID | `test_scenario_1_minimal_report_gets_an_id_and_the_fallback_queue`; missing urgency → 400 `test_report_requires_title_symptom_and_urgency` | PASS |
| Scenario 8: existing FC lifecycle/rework tests unchanged; FC-less issue in lists, search, dashboard | Full suite with `test_lifecycle.py` etc. untouched (see WP5.md); `test_scenario_8_general_issue_shows_in_list_search_and_dashboard` (also similar endpoint) | PASS |
| Discovery facts cannot change through API or services | `test_discovery_facts_cannot_change_through_the_api`, `test_discovery_facts_cannot_change_through_services` | PASS |
| Incident with Software and Firmware workstreams: `fw_member` sees Firmware workstream + incident summary, not the Software workstream's notes | `test_incident_workstreams_are_scoped_separately` (incident detail and Software workstream 404 for `fw_member`) | PASS |
| Linking a severe issue to an FC does not block its stage without `blocks_stage` | `test_linking_a_severe_issue_does_not_block_without_the_decision` (BLOCKER report on an FC and a unit link: no BLOCKED status, no stage blockers; member refused; lead's decision blocks) | PASS |

Also `test_attachment_failure_does_not_fail_the_report`.

## Commands run and results

`makemigrations --check --dry-run`: no changes. Fresh disposable DB `fcops_wp35b`: migrate, `seed --demo` (5 issues, all `blocks_stage=True` after backfill), reverse `issues 0003` + `core 0004`: OK, forward again: OK, `dbcheck --deep`: all checks passed. Full suite: see `WP5.md`.

## Not done / deviations from plan

- **Reversal of `issues/0004` fails once an FC-less issue exists** (`fc_id` cannot become NOT NULL again). Observed on `fcops_wp35`. Reversible only before general reports are created; this is inherent to the change.
- The plan's `discovered_department` is the existing `discovering_department`.
- `POST /api/issues/` (the lifecycle form) remains, now with an optional FC; the quick report is the separate `report` action.
- `blocks_stage` authority is a placeholder: department leads and managers (`User.is_lead_role`), not per-stage lifecycle authority.
- The Django admin can still edit discovery fields directly (pre-existing admin follow-up from WP1).

## Decisions taken in this session (and why)

- The API refuses (409) rather than silently ignores attempts to rewrite discovery facts, so a client bug is visible.
- `parent_summary` is a fixed headline, not a nested issue serializer, so a workstream cannot leak its incident's notes or siblings.

## Follow-ups (out of scope, noticed)

- Frontend quick-report screen, workstream creation UI and an FC-less issue detail layout (WP14).
- `create_issue`'s high-severity manager notifications still key off `severity`, which reports leave at the Major default; review once urgency drives alerts (WP6).

## Placeholders introduced

`ATTACHMENT_MAX_BYTES=10 MiB`; `Impact` choices (Stops work / Degraded / Minor / Unknown); `blocks_stage` authority = leads and managers.
