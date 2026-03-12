#!/usr/bin/env python3
"""Inspect the Jobs / Diffs Dashboard page to get actual DOM selectors."""

import os
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

load_dotenv()

def main():
    pw = sync_playwright().start()
    browser = pw.chromium.launch(headless=False, slow_mo=100)
    context = browser.new_context(viewport={"width": 1440, "height": 900})
    page = context.new_page()

    # Login
    page.goto("https://admin.probook.ai", wait_until="networkidle")
    email = page.locator('input[type="email"], input[name="email"], input[id*="email"]').first
    email.fill(os.getenv("PROBOOK_USERNAME", ""))
    pw_field = page.locator('input[type="password"]').first
    pw_field.fill(os.getenv("PROBOOK_PASSWORD", ""))
    page.locator('button[type="submit"]').first.click()
    page.wait_for_timeout(5000)

    # Select customer
    page.get_by_text("Dyess Air", exact=False).first.click()
    page.wait_for_timeout(2000)

    # Navigate: Audit > AI Validation
    page.get_by_text("Audit", exact=False).first.click()
    page.wait_for_timeout(2000)
    page.get_by_text("AI Validation", exact=False).first.click()
    page.wait_for_timeout(2000)

    # Click "Jobs / Diffs Dashboard" tab
    page.get_by_text("Jobs / Diffs Dashboard", exact=False).first.click()
    page.wait_for_timeout(3000)

    # Screenshot the page
    page.screenshot(path="inspect_diffs_dashboard.png", full_page=True)
    print("Saved: inspect_diffs_dashboard.png")

    # Dump all visible interactive elements
    print("\n=== ALL BUTTONS ===")
    buttons = page.locator('button')
    for i in range(min(buttons.count(), 30)):
        try:
            text = buttons.nth(i).text_content().strip()[:80]
            visible = buttons.nth(i).is_visible()
            print(f"  [{i}] visible={visible} text='{text}'")
        except:
            pass

    print("\n=== ALL SELECT/DROPDOWN ===")
    selects = page.locator('select, [role="combobox"], [role="listbox"]')
    for i in range(min(selects.count(), 20)):
        try:
            html = selects.nth(i).evaluate("e => e.outerHTML.substring(0, 500)")
            print(f"  [{i}] {html}")
        except:
            pass

    print("\n=== ALL INPUTS ===")
    inputs = page.locator('input, textarea')
    for i in range(min(inputs.count(), 20)):
        try:
            html = inputs.nth(i).evaluate("e => e.outerHTML.substring(0, 300)")
            visible = inputs.nth(i).is_visible()
            print(f"  [{i}] visible={visible} {html}")
        except:
            pass

    # Dump the main content area HTML
    main_html = page.evaluate("""
        () => {
            // Get the main content area
            const content = document.querySelector('main') || document.querySelector('[class*="content"]') || document.body;
            return content.innerHTML.substring(0, 10000);
        }
    """)
    with open("inspect_diffs_content.html", "w") as f:
        f.write(main_html)
    print("\nSaved: inspect_diffs_content.html")

    # Also check if there are any job rows visible
    print("\n=== LOOKING FOR JOB DATA ===")
    for selector in ['tr', 'table', '[class*="job"]', '[class*="Job"]', '[class*="row"]',
                     '[class*="card"]', '[class*="diff"]', '[class*="Diff"]',
                     '[data-testid]', '[class*="accordion"]', '[class*="Accordion"]']:
        count = page.locator(selector).count()
        if count > 0:
            print(f"  '{selector}' => {count} matches")
            # Show first few texts
            for j in range(min(count, 3)):
                try:
                    text = page.locator(selector).nth(j).text_content().strip()[:100]
                    print(f"    [{j}] '{text}'")
                except:
                    pass

    browser.close()
    pw.stop()

if __name__ == "__main__":
    main()
