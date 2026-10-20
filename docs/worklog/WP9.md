# WP9 — Customers and deployments (minimal)
Agent: Codex    Branch: main    Date: 20 October 2026

The user explicitly authorised WP9, commit and integration onto main without a new branch. The checkout was already on main and clean; implementation is committed directly there. No PR, external review, push, deployment, shared-data changes or real email are part of this session.

## Done

- Added the `customers` app: engineering-only `Customer(name, region, notes)`, restricted `CustomerContact(customer, name, phone, email, role)`, and `Deployment(customer, site_name, units, gcs_version_at_handover, notes, deployed_at)`.
- Added list/detail/create/update APIs at `/api/customers/`, `/api/customer-contacts/`, `/api/deployments/`. Contacts use a separate serializer and endpoint, never nested into summaries, issues or search responses. No delete API is exposed; related records use PROTECT.
- Central policy helpers scope summaries and deployments by the existing FC policy. Contacts require an active `can_view_customer_contacts` grant, independently of FC visibility, team sharing, head/manager status and account administration. Revocation takes effect on the next request.
- Added nullable `Issue.customer` and `Issue.deployment`, settable or clearable after reporting through the existing issue PATCH service. Related IDs are validated through scoped fields; mismatched customer/deployment pairs are rejected. Linked summary IDs are hidden from issue readers without FC-summary access, including issue audit snapshots. Search, FC issue/audit actions and known-issue occurrences now supply serializer request context.
- Customer writes and deployment unit membership changes go through a transactional, audited service. Contact audit snapshots and labels remain restricted, including for managers. Deployment customer changes cannot invalidate current issue context; deployment rows are locked against concurrent issue associations.
- Added reversible schema migrations `customers/0001_initial.py` and `issues/0008_issue_customer_issue_deployment.py` without altering existing records.
- Updated agent guidance and the implementation-plan pointer to record WP9 authorisation without authorising later WPs.

## Acceptance

| Item | Evidence | Result |
|---|---|---|
| Linked issue never includes restricted contact fields in detail, lists, search or nested responses | `test_issue_detail_lists_search_and_audit_do_not_leak_contacts` (includes FC issue and audit actions), `test_summary_and_deployment_visible_without_contacts` | PASS |
| Cross-team issue sharing does not grant contacts | `test_cross_team_sharing_does_not_expose_contacts` | PASS |
| Manager/admin cannot implicitly read contacts or their audit history | `test_manager_and_admin_do_not_implicitly_get_contacts`, `test_capability_grants_and_revokes_contacts_and_their_audit` | PASS |
| Summary and related-ID access follows FC policy, independently of issue sharing | `test_no_fc_access_hides_summaries_related_ids_and_audit`, `test_summary_scope_tracks_fc_policy_configuration`, `test_contact_grant_is_independent_of_fc_visibility` | PASS |
| Issue context remains optional, editable after submission and consistent | `test_post_submission_links_nullable_audited_and_customer_consistent`, `test_deployment_customer_change_cannot_invalidate_issue_context` | PASS |
| Writes and related IDs are authorised; routes use the access layer | `test_summary_writes_are_head_only_and_contact_writes_require_capability`, `test_related_ids_are_scoped_for_deployment_and_contact_writes`, route-coverage meta-tests | PASS |

## Commands run and results

Inspected `config/db.py` and `config/test_runner.py` before running database checks. Reused WP0's private Python 3.12 environment and portable PostgreSQL 16 cluster, exclusively on 127.0.0.1:55432. Private harnesses under `.git/` load disposable credentials without publishing them, clear remote URL overrides, and leave remote-test protection enabled. No original `.env` was read for credentials or modified.

- Initial targeted run: 13 tests, two errors and one assertion failure. Fixed missing request context on explicit serializer call sites and corrected test expectations for the existing capability-revocation signature and HTTP 409 workflow errors.
- Targeted run after those fixes: 13 tests, OK. Final expanded WP9 + route-coverage run: **15 tests in 4.081s, OK**.
- A full-suite attempt was interrupted when the disposable PostgreSQL server stopped; no pass is claimed for that run. An overlapping targeted attempt refused to recreate the busy disposable test database; subsequent checks use distinct disposable database names. Two restart attempts failed before tests because the server was unavailable/defaulted to the wrong port; restarting explicitly on loopback port 55432 restored the test environment.
- Final full suite: `manage.py test tests --noinput --parallel 2`: **241 tests in 324.590s, OK**. The stale disposable test database from the interrupted attempt was recreated; both isolated worker clones and the base test database were removed by the runner.
- On a separately created disposable database `fcops_wp9_validation`: `migrate --noinput`, `migrate customers zero --noinput` (also reverses issue migration 0008), reapply `migrate --noinput`, `check`, `makemigrations --check --dry-run`: all passed. The database was then removed. Reversal removes WP9 tables/fields and therefore loses WP9 data; restore from backup if preserving that data is necessary.
- `git diff --check`: passed.
- No frontend files changed; build and browser walkthroughs were not run.

## Decisions and limitations

- Minimal backend/API scope; dedicated customer/deployment screens are deferred to later UI work. Initial issue reporting remains unchanged; attach optional context afterward with PATCH.
- Summary/deployment read access inherits the existing configurable, provisional all-or-nothing FC matrix from WP1. This session does not approve a permanent FC/customer policy.
- Conservative maintenance default: active heads/managers with FC scope maintain engineering summaries and deployments; the contact capability gates contact maintenance as well as reading. A separate customer-maintenance capability/role matrix remains a policy follow-up.
- Engineering notes are explicitly for summaries. The service does not infer/redact sensitive information manually placed in free text; contact fields belong exclusively in the restricted contact resource.
- No new dependencies, mailing-list integration, release/campaign changes, actual installation tracking, real sending or deployment.
- No Graphify graph exists at the workspace or fcops root; no graph update was applicable.

## Follow-ups (out of scope)

- WP10–WP15 remain unauthorised. Confirm permanent customer write roles and FC/customer-summary access before shared use.
- Customer/deployment UI and browser acceptance; broader operational readiness remains WP14/WP15.
