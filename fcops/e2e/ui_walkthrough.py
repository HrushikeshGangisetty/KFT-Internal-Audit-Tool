"""Production loop: register an FC, walk the lifecycle, fail a stage, raise and
resolve an issue (RBAC refusal included), verify independently, rework, re-run
and take it to manager approval."""
from common import (BASE, browser, card, dialog, expect_error, field, finish, go, log,
                    login, nav, no_error, shot)

CURRENT = card("Current stage")


def current_stage(page):
    return page.locator(f"{CURRENT} p strong").first.inner_text()


def settle(page):
    """Wait until no action button in the stage card is busy."""
    page.wait_for_function(
        "() => { const c = [...document.querySelectorAll('.card')].find(x =>"
        " x.querySelector('h2')?.textContent === 'Current stage');"
        " return c && ![...c.querySelectorAll('button')].some(b => b.disabled"
        " && b.textContent !== 'Mark passed') }", timeout=15000)


def advance(page, until):
    """Start + pass stages until the FC reaches `until`."""
    for _ in range(15):
        stage = current_stage(page)
        if stage.lower() == until.lower():
            return
        page.click(f'{CURRENT} button:has-text("Start stage")')
        settle(page)
        page.click(f'{CURRENT} button:has-text("Mark passed")')
        page.wait_for_function(
            "s => { const c = [...document.querySelectorAll('.card')].find(x =>"
            " x.querySelector('h2')?.textContent === 'Current stage');"
            " return c && c.querySelector('p strong')?.textContent !== s }", arg=stage, timeout=15000)
        no_error(page, f"passing {stage}")
    raise AssertionError(f"never reached {until}, stuck at {current_stage(page)}")


def reassignment_entries(page):
    return page.locator(f'{card("Reassignment history")} ul.timeline li').all_inner_texts()


def header(page):
    return page.locator(".page-header").inner_text()


