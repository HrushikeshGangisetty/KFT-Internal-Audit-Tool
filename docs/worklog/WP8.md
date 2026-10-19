# WP8 — FC workflow preservation and configuration evidence
Agent: Claude Code    Branch: wp/06-08-deadlines-verify-evidence    Date: 19 October 2026

Same authorisation and commit as WP6/WP7 (see `WP6.md`).

## Preserved work integrated

From `preserve/local-work-2026-10-17` (`900680d`), per the WP0 integration list:

| Path | How | SHA-256 |
|---|---|---|
| `fcops/backend/fc/parameters.py` | unchanged | `b05181cd…c09c46` (matches INVENTORY.md) |
| `fcops/backend/fc/migrations/0005_parameterfile.py` | unchanged (kept so any database that already applied it stays consistent) | `17858bd3…21da0` (matches) |
| `ParameterFile` model (`fc/models.py`) | preserved fields unchanged, WP8 fields added | — |
| `ParameterParsingTests`, `ParameterCompareTests`, `SAMPLE_A/B` | copied verbatim into `tests/test_parameters.py` by script | — |
| `ParameterFileViewSet` (upload, `parameters`, `compare`) | adapted: scoped, bytes stored once, original-byte download | — |
| Preserved `ParameterApiTests` | adapted to the access matrix world and byte storage | — |
| `frontend/src/pages/ParamCompare.jsx` + nav/route | unchanged except the import of the removed `getTokens` (JWT, WP2) | — |

**Not integrated** (they change lifecycle or caching rules that WP8 must not change, or depend on endpoints absent from main): failure routing in `lifecycle.py`/`services.py` and its tests, `stage_progress` prefetch rewrite, `/api/fcs/<id>/full/`, dashboard caching (contradicts the WP1 no-cache decision) and `QueryBudgetTests`, `e2e/param_and_routing.py`, the `serve` command. They remain on the preservation branch. The plan asked for the preserved files as a separate first commit; at the user's request this batch is one commit, so the table above records provenance instead.

## Done

- **Models** (`fc/models.py`, migrations `fc/0006_config_evidence.py`, `0007_backfill_parameter_file_hashes.py`): `ParameterFile` gains `sha256` (unique), `size`, private `file`, `parser_version`, `parse_warnings` (parsed values stay on the row; no separate `ParsedParameters` table). `ConfigEvidence(kind ∈ approved_baseline/flashed_record/readback, file, fc nullable, unit_identity_confidence, firmware_version, firmware_build, gcs_version, hardware_revision, captured_at, recorded_by, tool, source_note, supersedes)`; `BaselineApproval(evidence, revision, approved_by, approved_at, compatibility, scope)`; `IssueEvidenceLink`; `ParameterComparison(left_evidence, right_evidence, tolerance, result, parser_versions, created_by)` with **no safety field**.
- **Services** (`fc/evidence.py`): `store_parameter_file` (dedupe by SHA-256, race-safe), `record_evidence` (supersedes the current row for the same unit and kind; audit + FC timeline), `associate_unit` (new row superseding the unknown-unit row, with reason, audited), `approve_baseline` (authenticated user; placeholder authority Firmware lead or manager; one approval per evidence row), `compare_evidence` (differences + parser warnings), `link_evidence`, `versions_at_time` (linked evidence, else latest of each kind captured before the report, always with `captured_at`).
- **API**: `/api/parameter-files/` (upload → 201 new or 200 `already_stored`; `/<id>/download/` original bytes after scope check; `/<id>/parameters/`; `/compare/`), `/api/config-evidence/` (create, `/<id>/associate/`, `/<id>/approve-baseline/`), `/api/parameter-comparisons/`, `POST /api/issues/<id>/evidence/`. All follow FC scope (`access.policy.scope_by_fc`); route-coverage test passes without allowlisting. Issue detail exposes `versions_at_time`.
- **FC page**: linking an issue to a unit writes an `ISSUE_LINKED` FC timeline entry (filtered by issue scope like other issue events); the FC issues tab includes linked issues (WP4).

## Acceptance

| Item | Evidence | Result |
|---|---|---|
| Scenario 4: baseline, flashed record and readback for one unit stored as distinct kinds, originals retrievable byte-for-byte (hash matches), comparable with differences and parser warnings, no safety verdict | `test_scenario_4_three_kinds_byte_for_byte_and_compared` | PASS |
| Evidence with an unknown unit can be created and later associated, with the association recorded | `test_unknown_unit_evidence_can_be_associated_later` (new row supersedes, audit entry with reason) | PASS |
| Uploading the same file twice stores the bytes once | `test_same_file_twice_is_stored_once` | PASS |
| Scenario 8: existing FC lifecycle and rework tests pass unchanged | full suite; `test_lifecycle.py` untouched | PASS |

Also: baseline approval refused for a technician; newer evidence supersedes without overwriting; issue versions from linked evidence with capture time; no FC scope → no files, downloads or evidence; linked unit on the FC timeline and issues tab; the 10 preserved parser/compare tests.

## Commands run and results

Disposable WP0 environment (Python 3.12 venv, portable PostgreSQL 16 on 127.0.0.1:55432; remote URLs blanked).

- `manage.py check`: no issues. `makemigrations --check --dry-run`: no changes.
- Module runs: `test_deadlines` 12 OK, `test_resolution` 8 OK, `test_parameters` 23 OK; regression run of issues/lifecycle/routing/rbac/route-coverage/jobs modules OK after one fix (stale instance after `verify`).
- Full suite `manage.py test tests --noinput`: **229 tests in 444.493s, OK** (186 on the WP3–WP5 branch + 12 WP6 + 8 WP7 + 23 WP8).
- `npm run build`: OK.
- Fresh DB `fcops_wp68`: migrate, `seed --demo`, reverse `fc 0004` and `issues 0005`, re-apply, `dbcheck --deep` all passed, `run_worker --once` OK.
- Not run: E2E walkthrough; ParamCompare page not opened in a browser.

## Not done / deviations from plan

- No separate `ParsedParameters` table; one parse per stored file (`parser_version` recorded).
- Legacy (pre-WP8) parameter files have no original bytes; their hash is computed from the stored text and download returns 409 `no_original_bytes`. A legacy duplicate keeps a NULL hash.
- Baseline approval is a single authenticated approval (the dual-approval pattern is WP11).
- Version-at-time uses `submitted_at` as the reference: `occurred_at_approx` is free text.
- No evidence UI beyond the preserved ParamCompare page (WP14 / cut line).

## Follow-ups (out of scope, noticed)

- Decide what to do with the non-integrated preserved work listed above (failure routing especially).
- Object storage for parameter files and attachments (WP15).

## Placeholders introduced

Baseline approval authority (Firmware lead or manager); `PARSER_VERSION="fc.parameters/1"`.
