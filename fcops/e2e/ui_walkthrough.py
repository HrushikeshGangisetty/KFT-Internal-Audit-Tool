"""End-to-end UI walkthrough: register an FC, walk the lifecycle, fail a stage,
raise and resolve an issue, rework, re-run, and take it to manager approval."""
import os
import sys
from playwright.sync_api import sync_playwright, expect

BASE = os.environ.get("E2E_BASE_URL", "http://127.0.0.1:5173")
PW = "ChangeMe123!"
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
    """Fail loudly if the app surfaced an error banner for the last action."""
    banners = page.locator(".banner.error")
    if banners.count() and banners.first.is_visible():
        raise AssertionError(f"{what}: app reported '{banners.first.inner_text()}'")


def expect_error(page, what):
    banners = page.locator(".banner.error")
    if not (banners.count() and banners.first.is_visible()):
        raise AssertionError(f"{what}: expected the app to refuse this, but it did not")
    return banners.first.inner_text()


def reassignment_entries(page):
    """Text of the recorded reassignment log rows only (not the <select> options)."""
    card = page.locator('.card:has(h2:text("Reassignment history"))')
    return card.locator("ul.timeline li").all_inner_texts()


def current_stage(page):
    return page.locator('.card:has(h2:text("Current stage")) p strong').first.inner_text()

def advance(page, until):
    """Start + pass stages until the FC reaches `until`."""
    for _ in range(15):
        stage = current_stage(page)
        if stage.lower() == until.lower():
            return
        page.click('button:has-text("Start stage")')
        page.wait_for_timeout(900)
        page.click('button:has-text("Mark passed")')
        page.wait_for_function(
            "s => document.querySelector('.card h2')"
            " && !document.querySelector('button:disabled')", arg=None, timeout=15000)
        page.wait_for_timeout(700)
    raise AssertionError(f"never reached {until}, stuck at {current_stage(page)}")

