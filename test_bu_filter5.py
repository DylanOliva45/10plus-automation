#!/usr/bin/env python3
"""Test: Open BU filter twice (reset then re-apply) and check visibility each time."""
import json, time
from roi_scraper import ServiceTitanScraper

def dump_bu_state(scraper, label):
    info = scraper.page.evaluate('''() => {
        const result = {};
        const cbs = [];
        document.querySelectorAll('input[type="checkbox"]').forEach(el => {
            const r = el.getBoundingClientRect();
            const label = el.closest('label');
            const text = label ? label.textContent?.trim() : '';
            if (text && text !== 'Include Inactive Technicians') {
                cbs.push({text: text, checked: el.checked, visible: r.width > 0 || r.height > 0, y: Math.round(r.y)});
            }
        });
        result.checkboxes = cbs;

        // Is the trigger / dropdown open?
        const trigger = document.querySelector('[data-criteria-name="BusinessUnitId"] .Trigger');
        result.triggerExists = !!trigger;

        // Search input
        const inputs = document.querySelectorAll('input[type="text"]');
        const searchInputs = [];
        for (const inp of inputs) {
            const r = inp.getBoundingClientRect();
            if (r.width > 50 && r.y > 300 && r.y < 400 && r.x > 400) {
                searchInputs.push({x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), value: inp.value});
            }
        }
        result.searchInputs = searchInputs;

        // Filter button
        const filterBtns = [];
        document.querySelectorAll('button').forEach(el => {
            if (el.textContent.trim() === 'Filter') {
                const r = el.getBoundingClientRect();
                filterBtns.push({visible: r.width > 0 && r.height > 0, x: Math.round(r.x), y: Math.round(r.y)});
            }
        });
        result.filterButtons = filterBtns;

        return result;
    }''')
    print(f"\n--- {label} ---")
    visible_cbs = [cb for cb in info['checkboxes'] if cb['visible']]
    print(f"  Visible checkboxes: {len(visible_cbs)} (total {len(info['checkboxes'])})")
    for cb in visible_cbs[:5]:
        print(f"    {'[x]' if cb['checked'] else '[ ]'} {cb['text']} (y={cb['y']})")
    if len(visible_cbs) > 5:
        print(f"    ... and {len(visible_cbs) - 5} more")
    print(f"  Trigger exists: {info['triggerExists']}")
    print(f"  Search inputs: {info['searchInputs']}")
    print(f"  Filter buttons: {info['filterButtons']}")

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

        # Step 1: Apply HVAC filter
        print("\n=== Step 1: Apply HVAC BU filter ===")
        scraper.set_business_unit_filter(["NL-HVAC: SVC"])
        time.sleep(2)
        dump_bu_state(scraper, "After HVAC filter applied")

        # Step 2: Reset
        print("\n=== Step 2: Reset BU filter ===")
        scraper._reset_bu_filter()
        time.sleep(2)
        dump_bu_state(scraper, "After reset")

        # Step 3: Open trigger again for Plumbing
        print("\n=== Step 3: Open trigger for Plumbing ===")
        bu_container = scraper.page.locator('[data-criteria-name="BusinessUnitId"]')
        trigger = bu_container.first.locator('.Trigger')
        trigger.first.click()
        time.sleep(3)
        dump_bu_state(scraper, "After re-opening trigger")

        # Step 4: Try typing "Plumb" into search
        print("\n=== Step 4: Type 'Plumb' into search ===")
        scraper.page.evaluate('''() => {
            const inputs = document.querySelectorAll('input[type="text"]');
            for (const inp of inputs) {
                const r = inp.getBoundingClientRect();
                if (r.width > 50 && r.y > 300 && r.y < 400 && r.x > 400) {
                    const nativeInputValueSetter = Object.getOwnPropertyDescriptor(
                        window.HTMLInputElement.prototype, 'value'
                    ).set;
                    nativeInputValueSetter.call(inp, 'Plumb');
                    inp.dispatchEvent(new Event('input', { bubbles: true }));
                    return true;
                }
            }
            return false;
        }''')
        time.sleep(2)
        dump_bu_state(scraper, "After typing 'Plumb' in search")

        # Try alternate approach: use Playwright fill() on the search input
        print("\n=== Step 5: Try Playwright fill() ===")
        # First clear with native setter
        scraper.page.evaluate('''() => {
            const inputs = document.querySelectorAll('input[type="text"]');
            for (const inp of inputs) {
                const r = inp.getBoundingClientRect();
                if (r.width > 50 && r.y > 300 && r.y < 400 && r.x > 400) {
                    inp.focus();
                    inp.value = '';
                    inp.dispatchEvent(new Event('input', { bubbles: true }));
                    return;
                }
            }
        }''')
        time.sleep(1)

        # Use keyboard to type
        scraper.page.keyboard.type("NL-Plumb", delay=50)
        time.sleep(2)
        dump_bu_state(scraper, "After keyboard type 'NL-Plumb'")

    finally:
        scraper.close()

if __name__ == "__main__":
    main()
