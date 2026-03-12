#!/usr/bin/env python3
"""Full flow test: select dataset + config, run validation tab, then diffs dashboard."""

import os
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

load_dotenv()

def main():
    pw = sync_playwright().start()
    browser = pw.chromium.launch(headless=False, slow_mo=100)
    context = browser.new_context(viewport={"width": 1440, "height": 900})
    page = context.new_page()

    # Login + navigate
    page.goto("https://admin.probook.ai", wait_until="networkidle")
    page.locator('input[type="email"], input[id*="email"]').first.fill(os.getenv("PROBOOK_USERNAME", ""))
    page.locator('input[type="password"]').first.fill(os.getenv("PROBOOK_PASSWORD", ""))
    page.locator('button[type="submit"]').first.click()
    page.wait_for_timeout(5000)
    page.get_by_text("Dyess Air", exact=False).first.click()
    page.wait_for_timeout(2000)
    page.get_by_role("tab", name="Audit").click()
    page.wait_for_timeout(2000)
    page.get_by_role("tab", name="AI Validation").click()
    page.wait_for_timeout(2000)

    # Step 1: Select first dataset card
    print("=== STEP 1: Select dataset ===")
    dataset_card = page.locator('[data-slot="button"]').filter(has_text="Past Dataset").first
    dataset_card.click()
    page.wait_for_timeout(1000)
    print(f"  Dataset selected: bg-primary={'bg-primary' in dataset_card.evaluate('e => e.className')}")

    # Step 2: Select Production Version 3 config
    print("=== STEP 2: Select rule config ===")
    version3_div = page.locator('div.cursor-pointer').filter(has_text="Version 3").first
    version3_div.scroll_into_view_if_needed()
    page.wait_for_timeout(500)
    version3_div.click()
    page.wait_for_timeout(1000)
    parent_class = version3_div.evaluate("e => e.parentElement?.className || ''")
    print(f"  Rule config selected: border-primary={'border-primary' in parent_class}")
    page.screenshot(path="flow_step2_selected.png", full_page=True)

    # Step 3: Click "Run AI Validation" sub-tab
    print("=== STEP 3: Go to Run AI Validation tab ===")
    page.get_by_text("Run AI Validation", exact=True).first.click()
    page.wait_for_timeout(3000)
    page.screenshot(path="flow_step3_run_tab.png", full_page=True)
    print("  Saved: flow_step3_run_tab.png")

    # Dump what's on this page
    print("\n  Visible buttons on Run AI Validation tab:")
    btns = page.locator('[data-slot="button"], button')
    for i in range(btns.count()):
        try:
            if btns.nth(i).is_visible():
                text = btns.nth(i).text_content().strip()[:60]
                if text and text not in ["Forecasts", "7 Day Call Board", "Audit", "Settings",
                                         "Utilization", "Job History", "Messages", "AI Validation", "Logout"]:
                    print(f"    [{i}] '{text}'")
        except:
            pass

    # Look for select/dropdown elements (for dataset/config selection on this page)
    selects = page.locator('select, [data-slot="select"]')
    print(f"\n  Select elements: {selects.count()}")
    for i in range(selects.count()):
        try:
            html = selects.nth(i).evaluate("e => e.outerHTML.substring(0, 300)")
            print(f"    [{i}] {html}")
        except:
            pass

    # DON'T click Run (we don't want to actually run it)
    # Just go to Jobs / Diffs Dashboard
    print("\n=== STEP 4: Go to Jobs / Diffs Dashboard ===")
    page.get_by_text("Jobs / Diffs Dashboard", exact=True).first.click()
    page.wait_for_timeout(5000)
    page.screenshot(path="flow_step4_diffs.png", full_page=True)
    print("  Saved: flow_step4_diffs.png")

    # Check content
    content_text = page.locator('[data-slot="card-content"]').all_text_contents()
    for i, t in enumerate(content_text[:5]):
        print(f"  Card content [{i}]: '{t.strip()[:200]}'")

    # Dump the HTML of the diffs page content
    diffs_html = page.evaluate("""
        () => {
            const panels = document.querySelectorAll('[role="tabpanel"]:not([hidden])');
            let html = '';
            panels.forEach(p => { html += p.innerHTML; });
            return html.substring(0, 15000);
        }
    """)
    with open("flow_step4_diffs.html", "w") as f:
        f.write(diffs_html)
    print("  Saved: flow_step4_diffs.html")

    browser.close()
    pw.stop()

if __name__ == "__main__":
    main()
