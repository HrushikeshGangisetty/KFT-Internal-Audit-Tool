# Implementation Plan — KapilFutureTech Internal Engineering Platform

Version 1, 17 October 2026. Implements `PRD.md` v0.2.

**Gate:** implementation starts only after the product owner authorises the pilot feature cut (PRD §15, last row). Until then, only WP0 (inventory and baseline) may run, because it reads and records without changing the application.

---

## 0. How to use this plan

This plan is split into **work packages (WPs)**. Each WP is sized for one agent session, or two at most, and produces one pull request.

**One WP = one branch = one PR.** Branch name: `wp/<nn>-<slug>`, for example `wp/01-access-policy`.

**Agent split (Codex first, then Claude Code):**

- Whichever agent implements a WP, the *other* agent reviews its PR before merge. Review against the WP's acceptance checklist and against `AGENTS.md`, not just "does it look right".
- Never run both agents on the same WP or the same branch at the same time.
- Each session ends by writing `docs/worklog/WP<nn>.md` (template in Appendix B). The next session, whichever agent runs it, reads the worklogs of the WP's dependencies first.

**Session prompt template** (paste into Codex or Claude Code, then fill in):

```
Read AGENTS.md, PRD.md, and IMPLEMENTATION_PLAN.md section WP<nn>.
Read docs/worklog/ for WPs listed under "Depends on".
Implement WP<nn> on branch wp/<nn>-<slug>.
Stay inside the WP's scope; list anything out of scope you noticed under
"Follow-ups" in the worklog instead of doing it.
Before finishing: run the full backend test suite and the WP's listed checks,
then write docs/worklog/WP<nn>.md with what you actually ran and the results.
Do not mark an acceptance item done unless a test or a recorded manual check
demonstrates it.
```

**Definition of done for every WP:**

1. Every acceptance item has a test, or a manual check recorded in the worklog.
2. The full backend test suite passes. Frontend build passes if the frontend was touched.
3. Migrations are reversible, or the worklog says why one is not.
4. No new endpoint returns data without going through the access layer (WP1). The route-coverage meta-test enforces this.
5. All state changes go through service functions, which write audit entries. Views never call `.save()` on domain models directly.
6. The worklog is written.

---

## 1. Invariants (carried into AGENTS.md)

These hold across every WP. A PR that breaks one is not mergeable even if its tests pass.

1. **Preserve local work.** Never delete, overwrite, or reformat files outside the WP's scope. The untracked parameter work is preserved by WP0 before anything else happens.
2. **Services own state.** Domain state changes happen in `services.py` functions that validate, write, and audit in one transaction. This pattern already exists; keep it.
3. **Access is enforced in the backend, in one place.** Querysets are scoped through the access module. Never rely on the frontend hiding something.
4. **Audit is append-only.** The existing database trigger stays. New auditable events use the existing audit service.
5. **FC status stays derived.** `recompute_status` and `fc/lifecycle.py` rules are extended, never bypassed or replaced wholesale.
6. **History, not overwrite.** Evidence, approvals, verifications, handoffs, and daily updates are new rows. A "current" value is derived or pointed to; older rows are kept.
7. **External side effects happen after commit.** Email, alerts, and calls to the signup API are enqueued as jobs inside the transaction and executed by the worker after commit.
8. **No fabricated verification.** If something was not run, the worklog says so. "Should work" is not "works".
9. **No real recipients without approval.** Until the signup API contract and the sending provider are approved, only the synthetic adapter and the console/file email backend are allowed.

---

## 2. Known starting point (verify in WP0)

From the August 2026 build notes. **Every line here is an assumption until WP0 confirms it against the repository.**

| Area | Believed state |
| --- | --- |
| Backend | Django 5.2, DRF, PostgreSQL 16. Apps: `core` (audit, notifications, dashboard), `accounts` (users, departments, RBAC), `fc` (lifecycle, stages, rework, firmware, tests), `issues` (issues, notes, reassignment, known issues, full-text search) |
| Frontend | React 19 + Vite. Pages: login, dashboard, FC list/create/detail, issues, search, known issues, audit log, admin, Diagnostics |
| Auth | JWT stored in browser local storage |
| Access | Universal read for authenticated users, with tests asserting it |
| Issues | Assumed to require an FC and a stage (PRD §11 says this must be removed) |
| Releases | Release/version records exist with a *named* approver field, not authenticated approval |
| Parameters | Parameter comparison exists, partly as **untracked local files** |
| Audit | Append-only, enforced by a database trigger |
| Attachments | Local disk, served from the media URL |
| Notifications | In-app only |
| DB config | `backend/config/db.py` handles `DATABASE_URL`, pooler detection, test-DB guard |
| Commands | `dbcheck [--deep]`, `reindex_search`, `seed --demo` |
| Tests | 63 backend tests passing as of 25 Aug 2026 (historical claim); 23 frontend diagnostics tests; `e2e/ui_walkthrough.py` |
| Python | 3.10 minimum, 3.12 recommended |

---

## 3. Target module map

Keep the existing four apps. Add new apps only where a boundary is real.

| App | Status | Owns |
| --- | --- | --- |
| `accounts` | extend | Users, departments, team membership and roles, capability grants |
| `access` | **new** | The policy module: scope querysets, object checks, the DRF mixin, the route-coverage meta-test. No models of its own except `AccessGrant` if explicit sharing does not fit on issue participants |
| `core` | extend | Audit, notifications, dashboard, **jobs/worker/scheduler**, **alert delivery**, private file downloads, working calendar |
| `issues` | extend | Issues (decoupled from FC), incidents/workstreams, routing, acknowledgement, ownership, handoffs, deadlines, resolution, verification, knowledge |
| `fc` | extend | Lifecycle (unchanged rules), issue↔unit links, **typed configuration evidence** |
| `customers` | **new** | Customer, restricted contact, deployment |
| `releases` | **new or extracted** | Release revisions, approvals, recipients, campaigns, deliveries. If release models currently live in `fc`, move them here in WP11 with a data-preserving migration |
| `tasks` | **new** | Tasks, collaborators, daily updates |

Dependency direction: `access` may import models from any app. Domain apps call `access` for scoping. `core.jobs` must not import domain apps; domain apps register job handlers with it.

---

## 4. Sequencing

