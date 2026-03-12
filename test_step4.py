#!/usr/bin/env python3
"""Quick test to inspect Save step (Step 4) form elements."""
import json, time
from roi_scraper import ServiceTitanScraper

def main():
    scraper = ServiceTitanScraper("george_eli", "@esT0frEtEk5dLYEXi47", log_fn=print)
    try:
        scraper.launch()
        scraper.login(mfa_code_fn=lambda: input("MFA: "))

        # Quick path: Create Report → Technicians → Technician Performance → select 1 col → Next
        scraper.page.goto("https://go.servicetitan.com/#/new/reports/all", wait_until="domcontentloaded", timeout=15000)
        time.sleep(4)
        scraper.page.locator('button:has-text("Create Report")').click()
        time.sleep(4)

        scraper.page.wait_for_selector('text="Technicians"', timeout=15000)
        scraper.page.locator('text="Technicians"').first.click()
        time.sleep(3)
        scraper.page.locator('text="Technician Performance"').first.click()
        time.sleep(3)

        # Select just one column (Total Sales) to enable Next
        search = scraper.page.locator('input[placeholder="Search columns"]')
        search.first.fill("Total Sales")
        time.sleep(2)
        cards = scraper.page.locator('.qa-column-togglebox')
        for i in range(cards.count()):
            card = cards.nth(i)
            if card.is_visible():
                text = card.locator('.Togglebox__content').first.text_content().strip()
                if text == "Total Sales":
                    card.locator('input.Checkbox__input').first.click(force=True)
                    break
        time.sleep(1)

        # Click Next to get to Step 4
        scraper.page.locator('button:has-text("Next")').click()
        time.sleep(5)

        print("\n=== STEP 4 FORM INSPECTION ===")

        # Dump all form elements
        info = scraper.page.evaluate('''() => {
            const result = {};
            // All inputs
            result.inputs = [];
            document.querySelectorAll('input, select, textarea').forEach(el => {
                const r = el.getBoundingClientRect();
                if (r.width > 0 && r.height > 0) {
                    result.inputs.push({
                        tag: el.tagName,
                        type: el.type,
                        name: el.name,
                        value: el.value.substring(0, 40),
                        placeholder: el.placeholder,
                        cls: el.className.substring(0, 80),
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height)
                    });
                }
            });
            // All selects (even hidden)
            result.selects = [];
            document.querySelectorAll('select').forEach(el => {
                const opts = Array.from(el.options).map(o => ({v: o.value, t: o.text}));
                result.selects.push({name: el.name, cls: el.className.substring(0, 60), opts: opts, visible: el.getBoundingClientRect().width > 0});
            });
            // All buttons
            result.buttons = [];
            document.querySelectorAll('button').forEach(el => {
                const r = el.getBoundingClientRect();
                if (r.width > 0 && r.height > 0) {
                    result.buttons.push({text: el.textContent.trim().substring(0, 40), cls: el.className.substring(0, 60), disabled: el.disabled});
                }
            });
            // Labels
            result.labels = [];
            document.querySelectorAll('label, .label, [class*="Label"]').forEach(el => {
                const r = el.getBoundingClientRect();
                if (r.width > 0 && r.height > 0) {
                    result.labels.push({text: el.textContent.trim().substring(0, 40), cls: el.className.substring(0, 60)});
                }
            });
            return result;
        }''')

        print(f"\nInputs ({len(info['inputs'])}):")
        for inp in info['inputs']:
            print(f"  [{inp['x']},{inp['y']}] {inp['tag']} type={inp['type']} name={inp['name']} placeholder={inp['placeholder']} value={inp['value']} cls={inp['cls']}")

        print(f"\nSelects ({len(info['selects'])}):")
        for sel in info['selects']:
            print(f"  name={sel['name']} visible={sel['visible']} cls={sel['cls']}")
            for opt in sel['opts'][:5]:
                print(f"    value={opt['v']} text={opt['t']}")

        print(f"\nButtons ({len(info['buttons'])}):")
        for btn in info['buttons']:
            print(f"  {btn['text']} disabled={btn['disabled']} cls={btn['cls'][:40]}")

        print(f"\nLabels ({len(info['labels'])}):")
        for lbl in info['labels'][:10]:
            print(f"  {lbl['text']}")

    finally:
        scraper.close()

if __name__ == "__main__":
    main()
