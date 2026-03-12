#!/usr/bin/env python3
"""Debug: after applying BU filter + reopening, screenshot + dump full page state."""
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

        # Apply HVAC filter
        scraper.set_business_unit_filter(["NL-HVAC: SVC"])
        time.sleep(2)

        scraper.page.screenshot(path="/tmp/bu_step1_after_filter.png")
        print("Screenshot: /tmp/bu_step1_after_filter.png")

        # Now check: what does the BU trigger show?
        info = scraper.page.evaluate('''() => {
            const container = document.querySelector('[data-criteria-name="BusinessUnitId"]');
            if (!container) return {error: "no container"};
            return {
                html: container.outerHTML.substring(0, 2000),
                text: container.textContent?.trim().substring(0, 200),
            };
        }''')
        print(f"\nBU container text: {info.get('text', 'N/A')}")

        # Click the trigger
        print("\n--- Clicking trigger ---")
        bu_container = scraper.page.locator('[data-criteria-name="BusinessUnitId"]')
        trigger = bu_container.first.locator('.Trigger')
        print(f"Trigger count: {trigger.count()}")
        trigger.first.click()
        time.sleep(3)

        scraper.page.screenshot(path="/tmp/bu_step2_reopen.png")
        print("Screenshot: /tmp/bu_step2_reopen.png")

        # Dump EVERYTHING that appeared — check whole page
        all_info = scraper.page.evaluate('''() => {
            const result = {};
            // ALL checkboxes on the page
            const cbs = [];
            document.querySelectorAll('input[type="checkbox"]').forEach(el => {
                const label = el.closest('label');
                const text = label ? label.textContent?.trim() : '';
                const r = el.getBoundingClientRect();
                cbs.push({text: text.substring(0, 50), visible: r.width > 0 || r.height > 0, x: Math.round(r.x), y: Math.round(r.y)});
            });
            result.allCheckboxes = cbs;

            // ALL inputs
            const inputs = [];
            document.querySelectorAll('input').forEach(el => {
                const r = el.getBoundingClientRect();
                inputs.push({type: el.type, placeholder: el.placeholder, visible: r.width > 0 && r.height > 0, x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width)});
            });
            result.allInputs = inputs;

            // Check if there's a popup/overlay portal
            const portals = [];
            document.querySelectorAll('[class*="portal" i], [class*="Portal"], [id*="portal" i], [class*="popover" i], [class*="Popover"]').forEach(el => {
                const r = el.getBoundingClientRect();
                portals.push({cls: (typeof el.className === 'string' ? el.className : '').substring(0, 80), visible: r.width > 0 && r.height > 0, children: el.children.length});
            });
            result.portals = portals;

            // Any elements at body level that appeared
            const bodyChildren = [];
            for (const child of document.body.children) {
                const r = child.getBoundingClientRect();
                if (r.width > 0 && r.height > 0) {
                    bodyChildren.push({
                        tag: child.tagName, id: child.id,
                        cls: (typeof child.className === 'string' ? child.className : '').substring(0, 60),
                        x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height),
                    });
                }
            }
            result.bodyChildren = bodyChildren;

            return result;
        }''')

        print(f"\nAll checkboxes ({len(all_info['allCheckboxes'])}):")
        visible_cbs = [cb for cb in all_info['allCheckboxes'] if cb['visible']]
        invisible_cbs = [cb for cb in all_info['allCheckboxes'] if not cb['visible']]
        print(f"  Visible: {len(visible_cbs)}")
        for cb in visible_cbs[:10]:
            print(f"    [{cb['x']},{cb['y']}] {cb['text']}")
        print(f"  Invisible: {len(invisible_cbs)}")
        for cb in invisible_cbs[:5]:
            print(f"    {cb['text']}")

        print(f"\nAll inputs ({len(all_info['allInputs'])}):")
        for inp in all_info['allInputs']:
            print(f"  [{inp['x']},{inp['y']} w={inp['w']}] type={inp['type']} visible={inp['visible']} placeholder='{inp['placeholder']}'")

        print(f"\nPortals ({len(all_info['portals'])}):")
        for p in all_info['portals']:
            print(f"  cls={p['cls']} visible={p['visible']} children={p['children']}")

        print(f"\nBody children ({len(all_info['bodyChildren'])}):")
        for bc in all_info['bodyChildren']:
            print(f"  [{bc['x']},{bc['y']} {bc['w']}x{bc['h']}] {bc['tag']} id={bc['id']} cls={bc['cls'][:50]}")

    finally:
        scraper.close()

if __name__ == "__main__":
    main()
