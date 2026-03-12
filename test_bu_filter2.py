#!/usr/bin/env python3
"""Inspect the BU filter: click it open and dump the dropdown DOM."""
import json, time
from roi_scraper import ServiceTitanScraper

def main():
    scraper = ServiceTitanScraper("george_eli", "@esT0frEtEk5dLYEXi47", log_fn=print)
    try:
        scraper.launch()
        scraper.login(mfa_code_fn=lambda: input("MFA: "))

        # Navigate to an existing saved report
        scraper.page.goto(
            "https://go.servicetitan.com/#/new/reports/354643851",
            wait_until="domcontentloaded", timeout=15000
        )
        time.sleep(5)
        print(f"URL: {scraper.page.url}")

        # Take screenshot before clicking
        scraper.page.screenshot(path="/tmp/bu_before.png")
        print("Screenshot saved: /tmp/bu_before.png")

        # Find the BU filter area using data-cy or label
        info = scraper.page.evaluate('''() => {
            const result = {};

            // Find all filter chips / filter sections
            const filterEls = [];
            document.querySelectorAll('[data-cy], [data-testid]').forEach(el => {
                const r = el.getBoundingClientRect();
                if (r.width > 0 && r.height > 0) {
                    filterEls.push({
                        tag: el.tagName,
                        text: el.textContent?.trim().substring(0, 60) || '',
                        dataCy: el.getAttribute('data-cy') || '',
                        dataTestid: el.getAttribute('data-testid') || '',
                        cls: (typeof el.className === 'string' ? el.className : '').substring(0, 80),
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                    });
                }
            });
            result.dataCyElements = filterEls;

            // Find BU-related text
            const buEls = [];
            document.querySelectorAll('*').forEach(el => {
                const r = el.getBoundingClientRect();
                if (r.width === 0 || r.height === 0) return;
                const text = el.textContent?.trim() || '';
                if ((text.includes('Business') || text.includes('business')) && text.length < 80) {
                    buEls.push({
                        tag: el.tagName,
                        text: text.substring(0, 60),
                        cls: (typeof el.className === 'string' ? el.className : '').substring(0, 80),
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                    });
                }
            });
            result.buElements = buEls;

            return result;
        }''')

        print(f"\nElements with data-cy/data-testid ({len(info['dataCyElements'])}):")
        for el in info['dataCyElements'][:20]:
            print(f"  [{el['x']},{el['y']} {el['w']}x{el['h']}] {el['tag']} text='{el['text'][:40]}' data-cy={el['dataCy']} data-testid={el['dataTestid']}")

        print(f"\nBusiness Unit elements ({len(info['buElements'])}):")
        for el in info['buElements'][:15]:
            print(f"  [{el['x']},{el['y']} {el['w']}x{el['h']}] {el['tag']} text='{el['text'][:40]}' cls={el['cls'][:50]}")

        # Now click the BU filter to open it
        print("\n--- Clicking BU filter ---")
        bu_clicked = scraper.page.evaluate('''() => {
            // Try clicking the filter chip/dropdown that contains "Business Unit"
            const allEls = document.querySelectorAll('*');
            for (const el of allEls) {
                const r = el.getBoundingClientRect();
                if (r.width === 0 || r.height === 0) continue;
                const text = el.textContent?.trim() || '';
                const dataCy = el.getAttribute('data-cy') || '';
                // Look for the clickable filter chip
                if (dataCy === 'custom-filter' && text.includes('Business Unit')) {
                    el.click();
                    return {clicked: true, tag: el.tagName, text: text.substring(0, 60), dataCy: dataCy};
                }
            }
            // Fallback: click anything with "Business Unit" text that's a small element
            for (const el of allEls) {
                const r = el.getBoundingClientRect();
                if (r.width === 0 || r.height === 0 || r.width > 500) continue;
                const text = el.textContent?.trim() || '';
                if (text.includes('Business Unit') && text.length < 30) {
                    el.click();
                    return {clicked: true, tag: el.tagName, text: text, cls: (typeof el.className === 'string' ? el.className : '').substring(0, 80)};
                }
            }
            return {clicked: false};
        }''')
        print(f"Click result: {json.dumps(bu_clicked, indent=2)}")

        time.sleep(3)

        # Take screenshot after clicking
        scraper.page.screenshot(path="/tmp/bu_after.png")
        print("Screenshot saved: /tmp/bu_after.png")

        # Now dump the dropdown/popup that appeared
        dropdown_info = scraper.page.evaluate('''() => {
            const result = {};

            // Look for any new popups/dropdowns/overlays
            const popups = [];
            document.querySelectorAll('[role="dialog"], [role="listbox"], [class*="popup" i], [class*="Popup"], [class*="dropdown" i], [class*="Dropdown"], [class*="overlay" i], [class*="modal" i], [class*="flyout" i], [class*="panel" i]').forEach(el => {
                const r = el.getBoundingClientRect();
                if (r.width > 0 && r.height > 0) {
                    popups.push({
                        tag: el.tagName,
                        cls: (typeof el.className === 'string' ? el.className : '').substring(0, 100),
                        role: el.getAttribute('role'),
                        text: el.textContent?.trim().substring(0, 200) || '',
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                    });
                }
            });
            result.popups = popups;

            // Look for checkboxes that appeared
            const checkboxes = [];
            document.querySelectorAll('input[type="checkbox"]').forEach(el => {
                const r = el.getBoundingClientRect();
                if (r.width > 0 || r.height > 0) {
                    // Get the label text near this checkbox
                    const parent = el.closest('label, div, li');
                    const labelText = parent ? parent.textContent?.trim().substring(0, 60) : '';
                    checkboxes.push({
                        name: el.name,
                        checked: el.checked,
                        labelText: labelText,
                        x: Math.round(r.x), y: Math.round(r.y),
                    });
                }
            });
            result.checkboxes = checkboxes;

            // Look for search inputs
            const inputs = [];
            document.querySelectorAll('input[type="text"], input[type="search"], input[placeholder]').forEach(el => {
                const r = el.getBoundingClientRect();
                if (r.width > 0 && r.height > 0) {
                    inputs.push({
                        type: el.type,
                        placeholder: el.placeholder,
                        value: el.value,
                        cls: (typeof el.className === 'string' ? el.className : '').substring(0, 80),
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width),
                    });
                }
            });
            result.inputs = inputs;

            // Any list items
            const listItems = [];
            document.querySelectorAll('li, [role="option"], [role="menuitem"]').forEach(el => {
                const r = el.getBoundingClientRect();
                if (r.width > 0 && r.height > 0 && r.height < 100) {
                    listItems.push({
                        tag: el.tagName,
                        text: el.textContent?.trim().substring(0, 60) || '',
                        role: el.getAttribute('role'),
                        x: Math.round(r.x), y: Math.round(r.y),
                    });
                }
            });
            result.listItems = listItems.slice(0, 30);

            return result;
        }''')

        print(f"\nPopups/Dropdowns ({len(dropdown_info['popups'])}):")
        for p in dropdown_info['popups']:
            print(f"  [{p['x']},{p['y']} {p['w']}x{p['h']}] {p['tag']} role={p['role']} text='{p['text'][:80]}' cls={p['cls'][:60]}")

        print(f"\nCheckboxes ({len(dropdown_info['checkboxes'])}):")
        for cb in dropdown_info['checkboxes'][:20]:
            print(f"  [{cb['x']},{cb['y']}] checked={cb['checked']} name={cb['name']} label='{cb['labelText'][:40]}'")

        print(f"\nInputs ({len(dropdown_info['inputs'])}):")
        for inp in dropdown_info['inputs']:
            print(f"  [{inp['x']},{inp['y']} w={inp['w']}] type={inp['type']} placeholder='{inp['placeholder']}' value='{inp['value']}' cls={inp['cls'][:50]}")

        print(f"\nList items ({len(dropdown_info['listItems'])}):")
        for li in dropdown_info['listItems']:
            print(f"  [{li['x']},{li['y']}] {li['tag']} role={li['role']} text='{li['text'][:50]}'")

        input("\nPress Enter to close...")

    finally:
        scraper.close()

if __name__ == "__main__":
    main()