with sync_playwright() as p:
    b = p.chromium.launch(**({"executable_path": os.environ["PLAYWRIGHT_CHROMIUM"]} if os.environ.get("PLAYWRIGHT_CHROMIUM") else {}))
    ctx = b.new_context(viewport={"width": 1440, "height": 1100})
    page = ctx.new_page()
    page.on("pageerror", lambda e: errs.append(str(e)))
    # 404 (favicon) and 409 (the deliberate RBAC-refusal step) are expected.
    page.on("console", lambda m: errs.append("console: " + m.text)
            if m.type == "error" and not any(c in m.text for c in ("404", "409"))
            else None)

    # ---- 1. Login (technician) ----
    login(page, "hw.tech1")
    log("login as technician + dashboard renders")

    # ---- 2. FC list ----
    page.click('a:has-text("Flight Controllers")')
    page.wait_for_selector("table", timeout=10000)
    log("FC list renders")

    # ---- 3. FC creation ----
    page.click('a:has-text("Register FC")')
    page.wait_for_selector("text=Register a new flight controller", timeout=10000)
    page.fill('input >> nth=0', "rev-D")
    page.fill('input >> nth=1', "B-2026-99")
    page.click('button:has-text("Register FC")')
    page.wait_for_selector("text=Lifecycle progress", timeout=15000)
    serial = page.locator("h2.mono").first.inner_text()
    log(f"FC created via UI: {serial}")
    fc_url = page.url

    # ---- 4. Lifecycle progression ----
    advance(page, "Ground Testing")
    log("lifecycle progressed Fabrication -> Ground Testing (8 stages)")

    # ---- 5. Fail a stage ----
    page.fill('textarea', "No GPS fix after 5 minutes on the pad.")
    page.click('button:has-text("Mark failed")')
    page.wait_for_timeout(1500)
    assert "Failed" in page.locator('.card:has(h2:text("Current stage"))').inner_text()
    log("Ground Testing marked FAILED")

    # ---- 6. Issue creation + similar issues ----
    page.click('a:has-text("Report an issue")')
    page.wait_for_selector("text=Has this happened before?", timeout=10000)
    page.fill('input[placeholder^="e.g. GPS"]', "GPS not detected during ground test")
    page.fill('textarea >> nth=0',
              "GPS module not detected. No satellites, no fix, serial port silent.")
    page.select_option('select >> nth=3', "HARDWARE")
    page.wait_for_timeout(2200)
    similar = page.locator('.card:has(h2:text("Has this happened before?"))').inner_text()
    assert "ISS-" in similar, "similar-issue panel found nothing"
    log("similar-issue panel surfaced prior issues live while typing")
    # assign to Machine Assembly
    page.select_option('select >> nth=4', label="Machine Assembly")
    page.click('button:has-text("Create issue")')
    page.wait_for_selector("text=Investigation log", timeout=15000)
    no_error(page, "creating the issue")
    issue_url = page.url
    issue_key = page.locator("h2.mono").first.inner_text()
    log(f"issue created: {issue_key}")

    # ---- 7. Investigation ----
    page.fill('textarea >> nth=0', "Continuity check shows an open circuit at pin 3.")
    page.click('button:has-text("Add note")')
    page.wait_for_selector("text=open circuit at pin 3", timeout=15000)
    page.wait_for_timeout(800)
    log("investigation note added (status auto-advanced to Investigating)")

    # ---- 8a. RBAC: a technician outside the assigned department is refused ----
    page.select_option('.card:has(h2:text("Reassignment history")) select',
                       label="Hardware Rework")
    page.fill('.card:has(h2:text("Reassignment history")) input',
              "Open circuit at the connector - hardware, not firmware.")
    page.click('button:has-text("Reassign")')
    page.wait_for_timeout(2000)
    message = expect_error(page, "technician reassigning another department's issue")
    assert "lead" in message.lower() or "manager" in message.lower(), message
    assert len(reassignment_entries(page)) == 1, "a refused reassignment was recorded"
    log(f"RBAC upheld in the UI: technician refused — \"{message[:60]}...\"")

    # ---- 8b. A department lead performs the reassignment ----
    login(page, "hw.lead")
    page.goto(issue_url, wait_until="networkidle")
    page.wait_for_selector("text=Reassignment history", timeout=15000)
    page.select_option('.card:has(h2:text("Reassignment history")) select',
                       label="Hardware Rework")
    page.fill('.card:has(h2:text("Reassignment history")) input',
              "Open circuit at the connector - hardware, not firmware.")
    page.click('button:has-text("Reassign")')
    page.wait_for_timeout(2500)
    no_error(page, "lead reassigning the issue")
    entries = reassignment_entries(page)
    assert len(entries) == 2, f"reassignment not recorded, log has {len(entries)} row(s)"
    assert "Hardware Rework" in entries[-1] and "Open circuit" in entries[-1], entries[-1]
    log("issue reassigned by a department lead, with the reason recorded in the log")

    # ---- 9. Resolve ----
    page.fill('.card:has(h2:text("Root cause")) textarea >> nth=0',
              "Cold solder joint on GPS connector pin 3 from machine soldering.")
    page.select_option('.card:has(h2:text("Root cause")) select',
                       label="Machine Assembly")
    page.fill('.card:has(h2:text("Root cause")) textarea >> nth=1',
              "Reflowed the joint and confirmed continuity.")
    page.click('button:has-text("Mark resolved")')
    page.wait_for_timeout(2500)
    no_error(page, "recording the resolution")
    log("root cause + resolution recorded (root-cause dept differs from discovery)")
    page.screenshot(path="/tmp/v2-issue.png", full_page=True)

    # ---- 10. Verification by a different person ----
    login(page, "test.eng1")
    page.goto(issue_url, wait_until="networkidle")
    page.wait_for_selector("text=Investigation log", timeout=15000)
    page.click('button:has-text("Verify fix")')
    page.wait_for_timeout(2000)
    page.click('button:has-text("Close issue")')
    page.wait_for_timeout(2000)
    no_error(page, "closing the issue")
    assert "Closed" in page.locator("h2.mono").first.locator("xpath=..").inner_text()
    log("fix verified by a second person, then closed")

    # ---- 11. Rework ----
    page.goto(fc_url, wait_until="networkidle")
    page.wait_for_selector("text=Lifecycle progress", timeout=15000)
    page.click('button:has-text("Stages")')
    page.wait_for_timeout(800)
    page.click('button:has-text("Add rework")')
    page.wait_for_selector("text=What was reworked", timeout=10000)
    page.fill('form textarea', "Reflowed GPS connector pin 3, re-inspected under scope.")
    page.select_option('form select >> nth=0', label="Machine Assembly / Soldering")
    page.click('button:has-text("Record rework")')
    page.wait_for_timeout(2500)
    no_error(page, "recording the rework")
    stage_now = current_stage(page)
    assert "machine" in stage_now.lower(), f"rework did not return FC, at {stage_now}"
    log(f"rework recorded; FC routed back to {stage_now}")

    # ---- 12. Re-run to Manager Approval ----
    advance(page, "Manager Approval")
    log("FC re-run through the lifecycle to Manager Approval")

    # ---- 13. Timeline ----
    page.click('button:has-text("Timeline")')
    page.wait_for_timeout(1200)
    timeline = page.locator(".timeline").inner_text()
    for expected in ["registered", "FAILED", "opened", "reassigned", "Rework", "Verified"]:
        assert expected.lower() in timeline.lower(), f"timeline missing '{expected}'"
    log("timeline contains registration, failure, issue, reassignment, rework, verification")
    page.screenshot(path="/tmp/v2-timeline.png", full_page=True)

    # ---- 14. Technician cannot approve ----
    approve_visible = page.locator('button:has-text("Approve for release")').count()
    assert approve_visible == 0, "technician was offered the approval button"
    log("technician is not offered the manager approval action")

    # ---- 15. Manager approval ----
    login(page, "mgr.rao")
    page.goto(fc_url, wait_until="networkidle")
    page.wait_for_selector("text=Lifecycle progress", timeout=15000)
    page.click('button:has-text("Approve for release")')
    page.wait_for_timeout(2500)
    no_error(page, "manager approval")
    header = page.locator("h2.mono").first.locator("xpath=..").inner_text()
    assert "Approved" in header, f"FC not approved: {header}"
    log("manager approved the FC for release")
    page.screenshot(path="/tmp/v2-approved.png", full_page=True)

    ctx.close(); b.close()

print("\nSTEPS PASSED:", len(steps))
print("PAGE ERRORS:", errs[:8] if errs else "none")
sys.exit(1 if errs else 0)
