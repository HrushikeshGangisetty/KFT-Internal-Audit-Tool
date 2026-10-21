# End-to-end UI walkthroughs

Real-browser walkthroughs against a running backend. They **create and change
data**: run them only against a disposable database seeded with
`seed --demo` and `seed_pilot_config`, never a shared one.

| Script | Covers |
| --- | --- |
| `ui_walkthrough.py` | Production loop: register an FC, lifecycle, stage failure, issue with live similar-issue search, RBAC refusal, reassignment, resolution, independent verification, rework, re-run, timeline, manager approval, no credentials in browser storage. |
| `config_features.py` | Firmware catalogue, test configuration, FC models, accounts; each sidebar entry appears only for the role entitled to it. |
| `work_features.py` | Quick report, issue list infinite scroll and filters, top-bar search, known issues, activity log, tasks and daily update, queue acknowledge and handoff answer, releases with dual approval, announcement preview and single send (console email), parameter compare, notifications, phone-width drawer. |
| `screens.py` | Read-only: one screenshot per screen (used for `docs/platform-overview/`). |

`work_features.py` also expects a Software head (`sw.lead`), a sender grant for
`sw.eng`, more than 25 reports and one pending handoff to Firmware.

## Running

```bash
pip install -r requirements-dev.txt
playwright install chromium        # or set PLAYWRIGHT_CHROMIUM to an installed Chrome
# backend serving the built SPA (or Vite on 5173), plus `manage.py run_worker`
E2E_BASE_URL=http://127.0.0.1:8010 python e2e/ui_walkthrough.py
```

Each script exits non-zero on a failed assertion or any uncaught page error,
and writes screenshots to `E2E_SHOTS` (default: the system temp dir).
Mutating steps are followed by `no_error(...)`, which fails if the app showed an
error banner, so a step cannot pass while the server quietly refused it.
