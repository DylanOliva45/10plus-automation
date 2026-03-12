#!/usr/bin/env python3
"""Quick test to find exact column names for Opportunities and Sales Opportunities."""
import json, time
from roi_scraper import ServiceTitanScraper

def main():
    scraper = ServiceTitanScraper("george_eli", "@esT0frEtEk5dLYEXi47", log_fn=print)
    try:
        scraper.launch()
        scraper.login(mfa_code_fn=lambda: input("MFA: "))

        # Go to create report → Technicians → Technician Performance
        scraper.page.goto("https://go.servicetitan.com/#/new/reports/all", wait_until="domcontentloaded", timeout=15000)
        time.sleep(4)
        scraper.page.locator('button:has-text("Create Report")').click()
        time.sleep(4)
        scraper.page.locator('text="Technicians"').first.click()
        time.sleep(3)
        scraper.page.locator('text="Technician Performance"').first.click()
        time.sleep(3)

        # Search for "Opportunit" (partial) to see all matches
        search = scraper.page.locator('input[placeholder="Search columns"]')
        for term in ["Opportunit", "Sales Opp", "Opportunities"]:
            search.first.fill("")
            time.sleep(0.3)
            search.first.fill(term)
            time.sleep(2)

            cards = scraper.page.locator('.qa-column-togglebox')
            count = cards.count()
            print(f"\nSearch '{term}': {count} cards")
            for i in range(count):
                card = cards.nth(i)
                if card.is_visible():
                    content = card.locator('.Togglebox__content')
                    text = content.first.text_content().strip() if content.count() > 0 else card.text_content().strip()
                    print(f"  [{i}] '{text}'")

    finally:
        scraper.close()

if __name__ == "__main__":
    main()
