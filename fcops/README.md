# FC Production, Traceability & Engineering Knowledge System

An internal web application that gives every in-house-manufactured flight
controller a complete digital history: where it is in the production lifecycle,
what went wrong, who investigated it, what the root cause actually was, how it
was fixed, whether the fix was verified — and whether the same problem has
happened before.

It is deliberately **not** a generic issue tracker. Every issue is anchored to a
specific FC, a specific lifecycle stage, and keeps *where a problem was
discovered* separate from *where it originated*.

---

## Architecture

A **modular monolith**: one Django project, four cohesive apps, one PostgreSQL
database, one React SPA.

```
backend/
  config/        Django project settings, URL routing
  core/          Cross-cutting: append-only audit log, notifications,
                 actor middleware, dashboard aggregate, error handling
  accounts/      Users, Departments, Roles, server-side RBAC permissions
  fc/            FlightController, lifecycle state machine, StageRecord,
                 ReworkRecord, FirmwareRecord, TestResult, ChecklistTemplate,
                 SoftwareVersion, FCEvent (timeline)
  issues/        Issue, investigation notes, reassignment log, KnownIssue,
                 PostgreSQL full-text search + similar-issue ranking
  tests/         46 tests covering lifecycle, issues, search, RBAC, audit
frontend/
  src/pages/     Login, Dashboard, FC list/create/detail, Issue list/create/
                 detail, Known Issues, Knowledge Search, Audit Log, Admin
  src/lib/       API client (JWT + silent refresh), auth context
```

### Why this stack

| Concern | Choice | Reason |
|---|---|---|
| Backend | Django 5 + DRF | The PRD (§38) notes the team already runs Django + React + PostgreSQL. Django's ORM, migrations, admin and auth remove most of the plumbing for a strongly relational, audited workflow app. |
| Database | PostgreSQL (Supabase-hosted) | The data is inherently relational (FC → stages → issues → departments) and needs transactional integrity for workflow changes. Also gives us full-text search for free. Supabase is used purely as managed PostgreSQL — no Supabase Auth, no RLS, no PostgREST. |
| Search | Postgres `tsvector` + GIN | Sufficient for v1 volume; no separate search cluster to run. |
| Auth | JWT (SimpleJWT) + Django auth | No internal identity provider was available (see IMPLEMENTATION_NOTES). SSO can be layered in later without touching the permission model. |
| Frontend | React 19 + Vite + React Router | Fast dev loop, no build ceremony. Plain CSS with design tokens — desktop-first, tablet-friendly. |
| Structure | Modular monolith | One deployable, one transaction boundary. Microservices would add operational cost with no benefit at this scale. |

### The three ideas the design rests on

1. **The FC is the central entity.** Stage records, firmware records, test
   results, issues, rework and audit entries all hang off one FC.
2. **History is append-only.** A stage re-run creates a *new* attempt; a
   correction creates a *new linked record*. Passed-and-signed stage records are
   immutable. Investigation notes and audit entries cannot be edited or deleted —
   the audit table is protected by a database trigger, not just application code.
3. **Discovery ≠ root cause.** An issue records the stage/department/person that
   *found* the symptom, separately from the department that *owned* the root
   cause — plus a reassignment log with a mandatory reason for every move.

### Where the pieces run

```
Browser (React, Vite)            no database credentials, ever
        |  HTTPS + JWT
        v
Django REST API                  auth, RBAC, lifecycle state machine,
        |                        audit logging, search — all business logic
        |  psycopg2 + TLS
        v
Supabase PostgreSQL              shared by the whole team
        
Django  ->  local filesystem     issue attachments (MEDIA_ROOT)
```

Supabase is managed PostgreSQL and nothing more. Auth stays in Django (JWT),
RBAC stays in `accounts/permissions.py`, and the lifecycle state machine stays
in `fc/services.py`. Row-level security is not used, because every query already
goes through a single trusted backend that enforces permissions server-side.

### Workflow enforcement

