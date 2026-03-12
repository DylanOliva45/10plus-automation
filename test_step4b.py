#!/usr/bin/env python3
"""Find the Category dropdown on Step 4."""
import json, time
from roi_scraper import ServiceTitanScraper

def main():
    scraper = ServiceTitanScraper("george_eli", "@esT0frEtEk5dLYEXi47", log_fn=print)
    try:
        scraper.launch()
        scraper.login(mfa_code_fn=lambda: input("MFA: "))

        scraper.page.goto("https://go.servicetitan.com/#/new/reports/all", wait_until="domcontentloaded", timeout=15000)
        time.sleep(4)
        scraper.page.locator('button:has-text("Create Report")').click()
        time.sleep(5)
        scraper.page.wait_for_selector('text="Technicians"', timeout=15000)
        scraper.page.locator('text="Technicians"').first.click()
        time.sleep(3)
        scraper.page.locator('text="Technician Performance"').first.click()
        time.sleep(3)

        # Select 1 column to enable Next
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
        scraper.page.locator('button:has-text("Next")').click()
        time.sleep(5)

        # Now find everything near "Category"
        info = scraper.page.evaluate('''() => {
            const result = {};
            // Find all elements near the Category label
            const allEls = document.querySelectorAll('*');
            const categoryEls = [];
            for (const el of allEls) {
                const text = el.textContent?.trim();
                if (text && text.startsWith('Category') && text.length < 15) {
                    categoryEls.push({tag: el.tagName, text: text, cls: (typeof el.className === 'string' ? el.className : '').substring(0, 80), id: el.id});
                }
            }
            result.categoryEls = categoryEls;

            // Find all clickable elements between y=350 and y=450 (around Category)
            const nearCategory = [];
            for (const el of allEls) {
                const r = el.getBoundingClientRect();
                if (r.y > 330 && r.y < 430 && r.width > 0 && r.height > 0 && r.width < 500) {
                    nearCategory.push({
                        tag: el.tagName,
                        text: el.textContent?.trim().substring(0, 40) || '',
                        cls: (typeof el.className === 'string' ? el.className : '').substring(0, 80),
                        x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height),
                        role: el.getAttribute('role'),
                        tabindex: el.getAttribute('tabindex')
                    });
                }
            }
            result.nearCategory = nearCategory;

            // Find any dropdown/select-like elements
            const dropdowns = [];
            document.querySelectorAll('[role="listbox"], [role="combobox"], [role="select"], [class*="dropdown" i], [class*="Dropdown"], [class*="Select"], [class*="select"]').forEach(el => {
                const r = el.getBoundingClientRect();
                dropdowns.push({
                    tag: el.tagName, cls: (typeof el.className === 'string' ? el.className : '').substring(0, 80),
                    role: el.getAttribute('role'),
                    visible: r.width > 0 && r.height > 0,
                    text: el.textContent?.trim().substring(0, 40) || ''
                });
            });
            result.dropdowns = dropdowns;

            return result;
        }''')

        print(f"\nCategory elements ({len(info['categoryEls'])}):")
        for el in info['categoryEls']:
            print(f"  {el['tag']} text='{el['text']}' cls={el['cls']}")

        print(f"\nElements near Category y=350-430 ({len(info['nearCategory'])}):")
        for el in info['nearCategory']:
            print(f"  [{el['x']},{el['y']} {el['w']}x{el['h']}] {el['tag']} text='{el['text'][:30]}' role={el['role']} cls={el['cls'][:50]}")

        print(f"\nDropdown-like elements ({len(info['dropdowns'])}):")
        for el in info['dropdowns']:
            print(f"  {el['tag']} role={el['role']} visible={el['visible']} text='{el['text'][:30]}' cls={el['cls'][:50]}")

    finally:
        scraper.close()

if __name__ == "__main__":
    main()
