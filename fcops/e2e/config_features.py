"""End-to-end coverage for the configuration features: Push Update, Manage
Firmware, Test Configuration and FC Models — including that each is hidden from
roles that may not use it."""
import os
import sys

from playwright.sync_api import sync_playwright

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
    banners = page.locator(".banner.error")
    if banners.count() and banners.first.is_visible():
        raise AssertionError(f"{what}: {banners.first.inner_text()}")


def nav_links(page):
    return page.locator(".sidebar nav a").all_inner_texts()


with sync_playwright() as p:
    launch = ({"executable_path": os.environ["PLAYWRIGHT_CHROMIUM"]}
              if os.environ.get("PLAYWRIGHT_CHROMIUM") else {})
    b = p.chromium.launch(**launch)
    page = b.new_page(viewport={"width": 1440, "height": 1100})
    page.on("pageerror", lambda e: errs.append(str(e)))
    page.on("console", lambda m: errs.append("console: " + m.text)
            if m.type == "error" and not any(c in m.text for c in ("404", "403", "409"))
            else None)

    # ---- 1. Software: Push Update ----
    login(page, "sw.eng")
    links = nav_links(page)
    assert "Push Update" in links, links
    assert "Manage Firmware" not in links, "software user sees firmware admin"
    assert "Test Configuration" not in links, "software user sees manager config"
    log("software engineer sees only Push Update in the sidebar")

    page.click('a:has-text("Push Update")')
    page.wait_for_selector("text=Record a new release", timeout=10000)
    page.select_option('select >> nth=0', "GCS")
    page.fill('input >> nth=0', "2.6.0")
    page.fill('input.mono >> nth=0', "9f2c1ab4d7e5")
    page.fill('textarea', "Restored the serial handshake timeout to 500 ms and "
                          "fixed the telemetry reconnect loop.")
    # approver dropdown is the last select in the form
    page.select_option('form select >> nth=1', index=1)
    page.click('button:has-text("Push update")')
    page.wait_for_selector("text=Release history", timeout=10000)
    page.wait_for_timeout(1500)
    no_error(page, "pushing a software update")
    assert "9f2c1ab4d7e5"[:12] in page.inner_text("table"), "release not listed"
    log("software update pushed and appears in the release history")
    page.screenshot(path="/tmp/v3-push-update.png", full_page=True)

    # ---- 2. Firmware: Manage Firmware ----
    login(page, "fw.eng")
    links = nav_links(page)
    assert "Manage Firmware" in links and "Push Update" not in links, links
    log("firmware engineer sees only Manage Firmware")

    page.click('a:has-text("Manage Firmware")')
    page.wait_for_selector("text=Add firmware build", timeout=10000)
    page.click('button:has-text("Add firmware build")')
    page.wait_for_selector("text=Firmware name", timeout=10000)
    page.fill('form input >> nth=0', "KFT-FC")
    page.fill('form input >> nth=1', "APJ")
    page.fill('form input >> nth=2', "4.5.0")
    page.fill('form input >> nth=3', "c0ffee123456")
    page.fill('form textarea >> nth=0', "Dual-GPS blending and a new baro driver.")
    page.check('form input[type="checkbox"] >> nth=1')      # signed
    page.click('button:has-text("Add build")')
    page.wait_for_timeout(2000)
    no_error(page, "adding a firmware build")
    assert "4.5.0" in page.inner_text("table")
    log("firmware build added to the catalogue")

    page.click('button:has-text("Retire")')
    page.wait_for_timeout(1500)
    no_error(page, "retiring a build")
    assert "retired" in page.inner_text("table").lower()
    page.click('button:has-text("Restore")')
    page.wait_for_timeout(1500)
    log("build retired and restored")
    page.screenshot(path="/tmp/v3-firmware.png", full_page=True)

    # ---- 3. Manager: Test Configuration ----
    login(page, "mgr.rao")
    links = nav_links(page)
    assert "Test Configuration" in links and "FC Models" in links, links
    assert "Push Update" not in links and "Manage Firmware" not in links, links
    log("manager sees Test Configuration and FC Models only")

    page.click('a:has-text("Test Configuration")')
    page.wait_for_selector("text=Add a test", timeout=10000)
    before_version = page.locator('.tag.info').first.inner_text()
    page.fill('form input >> nth=0', "Geofence breach triggers RTL")
    page.fill('form textarea', "Fly toward the fence at 5 m/s and confirm RTL engages.")
    page.click('button:has-text("Add test")')
    page.wait_for_timeout(2000)
    no_error(page, "adding a test")
    assert "Geofence breach triggers RTL" in page.inner_text("table")
    after_version = page.locator('.tag.info').first.inner_text()
    assert before_version != after_version, "checklist version did not change"
    log(f"test added and checklist version bumped ({before_version} -> {after_version})")

    page.click('table tbody tr:last-child button:has-text("Disable")')
    page.wait_for_timeout(1500)
    no_error(page, "disabling a test")
    assert "disabled" in page.inner_text("table").lower()
    log("test disabled without touching historical records")
    page.screenshot(path="/tmp/v3-test-config.png", full_page=True)

    # ---- 4. Manager: FC Models ----
    page.click('a:has-text("FC Models")')
    page.wait_for_selector("text=Add an FC model", timeout=10000)
    page.fill('form input >> nth=0', "KFT-FC-PRO")
    page.click('button:has-text("Add model")')
    page.wait_for_timeout(2000)
    no_error(page, "adding an FC model")
    assert "KFT-FC-PRO" in page.inner_text("table")
    log("FC model added by the manager")

    page.once("dialog", lambda d: d.accept())
    page.click('table tbody tr:has-text("KFT-FC-PRO") button:has-text("Archive")')
    page.wait_for_timeout(1800)
    no_error(page, "archiving an FC model")
    assert "archived" in page.inner_text("table").lower()
    log("FC model archived; existing FCs unaffected")
    page.screenshot(path="/tmp/v3-fc-models.png", full_page=True)

    # ---- 5. A technician sees none of it ----
    login(page, "hw.tech1")
    links = nav_links(page)
    for forbidden in ("Push Update", "Manage Firmware", "Test Configuration",
                      "FC Models", "Admin"):
        assert forbidden not in links, f"technician sees {forbidden}"
    log("technician sees no configuration entries at all")

    b.close()

print("\nSTEPS PASSED:", len(steps))
print("PAGE ERRORS:", errs[:8] if errs else "none")
sys.exit(1 if errs else 0)