The lifecycle (`backend/fc/lifecycle.py`) is eleven stages, mostly sequential.
Backward movement is limited to an explicit allow-list of rework routes per
failed stage. Everything is enforced **server-side** in `fc/services.py`; the
frontend only reflects what the API permits. An invalid transition returns
HTTP 409 with an explanation. Managers and admins have an override that requires
a reason and is written to the audit log as an override.

---

## Requirements

| | Version | Why |
|---|---|---|
| **Python** | **3.10 minimum, 3.12 recommended** | Django 5.2, DRF 3.18, django-filter 26 and python-dotenv 1.2 all declare `Requires-Python >= 3.10`. |
| **Node.js** | **20 minimum, 22 recommended** | Vite 8 requires Node 20.19+ / 22.12+. |
| **PostgreSQL** | 14+ locally, or Supabase | Only needed locally if you also want a local database for running tests. |

### Python version

If `pip install -r requirements.txt` fails with a message about the Python
requirement, your interpreter is older than 3.10. **Do not downgrade Django** —
install a supported Python instead. `python manage.py` will refuse to start on
an unsupported interpreter and tell you the same thing.

Check what you have:

```powershell
py --list          # Windows: lists every installed Python
python --version
```

On Windows, install Python 3.12 from <https://www.python.org/downloads/> (tick
**"Add python.exe to PATH"** in the installer), or `winget install Python.Python.3.12`.
Then recreate the virtual environment — an existing `.venv` keeps pointing at the
old interpreter, so it must be deleted, not reused:

```powershell
cd backend
rmdir /s /q .venv            # PowerShell: Remove-Item -Recurse -Force .venv
py -3.12 -m venv .venv
.venv\Scripts\activate
python --version             # expect 3.12.x
pip install --upgrade pip
pip install -r requirements.txt
```

macOS/Linux equivalent: `python3.12 -m venv .venv && source .venv/bin/activate`.

## Setup

### 1. Database — shared Supabase PostgreSQL

The team shares one Supabase PostgreSQL database. Django remains the only thing
that talks to it: React never touches the database, and Supabase Auth, RLS and
PostgREST are not used. The credentials live in `backend/.env` and nowhere else.

```
React frontend  ->  Django REST API  ->  Supabase PostgreSQL
```

**Get the connection string.** In the Supabase dashboard for your project
(`https://<project-ref>.supabase.co`) go to **Project Settings -> Database ->
Connection string**, choose the **Session pooler** tab, and copy the URI. It
looks like:

```
postgresql://postgres.<project-ref>:<db-password>@aws-<n>-<region>.pooler.supabase.com:5432/postgres
```

**Use the session pooler (port 5432).** Supabase offers three routes and they
are not interchangeable:

| Route | Host / port | Use it? |
|---|---|---|
| **Session pooler** | `aws-<n>-<region>.pooler.supabase.com:5432` | **Yes.** IPv4-reachable, and behaves like a normal PostgreSQL session — migrations, prepared statements and server-side cursors all work. |
| Transaction pooler | same host, port `6543` | Only for serving traffic. Connections return to the pool between statements. The app detects the port and automatically sets `CONN_MAX_AGE=0` and disables server-side cursors. **Never run migrations through it.** |
| Direct connection | `db.<project-ref>.supabase.co:5432` | Avoid. Supabase serves this over IPv6 only, so it times out on most Windows/office networks. |

Put it in `backend/.env`:

```
DATABASE_URL=postgresql://postgres.<project-ref>:<db-password>@aws-<n>-<region>.pooler.supabase.com:5432/postgres
```

If the password contains `@ : / ? #` or `%`, percent-encode it (`@` -> `%40`,
`:` -> `%3A`, `/` -> `%2F`, `#` -> `%23`, `%` -> `%25`). TLS is required
automatically for any non-local host.

<details>
<summary>Local PostgreSQL instead (optional — useful for running the test suite)</summary>

```bash
sudo -u postgres psql -c "CREATE USER fcops WITH PASSWORD 'fcops';"
sudo -u postgres psql -c "CREATE DATABASE fcops OWNER fcops;"
```

Leave `DATABASE_URL` empty and set the `POSTGRES_*` variables instead.
</details>

### 2. Backend

