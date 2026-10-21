"""Shared helpers for the browser walkthroughs. Each script runs against a
disposable database seeded with `seed --demo` (see README.md)."""
import os
import sys
import tempfile
from contextlib import contextmanager

from playwright.sync_api import sync_playwright

BASE = os.environ.get("E2E_BASE_URL", "http://127.0.0.1:5173")
PW = os.environ.get("E2E_PASSWORD", "ChangeMe123!")
SHOTS = os.environ.get("E2E_SHOTS", os.path.join(tempfile.gettempdir(), "fcops-e2e"))
os.makedirs(SHOTS, exist_ok=True)
steps, errs = [], []


def log(msg):
    steps.append(msg)
    print("  ok:", msg, flush=True)


def shot(page, name):
    page.screenshot(path=os.path.join(SHOTS, f"{name}.png"), full_page=True)


def login(page, username):
    # Leave the app first so no in-flight request from the previous user
    # lands after the session is cleared.
    page.goto("about:blank")
    page.context.clear_cookies()
    page.goto(BASE + "/login", wait_until="networkidle")
    page.wait_for_selector('input[autocomplete="username"]', timeout=15000)
    page.fill('input[autocomplete="username"]', username)
    page.fill('input[type="password"]', PW)
    page.click('button:has-text("Sign in")')
    page.wait_for_selector("h1:has-text('Hello,')", timeout=20000)


def go(page, path, ready):
    """Open an app route and wait for `ready` (a selector) to be visible."""
    page.goto(BASE + path, wait_until="networkidle")
    page.wait_for_selector(ready, timeout=15000)


def nav(page, label):
    page.click(f'.sidebar nav a:has-text("{label}")')
    page.wait_for_load_state("networkidle")


def nav_links(page):
    return page.locator(".sidebar nav a").all_inner_texts()


def field(label, tag="input"):
    """A form control by its visible field label."""
    return f'.field:has(label:text-is("{label}")) >> {tag}'


def card(title):
    return f'.card:has(.card-header h2:text-is("{title}"))'


def toast(page, text, timeout=15000):
    page.wait_for_selector(f'.toast:has-text("{text}")', timeout=timeout)


def dialog(page, button, text=None):
    """Answer the app's confirmation/reason dialog."""
    page.wait_for_selector("dialog.dialog[open]", timeout=5000)
    if text is not None:
        page.fill("dialog.dialog textarea", text)
    page.click(f'dialog.dialog button:text-is("{button}")')
    page.wait_for_selector("dialog.dialog[open]", state="detached", timeout=5000)


def no_error(page, what):
    """Fail loudly if the app surfaced an error banner for the last action."""
    banners = page.locator(".banner.error")
    for i in range(banners.count()):
        if banners.nth(i).is_visible():
            raise AssertionError(f"{what}: app reported '{banners.nth(i).inner_text()}'")


def expect_error(page, what):
    banners = page.locator(".banner.error")
    page.wait_for_timeout(300)
    if not (banners.count() and banners.first.is_visible()):
        raise AssertionError(f"{what}: expected the app to refuse this, but it did not")
    return banners.first.inner_text()


@contextmanager
def browser(allowed_status=("404",)):
    """A page that records uncaught errors and unexpected console errors."""
    with sync_playwright() as p:
        exe = os.environ.get("PLAYWRIGHT_CHROMIUM")
        b = p.chromium.launch(**({"executable_path": exe} if exe else {}))
        ctx = b.new_context(viewport={"width": 1440, "height": 1000})
        page = ctx.new_page()
        page.on("pageerror", lambda e: errs.append(str(e)))
        page.on("console", lambda m: errs.append("console: " + m.text)
                if m.type == "error" and not any(c in m.text for c in allowed_status) else None)
        try:
            yield page
        finally:
            ctx.close()
            b.close()


def finish():
    print("\nSTEPS PASSED:", len(steps))
    print("PAGE ERRORS:", errs[:8] if errs else "none")
    print("SCREENSHOTS:", SHOTS)
    sys.exit(1 if errs else 0)
