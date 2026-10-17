# WP0 observed validation — 17 October 2026

All application checks use the unmodified preservation snapshot `900680d`, not a merge into main. See [ENVIRONMENT.md](ENVIRONMENT.md) for the fresh local PostgreSQL 16 cluster, Python 3.12 venv, explicit loopback connections and browser setup. No Supabase/shared data was used. Failures and harness retries are retained below. Logs contain full combined stdout/stderr; generated secrets are excluded and Windows line endings are standardised.

Commands use the isolated venv's `python`; backend commands run from the snapshot's `fcops/backend`, frontend commands from its frontend, and E2E from its `fcops` directory.

| Command / attempt | Observed result | Full output |
|---|---|---|
| `python --version` | exit 0; Python 3.12.10 | [python-version.txt](python-version.txt) |
| `postgres --version` | exit 0; PostgreSQL 16.15 | [postgres-version.txt](postgres-version.txt) |
| `initdb` (new cluster, SCRAM, UTF8) | exit 0 | [initdb.txt](initdb.txt) |
| PostgreSQL startup/readiness | observed listening at 127.0.0.1:55432; pg_ctl status exit 0 | [postgres-start.txt](postgres-start.txt), [postgres-status.txt](postgres-status.txt) |
| `createdb` (fresh fcops_wp0) | exit 0; no output | [createdb.txt](createdb.txt) |
| `python manage.py test tests --noinput` — first | harness timeout after 240 seconds; incomplete, no passing-suite claim | [backend-tests.txt](backend-tests.txt) |
| Same full suite — 900-second limit | exit 1; 155 tests in 251.246s, three failures | [backend-tests-complete.txt](backend-tests-complete.txt) |
| `python manage.py test tests.test_db_config.TestDatabaseGuardTests --noinput` — clean env | exit 0; 6 tests in 0.005s, OK | [backend-guard-clean-env.txt](backend-guard-clean-env.txt) |
| `python manage.py test tests --noinput` — clean env | **exit 0; 155 tests in 247.775s, OK** | [backend-tests-clean-env.txt](backend-tests-clean-env.txt) |
| `python manage.py migrate --noinput` | exit 0; all migrations including parameter-file migration applied | [migrate.txt](migrate.txt) |
| `python manage.py seed --demo` | exit 0; 10 departments, 12 users, 2 models; demo data created | [seed-demo.txt](seed-demo.txt) |
| `python manage.py dbcheck --deep` | exit 0; all checks passed, five issues searched; raw audit UPDATE and DELETE rejected | [dbcheck-deep.txt](dbcheck-deep.txt) |
| `node --version`; `npm --version` | v22.20.0; 11.6.1, exit 0 | [node-version.txt](node-version.txt), [npm-version.txt](npm-version.txt) |
| `npm ci` | exit 0; 71 packages added, one high advisory | [npm-ci.txt](npm-ci.txt) |
| `npm run build` | exit 0; 45 modules, built in 129ms | [frontend-build.txt](frontend-build.txt) |
| `npm run test:diagnostics` | exit 1: Missing script: "test:diagnostics" | [frontend-diagnostics.txt](frontend-diagnostics.txt) |
| `python e2e/ui_walkthrough.py` — source beneath .git | exit 1; Vite serving restriction prevents login form; Sign out locator timeout | [e2e-ui-walkthrough.txt](e2e-ui-walkthrough.txt), [Vite log](frontend-server.txt) |
| Same E2E — relocated frontend, Windows short path | exit 1; Vite path mismatch prevents login; same locator timeout | [e2e-ui-walkthrough-relocated.txt](e2e-ui-walkthrough-relocated.txt), [Vite log](frontend-server-relocated.txt) |
| Same E2E — canonical long frontend path | exit 0; **17 steps passed, PAGE ERRORS: none** | [e2e-ui-walkthrough-final.txt](e2e-ui-walkthrough-final.txt), [Vite log](frontend-server-longpath.txt) |
| `python -m pip check` | exit 0: No broken requirements found | [pip-check.txt](pip-check.txt) |
| `npm audit --json` | exit 1; one high source-map-js advisory; not fixed in WP0 | [npm-audit.json](npm-audit.json) |

## Backend environment sensitivity

The complete first run failed these pure configuration tests:

- `TestDatabaseGuardTests.test_local_postgres_vars_are_reused_for_the_fallback`: expected `mylocal`, got `fcops_wp0`.
- `TestDatabaseGuardTests.test_opt_in_allows_remote_test_database`: expected the synthetic pooler hostname, got loopback.
- `TestDatabaseGuardTests.test_redirected_fallback_is_flagged_for_the_test_runner`: expected redirect flag, absent.

The isolation harness supplied both primary POSTGRES_* and TEST_POSTGRES_* variables. These tests use `mock.patch.dict(..., clear=False)` and remove TEST_DATABASE_URL but leave TEST_POSTGRES_* present. That selects the explicit-test branch before the fallback/opt-in branches under test. Removing redundant TEST_POSTGRES_* from the child process preserves the primary loopback-only disposable connection and lets all six guard tests pass. No application/test source was modified and remote-test protection was not enabled. The tests' existing mocked remote-URL/opt-in scenarios build configuration dictionaries only; they do not connect to a remote database.

The interrupted first attempt left a disposable test database; the full retry's `--noinput` recreated it. Both events appear in the logs. No shared database was dropped.

## Limits and follow-ups

- Diagnostics page/script and the claimed 23 diagnostic tests were not found. No stub was added to make that command pass.
- Baseline tests and browser checks exercise the preserved prototype, including its broad reads; they do not demonstrate the future PRD access policy, dual approval, jobs or email delivery.
- The supplied plan refers to PRD v0.2/§12.1/scenario 13; only v0.1 exists in the supplied repository. The plan is saved verbatim, and the PRD copies retain the original bytes. Reconcile the missing revision before later WPs.
- E2E configuration/parameter scripts were inventoried but not run; WP0 requested the primary UI walkthrough.
- npm audit's source-map-js advisory and Django's unordered FlightController pagination warning are follow-ups; application/dependency remediation is outside this baseline.
- Database and temporary web processes are stopped at handoff. Runtime files stay outside tracked source; no credentials are committed.

Final check: **155 backend tests passed** under the clean local environment; the earlier three failures and timeout remain recorded. Temporary service shutdown is recorded in [cleanup.txt](cleanup.txt).