```bash
cd backend
py -3.12 -m venv .venv && .venv\Scripts\activate    # Windows
pip install -r requirements.txt

copy .env.example .env        # Windows   (cp on macOS/Linux)
#  -> set DATABASE_URL and DJANGO_SECRET_KEY
#  -> generate a key: python -c "import secrets; print(secrets.token_urlsafe(50))"

python manage.py dbcheck      # verifies the connection before you migrate
python manage.py migrate
python manage.py seed --demo
python manage.py dbcheck --deep
python manage.py runserver 0.0.0.0:8000
```

`seed` alone creates departments, users, FC models, checklist templates,
parameter profiles and GCS/Configurator versions. `--demo` additionally creates
resolved historical issues so knowledge search has something to find. Both are
idempotent for reference data; run `seed` without `--demo` on the shared
database once real production data exists.

**`dbcheck`** is the fastest way to confirm a new database is wired up
correctly. It prints the connection (never the password) and verifies
`plpgsql`, `tsvector`/`websearch_to_tsquery`, GIN index support, `jsonb`, the
audit table, the append-only trigger and both search indexes. With `--deep` it
also runs a real full-text query and confirms the audit log rejects a raw
`UPDATE` and `DELETE`.

If it cannot connect, the usual cause is the direct `db.<ref>.supabase.co` host
on an IPv4-only network — switch to the session pooler host.

### 3. Connection limits

Supabase caps how many clients may be connected at once — on the session pooler
that is **15**. Exceed it and every request fails with:

```
FATAL: (EMAXCONNSESSION) max clients reached in session mode
       - max clients are limited to pool_size: 15
```

The cause is not traffic volume, it is Django's development server: `runserver`
creates a **new thread per request**, and each thread opens its own database
connection. If connections are persistent they accumulate — a few minutes of
clicking around is enough, because the FC detail page alone fires four parallel
requests.

The project defaults `CONN_MAX_AGE` to **0 for any remote host**, so each
request opens and closes its own connection and nothing accumulates. That is
the safe default and needs no configuration.

**If you hit the error:** stop the API server (Ctrl-C) to release the
connections, confirm `DB_CONN_MAX_AGE` is not set to a non-zero value in
`.env`, and start it again. `python manage.py dbcheck` reports how many
connections this app currently holds.

**For better performance**, run under a WSGI server with a bounded thread pool
instead of `runserver`. Then connections can be persistent, because the pool
size is fixed:

```powershell
# backend\.env
DB_CONN_MAX_AGE=60

python -m waitress --listen=0.0.0.0:8000 --threads=6 config.wsgi:application
```

Six threads means at most six connections, comfortably under the cap, and each
request reuses a warm connection instead of paying a TLS handshake to Sydney.
This is also how you would serve several employees from one machine.

**If you need more headroom than that**, switch normal traffic to the
**transaction pooler** (port `6543`), which multiplexes many clients onto few
server connections. Migrations cannot run through it, so give them the session
pooler separately — the project routes them automatically:

```
DATABASE_URL=postgresql://postgres.<ref>:<pw>@aws-<n>-<region>.pooler.supabase.com:6543/postgres
MIGRATION_DATABASE_URL=postgresql://postgres.<ref>:<pw>@aws-<n>-<region>.pooler.supabase.com:5432/postgres
```

### 4. Frontend

```bash
cd frontend
npm install
npm run dev        # http://localhost:5173, proxies /api to :8000
```

For a production build: `npm run build` (output in `frontend/dist/`), served by
any static host or by Django/nginx.

### 5. Attachments

Issue attachments are written to the local filesystem at `MEDIA_ROOT`
(`backend/media/` by default). No object storage is configured, and the storage
layer is Django's standard `FileField`, so moving to Supabase Storage, S3 or
anything else later is a settings change rather than a code change.

### Seeded logins

Password for every seeded account: `ChangeMe123!` (override with
`python manage.py seed --password '…'`).

