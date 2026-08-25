# Implementation Notes

Decisions, assumptions and gaps.
Status: **P0 complete, P1 complete, P2 partially complete. Database moved to
shared Supabase PostgreSQL (pass 2).**

---

## 0. Pass 2 — Python version and Supabase migration

### The Python failure was an environment problem, not a code problem

`pip install -r requirements.txt` failed because the local interpreter was older
than 3.10. Four of the seven dependencies declare `Requires-Python >= 3.10`
(Django 5.2.17, DRF 3.18.0, django-filter 26.1, python-dotenv 1.2.2), so the
floor is **Python 3.10; 3.12 is recommended**. Django was deliberately *not*
downgraded — Django 4.2 would have meant losing `CONN_HEALTH_CHECKS`, the
current `STORAGES` API and five years of security support, to work around a
locally-installed interpreter.

Two guards now make this diagnosable in one second instead of via a stack trace:

- `manage.py` checks `sys.version_info` **before importing anything**, so an
  unsupported interpreter produces an explanatory message with the exact venv
  commands rather than a `SyntaxError` from inside a dependency.
- `config/settings.py` raises the same check for WSGI/ASGI entry points.

The most common trap after upgrading is a stale `.venv` still bound to the old
interpreter. It must be deleted and recreated, not reused — README says so
explicitly.

### Database configuration

All database settings now flow through `config/db.py`, which accepts **either**
`DATABASE_URL` **or** the original `POSTGRES_*` variables (URL wins). There is
one code path, not two competing systems, and no dependency was added — the URL
parser is ~40 lines of `urllib.parse` rather than another package to install on
a machine where `pip install` had already failed once.

It handles the things that actually break against Supabase:

| Concern | Handling |
|---|---|
| Percent-encoded passwords | Decoded. Supabase passwords routinely contain `@`, `:` and `/`, which are URL-significant. |
| TLS | `sslmode=require` by default for any non-local host, `disable` for localhost. Explicit `DB_SSLMODE` or an `?sslmode=` query parameter always wins. |
| **Transaction pooler (port 6543)** | Detected by port. `CONN_MAX_AGE` forced to 0 and `DISABLE_SERVER_SIDE_CURSORS` turned on, because PgBouncer in transaction mode returns the connection to the pool between statements. Without this, Django silently breaks on large querysets. |
| Session pooler (port 5432) | The recommended target. Full session semantics, IPv4-reachable. |
| Direct connection | Identified and documented as IPv6-only, which is why it fails on most Windows networks. |
| Visibility | `application_name=fcops-django` so connections are identifiable in Supabase's dashboard and `pg_stat_activity`. |

### The test-database guard

The suite creates, populates and drops a database. Pointed at the shared
Supabase instance that would be destructive, and the failure mode is silent and
catastrophic. `get_databases(is_test_run=True)` therefore **refuses a remote
primary**: it uses `TEST_DATABASE_URL` if set, otherwise falls back to local
PostgreSQL, and only targets a remote database if `ALLOW_TESTS_ON_REMOTE_DB` is
explicitly enabled. Four tests cover this, including one asserting that a remote
`DATABASE_URL` never reaches the test runner.

### Credential hygiene

`safe_description()` produces a password-free view of the connection, and it is
the only thing `dbcheck` and `settings.DATABASE_DESCRIPTION` expose. A test
asserts the description's keys are exactly the allow-listed non-secret set, so a
future edit cannot quietly add the password to something that gets logged.
`.gitignore` excludes `.env` and `.env.*` while keeping `.env.example`.

### `dbcheck`

`python manage.py dbcheck [--deep]` verifies connectivity, server version,
`plpgsql`, `tsvector`/`websearch_to_tsquery`, GIN support, `jsonb`, the audit
table, the append-only trigger and both search indexes; `--deep` additionally
runs a real full-text query and confirms the audit log rejects raw `UPDATE` and
`DELETE`. This is the one command to run after pointing the project at a new
database.

### Confirmed against the live Supabase instance

`dbcheck` → `migrate` → `seed` → `dbcheck --deep` all completed against the
project's Supabase database (**PostgreSQL 17.6**, session pooler,
`ap-southeast-2`, TLS on). Every capability and schema check passed: `plpgsql`,
`tsvector`/`websearch_to_tsquery`, GIN, `jsonb`, the audit table, the
append-only trigger and both search indexes. All 25 migrations applied cleanly,
including the raw-SQL trigger migration. Reference data (10 departments, 12
users, 2 FC models) is seeded; demo data was deliberately not loaded.

