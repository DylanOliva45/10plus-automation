#!/usr/bin/env python3
"""
Quick test script to debug the create_report flow step by step.
Saves DOM snapshots at each stage.
"""
import json
import time
from roi_scraper import ServiceTitanScraper

def dump_page(page, label):
    """Dump visible elements on the page."""
    info = page.evaluate('''() => {
        const result = {url: location.href, title: document.title};

        // All visible buttons
        const buttons = [];
        document.querySelectorAll('button, [role="button"]').forEach(el => {
            const r = el.getBoundingClientRect();
            if (r.width > 0 && r.height > 0) {
                buttons.push({text: el.textContent.trim().substring(0, 60), x: Math.round(r.x), y: Math.round(r.y), cls: el.className.substring(0, 60)});
            }
        });
        result.buttons = buttons;

        // All visible links
        const links = [];
        document.querySelectorAll('a').forEach(el => {
            const r = el.getBoundingClientRect();
            if (r.width > 0 && r.height > 0) {
                links.push({text: el.textContent.trim().substring(0, 60), href: el.href.substring(0, 80)});
            }
        });
        result.links = links;

        // All inputs
        const inputs = [];
        document.querySelectorAll('input, select').forEach(el => {
            const r = el.getBoundingClientRect();
            if (r.width > 0 && r.height > 0) {
                inputs.push({type: el.type, name: el.name, placeholder: el.placeholder, value: el.value.substring(0, 40), cls: el.className.substring(0, 60)});
            }
        });
        result.inputs = inputs;

        // Checkboxes specifically
        const cbs = [];
        document.querySelectorAll('input[type="checkbox"]').forEach(el => {
            const parent = el.closest('[class*="Card"], [class*="Togglebox"], [class*="toggle"], label, div');
            const parentText = parent ? parent.textContent.trim().substring(0, 50) : '';
            cbs.push({checked: el.checked, parentText: parentText, cls: (parent||el).className.substring(0, 60)});
        });
        result.checkboxes = cbs.slice(0, 20);

        // Elements with toggle/card classes
        const toggles = [];
        document.querySelectorAll('[class*="toggle" i], [class*="Toggle"], [class*="Card"], [class*="column"]').forEach(el => {
            const r = el.getBoundingClientRect();
            if (r.width > 0 && r.height > 0 && toggles.length < 20) {
                toggles.push({tag: el.tagName, text: el.textContent.trim().substring(0, 50), cls: el.className.substring(0, 80), x: Math.round(r.x), y: Math.round(r.y)});
            }
        });
        result.toggleElements = toggles;

        return result;
    }''')

    with open(f'/tmp/roi_debug_{label}.json', 'w') as f:
        json.dump(info, f, indent=2)

    print(f"\n{'='*60}")
    print(f"STAGE: {label}")
    print(f"URL: {info['url']}")
    print(f"Buttons ({len(info['buttons'])}):")
    for b in info['buttons'][:15]:
        print(f"  [{b['x']},{b['y']}] {b['text']}")
    print(f"Inputs ({len(info['inputs'])}):")
    for i in info['inputs'][:10]:
        print(f"  {i['type']} name={i['name']} placeholder={i['placeholder']}")
    print(f"Checkboxes ({len(info['checkboxes'])}):")
    for c in info['checkboxes'][:10]:
        print(f"  checked={c['checked']} text={c['parentText']}")
    print(f"Toggle/Card elements ({len(info['toggleElements'])}):")
    for t in info['toggleElements'][:10]:
        print(f"  [{t['x']},{t['y']}] {t['tag']}: {t['text'][:40]} cls={t['cls'][:50]}")


def main():
    scraper = ServiceTitanScraper(
        st_username="george_eli",
        st_password="@esT0frEtEk5dLYEXi47",
        log_fn=print,
    )

    try:
        scraper.launch()
        scraper.login(mfa_code_fn=lambda: input("Enter MFA code: "))

        # Step 1: Go to All Reports
        print("\n>>> STEP 1: Navigate to All Reports")
        scraper.page.goto(
            "https://go.servicetitan.com/#/new/reports/all",
            wait_until="domcontentloaded",
            timeout=15000,
        )
        time.sleep(4)
        dump_page(scraper.page, "01_all_reports")

        # Step 2: Click Create Report
        print("\n>>> STEP 2: Click Create Report")
        create_btn = scraper.page.wait_for_selector(
            'button:has-text("Create Report")',
            timeout=10000,
        )
        create_btn.click()
        time.sleep(4)
        dump_page(scraper.page, "02_after_create_click")

        # Step 3: Try to find and click "Technicians"
        print("\n>>> STEP 3: Looking for Technicians category")
        # Try multiple approaches
        for selector in [
            'text="Technicians"',
            'button:has-text("Technicians")',
            'div:has-text("Technicians")',
            'a:has-text("Technicians")',
            'span:has-text("Technicians")',
            'li:has-text("Technicians")',
        ]:
            el = scraper.page.query_selector(selector)
            if el:
                box = el.bounding_box()
                print(f"  Found with '{selector}' at {box}")
                el.click()
                time.sleep(3)
                break
            else:
                print(f"  Not found: {selector}")

        dump_page(scraper.page, "03_after_technicians")

        # Step 4: Try to find Technician Performance template
        print("\n>>> STEP 4: Looking for Technician Performance template")
        for selector in [
            'text="Technician Performance"',
            'button:has-text("Technician Performance")',
            'div:has-text("Technician Performance")',
            'span:has-text("Technician Performance")',
            'li:has-text("Technician Performance")',
        ]:
            el = scraper.page.query_selector(selector)
            if el:
                box = el.bounding_box()
                print(f"  Found with '{selector}' at {box}")
                el.click()
                time.sleep(3)
                break
            else:
                print(f"  Not found: {selector}")

        dump_page(scraper.page, "04_after_template")

        # Step 5: Deselect All
        print("\n>>> STEP 5: Deselect All")
        deselect = scraper.page.query_selector(
            'a:has-text("Deselect All"), button:has-text("Deselect All")'
        )
        if deselect:
            deselect.click()
            time.sleep(2)
            print("  Clicked Deselect All")
        else:
            print("  Deselect All not found")

        dump_page(scraper.page, "05_after_deselect")

        # Step 6: Try searching for "Total Sales"
        print("\n>>> STEP 6: Search for 'Total Sales'")
        search = scraper.page.query_selector('input[placeholder*="Search"]')
        if not search:
            search = scraper.page.query_selector('input[placeholder*="search" i]')
        if search:
            search.fill("Total Sales")
            time.sleep(3)
            print("  Typed 'Total Sales' in search")
        else:
            print("  No search input found!")

        dump_page(scraper.page, "06_after_search")

        # Take a screenshot too
        scraper.page.screenshot(path="/tmp/roi_debug_screenshot.png", full_page=True)
        print("\nScreenshot saved to /tmp/roi_debug_screenshot.png")

        # Keep browser open for manual inspection
        print("\nBrowser is open for inspection. Press Enter to close...")
        input()

    finally:
        scraper.close()


if __name__ == "__main__":
    main()