| Username | Role | Department |
|---|---|---|
| `admin` | Admin | Management |
| `mgr.rao` | Manager | Management |
| `hw.lead` | Department Lead | Machine Assembly |
| `hw.tech1` | Technician | Manual Assembly |
| `qc.tech` | Technician | Quality Control |
| `fw.lead` | Department Lead | Firmware |
| `fw.eng` | Technician | Firmware |
| `sw.eng` | Technician | Software |
| `mech.tech` | Technician | Mechanical |
| `test.eng1` / `test.eng2` | Test Engineer | Ground & Bench Testing |

---

## Environment variables

See `backend/.env.example` for the full list with comments. The essentials:

`backend/.env` is the only place credentials live. It is git-ignored; only
`.env.example` is committed. React never receives database credentials — the
browser talks to Django, Django talks to PostgreSQL.

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | *(empty)* | Full `postgresql://…` connection string. **Takes precedence over `POSTGRES_*`.** This is what you paste from Supabase. |
| `POSTGRES_DB/USER/PASSWORD/HOST/PORT` | `fcops`/`fcops`/*(empty)*/`127.0.0.1`/`5432` | Used only when `DATABASE_URL` is empty. |
| `DB_SSLMODE` | `require` remote, `disable` local | Override only for `verify-full` or similar. |
| `DB_CONN_MAX_AGE` | `0` remote, `60` local | Persistent connection lifetime. Forced to `0` on the transaction pooler. **Leave at 0 under `runserver`** — see Connection limits. |
| `MIGRATION_DATABASE_URL` | *(empty)* | Session-pooler URL used automatically for `migrate` / `makemigrations` / `dbcheck` when `DATABASE_URL` is a transaction pooler. |
| `DB_CONNECT_TIMEOUT` | `10` | Seconds before a connection attempt gives up. |
| `DB_APPLICATION_NAME` | `fcops-django` | Shows up in Supabase's dashboard and `pg_stat_activity`. |
| `TEST_DATABASE_URL` | *(empty)* | Database for the test suite. See the warning below. |
| `ALLOW_TESTS_ON_REMOTE_DB` | `False` | Escape hatch; leave it off. |
| `DJANGO_SECRET_KEY` | dev placeholder | **Must** be a random 50-char string in any shared environment. |
| `DJANGO_DEBUG` | `True` | Set `False` in production. |
| `DJANGO_ALLOWED_HOSTS` | `*` | Comma-separated hostnames. |
| `JWT_ACCESS_MINUTES` / `JWT_REFRESH_DAYS` | `120` / `7` | Token lifetimes. |
| `CORS_ALLOWED_ORIGINS`, `CSRF_TRUSTED_ORIGINS` | dev server | Frontend origins. |
| `MEDIA_ROOT` | `./media` | Attachment storage (local filesystem). |
| `REQUIRE_INDEPENDENT_VERIFICATION` | `True` | Verifier must differ from resolver (PRD §17). |
| `ALLOW_MANAGER_DEVIATION` | `True` | Manager may approve past unverified non-blocking issues with a mandatory justification. |

---

## Running the tests

> **The test suite creates, populates and drops a database.** It must never be
> pointed at the shared Supabase instance. If `DATABASE_URL` is remote and no
> test database is configured, the suite automatically redirects to local
> PostgreSQL rather than touching the shared one, and says so. To run tests you
> therefore need a local PostgreSQL (or a separate disposable database set as
> `TEST_DATABASE_URL`).

### One-time: a local PostgreSQL for tests

**Windows** — install PostgreSQL 17 (`winget install PostgreSQL.PostgreSQL.17`,
or the installer from <https://www.postgresql.org/download/windows/>; note the
superuser password you set). Then, from a new terminal:

```powershell
& "C:\Program Files\PostgreSQL\17\bin\psql.exe" -U postgres -c "CREATE USER fcops WITH PASSWORD 'fcops';"
& "C:\Program Files\PostgreSQL\17\bin\psql.exe" -U postgres -c "ALTER USER fcops CREATEDB;"
& "C:\Program Files\PostgreSQL\17\bin\psql.exe" -U postgres -c "CREATE DATABASE fcops OWNER fcops;"
```

`ALTER USER … CREATEDB` matters: Django creates a throwaway `test_fcops`
database for each run and cannot do that without it.