Note the connection reached Supabase over **IPv6** — which is why the session
pooler matters: it accepts both, whereas the direct `db.<ref>.supabase.co` host
accepts only IPv6.

### Connection-pool exhaustion, and a credential leak found alongside it

Clicking through the UI against Supabase produced
`FATAL: (EMAXCONNSESSION) max clients reached in session mode - pool_size: 15`.

Cause: `runserver` creates a new thread per request and each thread opens its
own connection. With `CONN_MAX_AGE=60` those persisted, and the FC detail page
fires four parallel requests, so a few minutes of use exhausted the pooler's
15-client budget. Django's own docs warn that persistent connections do not
suit the dev server's threading model; against a local PostgreSQL it is
harmless, against a capped remote pooler it is fatal.

Fixes:

- **`CONN_MAX_AGE` now defaults to 0 for any remote host** (60 stays for
  localhost). Safe by default, no configuration required.
- **`MIGRATION_DATABASE_URL`** lets normal traffic use the transaction pooler
  (port 6543, far more headroom) while `migrate`/`makemigrations`/`dbcheck`
  automatically take the session pooler, which is the only one that can run DDL.
- **Pool exhaustion now returns a 503** with instructions instead of a 500
  carrying a raw psycopg2 string.
- **`dbcheck` reports how many connections the app is holding**, so the
  condition is visible before it becomes an outage.
- Documented running under **waitress with a bounded thread pool**, which is
  the way to get persistent connections back safely.

**The more serious finding was in the error page itself.** Django's debug view
prints traceback locals, and a failed `psycopg2.connect` frame holds
`conn_params` and a `dsn` string containing the database password in clear
text. `SafeExceptionReporterFilter` masks *settings* but not frame locals, so
any DEBUG error page exposed the production database password to whoever could
reach the server — and the dev server is often bound to `0.0.0.0`.

`config/error_filter.py` now redacts the live password, any `password=` in a
libpq DSN, and any `user:password@` in a URL, from frame locals and settings
alike. Verified by rendering a real 128 KB debug page from a genuine psycopg2
failure and asserting the password appears nowhere in it; the DSN renders as
`password=***REDACTED***`. Six tests cover it.

This is defence in depth, not permission to run DEBUG on a reachable
interface. **`DJANGO_DEBUG=False` whenever anyone else can reach the server**,
and the password that was exposed should be rotated.

### A real bug that only Windows could surface

The first full test run on Windows failed one test:
`issue.reassignments.last()` returned the *initial* assignment instead of the
most recent reassignment. It had passed on Linux every time.

Cause: `IssueInvestigationNote` and `IssueReassignmentLog` ordered on
`created_at` alone. `auto_now_add` takes its value from Python, and
`datetime.now()` on Windows has roughly 15 ms granularity where Linux has
microseconds. Two rows written inside the same tick therefore shared a
timestamp, leaving their order undefined.

This was a product defect, not a test artefact: the investigation log and the
reassignment history are append-only evidence, and an audit trail that can
render out of sequence undermines the thing the system exists to provide.
`FCEvent` and `AuditLogEntry` already tie-broke on the primary key; these two
did not. Both now order on `("created_at", "id")`
(migration `issues.0002`, state-only — it emits no SQL).

A regression test forces every row in an issue to share one timestamp and
asserts insertion order survives. It was verified to fail with the fix reverted,
reproducing the original signature exactly.

### The test-run guard fired in practice

The first `python manage.py test` on the developer machine failed with
`connection to 127.0.0.1:5432 refused`. That was the guard working: it refused
to let the suite CREATE and DROP a database on the shared Supabase instance and
redirected to local PostgreSQL, which was not installed.

The behaviour was right but the diagnosis was a raw psycopg2 traceback, which
reads like a misconfiguration. `config/test_runner.py` now announces the
redirect up front, and on failure prints which host was tried, why, and the
three ways to fix it. The fallback also now reuses the `POSTGRES_*` variables
when they describe a local server, so a developer with local PostgreSQL under
their own credentials does not additionally have to set `TEST_DATABASE_URL`.

Running the suite therefore requires a local PostgreSQL (or a separate
disposable database). That is a deliberate cost: the alternative is a test run
that can silently destroy shared production data.

## 1. Architectural decisions