```
WP0 baseline ─┬─> WP1 access ──┬─> WP4 issue decouple ─> WP5 routing/ack/handoff ─> WP6 deadlines/escalation
              │                │                                     │
              ├─> WP2 auth/origin                                    └─> WP7 resolve/verify
              │                │
              └─> WP3 jobs+alerts ─────────────────────────────────────> (WP6 needs WP3)
                               │
                               ├─> WP8 FC + config evidence
                               ├─> WP9 customers/deployments
                               ├─> WP10 tasks/progress
                               └─> WP11 release approval ─> WP12 recipients ─> WP13 campaigns
                                                                                   │
                                     WP14 mobile UI + E2E  <── all of the above ───┘
                                     WP15 shared-use readiness (after approval; paid DB)
```

| Pilot day | WPs | Notes |
| --- | --- | --- |
| Day 1 | WP0, WP1, WP2, WP3 (core only) | WP1 is the critical path for everything after it |
| Day 2 | WP3 (alerts), WP4, WP5, WP6 | The highest-value day: the reference incident flow |
| Day 3 | WP7, WP8, WP9 (minimal), WP10 (minimal) | |
| Day 4 | WP11, WP12 (synthetic), WP13, WP14 | Ends with the pilot review |
| After approval | WP15 | Paid database, hosting, backups |

**Cut line if over time** (PRD §12): drop in this order:

1. WP10 head dashboard polish (keep the models and the API).
2. WP9 beyond the minimal deployment link.
3. WP13 real sending (keep preview, snapshot, idempotency, and synthetic delivery).
4. WP8 comparison UI (keep evidence storage).

Never cut: WP1, WP5, WP7's resolver≠verifier rule, WP11's revision-bound approval, or the FC lifecycle tests.

---

## 5. Work packages

### WP0 — Baseline, inventory, and preservation

**Depends on:** nothing. **Allowed before authorisation:** yes (read and record only).
**Suggested agent:** Codex. **Size:** half a day.

**Steps**

1. **Preserve local work before touching anything.**
   - Record `git status --porcelain`, `git stash list`, and `git log -1` in `docs/INVENTORY.md`.
   - Commit modified and untracked files, *as they are*, to a branch named `preserve/local-work-2026-10-17`, and push it. Do not clean them up, rename them, or run formatters on them. If any file looks like a secret (`.env`, keys), list its path in the inventory but do not commit it.
   - Create `main`-based working branches from here on. The parameter work is merged into the plan in WP8, deliberately.
2. **Inventory the code against Section 2.** For each row, record "confirmed", "different: …", or "not found", with file paths. Also record:
   - every DRF viewset/APIView and its route, and how it builds its queryset;
   - every model with a foreign key to `FlightController` or `Stage`, and whether it is nullable;
   - where release records and approver fields live;
   - where attachments are stored and how they are served;
   - how the frontend stores and sends the token;
   - existing management commands.
