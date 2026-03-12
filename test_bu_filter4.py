#!/usr/bin/env python3
"""Test: click BU Trigger, dump the dropdown structure including buttons."""
import json, time
from roi_scraper import ServiceTitanScraper

def main():
    scraper = ServiceTitanScraper("george_eli", "@esT0frEtEk5dLYEXi47", log_fn=print)
    try:
        scraper.launch()
        scraper.login(mfa_code_fn=lambda: input("MFA: "))

        scraper.page.goto(
            "https://go.servicetitan.com/#/new/reports/354643851",
            wait_until="domcontentloaded", timeout=15000
        )
        time.sleep(5)

        # Click the Trigger element to open BU dropdown
        trigger = scraper.page.locator('.Trigger.Trigger--s-medium').first
        # But there might be multiple triggers (one per filter). Find the one inside the BU filter.
        bu_filter = scraper.page.locator('[data-criteria-name="BusinessUnitId"]')
        if bu_filter.count() > 0:
            trigger = bu_filter.first.locator('.Trigger')
            print(f"Found BU filter trigger via data-criteria-name")
        trigger.click()
        time.sleep(3)

        # Get all BU names and the full dropdown structure
        dropdown = scraper.page.evaluate('''() => {
            const result = {};

            // All visible checkboxes with their labels
            const cbs = [];
            document.querySelectorAll('input[type="checkbox"]').forEach(el => {
                const r = el.getBoundingClientRect();
                if (r.width === 0 && r.height === 0) return;
                const label = el.closest('label');
                const text = label ? label.textContent?.trim() : '';
                if (text && text !== 'Include Inactive Technicians') {
                    cbs.push({text: text, checked: el.checked, y: Math.round(r.y)});
                }
            });
            result.bus = cbs;

            // Search input in the dropdown
            const inputs = [];
            document.querySelectorAll('input[type="text"]').forEach(el => {
                const r = el.getBoundingClientRect();
                if (r.width > 0 && r.height > 0 && r.y > 300 && r.y < 400) {
                    inputs.push({
                        placeholder: el.placeholder, value: el.value,
                        cls: (typeof el.className === 'string' ? el.className : '').substring(0, 80),
                        x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width),
                    });
                }
            });
            result.searchInputs = inputs;

            // Buttons in the dropdown area
            const buttons = [];
            document.querySelectorAll('button, a, [role="button"]').forEach(el => {
                const r = el.getBoundingClientRect();
                if (r.width > 0 && r.height > 0 && r.x > 400 && r.x < 800 && r.y > 300) {
                    buttons.push({
                        tag: el.tagName, text: el.textContent?.trim().substring(0, 40),
                        x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height),
                    });
                }
            });
            result.buttons = buttons;

            // "Select All" / "Clear" / "Apply" links
            const links = [];
            document.querySelectorAll('a, button, span[class*="link" i], [class*="action" i]').forEach(el => {
                const r = el.getBoundingClientRect();
                if (r.width > 0 && r.height > 0) {
                    const text = el.textContent?.trim() || '';
                    if (text.match(/select all|clear|apply|done|cancel|reset/i) && text.length < 20) {
                        links.push({tag: el.tagName, text: text, x: Math.round(r.x), y: Math.round(r.y)});
                    }
                }
            });
            result.actionLinks = links;

            return result;
        }''')

        print(f"\nBU options ({len(dropdown['bus'])}):")
        for bu in dropdown['bus']:
            print(f"  {'[x]' if bu['checked'] else '[ ]'} {bu['text']} (y={bu['y']})")

        print(f"\nSearch inputs ({len(dropdown['searchInputs'])}):")
        for inp in dropdown['searchInputs']:
            print(f"  [{inp['x']},{inp['y']} w={inp['w']}] placeholder='{inp['placeholder']}' cls={inp['cls'][:50]}")

        print(f"\nButtons ({len(dropdown['buttons'])}):")
        for btn in dropdown['buttons']:
            print(f"  [{btn['x']},{btn['y']} {btn['w']}x{btn['h']}] {btn['tag']} '{btn['text']}'")

        print(f"\nAction links ({len(dropdown['actionLinks'])}):")
        for lnk in dropdown['actionLinks']:
            print(f"  [{lnk['x']},{lnk['y']}] {lnk['tag']} '{lnk['text']}'")

        # Now test: type in search to filter, then check a specific BU
        print("\n--- Testing search filter ---")
        search_input = scraper.page.locator('input[type="text"]').nth(1)  # second text input (first is date)
        search_input.fill("HVAC")
        time.sleep(2)

        # Check what's visible now
        filtered = scraper.page.evaluate('''() => {
            const cbs = [];
            document.querySelectorAll('input[type="checkbox"]').forEach(el => {
                const r = el.getBoundingClientRect();
                if (r.width === 0 && r.height === 0) return;
                const label = el.closest('label');
                const text = label ? label.textContent?.trim() : '';
                if (text && text !== 'Include Inactive Technicians') {
                    cbs.push({text: text, checked: el.checked, visible: r.y > 0 && r.y < 900});
                }
            });
            return cbs;
        }''')

        print(f"\nFiltered BU options ({len(filtered)}):")
        for bu in filtered:
            print(f"  {'[x]' if bu['checked'] else '[ ]'} visible={bu['visible']} {bu['text']}")

    finally:
        scraper.close()

if __name__ == "__main__":
    main()
