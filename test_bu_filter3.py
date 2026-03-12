#!/usr/bin/env python3
"""Deep inspect BU filter inner structure, then click it open properly."""
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

        # Deep inspect the BU filter area children
        inner = scraper.page.evaluate('''() => {
            // Find the BU filter container (data-cy="custom-filter" with "Business Unit")
            const allEls = document.querySelectorAll('[data-cy="custom-filter"]');
            let buFilter = null;
            for (const el of allEls) {
                if (el.textContent.includes('Business Unit')) {
                    buFilter = el;
                    break;
                }
            }
            if (!buFilter) return {error: "BU filter not found"};

            // Dump ALL children recursively
            const children = [];
            function walk(el, depth) {
                const r = el.getBoundingClientRect();
                children.push({
                    depth: depth,
                    tag: el.tagName,
                    text: (el.childNodes.length === 1 && el.childNodes[0].nodeType === 3)
                        ? el.textContent.trim().substring(0, 40) : '',
                    cls: (typeof el.className === 'string' ? el.className : '').substring(0, 100),
                    role: el.getAttribute('role'),
                    dataCy: el.getAttribute('data-cy') || '',
                    tabindex: el.getAttribute('tabindex'),
                    type: el.getAttribute('type'),
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    clickable: el.tagName === 'BUTTON' || el.tagName === 'A' || el.tagName === 'INPUT' ||
                               el.tagName === 'SELECT' || el.getAttribute('role') === 'button' ||
                               el.getAttribute('role') === 'combobox' || el.getAttribute('role') === 'listbox' ||
                               el.getAttribute('tabindex') !== null,
                });
                for (const child of el.children) {
                    walk(child, depth + 1);
                }
            }
            walk(buFilter, 0);
            return {children: children, outerHTML: buFilter.outerHTML.substring(0, 2000)};
        }''')

        if 'error' in inner:
            print(f"ERROR: {inner['error']}")
            return

        print(f"BU filter children ({len(inner['children'])}):")
        for c in inner['children']:
            indent = "  " * c['depth']
            extras = []
            if c['role']: extras.append(f"role={c['role']}")
            if c['dataCy']: extras.append(f"data-cy={c['dataCy']}")
            if c['tabindex']: extras.append(f"tabindex={c['tabindex']}")
            if c['type']: extras.append(f"type={c['type']}")
            if c['clickable']: extras.append("*CLICKABLE*")
            ext = " ".join(extras)
            print(f"{indent}[{c['x']},{c['y']} {c['w']}x{c['h']}] {c['tag']} text='{c['text'][:30]}' cls={c['cls'][:60]} {ext}")

        print(f"\n--- outerHTML (first 2000 chars) ---")
        print(inner.get('outerHTML', ''))

        # Now try clicking the dropdown trigger — look for the element showing "All"
        print("\n--- Clicking the 'All' dropdown trigger ---")
        scraper.page.evaluate('''() => {
            const allEls = document.querySelectorAll('[data-cy="custom-filter"]');
            for (const el of allEls) {
                if (!el.textContent.includes('Business Unit')) continue;
                // Find the clickable inner element (NOT the label)
                const inner = el.querySelectorAll('*');
                for (const child of inner) {
                    const r = child.getBoundingClientRect();
                    if (r.height === 0 || r.width === 0) continue;
                    const text = child.textContent?.trim();
                    // Click the element that shows "All" and is below the label
                    if (text === 'All' && r.y > 260) {
                        child.click();
                        return;
                    }
                }
                // Fallback: click any select or button
                const sel = el.querySelector('select, button, [role="combobox"], [role="listbox"], [tabindex]');
                if (sel) { sel.click(); return; }
            }
        }''')
        time.sleep(3)

        scraper.page.screenshot(path="/tmp/bu_after2.png")
        print("Screenshot saved: /tmp/bu_after2.png")

        # Dump what appeared after clicking
        after = scraper.page.evaluate('''() => {
            const result = {};

            // Check for any new visible elements not in the filter area
            const popups = [];
            document.querySelectorAll('[role="dialog"], [role="listbox"], [class*="popup" i], [class*="Popup"], [class*="dropdown" i], [class*="Dropdown"], [class*="overlay" i], [class*="menu" i], [class*="Menu"], [class*="options" i], [class*="Options"]').forEach(el => {
                const r = el.getBoundingClientRect();
                if (r.width > 10 && r.height > 10) {
                    popups.push({
                        tag: el.tagName, cls: (typeof el.className === 'string' ? el.className : '').substring(0, 100),
                        role: el.getAttribute('role'),
                        text: el.textContent?.trim().substring(0, 300) || '',
                        x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height),
                    });
                }
            });
            result.popups = popups;

            // Any new checkboxes
            const cbs = [];
            document.querySelectorAll('input[type="checkbox"]').forEach(el => {
                const r = el.getBoundingClientRect();
                const parent = el.closest('label, div, li, span');
                cbs.push({
                    name: el.name, checked: el.checked,
                    label: parent ? parent.textContent?.trim().substring(0, 60) : '',
                    visible: r.width > 0,
                    x: Math.round(r.x), y: Math.round(r.y),
                });
            });
            result.checkboxes = cbs;

            // Any new inputs
            const inputs = [];
            document.querySelectorAll('input').forEach(el => {
                const r = el.getBoundingClientRect();
                if (r.width > 0 && r.height > 0) {
                    inputs.push({
                        type: el.type, placeholder: el.placeholder, value: el.value.substring(0, 40),
                        cls: (typeof el.className === 'string' ? el.className : '').substring(0, 80),
                        x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width),
                    });
                }
            });
            result.inputs = inputs;

            // Elements that contain BU-like names
            const buNames = [];
            document.querySelectorAll('*').forEach(el => {
                const r = el.getBoundingClientRect();
                if (r.width === 0 || r.height === 0) return;
                const text = el.textContent?.trim() || '';
                if ((text.includes('HVAC') || text.includes('Plumbing') || text.includes('Residential') ||
                     text.includes('Commercial') || text.includes('Service')) && text.length < 100 && r.height < 60) {
                    buNames.push({
                        tag: el.tagName, text: text.substring(0, 60),
                        x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height),
                    });
                }
            });
            result.buNames = buNames.slice(0, 20);

            return result;
        }''')

        print(f"\nPopups after click ({len(after['popups'])}):")
        for p in after['popups']:
            print(f"  [{p['x']},{p['y']} {p['w']}x{p['h']}] {p['tag']} role={p['role']} text='{p['text'][:100]}' cls={p['cls'][:60]}")

        print(f"\nCheckboxes ({len(after['checkboxes'])}):")
        for cb in after['checkboxes'][:20]:
            print(f"  [{cb['x']},{cb['y']}] visible={cb['visible']} checked={cb['checked']} label='{cb['label'][:40]}'")

        print(f"\nInputs ({len(after['inputs'])}):")
        for inp in after['inputs']:
            print(f"  [{inp['x']},{inp['y']} w={inp['w']}] type={inp['type']} placeholder='{inp['placeholder']}' cls={inp['cls'][:50]}")

        print(f"\nBU-like names ({len(after['buNames'])}):")
        for n in after['buNames']:
            print(f"  [{n['x']},{n['y']} {n['w']}x{n['h']}] {n['tag']} '{n['text']}'")

    finally:
        scraper.close()

if __name__ == "__main__":
    main()