3. **Establish the environment.** Python 3.12 virtual environment, local PostgreSQL 16 (Docker is fine), `.env` from `.env.example`. Do not point tests at the Supabase project.
4. **Run what exists and record the real results:** backend tests, `migrate`, `seed --demo`, `dbcheck --deep`, frontend `npm run build`, `npm run test:diagnostics`, and the E2E walkthrough if a browser is available. Failures are recorded, not fixed, in this WP.
5. **Add agent context files:** `AGENTS.md` (from the companion file), `CLAUDE.md` containing a single line `@AGENTS.md`, `docs/worklog/` with the template, and `PRD.md` plus this plan under `docs/`.
6. Add tooling for later WPs: `time-machine` (frozen time in tests), `factory_boy` if not present, `pytest-django` only if the suite already uses pytest (otherwise stay on Django's runner).

**Acceptance**

- [ ] The preservation branch exists and is pushed, and its file list matches the recorded `git status`.
- [ ] `docs/INVENTORY.md` covers every row of Section 2 with file paths.
- [ ] Test, build, and migrate results are recorded verbatim, including failures.
- [ ] `AGENTS.md`, `CLAUDE.md`, and `docs/worklog/` exist.

**Output used by later WPs:** the viewset list (WP1), the FC-coupled FK list (WP4), the release model location (WP11), and the parameter work file list (WP8).

---

### WP1 — Access policy foundation

**Depends on:** WP0. **Suggested agent:** Claude Code. **Size:** one day. **Critical path.**

**Model changes (`accounts`)**

- `TeamMembership(user, department, role ∈ {member, head, backup_head}, active_from, active_to)`. A user may belong to several departments. History is kept by closing `active_to`, not by deleting the row.
- Capabilities, kept separate from scope: `is_manager`, `is_software_head`, `can_draft_release`, `can_send_announcements`, `can_view_customer_contacts`, `can_administer_accounts`. Implement as Django permissions on groups, or as a `CapabilityGrant(user, capability, granted_by, granted_at, revoked_at)` table. Prefer the grant table because grants must be audited.
- Migrate existing role/department data into these. Record the mapping in the worklog.

**Policy module (`access/`)**

```
access/
  policy.py      # scope functions + object checks
  mixins.py      # ScopedViewSetMixin
  tests/
    fixtures.py  # the access matrix world
    test_matrix.py
    test_route_coverage.py
```

- `is_head_or_manager(user)`: active head or backup head of any department, or manager.
- `visible_issues(user) -> QuerySet`, for heads and managers all engineering issues; otherwise the union of:
  - issues whose responsible department is one of the user's active departments,
  - issues the user reported,
  - issues where the user is a participant (accountable, collaborator, assigned verifier, or handoff recipient while the handoff is pending or accepted).
  Build this as a single `Q` filter with `.distinct()`, not Python set unions, so it composes with search and counts.
- `can_view_issue(user, issue)`, implemented as `visible_issues(user).filter(pk=issue.pk).exists()` so there is exactly one definition.
- Equivalent functions for each record type that exists after WP0: `visible_fcs`, `visible_attachments`, `visible_notifications`, `visible_audit_entries`, `visible_knowledge`. Child records (notes, attachments, timeline events) are visible only through their parent's scope function, never through "you can see one linked thing".
- FC scope: until the FC access matrix is agreed (PRD §5), use *heads, managers, and members of production/engineering/testing/service departments*, configured in settings as `FC_VISIBLE_DEPARTMENTS`. Mark it clearly as a placeholder.

**DRF enforcement**

- `ScopedViewSetMixin` requires `get_scoped_queryset(self)`. `get_queryset` calls it and raises `ImproperlyConfigured` if the subclass did not define it. A detail lookup outside scope returns **404**, not 403, so that existence does not leak.
- Write and relationship validation: serializers that accept foreign keys (an issue's linked FC, a note's issue, a handoff's target) must validate that the user can see the referenced object. Put this in a reusable `ScopedPrimaryKeyRelatedField` whose queryset comes from the scope function for the request user.
- **Route-coverage meta-test:** iterate over `get_resolver()` URL patterns, find every DRF view, and fail if any non-allowlisted view does not use `ScopedViewSetMixin`. The allowlist (login, health, CSRF) lives in the test with a comment per entry. This is what stops a future endpoint from bypassing access.

**Surfaces to scope in this WP** (PRD §12.1, pilot column)

- Issue list and detail, notes, reassignment history.
- **Search and similar issues:** apply `visible_issues` *before* ranking and limiting, so a hidden match can neither occupy a slot nor appear in a count. Snippets come only from visible rows.
- **Dashboard counts:** compute from scoped querysets. If anything is cached, key the cache on user ID and a per-user access version (bumped on any membership or grant change). Simpler: no caching in the pilot. Record which was chosen.
- **Attachments:** remove public media serving for attachments. Add `GET /api/attachments/<id>/download/`, which checks scope through the parent and streams the file (`FileResponse`). Set `Content-Disposition: attachment` and `X-Content-Type-Options: nosniff`. For object storage later, the same view issues a short-lived signed URL instead.
- **Notifications:** store `(recipient, kind, target_type, target_id, created_at, read_at)` with no copied detail text. Render the title at read time from the target, and only if the recipient can still see it; otherwise show "You no longer have access to this item".
- **Known issues and knowledge:** occurrence counts and occurrence links filtered by `visible_issues`. An article's own visibility is its `audience` field (`all_staff`, `departments`, `heads`). Default to `heads` until an author sets it.

**Replace the universal-read tests.** Delete the tests that assert universal read, and say so in the PR description.

**The access matrix fixture** (`access/tests/fixtures.py`), reused by every later WP:

| Actor | Membership |
| --- | --- |
| `sw_member` | Software member |
| `sw_head` | Software head (also `is_software_head`) |
| `asm_member` | Assembly member |
| `asm_head` | Assembly head |
| `fw_member` | Firmware member |
| `svc_member` | Service member (reporter in scenarios) |
| `manager` | Manager capability, no department |
| `admin` | Account administrator, no department, not a head |
| `verifier` | Assembly member explicitly assigned as verifier on one Software issue |
| `ex_member` | Former Software member (membership closed yesterday) |

Seed one Software issue reported by `svc_member`, one Assembly issue, and one Software issue with `verifier` assigned. Parametrised tests then assert visibility for every actor × every surface, via list, detail by direct ID, search, similar issues, counts, attachment download, and notification rendering.

**Acceptance**

- [ ] Scenario 5: `sw_member` reads Software issues; `asm_member` gets 404 on their detail and does not see them in lists, search, similar results, or counts; heads and `manager` see everything.
- [ ] `verifier` sees only the issue they are assigned to, not other Software issues.
- [ ] `ex_member` loses access immediately after the membership is closed.
- [ ] `admin` sees no issues by virtue of being an administrator.
- [ ] Attachment URLs are not publicly fetchable, and an unauthorised download returns 404.
- [ ] A stored notification about an issue the user lost access to renders without detail.
- [ ] The route-coverage meta-test passes and fails when an unscoped viewset is added (demonstrate this with a temporary test view).

---

### WP2 — Single origin and cookie authentication

**Depends on:** WP0. Can run in parallel with WP1. **Suggested agent:** Codex. **Size:** half a day.
**Blocked on decision:** authentication approach (PRD §15). If JWT is kept instead, move tokens into HttpOnly cookies and skip the session-specific steps.

**Steps**

1. DRF default authentication becomes `SessionAuthentication`. Add `POST /api/auth/login/`, `POST /api/auth/logout/`, `GET /api/auth/me/`, `GET /api/auth/csrf/` (sets the cookie). Use Django's `login()` and `logout()` so sessions rotate.
2. Settings: `SESSION_COOKIE_HTTPONLY`, `SESSION_COOKIE_SECURE` and `CSRF_COOKIE_SECURE` in production, `SAMESITE=Lax`, and session age and idle timeout from env.
3. Login rate limiting, either with `django-axes` or a simple per-IP/per-username counter with lockout. Record which.
4. Deactivation: set `is_active=False` and delete that user's sessions in the same service function. Test that the next request returns 401/403.
5. Frontend: remove token storage and the `Authorization` header code. An API client fetches `/api/auth/csrf/` once and sends `X-CSRFToken` on unsafe methods with `credentials: 'same-origin'`. A 401 redirects to login.
6. Single origin:
   - **Dev:** the Vite dev server proxies `/api` and `/admin` to Django, so the browser sees one origin.
   - **Prod:** `npm run build` output is served by Django with WhiteNoise. A catch-all view returns `index.html` for non-API paths. The Web Serial secure-context requirement is still met over HTTPS.
   - Remove `django-cors-headers` configuration, or leave it disabled in production.
7. `seed --demo` refuses to run when `DEBUG=False` or when a `PRODUCTION=1` env flag is set.

**Acceptance**

- [ ] No token appears in `localStorage` or `sessionStorage` (checked in the E2E).
- [ ] A POST without a CSRF token is rejected.
- [ ] A deactivated user's existing session stops working on the next request.
- [ ] The production build serves the SPA and the API from one origin. Deep links (for example `/issues/42`) load the SPA.
- [ ] The Diagnostics page still loads (manual check over `localhost`).

---

### WP3 — Job queue, scheduler, and alert delivery

**Depends on:** WP0. The alert part needs WP1's notification scoping. **Suggested agent:** Claude Code. **Size:** about a day, split across Day 1 and Day 2.

**Job queue (`core/jobs/`)**

- Model `Job(id, kind, payload jsonb, status ∈ {queued, running, succeeded, failed, dead}, run_after, attempts, max_attempts, last_error, locked_by, locked_at, idempotency_key unique nullable, created_at, finished_at)`.
- `enqueue(kind, payload, *, run_after=None, idempotency_key=None)`, called inside the domain transaction via `transaction.on_commit` so a rolled-back transaction enqueues nothing. A duplicate idempotency key is a no-op that returns the existing job.
- Claiming: `select_for_update(skip_locked=True)` on queued jobs whose `run_after <= now`, ordered by `run_after`, in a short transaction that sets `running`, `locked_by`, and `locked_at`. Handlers run outside that transaction.
- Retries use exponential backoff with `run_after = now + base * 2^attempts`. After `max_attempts` the job becomes `dead` and is visible to administrators.
- Stale lock recovery: jobs `running` with `locked_at` older than a timeout return to `queued`. Handlers must therefore be idempotent (see the delivery rules below).
- A handler registry, `@job_handler("kind")`, lets domain apps register handlers without `core` importing them.

**Scheduler**

- `python manage.py run_worker`: a loop that claims and runs jobs, and every 60 seconds runs registered periodic tasks (`@periodic("name", every=timedelta(minutes=1))`). Periodic tasks run under a PostgreSQL advisory lock so two workers never run the same tick.
- **Heartbeat:** `WorkerHeartbeat(worker_id, last_seen, version)` updated every loop. An admin/health endpoint reports staleness. A stale heartbeat (over 3 minutes) shows a banner to administrators and the manager. The external monitor in WP15 alerts on it.
- A process manager runs `run_worker` in production as a second always-on process (PRD §10.1).

**Working calendar (`core/calendar.py`)**

- `WorkingCalendar` settings: workdays, hours (10:00–18:00), timezone `Asia/Kolkata`, and a `Holiday` table.
- `add_working_minutes(start, minutes)` and `working_minutes_between(a, b)`. These are pure functions with thorough tests: across a weekend, across a holiday, starting after hours, starting before hours.

**Alert delivery (`core/alerts/`)**

- A `Channel` interface with `send(recipient_user, message) -> DeliveryResult(status ∈ {accepted, failed, unknown}, provider_ref, error)`.
- `InAppChannel` creates a notification row. `EmailChannel` uses Django's email backend: console or file in development, the provider in production after approval. `SMSChannel` and `WhatsAppChannel` are stubs that raise until the decision is made.
- `AlertDelivery(alert_key, recipient, channel, status, attempts, provider_ref, error, created_at, updated_at)` with **unique `(alert_key, recipient, channel)`**. This is the deduplication guarantee: the same escalation step can never alert the same person twice on the same channel.
- `dispatch_alert(alert_key, recipients, urgency, target)` creates delivery rows and enqueues one job per row. Urgent alerts use in-app plus email (plus the chosen after-hours channel once decided). Normal alerts are in-app only, with email optional per user preference.
- Out-of-app content: issue ID, urgency, queue, and a link only (PRD §6.3).
- A `failed` or `dead` delivery creates an in-app notice to the responsible head and the manager (keyed so it is also not duplicated).

**Acceptance**

- [ ] A job enqueued in a rolled-back transaction never runs.
- [ ] Two concurrent workers never run the same job (test with two threads on a `TransactionTestCase`).
- [ ] A job that crashes mid-handler is retried after lock timeout, and the handler's idempotency prevents a double effect.
- [ ] Calling `dispatch_alert` twice with the same key produces one delivery per recipient and channel.
- [ ] Scenario 13: with the heartbeat stale, the admin health endpoint reports it; after restart, overdue periodic work runs once.
- [ ] Working-calendar tests pass for weekends, holidays, and after-hours starts.

---

### WP4 — Decouple issues from FCs; incidents and workstreams

**Depends on:** WP1. **Suggested agent:** Codex. **Size:** half a day.

**Model changes (`issues`)**

- Make the FC and stage foreign keys on `Issue` **nullable**. Existing rows keep their values. This is a non-destructive migration.
- Add the fields below, all nullable except where stated:
  - `product_area` (choices: GCS, Configurator, Firmware, Parameters, FC hardware, Mechanical, Rover, Other, **Unknown**; required, default Unknown),
  - `impact` (choices including **Unknown**; required),
  - `urgency` (`urgent`, `normal`, `unknown`; required),
  - `occurred_at_approx`, `location_context`, `reproduction_notes`,
  - `reporter` (auto, required) and `submitted_at` (auto, required).
- **Immutable discovery facts:** `discovered_stage`, `discovered_department`, `discovered_by`, `reporter`, and `submitted_at` are write-once. Enforce this in the service function and with a test. Later links go in a new `IssueUnitLink(issue, fc, linked_by, linked_at, reason)`, never by editing the discovery FK.
- `kind ∈ {incident, workstream, standalone}` and `parent` (self-FK, only to an `incident`). An incident groups workstreams owned by different teams. A workstream inherits nothing automatically except a visible link back to its parent. Parent visibility is computed separately: seeing a workstream does not grant its sibling workstreams.
- Root-cause department stays separate from the responsible department (this exists; keep it).
- **Production blocking is separate:** an issue linked to an FC does not block its stage unless a `blocks_stage` decision is recorded by someone with lifecycle authority on that stage. Find where the current code blocks stages on open issues and gate it on this flag. Existing linked issues are migrated with `blocks_stage = true` where they currently block, so behaviour does not change for them.

**Services and API**

- `submit_report(reporter, title, symptom, impact, urgency, **optional)` validates only the three required fields, creates the issue, writes `submitted` and audit events, and calls routing (WP5; until then, a stub that leaves it unrouted). It returns the ID and the queue.
- Update the issue serializer and endpoints so FC and stage are optional everywhere. Remove FC assumptions from search, the similar-issue ranking, and the dashboard: a null FC must not crash or be excluded.
- Attachments on submission accept multiple files with a per-file size limit from settings. If one upload fails, the report itself still succeeds, and the response lists which files failed.

**Acceptance**

- [ ] Scenario 1 backend: a report with only title, symptom, and urgency=Unknown succeeds and returns an ID.
- [ ] Scenario 8: every existing FC lifecycle and rework test still passes unchanged. A general issue with no FC shows in lists, search, and the dashboard.
- [ ] Discovery facts cannot be changed through the API or services (test both).
- [ ] An incident with a Software workstream and a Firmware workstream: `fw_member` sees the Firmware workstream and the parent incident summary, but not the Software workstream's notes.
- [ ] Linking a severe issue to an FC does not block its stage without the `blocks_stage` decision.

---

### WP5 — Routing, acknowledgement, ownership, and handoffs

**Depends on:** WP4 (and WP1). **Suggested agent:** Claude Code. **Size:** one day. **Blocked on decision:** queue heads, backups, fallback coordinator (placeholders allowed in development, configured as data, not code).

**Models**

- `Queue(department, head, backup, is_fallback)`. Exactly one `is_fallback` queue, with the coordinator as head and the manager as backup. A queue without a head and backup is invalid (enforced by validation; unrouted reports go to the fallback).
- `RoutingRule(product_area, queue, priority)`. Unknown or unmatched areas go to the fallback.
- On `Issue`: `queue`, `accountable_user`, `acknowledged_at`, `acknowledged_by`. **Accountable defaults to the queue head** until a member accepts ownership.
- `IssueParticipant(issue, user, role ∈ {collaborator, verifier}, added_by, added_at, removed_at)`. This feeds WP1's scope function.
- `IssueEvent(issue, type, actor nullable, at, data jsonb)` with types `submitted`, `routed`, `assigned`, `notified`, `acknowledged`, `handoff_proposed`, `handoff_accepted`, `handoff_rejected`, `ownership_accepted`, `waiting_set`, `waiting_cleared`, `reminder_sent`, `escalated`. It is append-only (reuse the audit trigger pattern, or write it through the audit service). This is the timeline source and the measurement source (PRD §14).
- `Handoff(issue, from_user, from_department, to_department, to_user nullable, reason, proposed_by, proposed_at, status ∈ {pending, accepted, rejected, withdrawn}, responded_by, responded_at, response_reason)`. At most one `pending` per issue (partial unique index).

**Services** (all use `select_for_update` on the issue)

- `route(issue)` picks the queue by rule, sets accountable to the queue head, writes `routed` and `assigned` events, and dispatches an alert to the head (urgent: immediately via out-of-app channels; normal: in-app).
- `acknowledge(issue, user)` is allowed only for the accountable user, the queue head, or the backup. It is idempotent: a second call is a no-op that does not create a second event. **Viewing an issue never acknowledges it.**
- `accept_ownership(issue, member)` is called by the queue head (or by the member, if the head offered it) and moves accountability to a named member.
- `propose_handoff(issue, actor, to_department, to_user?, reason)` requires a reason. Accountability **does not change**. The receiving queue's head (or `to_user`) gains read access through WP1's participant rule while the handoff is pending. It dispatches an alert to the receiver.
- `respond_handoff(handoff, actor, accept|reject, reason?)`. Only the receiving head, backup, or the named recipient can respond. Rejection requires a reason. Acceptance moves queue, responsible department, and accountable user (to the receiving head or named user) in one transaction, and resets the acknowledgement clock for the new owner.
- The reporter always keeps visibility (already covered by the reporter rule in WP1). The previous team's continued access is a **settings flag** `HANDOFF_PREVIOUS_TEAM_ACCESS ∈ {none, read}`, defaulting to `read`, until the PRD decision is made.

**API**

`POST /api/issues/report/`, `POST /api/issues/<id>/acknowledge/`, `POST /api/issues/<id>/accept-ownership/`, `POST /api/issues/<id>/handoffs/`, `POST /api/handoffs/<id>/respond/`, `GET /api/me/queue/` (what I'm accountable for, what awaits my acknowledgement, handoffs awaiting my response).

**Acceptance**

- [ ] Scenario 1: the response includes the ID and the queue name; an unknown product area goes to the fallback queue.
- [ ] Scenario 2 (first half): the Software head receives an alert; acknowledgement records actor and time; opening the issue does not acknowledge it.
- [ ] Scenario 3: a proposed Firmware handoff gives the Firmware head read access, keeps the Software owner accountable until acceptance, requires a reason to reject, and records every step as events.
- [ ] Two simultaneous handoff proposals on one issue produce one pending handoff and one clean error.
- [ ] The `routed` and `acknowledged` events give submission-to-routing and submission-to-acknowledgement times directly.

---

### WP6 — Deadlines, reminders, waiting, and escalation

**Depends on:** WP3, WP5. **Suggested agent:** Codex. **Size:** half to one day. **Blocked on decision:** targets (placeholders acceptable).

**Configuration (data, not code)**

`DeadlinePolicy(urgency, ack_target_minutes, ack_uses_working_hours, followup_interval_minutes, escalation_steps jsonb)`.

Pilot placeholders, to be replaced by the decision:

| Urgency | Ack target | Clock | Escalation steps |
| --- | --- | --- | --- |
| urgent | 30 min | wall clock | 0 min: head (in-app + out-of-app); 30 min: backup; 60 min: manager |
| normal | 4 working hours | working hours | at target: head reminder; +4 working hours: backup; +1 working day: manager |
| unknown | treat as normal | | |

Unaccepted handoffs use the normal policy, measured from `proposed_at`, escalating to the receiving head, then the manager.

**Periodic task** `issues.check_deadlines` (every minute)

- For each unacknowledged issue, compute elapsed time (working minutes or wall clock), find which escalation steps are due, and call `dispatch_alert` with `alert_key = f"ack:{issue.id}:{owner_epoch}:{step}"`. `owner_epoch` increments when ownership changes, so a new owner gets a fresh sequence, but a re-run never re-sends the same step. Write `reminder_sent` or `escalated` events once per step.
- The same for pending handoffs and for follow-ups on acknowledged but stale issues (no event for `followup_interval`).
- **Waiting:** `set_waiting(issue, reason, dependency_owner, next_followup_at)`. Reason and date are required, and `next_followup_at` has a maximum horizon (for example 14 days). While waiting, ordinary follow-ups pause, but on `next_followup_at` a reminder fires to the accountable user, and if it is ignored it escalates. Waiting never pauses escalation of an *unacknowledged* report.
- **Coverage gaps:** if a queue's head and backup are both inactive, or an alert has no deliverable channel for its recipient, raise a coverage-gap notice to the manager (deduplicated per day).

**Acceptance**

- [ ] Scenario 2 (second half): with frozen time, an unacknowledged urgent report alerts the head immediately, then the backup, then the manager. Running the periodic task ten times at the same instant sends each step once.
- [ ] A normal report submitted Friday at 17:30 IST reaches its 4-working-hour target on Monday at 13:30 (adjust for configured holidays).
- [ ] Acknowledging stops further acknowledgement escalations. Accepting a handoff starts a new sequence for the new owner.
- [ ] A waiting issue past `next_followup_at` reminds, then escalates.
- [ ] After-hours urgent alerts say who is on duty only if a duty contact is configured. Otherwise the alert reaches the head and the coverage gap is shown; nothing claims coverage that does not exist.

---

### WP7 — Status, resolution, verification, and reopening

**Depends on:** WP5. **Suggested agent:** Claude Code. **Size:** half a day. Much of this exists (the August E2E covered independent verification); adapt it rather than rebuilding.

**Steps**

- Status: `open → investigating → resolved → verified → closed`. Transitions go through a service with an allow-list (same pattern as `fc/lifecycle.py`). Acknowledgement and pending handoff stay separate attributes.
- Notes are append-only and typed: `observation`, `suspected_cause`, `confirmed_cause`, `workaround`, `permanent_fix`, `general`. Edits create a new note that references the old one; the original is kept.
- `Resolution(issue, resolved_by, at, change_summary, workaround, evidence links, affected_versions, affected_units, unresolved_risks, root_cause_status ∈ {confirmed, suspected, unknown, mitigated_only})`. **Do not require a confirmed root cause.**
- `Verification(resolution, verifier, at, what_tested, evidence, result ∈ {pass, fail}, notes)`. The service rejects `verifier == resolution.resolved_by`. It also rejects anyone who co-authored the resolution, if co-authorship exists. A fail returns the issue to `investigating` and keeps the resolution row.
- Assigning a verifier adds an `IssueParticipant(role=verifier)`, which gives them read access through WP1.
- Reopen: `reopen(issue, actor, reason)` returns to `investigating`. Authority is a settings placeholder (`REOPEN_ALLOWED = {accountable, queue_head, any_head, manager}`) until the decision. Prior resolutions and verifications are kept.
- Knowledge promotion: `promote_to_knowledge(issue, author, audience, redacted_summary)` creates an article. Occurrence links are filtered per reader (WP1).

**Acceptance**

- [ ] Scenario 7: resolving does not verify; the resolver cannot verify (API and service both reject); a failed verification returns the issue to investigating with history intact.
- [ ] Resolving with `root_cause_status=unknown` is allowed.
- [ ] Reopening after verification keeps the earlier resolution and verification visible in the timeline.

---

### WP8 — FC workflow preservation and configuration evidence

**Depends on:** WP1, WP4. **Suggested agent:** Codex. **Size:** one day. **Read first:** the WP0 inventory list of untracked parameter files.

**Steps**

1. **Integrate the preserved parameter work deliberately.** Diff the preservation branch's parameter files against `main` and bring them in as a separate first commit in this WP, unchanged, so review can tell "existing work" from "new changes". Then adapt them.
2. Models (`fc`):
   - `ParameterFile(sha256 unique, original_name, size, storage_ref, uploaded_by, uploaded_at)`. Raw bytes are stored once (private storage, same download rule as attachments).
   - `ParsedParameters(file, parser_version, values jsonb, warnings jsonb)`.
   - `ConfigEvidence(kind ∈ {approved_baseline, flashed_record, readback}, file, fc nullable, unit_identity_confidence ∈ {confirmed, probable, unknown}, firmware_version, firmware_build, gcs_version, hardware_revision, deployment nullable, captured_at, recorded_by, tool, source_note, supersedes nullable)`.
   - Baseline-only fields (or a `BaselineApproval` side table): `revision`, `approved_by`, `approved_at`, `compatibility`, `scope`. A baseline must be approved by an authenticated action, not a typed name, using the same pattern as WP11.
   - `IssueEvidenceLink(issue, evidence, linked_by, linked_at)`.
   - `ParameterComparison(left_evidence, right_evidence, tolerance jsonb, result jsonb, created_by, created_at, parser_versions)`. The result records differences only. **No `safe` or `unsafe` field.**
3. **No overwrite:** new evidence for the same unit and kind references the previous one through `supersedes`. The "current" value is the latest non-superseded row, and the UI always shows `captured_at` next to any value.
4. **Version-at-time:** the issue view shows versions from evidence linked to the issue, or from the evidence nearest before `occurred_at_approx`, labelled with its capture time, never the FC's latest version silently.
5. Readback in the pilot is an upload with `tool` set (for example "Mission Planner export"). Diagnostics-tab read-back is out of scope (PRD §4).
6. Existing lifecycle: no rule changes. Add `IssueUnitLink` display on the FC detail page, and an FC timeline entry for linked issues, filtered by issue scope.

**Acceptance**

- [ ] Scenario 4: a baseline, a flashed record, and a readback for the same unit are stored as distinct kinds with their original files retrievable byte-for-byte (hash matches), and can be compared. The comparison shows differences and parser warnings, with no safety verdict.
- [ ] Evidence with an unknown unit can be created and later associated, with the association recorded.
- [ ] Uploading the same file twice stores the bytes once.
- [ ] Scenario 8: the full existing FC lifecycle and rework test set passes unchanged.

---

### WP9 — Customers and deployments (minimal)

**Depends on:** WP1. **Suggested agent:** Codex. **Size:** a few hours.

- `Customer(name, region, notes)`: broadly visible engineering summary.
- `CustomerContact(customer, name, phone, email, role)`: **restricted.** Visible only with `can_view_customer_contacts`. A separate serializer and endpoint; never nested in issue responses.
- `Deployment(customer, site_name, units (M2M FC), gcs_version_at_handover, notes, deployed_at)`.
- `Issue.customer` and `Issue.deployment` are nullable and settable after submission.
- Access: customer and deployment summaries follow FC visibility. Contacts follow the capability only.

**Acceptance**

- [ ] An issue linked to a customer never includes contact fields for a user without the capability, through the issue detail, search, or any nested response.
- [ ] Sharing an issue cross-team does not expose contacts.

---

### WP10 — Tasks and daily progress (minimal)

**Depends on:** WP1. **Suggested agent:** Claude Code. **Size:** half a day.

- `Task(title, accountable_user, department, priority, due_date, status ∈ {planned, in_progress, blocked, done, cancelled}, links to issue/release/fc nullable)` and `TaskCollaborator`.
- `DailyUpdate(task nullable, author, date, progress, next_step, blockers, created_at)`. New rows only; editing the same day's update creates a revision row (or edits are allowed only on the same day, with history kept). Record which approach was chosen.
- Scope: `visible_tasks(user)` covers own and collaborative tasks, tasks in departments the user heads, all tasks for any head and the manager. Ordinary teammates do **not** see each other's tasks by default (PRD §3); this is a settings flag until decided.
- Head view, `GET /api/progress/?department=`: assigned work, who has no update today, overdue, blocked, next steps. **No activity-count metrics or rankings.**

**Acceptance**

- [ ] Scenario 11: a blocker and a dated update appear in the head view; yesterday's update is unchanged after today's update.
- [ ] `sw_member` cannot see another Software member's task unless they are a collaborator.

---

### WP11 — Releases with dual authenticated approval

**Depends on:** WP1. **Suggested agent:** Claude Code. **Size:** one day. **Read first:** WP0 notes on where release models live.

**Models (`releases`)**

- `Release(product='GCS', version, created_by, created_at, legacy bool)`.
- `ReleaseRevision(release, number, source_ref (commit SHA or tag, required), artifact_ref, artifact_sha256, internal_notes, recipient_notes, compatibility, known_limitations, content_hash, created_by, created_at)`. **Revisions are immutable.** Editing creates revision N+1. `content_hash` is computed over the approval-relevant fields.
- `ReleaseApproval(revision, role ∈ {software_head, manager}, actor, decision ∈ {approve, reject}, comment, at)`, unique on `(revision, role)`.
- A revision is **approved** when it has an `approve` for both roles from two **distinct** users who held the corresponding capability at the time of the decision. "Current approved revision" is computed, never stored as a flag that could drift.
- Rejection requires a comment. The release then needs a new revision.

**Legacy data:** migrate existing release rows to `Release(legacy=True)` with one revision. Existing named-approver text goes into `internal_notes` as "Legacy approver field: …". **No `ReleaseApproval` rows are created from legacy data**, so legacy releases are never shown as dual-approved (PRD §8.1).

**Services**

- `approve(revision, actor, role, comment)`: `select_for_update` on the release; verify the actor holds the role's capability; verify the revision is the latest; reject if the same user already approved this revision in the other role.
- Drafting a revision requires `can_draft_release`. Approval does not.

**Acceptance**

- [ ] Scenario 9: one approval does not approve; two approvals by the same person (in both roles) are rejected; an edit after both approvals produces a new unapproved revision, and announcement is blocked until it is re-approved.
- [ ] Legacy releases show "legacy — not approved under current process".
- [ ] An administrator without the capability cannot approve.

---

### WP12 — Recipient source (signup API adapter)

**Depends on:** WP11. **Suggested agent:** Codex. **Size:** a few hours (synthetic), more once the contract arrives.

- `RecipientSource` interface with `fetch_eligible(segment) -> RecipientFetch(source, fetched_at, recipients[], errors[])`.
- `SyntheticRecipientSource`: returns clearly fake addresses at `example.invalid` and labels every result `SYNTHETIC`. It is the **only** source enabled until the contract is approved (feature flag `SIGNUP_API_ENABLED=false`).
- `SignupApiRecipientSource`: implemented only once the contract is in hand. Credentials come from env, never from the frontend. Every field is validated (email syntax, stable ID, active/opt-out flags). Pagination and rate limits follow the contract. **Any error returns a visible failure; no fallback to "all known addresses".**
- `RecipientSnapshot(source, segment, fetched_at, fetched_by, recipients jsonb, count)` is the frozen list a campaign is built from.
- Contact data visibility: snapshots are visible only to users with `can_send_announcements` or `can_view_customer_contacts`.

**Acceptance**

- [ ] With the API disabled, only synthetic recipients are available, and the UI and every campaign record say so.
- [ ] A simulated API failure produces an error state, not an empty or partial list that looks complete.

---

### WP13 — Announcement campaigns: preview, send, history

**Depends on:** WP3, WP11, WP12. **Suggested agent:** Claude Code. **Size:** one day.

**Models**

- `Campaign(release_revision, subject, body_text, body_html, snapshot, created_by, created_at, idempotency_key unique, status ∈ {draft, queued, sending, completed, completed_with_failures}, sent_by, sent_at, resend_of nullable, resend_reason)`.
- `CampaignDelivery(campaign, recipient_id, email, status ∈ {queued, accepted, failed, unknown}, attempts, provider_ref, last_error, updated_at)`, unique `(campaign, recipient_id)`.

**Flow**

1. **Preview:** `POST /api/campaigns/preview/` with release revision, segment, and template. It renders the exact subject and body from `recipient_notes` **only** (internal notes are never available to the template context) and returns the recipient count and list. No side effects except storing a draft.
2. **Send:** `POST /api/campaigns/<id>/send/` with a client-generated idempotency key. The service, under lock: checks `can_send_announcements`; checks the revision is still the current approved revision; checks the snapshot is not stale (age limit in settings); sets `queued`; creates delivery rows; enqueues one job per delivery on commit. A repeated send with the same key returns the same campaign. A second send of a completed campaign is refused unless it is an explicit resend with a reason, which creates a new linked campaign.
3. **Delivery job:** one message per recipient (no shared To/CC). Before calling the provider, the handler checks the delivery is still `queued` (idempotency under retries). Outcomes: provider accepts → `accepted`; provider rejects with a definite error → `failed`; timeout or ambiguous → `unknown`.
4. **Retry:** an explicit action retries only `failed`. `unknown` requires reconciliation first (check the provider log where supported, or mark "confirmed not sent" by an authorised user) before it can be retried.
5. In development, the email backend is console or file. The pilot uses synthetic recipients, so nothing reaches a real inbox.

**Acceptance**

- [ ] Scenario 10: preview shows the exact message and count; double-clicking Send (two concurrent requests, same key) creates one campaign; failed and unknown deliveries are listed; retrying only touches `failed` rows.
- [ ] Internal notes never appear in rendered output (test with a sentinel string in internal notes).
- [ ] Editing the release after approval blocks sending the existing draft.

---

### WP14 — Mobile-first flows and end-to-end tests

**Depends on:** the WPs it exercises; start the quick-report screen after WP5. **Suggested agent:** Codex for UI, Claude Code for the E2E suite. **Size:** one day, spread over Days 2–4.

**Screens (React)**

- **Quick report:** three required fields on top, optional sections collapsed, camera/file input (`accept="image/*,.log,.txt,.param,.parm,.bin"`, `capture` for photos), per-file upload progress. On success, a confirmation page shows the ID and queue. On network loss, the form state stays on screen with a clear "Not submitted — retry" state. There is no silent offline queue (PRD §10).
- **My queue:** items awaiting acknowledgement, items I own, handoffs awaiting me, each with an obvious Acknowledge / Accept / Reject action.
- **Issue detail:** timeline from `IssueEvent`, notes by type, evidence, handoff panel, resolution and verification panel.
- **Daily update:** one screen, defaulting to today, with task picker and blocker toggle.
- **Releases:** revision view, approval buttons (shown only to capability holders), campaign preview and send, and delivery table.
- **Head progress view** and **admin health** (worker heartbeat, dead jobs, failed alerts).

**E2E (Playwright, extending `e2e/ui_walkthrough.py` or replacing it)**

One test per acceptance scenario 1–13, run at desktop and at a 390×844 viewport for scenarios 1, 2, 11, and 12. Scenario 12's network failure is simulated with Playwright route interception. Scenario 6 runs the access matrix through the UI for at least the issue list, direct URL, and search.

**Acceptance**

- [ ] All 13 scenarios pass in the E2E suite, or the worklog lists each failing one with the reason and the WP that owns it.
- [ ] No console errors on any page during the suite.

---

### WP15 — Shared-use readiness (after approval)

**Depends on:** the pilot review and the approval of hosting and database. **Suggested agent:** either, with a human doing provider setup. Not part of the four days.

1. **Database:** provision the approved paid PostgreSQL in an India-adjacent region. Run `dbcheck --deep` against it. Confirm the backup schedule and point-in-time recovery.
2. **Hosting:** two always-on processes (web: `gunicorn`; worker: `run_worker`) and one HTTPS origin. No sleeping tiers (PRD §10.1).
3. **Storage:** private object storage for attachments and parameter files. Switch the download view to short-lived signed URLs. Migrate any pilot files.
4. **Email:** the approved transactional provider, with SPF, DKIM, and DMARC on the approved sending domain. Bounce webhooks if the provider supports them (feeds `CampaignDelivery` and `AlertDelivery`).
5. **Monitoring:** error tracking, an uptime check, a worker heartbeat check (alerts if stale), and a dead-job and failed-alert count check.
6. **Restore exercise:** restore the database and storage into a scratch environment, run `dbcheck --deep` and a smoke test, and record the time taken in `docs/RESTORE_LOG.md`.
7. **Accounts:** real users created by an administrator, no seeded credentials, admin restricted, deactivation tested.
8. **Release process:** a migration and rollback runbook, a dependency review (`pip-audit`, `npm audit`), and upload limits set.
9. Complete the "before wider rollout" column of PRD §12.1: timelines, audit views, exports (or disable them), parameter comparison inputs.

---

## 6. Testing strategy (cross-cutting)

| Layer | What | Where |
| --- | --- | --- |
| Policy | Actor × surface matrix from the WP1 fixture. Every new surface adds rows | `access/tests/` |
| Coverage | The route-coverage meta-test fails on any unscoped endpoint | `access/tests/test_route_coverage.py` |
| Services | Each service's validation, events written, and audit written | per app |
| Concurrency | Handoff proposals, approvals, campaign sends, job claiming. Use `TransactionTestCase` with threads and a barrier | per app, tagged `concurrency` |
| Time | Deadlines and calendar with `time-machine` | `issues/tests/test_deadlines.py`, `core/tests/test_calendar.py` |
| Regression | The existing FC lifecycle and rework tests run unchanged in every PR | existing |
| E2E | Scenarios 1–13 | `e2e/` |

Test database: local PostgreSQL only (the `db.py` guard already refuses a remote primary). CI runs on GitHub Actions with a PostgreSQL 16 service container: backend tests, frontend build, diagnostics tests, and E2E on the main branch.

---

## 7. Risks and how this plan handles them

| Risk | Mitigation |
| --- | --- |
| A later endpoint bypasses access | The route-coverage meta-test fails the build |
| Two agents produce conflicting conventions | `AGENTS.md`, worklogs, and cross-review by the other agent on every PR |
| Untracked parameter work is lost or silently rewritten | The preservation branch in WP0; integration as an unchanged first commit in WP8 |
| Escalations stop silently in production | Always-on worker, heartbeat, external monitor (WP3, WP15) |
| Duplicate alerts or emails under retries | Unique delivery keys plus a status check before each provider call |
| Real customers emailed during the pilot | Synthetic source only; the API is feature-flagged off until the contract is approved |
| Day 2 blocked by missing decisions | Placeholders are configuration data, so real values replace them without code changes |
| The four days overrun | The cut line in Section 4; the never-cut list protects access, ownership, verification, and approval |

---

## Appendix A — Pilot placeholder configuration

Loaded by `python manage.py seed_pilot_config` (development and staging only). Every value is labelled as a placeholder in the admin UI until replaced.

- Departments and queues: Software, Firmware, Service, Assembly, plus Fallback.
- Heads, backups, coordinator: test users from the access matrix.
- Working hours: Monday–Saturday or Monday–Friday (decision), 10:00–18:00 `Asia/Kolkata`, no holidays.
- Deadline policies: as in WP6.
- Feature flags: `SIGNUP_API_ENABLED=false`, `ALERT_CHANNELS=["in_app","email"]`, `HANDOFF_PREVIOUS_TEAM_ACCESS="read"`, `TEAM_TASK_VISIBILITY="own_and_collab"`.

## Appendix B — Worklog template (`docs/worklog/WP<nn>.md`)

```markdown
# WP<nn> — <title>
Agent: Codex | Claude Code    Branch: wp/<nn>-<slug>    Date:

## Done
- (what changed, with file paths)

## Acceptance
| Item | Evidence (test name or manual check) | Result |
|---|---|---|

## Commands run and results
(verbatim summary: test counts, failures, build output)

## Not done / deviations from plan
## Decisions taken in this session (and why)
## Follow-ups (out of scope, noticed)
## Placeholders introduced
```
