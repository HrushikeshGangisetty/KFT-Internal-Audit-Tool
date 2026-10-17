# WP1 — Access policy foundation
Agent: Claude Code    Branch: wp/01-access-policy    Date: 17 October 2026

Authorised by the user in chat ("Continue with the next task in the implementation_plan.md"), after WP0 was merged to `main`. Built on `main` (`e2d1040`), not on the preserved local work.

## Done

- **Memberships and capabilities** (`fcops/backend/accounts/models.py`, `accounts/services.py`): `TeamMembership(user, department, role ∈ member/head/backup_head, active_from, active_to, created_by)` with one open membership per user+department (DB constraint); `CapabilityGrant(user, capability, granted_by, granted_at, revoked_at, revoked_by, note)` with one active grant per capability (DB constraint). Services `add_membership`, `close_membership`, `grant_capability`, `revoke_capability` audit every change. `sync_legacy_fields` applies only the delta when `User.department`/`User.role` change through the user admin API (`accounts/views.py`), the seed command and the test factory.
- **Legacy mapping** (`accounts/migrations/0003_migrate_legacy_roles.py`): user with a department → open membership (head if DEPARTMENT_LEAD, else member, active from `date_joined`); MANAGER → `is_manager`; ADMIN → `can_administer_accounts` only (no record access); member of a SOFTWARE-kind department → `can_draft_release`, plus `is_software_head` if DEPARTMENT_LEAD. On the seeded demo data this produced 12 memberships and 3 grants. Added `Department.KIND_SERVICE` (choices only).
- **Policy module** (`fcops/backend/access/policy.py`): `is_head_or_manager`, `visible_issues` (responsible department ∈ active memberships, reporter, assigned person, active collaborator/verifier participant), `can_view_issue` (defined via `visible_issues`), `visible_attachments`, `visible_knowledge` (audience `all_staff` / `departments` / `heads`), `can_view_fcs` / `scope_by_fc` / `visible_fcs` / `visible_stage_records`, `visible_notifications`, `visible_audit_entries`.
- **DRF enforcement** (`access/mixins.py`): `ScopedViewSetMixin` (raises `ImproperlyConfigured` without `get_scoped_queryset`; out-of-scope detail = 404) and `ScopedPrimaryKeyRelatedField`. Every router viewset now uses the mixin; class-level `queryset` attributes were removed so nothing can read an unscoped default (explicit router basenames keep the old URL names).
- **Surfaces scoped**: issue list/detail/notes/reassignment/status/actions; search (`/issues/?q=` and `/issues/search/`) scopes before ranking; similar issues and similar-search rank only within `visible_issues` / `visible_knowledge` (`issues/search.py::find_similar` now takes the scoped querysets); dashboard counts from scoped querysets, no caching; FC detail/timeline/issues/audit actions (timeline drops events about unseen issues); stage/rework/firmware/test records via FC scope; firmware `flash`/`flashes`; known issues (occurrence count, verification count, first/last occurrence links and occurrences action are per-reader); audit log.
- **Relationship validation**: attachment `issue`, rework `stage_record`/`originating_issue`, firmware record `fc`/`stage_record`, test result `fc`/`stage_record`/`linked_issue` use `ScopedPrimaryKeyRelatedField`; issue create looks up the FC in `visible_fcs`; `link-known-issue` looks up in `visible_knowledge`.
- **Attachments**: removed DEBUG public media serving (`config/urls.py`). Added `GET /api/issue-attachments/<id>/download/` (scope via parent, `FileResponse`, `Content-Disposition: attachment`, `X-Content-Type-Options: nosniff`). Serializer no longer exposes the storage path; `url` is the download endpoint. Frontend fetches it with the bearer token (`frontend/src/lib/api.js::download`).
- **Notifications** (`core/models.py`, `core/migrations/0004_notification_target_pointer.py`, `core/serializers.py`): stored as `(recipient, kind, target_type, target_id, read_at, created_at)`; copied `message`/`link` columns dropped after converting `/issues/<id>` links. Text is rendered at read time only if the recipient can still see the issue, otherwise "You no longer have access to this item" with no link. Department notifications go to active members; high-severity notifications go to `is_manager` grant holders (no longer to admins).
- **Participants** (`issues/models.py::IssueParticipant`, `issues/services.py::add_participant/remove_participant`, `POST /api/issues/<id>/participants/`): collaborator/verifier with history (`removed_at`). Needed so the "assigned verifier" actor exists and so the existing verification flow stays usable. Small "Participants" card in `frontend/src/pages/IssueDetail.jsx`.
- **Tests**: `tests/access_fixtures.py` (the access-matrix world), `tests/test_access_matrix.py` (14 tests, every actor × list, detail by ID, search, list text query, similar/similar-search with `limit=1`, dashboard counts, attachment download, audit log; plus named acceptance cases), `tests/test_route_coverage.py` (3 tests). Removed `test_everyone_can_read_everything`; adapted two API workflow tests and the `find_similar` unit tests.
- **E2E** (`fcops/e2e/ui_walkthrough.py`): technician similar-panel step now accepts a scoped/empty answer; added "head sees prior issues" and "head assigns verifier" steps. Seed demo marks promoted known issues `all_staff`.