Then set the local credentials in `backend/.env` (alongside `DATABASE_URL`,
which stays pointed at Supabase — they do not conflict, the test runner picks
the local one automatically):

```
POSTGRES_DB=fcops
POSTGRES_USER=fcops
POSTGRES_PASSWORD=fcops
POSTGRES_HOST=127.0.0.1
POSTGRES_PORT=5432
```

**Docker alternative**, if you would rather not install PostgreSQL:

```bash
docker run -d --name fcops-pg -p 5432:5432 \
  -e POSTGRES_USER=fcops -e POSTGRES_PASSWORD=fcops -e POSTGRES_DB=fcops postgres:17
```

### Running them

```bash
cd backend
python manage.py test tests --noinput
```

77 tests, ~1–3 minutes (PostgreSQL index creation dominates). They cover the full
production loop, workflow rejection paths, RBAC at the API layer,
search/similarity, audit-log immutability including a raw-SQL tamper attempt,
and the database-configuration layer (URL parsing, percent-encoded passwords,
pooler-mode detection, connection-lifetime defaults, migration routing, TLS
defaults, credential scrubbing on debug pages, and the guard above).

If the database cannot be reached, the run stops with an explanation of which
host it tried and why, rather than a psycopg2 traceback — see
`config/test_runner.py`.

### End-to-end UI test

```bash
pip install -r requirements-dev.txt
playwright install chromium
python e2e/ui_walkthrough.py     # with backend and frontend both running
```

Drives a real browser through registration, lifecycle progression, stage
failure, issue creation with live similar-issue search, an RBAC refusal,
reassignment, resolution, independent verification, rework, re-run, timeline and
manager approval. See `e2e/README.md`.

---

## API overview

All endpoints are under `/api/` and require `Authorization: Bearer <access>`
except `/api/health/` and `/api/auth/token/`.

| Endpoint | Purpose |
|---|---|
| `POST /api/auth/token/` · `…/refresh/` | Obtain / refresh JWT. Logins are audited. |
| `GET /api/users/me/` | Current user plus a resolved permission map. |
| `GET/POST /api/fcs/` | List / register FCs. `?search=` matches serial, revision, batch. |
| `GET /api/fcs/{id}/` | Detail incl. stage progress and approval blockers. |
| `POST /api/fcs/{id}/start_stage/` · `pass_stage/` · `fail_stage/` | Lifecycle transitions (validated server-side). |
| `POST /api/fcs/{id}/approve/` | Manager release decision. Manager/admin only. |
| `POST /api/fcs/{id}/override_stage/` | Audited manual transition. Manager/admin only. |
| `GET /api/fcs/{id}/timeline/` · `stage_records/` · `issues/` · `audit_log/` | FC history views. |
| `GET/POST /api/issues/` | List (with full-text + structured filters) / create. |
| `POST /api/issues/{id}/status/` · `notes/` · `reassign/` · `promote/` · `reopen/` · `waiting/` | Issue workflow. |
| `GET /api/issues/{id}/similar/` · `GET|POST /api/issues/similar-search/` | Ranked similar historical issues + matching known issues. |
| `GET /api/issues/search/` | Paginated keyword + structured search. |
| `GET /api/known-issues/` · `{id}/occurrences/` | Knowledge base. |
| `GET/POST /api/rework-records/` · `{id}/complete/` | Rework attached to a failed stage. |
| `GET/POST /api/firmware-records/` · `/api/test-results/` | Firmware and test/checklist traceability. |
| `GET /api/dashboard/summary/` | Manager dashboard aggregate. |
| `GET /api/audit-log/` | Read-only, filterable. No write route exists. |
| `GET /api/lifecycle/` | Stage list and allowed rework targets (drives the UI). |

### Management commands

| Command | Purpose |
|---|---|
| `python manage.py dbcheck [--deep]` | Verify the database connection and every PostgreSQL feature the project relies on. Never prints the password. |
| `python manage.py seed [--demo] [--password …]` | Seed reference data, optionally with demo FCs and resolved issues. |
| `python manage.py reindex_search` | Rebuild `search_vector` for all issues and known issues after a bulk load or restore. |

Django admin is available at `/admin/` for admin users.
