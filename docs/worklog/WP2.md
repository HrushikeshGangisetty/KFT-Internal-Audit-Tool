# WP2 — Single origin and session authentication
Agent: Claude Code    Branch: wp/02-session-auth    Date: 17 October 2026

Authorised by the user in chat ("continue with the next one in the list as well, merge both together"). Authentication decision (PRD §15) taken by the user in chat: **Django sessions**. Branched from `wp/01-access-policy`, so WP1's scoped views are included. Kept local, not pushed, at the user's request.

## Done

- **Session-only API auth** (`config/settings.py`, `core/authentication.py`): DRF uses `core.authentication.SessionAuthentication`, which returns **401** (not DRF's default 403) for anonymous requests. SimpleJWT removed from settings, URLs and `requirements.txt`.
- **Auth endpoints** (`accounts/views.py`, `config/urls.py`): `GET /api/auth/csrf/` (sets the cookie, returns the token), `POST /api/auth/login/` (CSRF-enforced, Django `login()` rotates session and CSRF token, audited, rate-limited), `POST /api/auth/logout/`, `GET /api/auth/me/` (profile, or empty 200 when signed out). Removed `/api/auth/token/*` and `/api/users/me/`.
- **Cookie and timeout settings**: `SESSION_COOKIE_HTTPONLY`, `SAMESITE=Lax` for session and CSRF cookies, `SESSION_COOKIE_SECURE`/`CSRF_COOKIE_SECURE` default on when `DEBUG` is off (env-overridable). Idle timeout `SESSION_IDLE_SECONDS` (sliding, `SESSION_SAVE_EVERY_REQUEST`); absolute lifetime `SESSION_ABSOLUTE_SECONDS` via `core.middleware.AbsoluteSessionTimeoutMiddleware`.
- **Login rate limiting** (`accounts/ratelimit.py`): a **simple per-username and per-IP failure counter in the Django cache** (not django-axes). `LOGIN_FAILURE_LIMIT` failures lock for `LOGIN_LOCKOUT_SECONDS` (HTTP 429). A success clears only the username counter.
- **Deactivation** (`accounts/services.py::end_sessions`, `UserViewSet.perform_update`): setting `is_active=False` through the user API deletes that user's live sessions in the same request and audits it.
- **Single origin**: WhiteNoise middleware serves the built SPA from `FRONTEND_DIST` (default `../frontend/dist`) at the site root; `core.views.spa_index` returns `index.html` for every non-`api/`, `api-auth/`, `admin/`, `static/`, `media/` path. `django-cors-headers` removed from settings and requirements. Dev: Vite proxies `/api`, `/api-auth`, `/admin`, `/static` with `changeOrigin: false`, so Django sees the browser's Host and needs no trusted origins (`CSRF_TRUSTED_ORIGINS` now defaults to empty).
- **Seed guard**: `seed --demo` raises `CommandError` when `DEBUG` is off or `PRODUCTION=1`.
- **Frontend** (`frontend/src/lib/api.js`, `lib/auth.jsx`, `App.jsx`, `pages/IssueDetail.jsx`, `vite.config.js`): no token storage or `Authorization` header; `credentials: 'same-origin'`; CSRF token fetched once from `/api/auth/csrf/`, kept in memory, dropped after login/logout; a 401 redirects to `/login`. Attachment links are plain links again (the WP1 bearer-token download helper is deleted).
- **Docs**: `backend/.env.example` and `README.md` (architecture, config table, API overview) updated for sessions.
- **Tests**: `tests/test_session_auth.py` (11 tests). Login helpers in `test_api_rbac.py`/`test_config_features.py` now sign in through `/api/auth/login/`; route-coverage allowlist updated for the new auth views.
- **E2E**: added step 16 asserting `localStorage` and `sessionStorage` are empty and the session cookie is not visible to scripts.
- Pinned `whitenoise==6.12.0` (it was already listed, unpinned, in `requirements.txt`) and installed it into the disposable WP0 venv.

## Acceptance

| Item | Evidence | Result |
|---|---|---|
| No token in localStorage or sessionStorage (checked in the E2E) | `ui_walkthrough.py` step 16, both single-origin and Vite-proxy runs | PASS |
| A POST without a CSRF token is rejected | `test_post_without_csrf_token_is_rejected` (anonymous login POST and authenticated POST both 403; with token 200/201) | PASS |
| A deactivated user's existing session stops working on the next request | `test_deactivated_user_session_stops_working` (next request 401, no live session rows) | PASS |
| Production build serves SPA and API from one origin; deep links load the SPA | `test_deep_links_load_the_spa_and_assets_share_the_origin`; manual: Django on 127.0.0.1:58000 returned 200 HTML for `/`, `/issues/42`, `/login`, 200 for the hashed JS asset, JSON for `/api/health/`, 401 for `/api/issues/`; full E2E against that origin | PASS |
| Diagnostics page still loads (manual check over localhost) | Not checkable: the Diagnostics page/script does not exist on `main` (WP0 finding) | NOT APPLICABLE |

## Commands run and results

Same disposable environment as WP1 (WP0 venv, PostgreSQL 16 on 127.0.0.1:55432, TEST_POSTGRES_* unset); `fcops_wp1` recreated, migrated and seeded for the E2E.

- `pip install whitenoise==6.12.0` into the disposable venv; `pip check`: no broken requirements.
- `manage.py check`: no issues.
- `manage.py test tests.test_session_auth tests.test_route_coverage`: 14 tests OK.
- Full suite `manage.py test tests --noinput`: **153 tests in 253.860s, OK**.
- `npm run build`: OK.
- E2E single origin (Django serving `dist/`): first run 20 steps passed but exited 1 on one console error (anonymous `/api/auth/me/` returned 401 on page load). Changed `me` to an empty 200 for anonymous callers; rerun **STEPS PASSED: 20, PAGE ERRORS: none**.
- E2E through a freshly started Vite proxy: **STEPS PASSED: 20, PAGE ERRORS: none**. (An earlier dev run hit a leftover Vite process from WP1; it was killed and the run repeated.)

## Not done / deviations from plan

- No `collectstatic` was run; WhiteNoise warns in tests that `staticfiles/` does not exist. Production deployment must run `collectstatic` (admin static).
- Absolute session lifetime is enforced only for sessions created through `/api/auth/login/` (sessions from `/admin/` or `/api-auth/` logins carry no start time).
- Diagnostics acceptance item not checkable (page absent).
- Nothing pushed; no PR opened (user instruction).

## Decisions taken in this session (and why)

- Sessions over JWT-in-cookie (user's choice).
- Rate limiting: cache counter rather than django-axes, to avoid a new dependency; per-process cache noted with a `ponytail:` comment.
- CSRF token returned in the `/api/auth/csrf/` body and held in memory, so the client never parses cookies.
- `GET /api/auth/me/` answers 200 with an empty body when signed out, so the SPA's startup probe is not logged as an error; every protected endpoint still returns 401.
- `changeOrigin: false` in the Vite proxy so no trusted-origin configuration is needed in dev.

## Follow-ups (out of scope, noticed)

- Use a shared cache (database or Redis) for the login counters if more than one server process runs.
- `end_sessions` decodes every live session; add a user index if the session table grows.
- Django admin login is still available at `/admin/` (see WP1 follow-up on admin access).
- `gunicorn` in `requirements.txt` is unpinned (pre-existing).

## Placeholders introduced

- Defaults: idle 8 h, absolute 24 h, 5 failures, 15 min lockout. Product owner to confirm.