## Acceptance

| Item | Evidence | Result |
|---|---|---|
| Scenario 5: `sw_member` reads Software issues; `asm_member` 404 on detail, absent from lists, search, similar, counts; heads and `manager` see all | `test_scenario_5_software_issue_hidden_from_assembly`, `test_issue_list_and_detail`, `test_search_and_list_text_query`, `test_similar_results_rank_only_visible_issues`, `test_dashboard_counts` | PASS |
| `verifier` sees only the assigned Software issue | `test_verifier_sees_only_the_assigned_software_issue` + matrix rows | PASS |
| `ex_member` loses access immediately after closure | `test_membership_closure_removes_access_immediately` (closure mid-test, and closed-yesterday actor) | PASS |
| `admin` sees no issues by being an administrator | `test_admin_sees_no_issues_by_being_admin` (superuser, 0 issues) | PASS |
| Attachment URLs not publicly fetchable; unauthorised download 404 | `test_attachments_are_not_publicly_fetchable` (401 unauthenticated, `/media/...` 404), `test_attachment_download` (404 per out-of-scope actor) | PASS |
| Notification about an issue the user lost access to renders without detail | `test_notification_renders_without_detail_after_access_lost` | PASS |
| Route-coverage meta-test passes, and fails for an unscoped viewset | `test_every_api_view_is_scoped_or_allowlisted`, `test_an_unscoped_viewset_is_caught` (temporary `UnscopedViewSet`) | PASS |

## Commands run and results

Disposable environment from WP0 (Python 3.12 venv, portable PostgreSQL 16 on 127.0.0.1:55432); TEST_POSTGRES_* not set. Fresh database `fcops_wp1` for migrate/seed/E2E.

- `manage.py check`: no issues. `makemigrations --check --dry-run`: no changes.
- First full suite run on the WP1 code before test updates: 123 tests, 2 failures + 3 errors — all expected policy consequences (Testing user could no longer read an Assembly issue; `find_similar` signature). Fixed in tests as described above.
- Targeted run (access matrix, route coverage, RBAC, issues/search): 55 tests, OK.
- Full suite (`manage.py test tests --noinput`): **142 tests in 248.561s, OK**.
- `migrate` on fresh DB: OK. `seed --demo`: OK (31 notifications, 12 memberships, 3 grants). Reversal `migrate core 0003; issues 0002; accounts 0001`: OK, 31 notifications restored with `/issues/<id>` links. Re-applied forward: OK, same counts. `dbcheck --deep`: all checks passed.
- `npm run build`: OK (node_modules copied from WP0's install of the identical lockfile).
- `e2e/ui_walkthrough.py` (Chrome via `PLAYWRIGHT_CHROMIUM`, loopback servers): **STEPS PASSED: 19, PAGE ERRORS: none**. The first two attempts failed at the similar-panel step, as the policy intends; assertion revised as described.

## Not done / deviations from plan

- Tests live in `fcops/backend/tests/` (not `access/tests/`) so the documented `manage.py test tests` command runs them.
- Scope functions use subqueries instead of joins plus `.distinct()`: same composability, and `values().annotate(Count)` counts stay exact.
- Download route is `/api/issue-attachments/<id>/download/` (existing resource prefix) rather than `/api/attachments/<id>/download/`.
- Handoff recipients are not in `visible_issues` yet (no handoff model until WP5). Accountable person = existing `assigned_person`.
- Write permissions still use the legacy `User.role` (unchanged permission classes); WP1 changes read scope. Capability grants are not yet used for write checks.
- No API/UI for managing memberships or grants beyond the legacy-field sync; services exist and are audited.
- Attachment download through the UI was not clicked in the E2E; covered by backend tests only.
- Diagnostics page/script still absent (WP0 finding).

## Decisions taken in this session (and why)

- Dashboard: **no caching** (plan's simpler option); nothing to key per user.
- Admin role maps to `can_administer_accounts` only, and superuser status grants no record access through the API.
- FC scope is all-or-nothing by department kind (placeholder), so FC child records use one helper.
- Known-issue default audience is `heads` (plan); demo seed opts its articles into `all_staff`.
- Participant adding allowed for heads, managers and the assigned person (placeholder until WP5/WP7). Refusal is 403.
- FC detail keeps its unfiltered internal issue prefetch so stage/approval blocking still counts every issue; only keys and statuses appear in blocker text.

## Follow-ups (out of scope, noticed)

- Django `/admin/` lets staff superusers read every issue; decide whether to restrict or unregister issue models (WP2/WP15).
- FC detail blocker messages show issue keys/statuses of issues the reader may not otherwise see; review once the FC access matrix (PRD §5) is agreed.
- Notification rendering does one query per notification; batch per page if lists grow.
- Membership/grant administration endpoints and UI; move write permissions to capabilities.
- `UserAdmin` in Django admin bypasses `sync_legacy_fields`.

## Placeholders introduced

- `FC_VISIBLE_DEPARTMENT_KINDS` (env, default `HARDWARE,FIRMWARE,SOFTWARE,MECHANICAL,TESTING,QUALITY,SERVICE`) until the FC access matrix is agreed.
- Participant-add rule in `IssueViewSet.participants`.
- Knowledge audience default `heads`.
