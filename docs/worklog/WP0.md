# WP0 — Baseline, inventory, and preservation
Agent: Codex    Branch: wp/00-baseline    Date: 17 October 2026

Draft review: [PR #1](https://github.com/HrushikeshGangisetty/KFT-Internal-Audit-Tool/pull/1). Cross-reviewed by Claude Code and merged to `main` on 17 October 2026 at the user's request.

## Done

- Preserved all 24 initial modified/untracked paths as-is in commit `900680d1efcaca988cc511a21064502b7945bb25`, pushed to `preserve/local-work-2026-10-17`. Verified exact path-set equality and every original SHA-256 against committed blobs and unchanged original files. Existing `.env` excluded. `fcops.tar.gz` included as found, never regenerated.
- Created this separate worktree/branch from `main` at `ab2d324e6bd1308270925527036532dce42b5b6e`; no preserved application/parameter files were merged.
- Recorded initial Git commands, all 14 plan Section 2 rows, all 24 repository DRF view classes plus imported token views/routes/actions, FC and StageRecord FKs/nullability, enum stage fields, releases, attachments, JWT flow, commands and WP8 parameter paths in `docs/INVENTORY.md`. Added direct-action query index `docs/QUERY_SURFACES.md`.
- Established Python 3.12.10 venv and a fresh loopback-only PostgreSQL 16.15 cluster. Configured new isolated `.env` from example; original environment not read/copied. Validation uses only disposable local/demo data.
- Added AGENTS.md from supplied repository guidance with WP0-only scope clarification; one-line CLAUDE.md; worklog template; byte-identical v0.1 PRD copies; supplied implementation plan verbatim; root navigation pointers.
- Added only `time-machine==3.5.1` and `factory_boy==3.3.3` to `fcops/requirements-dev.txt`. Kept Django's runner. Installed requirements and confirmed pip check.
- Ran backend suites (including recorded harness timeout/environment-sensitive failures), migrate, demo seed, deep DB checks, frontend build, requested diagnostics command and primary browser walkthrough. See full logs/results below.

## Acceptance

| Item | Evidence (test name or manual check) | Result |
|---|---|---|
| Preservation branch exists and is pushed; file list matches initial status | Git push observed; ls-remote returns 900680d; diff-tree set equals initial 24 status paths; blob/file SHA-256 checks | PASS |
| Every Section 2 row has status and paths | INVENTORY.md matrix; AST cross-check verifies all 24 local DRF classes are listed | PASS |
| Test/build/migrate outcomes recorded verbatim, including failures | docs/validation/*.txt and RESULTS.md; no application fixes | PASS (baseline diagnostics absence retained) |
| AGENTS.md, CLAUDE.md and docs/worklog exist | Manual file check; CLAUDE.md exact content @AGENTS.md plus newline | PASS |
| Full backend suite result | backend-tests-clean-env.txt: 155 tests in 247.775s, OK, exit 0 | PASS |

## Commands run and results

[Full command/result table](../validation/RESULTS.md), [environment provenance](../validation/ENVIRONMENT.md), and linked stdout/stderr are the authoritative execution record.

Observed: migrate/seed/deep checks/build succeeded; primary E2E finished `STEPS PASSED: 17`, `PAGE ERRORS: none`. Diagnostics command exited 1, `Missing script: "test:diagnostics"`. Full initial backend run completed 155 tests in 251.246s with three TEST_POSTGRES environment-sensitive guard failures; six guard tests passed in a clean environment. Final clean-environment full run: **155 tests in 247.775s, OK, exit 0**. Earlier 240-second timeout and two browser harness serving-path failures remain published.

## Not done / deviations from plan

- No Diagnostics implementation/tests exist in this snapshot; their historical claim is not confirmed. Recorded the command failure rather than adding/fixing features.
- Plan targets PRD v0.2 but supplied repository has v0.1; preserved existing requirements and exact supplied plan, flagged mismatch instead of inventing v0.2.
- Used portable PostgreSQL 16 because only PostgreSQL 17 was installed and Docker absent. Did not change the installed service. Used an isolated snapshot copy for validation, with temporary frontend relocation to avoid Vite .git/Windows short-path restrictions.
- Baseline results describe preserved local application code; the WP0 PR contains documentation and test tooling only. Full backend failures caused by redundant test-environment variables were retained; only the harness environment was corrected.
- CLAUDE Code cross-review remains required before merge. No merge, later WP, deployment or email is authorised/performed here.

## Decisions taken in this session (and why)

- Isolate all database writes on fresh local PostgreSQL 16 port 55432; keep original workspace and its private environment untouched.
- Preserve current bytes using core.autocrlf=false for staging; verify hashes rather than accepting implicit newline conversion.
- Keep Stage enum fields distinct from StageRecord FKs; WP4 must migrate actual schema, not assume a Stage table.
- Keep the preservation branch separate from main-based WP0 work so WP8 can integrate parameter work deliberately.
- Retain original requirements v0.1 and record the missing v0.2 as an open planning dependency.

## Follow-ups (out of scope, noticed)

- Reconcile supplied plan with PRD v0.2 and its §12.1/scenario 13 references before later WPs.
- WP1: broad reads, direct model lookups in actions, shared dashboard cache, public DEBUG media, copied notification details, related-object/nested/search scope.
- WP4: non-null Issue.fc and enum stage field; already-null discovered_stage_record; preserve production blocking and FC history.
- WP8: use inventory manifest/preservation commit for deliberate parameter integration, not archive extraction or whole-branch merge.
- WP11: SoftwareUpdate.approved_by is a submitted user ID, not authenticated dual approval; retain legacy provenance without fabricating approvals.
- Diagnostics script/page missing; investigate under authorised later scope.
- npm audit reports one high source-map-js advisory. Django reports unordered FlightController queryset pagination. Recorded without remediation.
- Guard unit tests inherit TEST_POSTGRES_* from process environment; future test-isolation hardening may be appropriate. No source/test change in WP0.

## Placeholders introduced

No operational product policy defaults introduced. Only disposable environment names/ports and documentation navigation. All plan proposals remain proposals.

Final handoff verification: original 24 worktree file hashes unchanged; exact preservation branch SHA confirmed remotely; full plan copied verbatim; all local documentation links resolve; generated credentials absent from deliverables. Markdown/JSON/dependency diff whitespace check used Windows CR-at-EOL handling; raw command logs retain observed blank lines. Temporary service shutdown is recorded in validation/cleanup.txt.