with browser(allowed_status=("404", "409")) as page:
    login(page, "hw.tech1")
    log("technician signs in; role-aware Home renders")

    nav(page, "Flight controllers")
    page.wait_for_selector("table")
    log("FC list renders")

    page.click('a:has-text("Register FC")')
    page.wait_for_selector("h1:text-is('Register a flight controller')")
    page.fill(field("Hardware revision"), "rev-D")
    page.fill(field("PCB batch / panel reference"), "B-2026-99")
    page.click('button:has-text("Register FC")')
    page.wait_for_selector("text=Lifecycle progress", timeout=15000)
    serial = page.locator("h1.mono").inner_text()
    fc_url = page.url
    log(f"FC registered via UI: {serial}")

    advance(page, "Ground Testing")
    log("lifecycle progressed Fabrication -> Ground Testing")

    page.fill(f"{CURRENT} textarea", "No GPS fix after 5 minutes on the pad.")
    page.click(f'{CURRENT} button:has-text("Mark failed")')
    page.wait_for_selector(f'{CURRENT} .tag:has-text("Failed")', timeout=15000)
    log("Ground Testing marked FAILED")

    page.click('a:has-text("Report an issue")')
    page.wait_for_selector("text=Has this happened before?")
    page.fill(field("Title"), "GPS not detected during ground test")
    page.fill(field("Symptoms", "textarea"),
              "GPS module not detected. No satellites, no fix, serial port silent.")
    page.select_option(field("Category", "select"), "HARDWARE")
    page.wait_for_timeout(1500)
    similar = page.locator(card("Has this happened before?")).inner_text()
    assert ("ISS-" in similar or "Known issues" in similar
            or "No similar historical issues found" in similar), similar
    log("similar-issue panel answered live while typing")
    page.select_option(field("Assign to department", "select"), label="Machine Assembly")
    page.click('button:has-text("Create issue")')
    page.wait_for_selector("text=Investigation log", timeout=15000)
    no_error(page, "creating the issue")
    issue_url = page.url
    log(f"issue created from the FC: {page.locator('.page-header .meta-row .mono').inner_text()}")

    page.fill(f'{card("Investigation log")} textarea', "Continuity check shows an open circuit at pin 3.")
    page.click('button:has-text("Add note")')
    page.wait_for_selector("text=open circuit at pin 3", timeout=15000)
    log("investigation note added; confirmation shown as a toast")

    page.select_option(f'{card("Reassignment history")} select', label="Hardware Rework")
    page.fill(f'{card("Reassignment history")} input', "Open circuit at the connector.")
    page.click('button:has-text("Reassign")')
    message = expect_error(page, "technician reassigning another department's issue")
    assert len(reassignment_entries(page)) == 1, "a refused reassignment was recorded"
    log(f"RBAC upheld in the UI: technician refused — \"{message[:60]}\"")

    login(page, "hw.lead")
    go(page, issue_url.replace(BASE, ""), "text=Reassignment history")
    page.wait_for_selector(f'{card("Similar past issues")} >> text=ISS-', timeout=15000)
    log("a head sees prior issues from other departments in the similar panel")
    page.select_option(f'{card("Reassignment history")} select', label="Hardware Rework")
    page.fill(f'{card("Reassignment history")} input', "Open circuit at the connector - hardware.")
    page.click('button:has-text("Reassign")')
    page.wait_for_function("() => document.querySelectorAll('ul.timeline li').length >= 2", timeout=15000)
    no_error(page, "lead reassigning the issue")
    assert "Hardware Rework" in reassignment_entries(page)[-1]
    log("issue reassigned by a head, reason recorded in the history")

    rc = card("Root cause & resolution")
    page.fill(f"{rc} textarea >> nth=0", "Cold solder joint on GPS connector pin 3.")
    page.select_option(f"{rc} select", label="Machine Assembly")
    page.fill(f"{rc} textarea >> nth=1", "Reflowed the joint and confirmed continuity.")
    page.click('button:has-text("Mark resolved")')
    page.wait_for_selector('.page-header .tag:has-text("Resolved")', timeout=15000)
    no_error(page, "recording the resolution")
    log("root cause + resolution recorded (root-cause dept differs from discovery)")

    page.select_option('select[aria-label="Participant"]', label="Sanjay Kumar")
    page.select_option('select[aria-label="Participant role"]', "verifier")
    page.click(f'{card("Participants")} button:has-text("Add")')
    page.wait_for_selector(f'{card("Participants")} >> text=Sanjay Kumar · Verifier', timeout=15000)
    log("head assigned the test engineer as independent verifier")

    login(page, "test.eng1")
    go(page, issue_url.replace(BASE, ""), "text=Investigation log")
    page.click('button:has-text("Verify fix")')
    page.wait_for_selector('.page-header .tag:has-text("Verified")', timeout=15000)
    page.click('button:has-text("Close issue")')
    page.wait_for_selector('.page-header .tag:has-text("Closed")', timeout=15000)
    no_error(page, "closing the issue")
    shot(page, "issue-closed")
    log("fix verified by a second person, then closed")

    go(page, fc_url.replace(BASE, ""), "text=Lifecycle progress")
    page.click('[role=tab]:has-text("Stages")')
    page.click('button:has-text("Add rework")')
    page.wait_for_selector("text=What was reworked")
    page.fill("form textarea", "Reflowed GPS connector pin 3, re-inspected under scope.")
    page.select_option(f'form {field("Return the FC to", "select")}', label="Machine Assembly / Soldering")
    page.click('button:has-text("Record rework")')
    page.wait_for_function(
        "() => /machine/i.test([...document.querySelectorAll('.card')].find(x =>"
        " x.querySelector('h2')?.textContent === 'Current stage')?.querySelector('p strong')?.textContent)",
        timeout=15000)
    no_error(page, "recording the rework")
    log(f"rework recorded; FC routed back to {current_stage(page)}")

    advance(page, "Manager Approval")
    log("FC re-run through the lifecycle to Manager Approval")

    page.click('[role=tab]:has-text("Timeline")')
    timeline = page.locator(".timeline").inner_text().lower()
    for expected in ["registered", "failed", "opened", "reassigned", "rework", "verified"]:
        assert expected in timeline, f"timeline missing '{expected}'"
    log("timeline has registration, failure, issue, reassignment, rework, verification")
    page.click('[role=tab]:has-text("Audit")')
    page.wait_for_selector(".card table >> text=Flight", timeout=15000)
    log("FC audit tab loads on demand")

    assert page.locator('button:has-text("Approve for release")').count() == 0
    log("technician is not offered the manager approval action")

    login(page, "mgr.rao")
    go(page, fc_url.replace(BASE, ""), "text=Lifecycle progress")
    page.click('button:has-text("Approve for release")')
    page.wait_for_selector('.page-header .tag:has-text("Approved")', timeout=15000)
    no_error(page, "manager approval")
    shot(page, "fc-approved")
    log("manager approved the FC for release")

    stored = page.evaluate("""() => JSON.stringify({
        local: Object.keys(localStorage), session: Object.keys(sessionStorage),
        cookies: document.cookie })""")
    assert '"local":[]' in stored and '"session":[]' in stored, stored
    assert "sessionid" not in stored, f"session cookie readable by script: {stored}"
    log("no token in localStorage/sessionStorage; session cookie is HttpOnly")

finish()
