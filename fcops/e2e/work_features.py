"""Everyday work: quick reports, issue lists with infinite scroll, knowledge
search, queue (acknowledge, handoffs), tasks and daily updates, releases with
dual approval and a synthetic announcement, parameter compare, customers and
deployments, and the phone layout. Expects `.git/uiref_data.py`-style data: 40+ reports, a pending
handoff to Firmware, `sw.lead` as Software head and a sender grant for `sw.eng`."""
import os
import tempfile

from common import (BASE, browser, card, dialog, field, finish, go, log, login, nav, no_error,
                    shot, toast)

ROWS = ".card tbody tr"


def row_count(page):
    return page.locator(ROWS).count()


with browser(allowed_status=("404", "403")) as page:
    # ---- Quick report from Home ----
    login(page, "hw.tech1")
    page.click('a:has-text("Report a problem")')
    page.fill(field("What is the problem?"), "Buzzer stays silent on arming")
    page.fill(field("What did you see?", "textarea"), "No arming tone; LEDs normal.")
    page.click('label.choice:has-text("Urgent")')
    page.click('button:has-text("Send report")')
    page.wait_for_selector("h1:text-is('Buzzer stays silent on arming')", timeout=15000)
    assert "Urgent" in page.locator(".page-header").inner_text()
    buzzer_url = page.url.replace(BASE, "")
    assert page.locator('button:has-text("Propose handoff")').count() == 0, "reporter offered a handoff"
    log("FC-less quick report sent and routed (urgency and owner shown)")

    # ---- Issues list: paging and filters ----
    nav(page, "Issues")
    page.wait_for_selector(ROWS)
    assert row_count(page) == 25, row_count(page)
    assert "Showing 25 of" in page.locator(".load-more").inner_text()
    page.locator(".load-more").scroll_into_view_if_needed()
    page.wait_for_function(f"() => document.querySelectorAll('{ROWS}').length > 25", timeout=10000)
    log(f"issue list pages in on scroll (25 -> {row_count(page)})")
    page.fill('input[type=search]', "Buzzer stays silent")
    page.wait_for_function(f"() => document.querySelectorAll('{ROWS}').length < 25", timeout=10000)
    assert "Buzzer stays silent on arming" in page.locator(".card tbody").inner_text()
    log("full-text filter narrows the list (debounced)")

    # ---- Search from the top bar ----
    page.fill(".topbar-search input", "Paging sample")
    page.press(".topbar-search input", "Enter")
    page.wait_for_url("**/search?q=Paging*")
    page.wait_for_selector(f'{card("Matching issues")} tbody tr', timeout=15000)
    log(f"top-bar search opens Knowledge search with results "
        f"({page.locator(card('Matching issues') + ' .card-actions .tag').inner_text()} matches)")

    nav(page, "Known issues")
    page.wait_for_selector("text=occurrences")
    page.click('button:has-text("Show occurrences") >> nth=0')
    page.wait_for_selector(".reveal table, .reveal .empty", timeout=10000)
    log("known issues list with occurrences expanding on demand")

    nav(page, "Activity log")
    page.wait_for_selector(ROWS)
    page.select_option(field("Action", "select"), "CREATE")
    page.wait_for_function(f"() => [...document.querySelectorAll('{ROWS} td:nth-child(2)')]"
                           ".every(td => td.textContent === 'Create')", timeout=10000)
    log("activity log filters by action")

    # ---- Tasks and daily update ----
    nav(page, "Tasks")
    page.fill(f'{card("New task for me")} {field("Title")}', "Calibrate bench PSU")
    page.click('button:has-text("Add task")')
    page.wait_for_selector('.qrow:has-text("Calibrate bench PSU")', timeout=10000)
    page.select_option('select[aria-label="Status of Calibrate bench PSU"]', "in_progress")
    page.wait_for_selector('.qrow:has-text("Calibrate bench PSU") .tag:has-text("In Progress")', timeout=10000)
    page.select_option(field("Task", "select"), label="Calibrate bench PSU")
    page.fill(field("Progress", "textarea"), "Reference meter borrowed; first two channels done.")
    page.fill(field("Next step"), "Channels 3 and 4")
    page.click('button:has-text("Post update")')
    page.wait_for_selector(f'{card("My recent updates")} >> text=first two channels done', timeout=10000)
    no_error(page, "posting the daily update")
    nav(page, "Home")
    page.wait_for_selector("text=Today's update posted", timeout=10000)
    log("task created, moved to In progress, daily update posted and reflected on Home")

    # ---- Issue detail: propose a handoff (manager) ----
    login(page, "mgr.rao")
    go(page, buzzer_url, card("Actions"))
    page.select_option('select[aria-label="Hand off to"]', label="Firmware")
    page.click('button:has-text("Propose handoff…")')
    dialog(page, "Propose handoff", "Arming tone is driven by firmware.")
    toast(page, "Handoff proposed.")
    page.wait_for_selector("text=is waiting for that team to accept")
    assert page.locator('button:has-text("Propose handoff")').count() == 0
    no_error(page, "proposing a handoff")
    log("manager proposes a handoff to Firmware from issue detail (pending, no second proposal)")

    # ---- Head: queue, handoff, team progress ----
    login(page, "fw.lead")
    page.wait_for_selector(card("Needs attention"))
    nav(page, "My queue")
    page.click('[role=tab]:has-text("Handoffs")')
    page.click('button:has-text("Reject…") >> nth=0')
    dialog(page, "Cancel")
    page.click('.qrow:has-text("Arming tone is driven by firmware") button:text-is("Accept")')
    toast(page, "accepted")
    no_error(page, "accepting a handoff")
    go(page, buzzer_url, card("Actions"))
    assert "Firmware" in page.locator(card("Discovery vs. ownership")).inner_text()
    assert page.locator("text=is waiting for that team to accept").count() == 0
    log("head sees Needs attention; reject asks for a reason (cancelled); accepts the "
        "issue-detail handoff from My queue and the issue moves to Firmware")
    go(page, "/tasks?view=team", card("Team progress"))
    page.wait_for_selector("h3:text-is('No update today')")
    log("team progress view for heads")

    login(page, "mgr.rao")
    nav(page, "My queue")
    page.click('[role=tab]:has-text("To acknowledge")')
    ack = '.qrow-action button:text-is("Acknowledge")'
    page.wait_for_selector(f"{ack}, .empty", timeout=10000)
    if page.locator(ack).count():
        page.click(f"{ack} >> nth=0")
        toast(page, "acknowledged")
        log("manager acknowledged a routed report from the queue")
    else:
        log("manager has nothing awaiting acknowledgement (empty state shown)")

    # ---- Releases: draft, dual approval, announcement ----
    login(page, "sw.eng")
    nav(page, "Releases")
    page.click('button:has-text("Draft a release")')
    page.fill(field("Version"), "3.0.0-e2e")
    page.fill(field("Source reference"), "abc123def456")
    page.fill(field("Recipient notes", "textarea"), "Faster telemetry reconnect.")
    page.fill(field("Internal notes", "textarea"), "INTERNAL-SENTINEL")
    page.click('button:has-text("Save revision 1")')
    page.wait_for_selector("h1:has-text('3.0.0-e2e')", timeout=15000)
    release_url = page.url.replace(BASE, "")
    assert "Not announceable" in page.locator(".page-header").inner_text()
    assert page.locator('button:has-text("Approve as")').count() == 0
    log("software engineer drafts revision 1; cannot approve; not announceable")

    login(page, "sw.lead")
    go(page, release_url, "text=Revision 1")
    page.click('button:has-text("Approve as Software Head")')
    toast(page, "approved as Software Head")
    assert "Not announceable" in page.locator(".page-header").inner_text()
    log("one approval (Software head) does not make it announceable")

    login(page, "mgr.rao")
    go(page, release_url, "text=Revision 1")
    page.click('button:has-text("Approve as Manager")')
    page.wait_for_selector('.page-header .tag:has-text("Can be announced")', timeout=15000)
    log("second approval by a different person (manager) approves the revision")

    login(page, "sw.eng")
    go(page, release_url, card("Announcement email"))
    page.wait_for_selector("text=SYNTHETIC recipients only")
    page.click(f'{card("Announcement email")} button:has-text("Preview")')
    page.wait_for_selector('button:has-text("Send to")', timeout=15000)
    body = page.locator(".email-body").inner_text()
    assert "Faster telemetry reconnect." in body and "INTERNAL-SENTINEL" not in body, body
    log("preview shows the exact email (recipient notes only, no internal notes)")
    page.dblclick('button:has-text("Send to")')
    toast(page, "Announcement sent.")
    page.wait_for_selector(f'{card("Announcement email")} table', timeout=20000)
    assert page.locator('button:has-text("Send to")').count() == 0
    no_error(page, "sending the announcement")
    shot(page, "release-announced")
    log("double-clicked Send produced one campaign with per-recipient delivery rows (console email)")

    page.click('button:has-text("Edit (creates revision 2)")')
    page.fill(field("Recipient notes", "textarea"), "Faster telemetry reconnect and a map fix.")
    page.click('button:has-text("Save new revision")')
    page.wait_for_selector('.page-header .tag:has-text("Not announceable")', timeout=15000)
    page.wait_for_selector("summary:has-text('Earlier revisions (1)')")
    log("editing creates revision 2, which is unapproved and not announceable")

    # ---- Parameter compare ----
    tmp = tempfile.mkdtemp()
    left, right = os.path.join(tmp, "left.param"), os.path.join(tmp, "right.param")
    open(left, "w").write("ATC_RAT_RLL_P,0.135\nATC_RAT_PIT_P,0.135\nGPS_TYPE,1\n")
    open(right, "w").write("ATC_RAT_RLL_P,0.150\nATC_RAT_PIT_P,0.135\nGPS_TYPE,1\nBATT_MONITOR,4\n")
    nav(page, "Test & evidence")
    page.set_input_files("form.card >> nth=0 >> input[type=file] >> nth=0", left)
    page.set_input_files("form.card >> nth=0 >> input[type=file] >> nth=1", right)
    page.click('button:has-text("Compare")')
    page.wait_for_selector('tr:has-text("ATC_RAT_RLL_P")', timeout=15000)
    assert page.locator('tr:has-text("BATT_MONITOR")').count() == 1
    log("parameter compare shows the changed value and the one-sided parameter")

    # ---- Customers and deployments (head-only writes; contacts restricted) ----
    login(page, "fw.lead")
    nav(page, "Customers")
    page.click('button:has-text("Add a customer")')
    page.fill(field("Name"), "E2E Agro Coop")
    page.fill(field("Region"), "Nashik")
    page.click('button:has-text("Save customer")')
    page.wait_for_selector("h1:text-is('E2E Agro Coop')", timeout=15000)
    customer_url = page.url.replace(BASE, "")
    page.click('button:has-text("Add deployment")')
    page.fill(field("Site"), "North orchard")
    page.fill(field("GCS version at handover"), "2.9.1")
    page.wait_for_selector(f'{field("Units", "select")} option')
    first_fc = page.locator(f'{field("Units", "select")} option').first
    serial = first_fc.inner_text()
    page.select_option(field("Units", "select"), first_fc.get_attribute("value"))
    page.click('button:has-text("Save deployment")')
    toast(page, "Deployment added.")
    page.wait_for_selector(f'{card("Deployments")} tr:has-text("North orchard") a:text-is("{serial}")')
    no_error(page, "adding a deployment")
    assert page.locator(card("Contacts")).count() == 0, "contacts shown without the capability"
    log(f"head adds a customer and a deployment with unit {serial} (linked); no contacts card")

    login(page, "hw.tech1")
    go(page, customer_url, f'{card("Deployments")} tr:has-text("North orchard")')
    assert page.locator('button:has-text("Add deployment"), button:has-text("Edit customer")').count() == 0
    log("non-head FC viewer sees the deployment read-only")

    # ---- Notifications, not found ----
    page.click('button[aria-label^="Notifications"]')
    page.wait_for_selector(".popover-head:text-is('Notifications')")
    page.keyboard.press("Escape")
    go(page, "/no-such-page", "text=Page not found")
    log("notifications popover and not-found page")

    # ---- Phone layout ----
    page.set_viewport_size({"width": 375, "height": 812})
    go(page, "/", "h1:has-text('Hello,')")
    assert not page.locator(".sidebar nav").is_visible() or \
        page.evaluate("() => document.querySelector('.sidebar').getBoundingClientRect().right <= 0")
    page.click('button[aria-label="Menu"]')
    page.wait_for_function("() => document.querySelector('.sidebar').getBoundingClientRect().left >= 0")
    page.click('.sidebar nav a:has-text("Issues")')
    page.wait_for_url("**/issues")
    page.wait_for_function("() => !document.querySelector('.app').classList.contains('menu-open')")
    page.wait_for_selector(f"{ROWS}, .card .empty")  # sw.eng may see no issues (team scope)
    overflow = page.evaluate("() => document.documentElement.scrollWidth - document.documentElement.clientWidth")
    assert overflow <= 0, f"horizontal scroll of {overflow}px at 375px"
    shot(page, "phone-issues")
    log("phone width: menu opens the drawer, navigating closes it, no horizontal page scroll")

finish()