| Decision | Rationale |
|---|---|
| Django 5 + DRF + PostgreSQL + React (Vite), modular monolith | PRD §38 recommends reusing the team's existing stack. One deployable, one transaction boundary, foreign-key integrity for a workflow system. |
| Four apps (`core`, `accounts`, `fc`, `issues`) | Clean seams for later extraction if ever needed, without microservice overhead now. |
| **All state changes go through service functions**, never through serializers | `fc/services.py` and `issues/services.py` are the only places that mutate lifecycle/issue state. This is what makes audit logging and validation impossible to bypass by adding a new endpoint. |
| JWT auth with silent refresh | No SSO provider was available. The permission model is independent of the auth mechanism, so SSO can replace this later. |
| Audit log protected by a **database trigger**, not just Python | PRD §30 requires the log be tamper-evident with no delete permission "for any role including admin". `core/migrations/0003_audit_append_only.py` installs a trigger that raises on any UPDATE or DELETE. A test verifies raw SQL is refused. |
| Denormalised `FCEvent` timeline table | The FC history page is the most-used read in the product. Assembling it from six tables per request would be slow and fragile; events are written by the same services that write the records. |
| FC `status` is **derived**, never hand-edited | `recompute_status()` runs after every relevant write: any open issue ⇒ `BLOCKED`; otherwise the status follows the stage. Removes a whole class of "status says one thing, reality says another" bugs. |

## 2. Assumptions made (PRD §36 open questions)

These were answered with the most defensible engineering reading of the PRD.
Each is cheap to change — they are data/config, not structure.

1. **Allowed rework routes** (`fc/lifecycle.py: ALLOWED_REWORK_TARGETS`) —
   the PRD asks for an explicit allow-list but says the actual routes must be
   confirmed with Hardware/Firmware/Testing leads. Assumed: a QC failure returns
   to Manual or Machine Assembly; Firmware/Sensor failures may return to
   Firmware, QC or assembly; Bench/Ground/Final failures may return to Firmware,
   Mechanical Assembly, QC or assembly. **Confirm with the leads.**
2. **Bench Testing gates Ground Testing.** They are modelled as sequential
   stages because the PRD's canonical sequence lists them in order. If they are
   genuinely parallel, this needs a workflow change (they already have separate
   records, so no schema change).
3. **Downstream re-runs after late rework are not forced.** The PRD flags this
   as open (§16, §36). Rework returns the FC to the chosen stage and it walks
   forward normally, re-running everything after that point. It does *not*
   selectively force a subset of downstream stages.
4. **Manual and machine assembly are separate stages** with separate records, so
   defects are separately attributable (PRD §40 explicitly asks for this).
5. **A stage cannot be passed while an issue discovered at that stage is open.**
   Not stated explicitly, but implied by "the FC is BLOCKED until the issue is
   resolved" (§8).
6. **Resolving an issue never auto-passes a stage.** The stage must be re-run
   and explicitly marked passed (§8).
7. **Verification requires a different person than the resolver**, and requires
   Test Engineer / Department Lead / Manager role (§17). Toggle:
   `REQUIRE_INDEPENDENT_VERIFICATION`.
8. **Approval rules** (§17): unresolved issues of any severity block approval;
   *resolved-but-unverified* issues block approval if Blocker/Major, and produce
   a warning requiring a mandatory written justification if Minor/Cosmetic;
   closed issues never block.
9. **Known Issue promotion is role-gated to Department Lead and above.** The PRD
   asks whether cross-department sign-off should be required (§36); it is not,
   for now — promotion is fully audited and reversible.
10. **Severity/category taxonomies are fixed enterprise-wide** (enums), not
    department-configurable. Departments and FC models *are* configurable rows.
11. **Reassignment permission**: department leads, managers/admins, or a member
    of the currently-assigned department. Managers use the same reassignment-log
    mechanism as everyone else (§36) — no silent unilateral move.
12. **Serial format** `FC-YYYY-NNNNN`, issue keys `ISS-YYYY-NNNNN`, both
    allocated per calendar year.
13. **Issue status set** simplified per §9: `OPEN → INVESTIGATING → RESOLVED →
    VERIFIED → CLOSED`, with `WAITING` as a flag and `KNOWN_ISSUE` as a link,
    not statuses. Reopening a closed issue is a manager action requiring a reason.

## 3. Similar-issue ranking (PRD §21)

`issues/search.py: find_similar()` scores candidates as:

```
score = postgres ts_rank(weighted tsvector, websearch query)
      + 0.35 firmware_version match      + 0.30 hardware_revision match
      + 0.25 discovered_stage match      + 0.20 category match
      + 0.20 gcs_version / configurator_version match
      + 0.15 parameter_profile match
      + 0.25 if the issue is resolved/verified/closed
      + 0.30 if it is linked to a Known Issue
```

