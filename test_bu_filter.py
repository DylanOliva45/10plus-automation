#!/usr/bin/env python3
"""Inspect the BU filter on a saved report page."""
import json, time
from roi_scraper import ServiceTitanScraper

def main():
    scraper = ServiceTitanScraper("george_eli", "@esT0frEtEk5dLYEXi47", log_fn=print)
    try:
        scraper.launch()
        scraper.login(mfa_code_fn=lambda: input("MFA: "))

        # Navigate to the saved report
        scraper.page.goto(
            "https://go.servicetitan.com/#/new/reports/354643851",
            wait_until="domcontentloaded", timeout=15000
        )
        time.sleep(5)
        print(f"URL: {scraper.page.url}")

        # Dump all filter-like elements
        info = scraper.page.evaluate('''() => {
            const result = {};
            // Find everything with "Business" or "filter" in text/class
            const filters = [];
            document.querySelectorAll('*').forEach(el => {
                const r = el.getBoundingClientRect();
                if (r.width === 0 || r.height === 0) return;
                const text = el.textContent?.trim() || '';
                const cls = (typeof el.className === 'string' ? el.className : '');
                if ((text.includes('Business') && text.length < 80) ||
                    cls.includes('filter') || cls.includes('Filter') ||
                    cls.includes('chip') || cls.includes('Chip') ||
                    el.getAttribute('data-testid')?.includes('filter')) {
                    filters.push({
                        tag: el.tagName,
                        text: text.substring(0, 60),
                        cls: cls.substring(0, 80),
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        role: el.getAttribute('role'),
                        dataCy: el.getAttribute('data-cy') || ''
                    });
                }
            });
            result.filters = filters.slice(0, 30);

            // All buttons on the page
            const buttons = [];
            document.querySelectorAll('button, [role="button"]').forEach(el => {
                const r = el.getBoundingClientRect();
                if (r.width > 0 && r.height > 0) {
                    buttons.push({text: el.textContent?.trim().substring(0, 40) || '', x: Math.round(r.x), y: Math.round(r.y)});
                }
            });
            result.buttons = buttons;

            return result;
        }''')

        print(f"\nFilter-like elements ({len(info['filters'])}):")
        for f in info['filters']:
            print(f"  [{f['x']},{f['y']} {f['w']}x{f['h']}] {f['tag']} text='{f['text'][:40]}' cls={f['cls'][:50]} data-cy={f['dataCy']}")

        print(f"\nButtons ({len(info['buttons'])}):")
        for b in info['buttons']:
            print(f"  [{b['x']},{b['y']}] {b['text']}")

    finally:
        scraper.close()

if __name__ == "__main__":
    main()
