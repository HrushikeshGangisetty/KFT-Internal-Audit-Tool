"""Configuration and administration: Firmware catalogue, Test configuration,
FC models and Accounts — and that each is hidden from roles that may not use it."""
from common import (browser, card, dialog, field, finish, log, login, nav, nav_links, no_error,
                    shot, toast)

with browser(allowed_status=("404", "403", "409")) as page:
    # ---- Firmware department: catalogue ----
    login(page, "fw.eng")
    links = nav_links(page)
    assert "Firmware" in links, links
    assert "Test configuration" not in links and "Accounts" not in links, links
    log("firmware engineer sees Firmware, not the manager/admin entries")

    nav(page, "Firmware")
    page.click('button:has-text("Add firmware build")')
    page.fill(field("Firmware name"), "KFT-FC")
    page.fill(field("Type / format"), "APJ")
    page.fill(field("Version / build id"), "4.5.0-e2e")
    page.fill(field("Git SHA / source reference"), "c0ffee123456")
    page.fill(field("Description", "textarea"), "Dual-GPS blending and a new baro driver.")
    page.check('label.row:has-text("Signed") input')
    page.click('button:has-text("Add build")')
    toast(page, "added to the catalogue")
    no_error(page, "adding a firmware build")
    row = 'tr:has-text("4.5.0-e2e")'
    page.wait_for_selector(row)
    log("firmware build added; confirmation shown as a toast")

    page.click(f'{row} button:has-text("Retire")')
    page.wait_for_selector(f'{row} .tag:has-text("retired")')
    page.click(f'{row} button:has-text("Restore")')
    page.wait_for_selector(f'{row} .tag:has-text("active")')
    page.fill('input[placeholder^="Search name"]', "4.5.0-e2e")
    page.wait_for_function("() => document.querySelectorAll('.card tbody tr').length === 1", timeout=10000)
    shot(page, "firmware")
    log("build retired, restored, and found with the debounced catalogue search")

    # ---- Manager: test configuration and FC models ----
    login(page, "mgr.rao")
    links = nav_links(page)
    assert "Test configuration" in links and "FC models" in links, links
    assert "Firmware" not in links and "Accounts" not in links, links
    log("manager sees Test configuration and FC models, not Firmware or Accounts")

    nav(page, "Test configuration")
    page.wait_for_selector("text=Add a test")
    before = page.locator(".filter-bar .tag.info").inner_text()
    page.fill(field("Test name / label"), "Geofence breach triggers RTL")
    page.fill(field("Instructions for the tester", "textarea"), "Fly at the fence at 5 m/s; RTL must engage.")
    page.click('button:has-text("Add test")')
    toast(page, "Test added.")
    page.wait_for_selector('tr:has-text("Geofence breach triggers RTL")')
    page.wait_for_function("v => document.querySelector('.filter-bar .tag.info')?.textContent !== v",
                           arg=before, timeout=10000)
    log(f"test added and checklist version bumped ({before} -> "
        f"{page.locator('.filter-bar .tag.info').inner_text()})")
    page.click('tr:has-text("Geofence breach triggers RTL") button:has-text("Disable")')
    page.wait_for_selector('tr:has-text("Geofence breach triggers RTL") .tag:has-text("disabled")')
    page.click('tr:has-text("Geofence breach triggers RTL") button:has-text("Remove")')
    dialog(page, "Cancel")
    assert page.locator('tr:has-text("Geofence breach triggers RTL")').count() == 1
    log("test disabled; Remove asks first and Cancel keeps it")

    nav(page, "FC models")
    page.fill(field("Model name"), "KFT-FC-PRO")
    assert page.locator(field("Code")).input_value() == "kft-fc-pro"
    page.click('button:has-text("Add model")')
    toast(page, "KFT-FC-PRO added.")
    page.click('tr:has-text("KFT-FC-PRO") button:has-text("Archive")')
    dialog(page, "Archive")
    page.wait_for_selector('tr:has-text("KFT-FC-PRO") .tag:has-text("archived")')
    no_error(page, "archiving an FC model")
    shot(page, "fc-models")
    log("FC model added (code derived from name) and archived after confirmation")

    # ---- Admin: accounts ----
    login(page, "admin")
    nav(page, "Accounts")
    page.wait_for_selector(f'{card("Users")} table')
    page.click('[role=tab]:has-text("Departments")')
    page.wait_for_selector(f'{card("Departments")} table')
    page.click('[role=tab]:has-text("Software versions")')
    page.fill(f'{card("Add a version")} {field("Version")}', "9.9.9-e2e")
    page.click('button:has-text("Add version")')
    page.wait_for_selector('td:text-is("9.9.9-e2e")', timeout=10000)
    no_error(page, "adding a software version")
    log("admin sees users and departments and adds a software version")

    # ---- A technician sees none of it ----
    login(page, "hw.tech1")
    links = nav_links(page)
    for forbidden in ("Firmware", "Test configuration", "FC models", "Accounts"):
        assert forbidden not in links, f"technician sees {forbidden}"
    log("technician sees no configuration entries")

finish()
