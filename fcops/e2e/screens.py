"""Capture one screenshot per screen for the platform overview document.
Read-only apart from sign-ins. Run after the three walkthroughs, on the same
disposable database, so the screens have data:  python screens.py <out-dir>"""
import os
import sys

from common import BASE, browser, card, go, login

OUT = sys.argv[1] if len(sys.argv) > 1 else "screens"
os.makedirs(OUT, exist_ok=True)


def snap(page, name):
    page.wait_for_timeout(450)  # let entrance animations finish
    page.screenshot(path=os.path.join(OUT, f"{name}.png"))
    print("  shot:", name, flush=True)


def open_first(page, row_text, path):
    go(page, path, ".card tbody tr")
    page.click(f'tr:has-text("{row_text}") td:first-child a')
    page.wait_for_load_state("networkidle")


with browser(allowed_status=("404", "403")) as page:
    page.set_viewport_size({"width": 1440, "height": 900})
    page.goto(BASE + "/login", wait_until="networkidle")
    snap(page, "01-login")

    login(page, "hw.tech1")
    snap(page, "02-home-member")
    go(page, "/report", "text=How urgent is it?")
    snap(page, "05-report")
    go(page, "/tasks", card("Today's update"))
    snap(page, "09-tasks")
    page.set_viewport_size({"width": 390, "height": 844})
    go(page, "/", "h1:has-text('Hello,')")
    snap(page, "27-phone-home")
    page.click('button[aria-label="Menu"]')
    page.wait_for_timeout(300)
    snap(page, "28-phone-menu")
    page.set_viewport_size({"width": 1440, "height": 900})

    login(page, "mgr.rao")
    snap(page, "03-home-manager")
    go(page, "/queue", card("Waiting on you"))
    snap(page, "04-queue")
    go(page, "/issues", ".card tbody tr")
    snap(page, "06-issues")
    open_first(page, "GPS not detected during ground test", "/issues?status=CLOSED")
    page.wait_for_selector("text=Investigation log")
    snap(page, "07-issue-detail")
    go(page, "/tasks?view=team", card("Team progress"))
    snap(page, "10-team-progress")
    go(page, "/fcs", ".card tbody tr")
    snap(page, "13-fcs")
    open_first(page, "Approved", "/fcs")
    page.wait_for_selector("text=Lifecycle progress")
    snap(page, "14-fc-detail")
    page.click('[role=tab]:has-text("Stages")')
    snap(page, "15-fc-stages")
    go(page, "/fcs/new", "text=Unit details")
    snap(page, "16-fc-register")
    go(page, "/known-issues", "text=occurrences")
    snap(page, "19-known-issues")
    go(page, "/search?q=GPS", card("Matching issues") + " tbody tr")
    snap(page, "20-search")
    go(page, "/audit", ".card tbody tr")
    snap(page, "21-activity")
    go(page, "/manager/test-configuration", "text=Add a test")
    snap(page, "22-test-config")
    go(page, "/manager/fc-models", ".card tbody tr")
    snap(page, "23-fc-models")
    page.click('button[aria-label^="Notifications"]')
    page.wait_for_selector(".popover")
    snap(page, "26-notifications")

    login(page, "sw.eng")
    go(page, "/releases", ".card tbody tr")
    snap(page, "11-releases")
    open_first(page, "3.0.0-e2e", "/releases")
    page.wait_for_selector(card("Announcement email"))
    snap(page, "12-release-detail")
    go(page, "/param-compare", "text=Stored dumps")
    snap(page, "17-param-compare")

    login(page, "fw.eng")
    go(page, "/firmware/builds", ".card tbody tr")
    snap(page, "18-firmware")

    login(page, "fw.lead")
    go(page, "/issues/new", "text=Has this happened before?")
    page.fill('.field:has(label:text-is("Title")) >> input', "GPS not detected after flashing")
    page.wait_for_timeout(1500)
    snap(page, "08-fc-issue-similar")

    login(page, "admin")
    go(page, "/admin", card("Users"))
    snap(page, "24-accounts")
print("done:", OUT)
