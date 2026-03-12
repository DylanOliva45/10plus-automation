#!/usr/bin/env python3
"""Inspect the AI Validation page to find all tabs, buttons, and selectors."""

import os
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

load_dotenv()

def main():
    pw = sync_playwright().start()
    browser = pw.chromium.launch(headless=False, slow_mo=100)
    ctx = browser.new_context(viewport={"width": 1440, "height": 900})
    ctx.set_default_timeout(30_000)
    page = ctx.new_page()

    # Login
    page.goto("https://admin.probook.ai", wait_until="networkidle")
    email = page.locator('input[type="email"], input[name="email"], input[name="username"], input[placeholder*="mail"], input[id*="email"]').first
    email.wait_for(state="visible", timeout=10_000)
    email.fill(os.getenv("PROBOOK_USERNAME", ""))
    pw_field = page.locator('input[type="password"]').first
    pw_field.fill(os.getenv("PROBOOK_PASSWORD", ""))
    page.locator('button[type="submit"], button:has-text("Log in"), button:has-text("Login")').first.click()
    page.wait_for_timeout(5000)

    # Select customer
    page.get_by_text("Dyess Air", exact=False).first.click()
    page.wait_for_timeout(3000)

    # Navigate to Audit > AI Validation
    page.get_by_text("Audit", exact=False).first.click()
    page.wait_for_timeout(2000)
    page.get_by_text("AI Validation", exact=False).first.click()
    page.wait_for_timeout(3000)

    # Screenshot the AI Validation page
    page.screenshot(path="inspect_ai_val_page.png", full_page=True)
    print("Saved: inspect_ai_val_page.png")

    # Dump ALL visible buttons with their text
    buttons = page.locator('button, [role="button"], [role="tab"], a[class*="tab"], a[class*="Tab"]')
    print(f"\n=== ALL BUTTONS/TABS ({buttons.count()}) ===")
    for i in range(min(buttons.count(), 50)):
        el = buttons.nth(i)
        try:
            text = el.text_content().strip()[:100] if el.is_visible() else "(hidden)"
            classes = el.evaluate("e => e.className || ''")
            aria = el.evaluate("e => e.getAttribute('aria-selected') || e.getAttribute('aria-current') || ''")
            print(f"  [{i}] text='{text}' class='{classes[:80]}' aria='{aria}'")
        except:
            pass

    # Dump ALL select/dropdown elements
    selects = page.locator('select, [role="combobox"], [role="listbox"], [class*="MuiSelect"]')
    print(f"\n=== SELECT/DROPDOWN ELEMENTS ({selects.count()}) ===")
    for i in range(min(selects.count(), 20)):
        el = selects.nth(i)
        try:
            html = el.evaluate("e => e.outerHTML.substring(0, 400)")
            print(f"  [{i}] {html}")
        except:
            pass

    # Now try clicking each sub-tab to find the diff/jobs page
    tab_names = ["Jobs", "Diffs", "Dashboard", "Run AI", "Metrics", "Results"]
    for name in tab_names:
        try:
            tab = page.get_by_text(name, exact=False).first
            if tab.is_visible(timeout=1000):
                print(f"\n  Found visible tab/text: '{name}'")
        except:
            pass

    # Click "Run AI Validation" to see that page
    try:
        page.get_by_text("Run AI Validation", exact=False).first.click()
        page.wait_for_timeout(2000)
        page.screenshot(path="inspect_run_validation.png", full_page=True)
        print("\nSaved: inspect_run_validation.png")

        # Check for dataset/config selection state
        highlighted = page.locator('[class*="selected"], [class*="active"], [aria-selected="true"], [class*="Mui-selected"]')
        print(f"\n=== HIGHLIGHTED/SELECTED ELEMENTS ({highlighted.count()}) ===")
        for i in range(min(highlighted.count(), 20)):
            el = highlighted.nth(i)
            try:
                text = el.text_content().strip()[:100]
                classes = el.evaluate("e => e.className")[:80]
                print(f"  [{i}] text='{text}' class='{classes}'")
            except:
                pass
    except Exception as e:
        print(f"Could not click Run AI Validation: {e}")

    # Go back to Dataset Builder and look at existing datasets + configs
    try:
        page.get_by_text("Dataset Builder", exact=False).first.click()
        page.wait_for_timeout(2000)
        page.screenshot(path="inspect_dataset_builder2.png", full_page=True)
        print("\nSaved: inspect_dataset_builder2.png")

        # Dump the main content area HTML (trimmed)
        main_html = page.evaluate("""
            () => {
                const main = document.querySelector('main, [class*="content"], [class*="Content"]');
                return main ? main.innerHTML.substring(0, 5000) : document.body.innerHTML.substring(0, 5000);
            }
        """)
        with open("inspect_main_content.html", "w") as f:
            f.write(main_html)
        print("Saved: inspect_main_content.html")
    except Exception as e:
        print(f"Could not inspect dataset builder: {e}")

    browser.close()
    pw.stop()

if __name__ == "__main__":
    main()
