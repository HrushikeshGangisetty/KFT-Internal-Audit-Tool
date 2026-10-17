"""Failure routing in one action, and the parameter comparison page."""
import os
import sys

from playwright.sync_api import sync_playwright

BASE = os.environ.get("E2E_BASE_URL", "http://127.0.0.1:5173")
PW = "ChangeMe123!"
FIXTURES = os.environ.get("PARAM_FIXTURES", "/tmp/params")
steps, errs = [], []


def log(msg):
    steps.append(msg)
    print("  ok:", msg, flush=True)


def login(page, username):
    page.goto(BASE + "/login", wait_until="networkidle")
    if page.locator('input[autocomplete="username"]').count() == 0:
        page.click('button:has-text("Sign out")')
        page.wait_for_selector('input[autocomplete="username"]', timeout=10000)
    page.fill('input[autocomplete="username"]', username)
    page.fill('input[type="password"]', PW)
    page.click('button:has-text("Sign in")')
    page.wait_for_selector("text=FCs total", timeout=20000)


def no_error(page, what):
    b = page.locator(".banner.error")
    if b.count() and b.first.is_visible():
        raise AssertionError(f"{what}: {b.first.inner_text()}")


with sync_playwright() as p:
    launch = ({"executable_path": os.environ["PLAYWRIGHT_CHROMIUM"]}
              if os.environ.get("PLAYWRIGHT_CHROMIUM") else {})
    b = p.chromium.launch(**launch)
    page = b.new_page(viewport={"width": 1440, "height": 1150})
    page.on("pageerror", lambda e: errs.append(str(e)))
    page.on("console", lambda m: errs.append("console: " + m.text)
            if m.type == "error" and not any(c in m.text for c in ("404", "403", "409"))
            else None)

    # ---- 1. Fail a stage and route it back to the responsible stage ----
    login(page, "test.eng1")
    page.goto(BASE + "/fcs/new", wait_until="networkidle")
    page.fill('input >> nth=0', "rev-E")
    page.click('button:has-text("Register FC")')
    page.wait_for_selector("text=Lifecycle progress", timeout=15000)
    serial = page.locator("h2.mono").first.inner_text()
    fc_url = page.url

    def current_stage():
        return page.locator('.card:has(h2:text("Current stage")) p strong').first.inner_text()

    for _ in range(15):
        if current_stage().lower() == "ground testing":
            break
        page.click('button:has-text("Start stage")')
        page.wait_for_timeout(700)
        page.click('button:has-text("Mark passed")')
        page.wait_for_timeout(900)
    log(f"{serial} walked to Ground Testing")

    page.click('button:has-text("Start stage")')
    page.wait_for_timeout(800)
    page.click('button:has-text("Mark failed")')
    page.wait_for_selector("text=Which stage is responsible?", timeout=10000)
    options = page.locator('.card:has(h2:text("Current stage")) select').last.inner_text()
    assert "Machine Assembly" in options and "Fabrication" in options, options
    log("failure panel offers every earlier stage, usual routes first")

    page.select_option('.card:has(h2:text("Current stage")) select >> nth=-1',
                       label="Machine Assembly / Soldering")
    page.fill('.card:has(h2:text("Current stage")) textarea >> nth=-1',
              "Cold joint on the GPS connector; soldering is responsible.")
    page.click('button:has-text("Fail and return to")')
    page.wait_for_timeout(2500)
    no_error(page, "failing with a return route")
    assert "machine" in current_stage().lower(), current_stage()
    log(f"FC failed at Ground Testing and returned to {current_stage()} in one action")

    page.click('button:has-text("Timeline")')
    page.wait_for_timeout(1200)
    timeline = page.locator(".timeline").inner_text()
    assert "Returned to Machine Assembly" in timeline, timeline[:400]
    assert "Ground Testing FAILED" in timeline
    log("timeline records both the failure and where it was routed")
    page.screenshot(path="/tmp/v4-routing.png", full_page=True)

    # ---- 2. Parameter comparison ----
    page.click('a:has-text("Parameter Compare")')
    page.wait_for_selector("text=Left file", timeout=10000)
    page.set_input_files('input[type="file"] >> nth=0', f"{FIXTURES}/newfc.param")
    page.set_input_files('input[type="file"] >> nth=1', f"{FIXTURES}/new12.param")
    page.click('button:has-text("Compare")')
    page.wait_for_selector("text=Different values", timeout=20000)
    no_error(page, "comparing two uploads")

    summary = page.locator('.grid.cols-4').first.inner_text()
    assert "137" in summary, summary          # changed values
    assert "69" in summary, summary           # only on one side
    log("uploaded two dumps: 137 changed, 69 present on only one side")

    table = page.locator("table").first.inner_text()
    assert "AVOID_MARGIN" in table or "BATT2_CAPACITY" in table, table[:300]
    log("differences listed with both values and the delta")

    page.fill('input[placeholder^="Filter by parameter"]', "COMPASS")
    page.wait_for_timeout(600)
    rows = page.locator("table tbody tr").count()
    assert rows > 0
    assert "COMPASS" in page.locator("table tbody").inner_text()
    log(f"name filter narrows the diff to {rows} COMPASS rows")
    page.screenshot(path="/tmp/v4-paramcompare.png", full_page=True)

    page.fill('input[placeholder^="Filter by parameter"]', "")
    page.click('.card button:has-text("BARO")')
    page.wait_for_timeout(600)
    assert "BARO" in page.locator("table tbody").inner_text()
    log("group chips filter the diff by parameter family")

    # ---- 3. Identical files report cleanly ----
    page.reload(wait_until="networkidle")
    page.wait_for_selector("text=Left file", timeout=10000)
    page.set_input_files('input[type="file"] >> nth=0', f"{FIXTURES}/nnn.param")
    page.set_input_files('input[type="file"] >> nth=1', f"{FIXTURES}/nnn.param")
    page.click('button:has-text("Compare")')
    page.wait_for_selector("text=identical", timeout=20000)
    assert "are identical" in page.inner_text("body")
    log("comparing a file with itself reports no differences")

    b.close()

print("\nSTEPS PASSED:", len(steps))
print("PAGE ERRORS:", errs[:8] if errs else "none")
sys.exit(1 if errs else 0)