Title and symptoms are weight A; root cause and resolution weight B;
description weight C. `websearch_to_tsquery` is used so arbitrary operator
characters in user input can never produce a query syntax error (there is a test
for that). If the text query returns nothing, it falls back to structured-field
matching alone, so terse symptom text still yields useful results. Matching
Known Issues are returned as a separate list and shown above raw issues.

## 4. Deviations from the PRD

- **Rework is auto-completed from the FC detail UI.** The API models
  create-then-complete as two steps (`POST /rework-records/` then
  `…/complete/`), but the shop-floor form does both in one submit, because a
  technician recording rework they have already performed does not benefit from
  a second click. The two-step API remains available for a future "rework in
  progress" workflow.
- **`WAITING` is a boolean flag with a reason**, not a status — as the PRD
  recommends over the source material's status list.
- **Attachments (P2) are implemented** end to end (`/api/issue-attachments/`
  plus an upload control on the Issue detail page) but store to the local
  filesystem; S3 is not wired up (see below).
- **Acceptance criterion "10 lifecycle stages"** (§37) — implemented as the
  11 stages listed in §7, which is what the rest of the PRD specifies.

## 5. Missing credentials / external services

Nothing blocks local development. The following are placeholders in
`.env.example` and need real values before a shared deployment:

| Item | Status | Needed for |
|---|---|---|
| **Supabase `DATABASE_URL`** | **done** — connected, migrated and seeded (PostgreSQL 17.6, session pooler, ap-southeast-2). | — |
| Local PostgreSQL on each developer machine | **needed to run the test suite** | The suite creates and drops a database, so it is kept off the shared instance. See README → Running the tests. |
| `DJANGO_SECRET_KEY` | dev placeholder | Any shared environment. Generate with `python -c "import secrets; print(secrets.token_urlsafe(50))"`. |
| Object storage credentials | **deliberately not configured** | Attachments stay on the local filesystem for now, by decision. No AWS. Supabase Storage or another provider is a later change; the `FileField` abstraction is unchanged so it stays a settings-level swap. |
| Internal identity provider (SSO) details | **unknown — PRD §36 open question** | Replacing the local user directory. Until then, users are managed in the Admin console. |
| SMTP / email provider | not needed for MVP | Email notifications are explicitly deferred (§20). |

## 6. Known limitations

- **Attachments are stored on local disk**, per the current decision. Each
  developer's machine therefore holds its own attachments even though the
  database is shared — an attachment uploaded on one machine will 404 on
  another. This is acceptable while the team is small and the database is the
  thing that matters, but it is the first thing to fix when attachments start
  being used in earnest.
- **Test runs need a local PostgreSQL** (or a second Supabase project), by
  design — see the test-database guard above.
- **Notifications are polled** (30 s interval) rather than pushed. Fine at this
  scale; WebSockets/SSE would be the upgrade.
- **No per-FC-model workflow variants.** Checklist templates can already be
  scoped per FC model; the *stage sequence* is currently global (Phase 2 item).
- **Search is English-config only.** `tsvector` uses the `english` dictionary.
- **Dashboard aggregates are computed per request** without caching. At current
  volumes this is well under 100 ms; it will need materialising if FC counts
  reach tens of thousands.
- **`search_vector` is maintained by explicit `reindex_issue()` calls** in the
  services, not by a database trigger. Any future write path that bypasses the
  services would leave the index stale. A trigger is the more robust long-term
  answer.
- **Closed issues are admin-editable** via `PUT /api/issues/{id}/` (audited), per
  PRD §8's "admin-level correction with an audit trail entry". There is no UI
  for this.
- **Test suite is slow** (~1–3 min for 77 tests) because each test class rebuilds
  GIN indexes. `--keepdb` helps locally.

## 7. Remaining work, in priority order

1. Rotate the Supabase database password (it was exposed on a debug page and
   in a chat transcript), then re-verify with `dbcheck`.
2. Confirm the §36 workflow questions with the Hardware/Firmware/Testing leads
   and adjust `ALLOWED_REWORK_TARGETS` — this is the highest-value unblocking
   conversation, and it is a one-file change.
3. Shared attachment storage (Supabase Storage is the natural fit given the
   database already lives there), once attachments matter.
3. Frontend tests (none exist; backend coverage is good). Playwright smoke tests
   were run manually against the live app during this pass.
4. Pagination controls in the UI list views (the API paginates; the UI currently
   requests large pages).
5. SSO integration once the identity provider question is answered.
6. Phase 2: QR codes, deeper analytics, live firmware/GCS/Configurator version
   capture, per-model workflow variants.
