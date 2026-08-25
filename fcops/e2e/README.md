# End-to-end UI walkthrough

Drives a real browser through the whole production loop against a running
backend and frontend: login, FC registration, lifecycle progression, stage
failure, issue creation with live similar-issue search, investigation,
RBAC refusal, reassignment, resolution, independent verification, rework,
re-run, timeline, and manager approval.

## Running it

```bash
pip install -r requirements-dev.txt
playwright install chromium

# in two other terminals:
#   cd backend  && python manage.py runserver
#   cd frontend && npm run dev

python e2e/ui_walkthrough.py
```

It exits non-zero on any uncaught page error or failed assertion, and writes
screenshots to `/tmp/v2-*.png`.

Every mutating step is followed by `no_error(page, ...)`, which fails if the app
surfaced an error banner. Without that guard a step can appear to pass while the
server quietly refused the request — which is exactly what happened the first
time this script was written.
