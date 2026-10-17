# Repository guidance for Claude Code and OpenAI Codex

## Purpose and current phase

This repository contains KapilFutureTech's internal engineering platform candidate in `fcops/`.

Read `fcops/PRD.md` before planning or changing product behaviour. Current phase is requirements and architecture planning. The user has authorised PRD and agent-guidance documentation, not application implementation. Do not treat this file as authorisation to implement, migrate, deploy, or send email. Once the user authorises implementation, proceed within the authorised scope without repeatedly seeking the same permission.

Confirmed requirements take precedence over legacy README assumptions. Proposed defaults and open decisions in the PRD must not be represented as approved policy.

## Instruction provenance and Graphify

This file incorporates the Graphify guidance found in `C:/Users/Hrushikesh/CLAUDE.md` on 17 October 2026 and adds repository-specific requirements from the planning discussion. No repository-local `CLAUDE.md` existed when this file was created. That user-level file was not modified.

- For codebase questions, first run `graphify query "<question>"` when `graphify-out/graph.json` exists in the relevant project root. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts.
- If `graphify-out/wiki/index.md` exists, use it for broad navigation.
- Read `graphify-out/GRAPH_REPORT.md` for broad architecture review or when focused queries are insufficient.
- After modifying code in a project with an existing Graphify graph, run `graphify update .` from that project root. If the tool is unavailable, report that limitation; do not claim the graph was updated.
- Do not create or install Graphify solely because this guidance exists. Neither workspace root nor `fcops/` had a graph at documentation creation time.

## Preserve ongoing work

- Start by inspecting `git status --short` and applicable nested instructions. This working tree already contains modified and untracked application files.
- Never reset, clean, overwrite, discard, or reformat unrelated work. Untracked files may contain important implementation.
- Read the working-tree source, not just committed content. Inspect diffs before editing a file with existing changes.
- Do not alter `fcops.tar.gz` or regenerate archives unless asked.
- Avoid concurrent agents editing the same files. Do not initiate agent delegation unless authorised by the user or applicable instructions.
- Keep changes focused, reviewable, and limited to the current request. Do not commit or push unless requested.

## Repository map

- `fcops/backend/accounts/`: users, departments, roles, permissions.
- `fcops/backend/core/`: audit, notifications, dashboard, shared infrastructure.
- `fcops/backend/fc/`: serials, lifecycle, tests/rework, firmware/software records, parameter evidence/comparison.
- `fcops/backend/issues/`: issues, investigation, assignment, knowledge/search.
- `fcops/backend/config/`: settings, database configuration, URL routing.
- `fcops/backend/tests/`: backend regression tests.
- `fcops/frontend/src/`: React pages, authentication/API client, styles.
- `fcops/e2e/`: existing browser walkthroughs; these create/change data.

The preferred architecture remains Django/DRF + React/Vite + PostgreSQL in a centrally hosted modular monolith. Keep Windows/Android browser access in mind. Do not add services or dependencies without a concrete need and operating-cost justification.

## Product rules for future authorised implementation

- General issues may exist without an FC, lifecycle stage, customer, or exact version. Preserve specialised FC lifecycle behaviour.
- Keep human acknowledgement, accountable ownership, work status, blockers, and handoff acceptance distinct.
- A handoff must not leave a report without accountability. Follow the approved ownership policy.
- Preserve discovery facts separately from root-cause findings and later unit/version evidence.
- Independent verification must use a person other than the resolver.
- Distinguish approved parameters, recorded flashed configuration, and actual read-back evidence. Preserve raw evidence and provenance.
- All heads/manager see engineering issues and progress; members see team issues, own reports, and explicitly shared issues. Sensitive customer/contact and recipient data requires separate permissions. Follow the PRD for unresolved access details.
- Authorise backend queries and mutations, including related-object IDs, search, similar results, nested serializers, counts, caches, notifications, audit, attachments, parameter comparison, and exports. UI hiding is insufficient.
- A readable parent does not automatically grant access to every linked object.
- Both the manager and Software head must explicitly approve the current release revision. A submitted approver ID is not an approval. Content changes invalidate affected approvals.
- Email is an explicit authorised action after recipient/message preview. Keep immutable campaign snapshots and per-recipient attempt history; guard against duplicate sends. Sending email does not install a release.
- Keep signup API credentials server-side. The API contract is pending; do not invent integration details or silently substitute a customer data source.
- Sales, marketing, social monitoring, and call tracking are outside current scope.

## Data and environment safety

- Never expose `.env` values, passwords, database URLs with credentials, tokens, or customer mailing lists in output, docs, logs, screenshots, or commits.
- Do not connect to or mutate shared/live data merely to inspect the source. Use a disposable test environment for future validation.
- Django tests create/drop databases. Inspect `config/db.py` and `config/test_runner.py` guards before running database tests; confirm the target is disposable. Do not bypass remote-database protection or enable `ALLOW_TESTS_ON_REMOTE_DB` to make tests pass.
- Seeds, migrations, `dbcheck --deep`, and browser walkthroughs may write data. Do not run them against a shared environment without explicit scope authorisation.
- Real email sending, deployment, and production schema changes require authorisation for those actions; documentation/planning approval is insufficient.
- Preserve audit/history and evidence. Do not describe append-only application/database protection as protection from all database-administrator actions.

## Validation and handoff

When implementation is authorised, run checks appropriate to the change in an isolated environment. Backend tests normally run from `fcops/backend/` using `python manage.py test tests --noinput`; inspect environment safety first. Frontend build/lint scripts are defined in `fcops/frontend/package.json`. Consult `fcops/e2e/README.md` before browser walkthroughs.

Prioritise meaningful negative permission tests, workflow/concurrency tests, evidence preservation, dual approval, and duplicate-send handling. Existing universal-read tests reflect the prototype and must be deliberately revised when access policy changes.

Do not claim checks ran or passed unless observed in the current work. Existing README and implementation-note validation claims are historical, not current verification. Documentation-only changes do not require launching the application or touching databases.

At handoff, state what changed, what was verified, limitations, and open decisions. Distinguish implemented features from planned features and simulated email from real delivery. Keep the PRD aligned with subsequently approved decisions.
