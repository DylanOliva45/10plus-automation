#!/usr/bin/env python3
"""Dump the Popper/Popover content after clicking BU trigger."""
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

        # Click BU trigger (fresh, no prior filter)
        bu_container = scraper.page.locator('[data-criteria-name="BusinessUnitId"]')
        trigger = bu_container.first.locator('.Trigger')
        trigger.first.click()
        time.sleep(3)

        # Dump the Popper element
        info = scraper.page.evaluate('''() => {
            const popper = document.querySelector('body > .Popper');
            if (!popper) return {error: "No Popper found"};

            const result = {};
            result.html = popper.outerHTML.substring(0, 3000);

            // Children walk
            const children = [];
            function walk(el, depth) {
                const r = el.getBoundingClientRect();
                const info = {
                    depth: depth,
                    tag: el.tagName,
                    cls: (typeof el.className === 'string' ? el.className : '').substring(0, 80),
                    text: el.children.length === 0 ? el.textContent?.trim().substring(0, 40) : '',
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    type: el.getAttribute('type'),
                    placeholder: el.getAttribute('placeholder'),
                };
                children.push(info);
                if (depth < 6) {
                    for (const child of el.children) {
                        walk(child, depth + 1);
                    }
                }
            }
            walk(popper, 0);
            result.children = children;

            return result;
        }''')

        if 'error' in info:
            print(f"ERROR: {info['error']}")
            return

        print(f"Popper children ({len(info['children'])}):")
        for c in info['children'][:60]:
            indent = "  " * c['depth']
            extras = []
            if c['type']: extras.append(f"type={c['type']}")
            if c['placeholder']: extras.append(f"placeholder={c['placeholder']}")
            ext = " ".join(extras)
            t = f" text='{c['text'][:30]}'" if c['text'] else ''
            print(f"{indent}[{c['x']},{c['y']} {c['w']}x{c['h']}] {c['tag']} cls={c['cls'][:50]}{t} {ext}")

    finally:
        scraper.close()

if __name__ == "__main__":
    main()
