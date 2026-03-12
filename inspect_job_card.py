#!/usr/bin/env python3
"""Inspect a single job card to get exact tag DOM structure."""

import os
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

load_dotenv()

def main():
    pw = sync_playwright().start()
    browser = pw.chromium.launch(headless=False, slow_mo=100)
    context = browser.new_context(viewport={"width": 1440, "height": 900})
    page = context.new_page()

    # Login + navigate
    page.goto("https://admin.probook.ai", wait_until="networkidle")
    page.locator('input[type="email"], input[id*="email"]').first.fill(os.getenv("PROBOOK_USERNAME", ""))
    page.locator('input[type="password"]').first.fill(os.getenv("PROBOOK_PASSWORD", ""))
    page.locator('button[type="submit"]').first.click()
    page.wait_for_timeout(5000)
    page.get_by_text("Dyess Air", exact=False).first.click()
    page.wait_for_timeout(2000)
    page.get_by_role("tab", name="Audit").click()
    page.wait_for_timeout(2000)
    page.get_by_role("tab", name="AI Validation").click()
    page.wait_for_timeout(2000)

    # Select dataset
    page.locator('[data-slot="button"]').filter(has_text="Past Dataset").first.click()
    page.wait_for_timeout(1000)

    # Select rule config
    page.locator('div.cursor-pointer').filter(has_text="Version 3").first.click()
    page.wait_for_timeout(1000)

    # Go to Jobs / Diffs Dashboard
    page.get_by_text("Jobs / Diffs Dashboard", exact=True).first.click()
    page.wait_for_timeout(5000)

    # Get the HTML of the first job card that has tags
    card_html = page.evaluate("""
        () => {
            const cards = document.querySelectorAll('div.border.rounded-md.p-4');
            for (const card of cards) {
                if (card.textContent.includes('best_tags') || card.textContent.includes('Tags')) {
                    return card.outerHTML.substring(0, 5000);
                }
            }
            // Return first card if no tags card found
            if (cards.length > 0) return cards[0].outerHTML.substring(0, 5000);
            return 'NO CARDS FOUND';
        }
    """)
    with open("inspect_job_card.html", "w") as f:
        f.write(card_html)
    print("Saved: inspect_job_card.html")

    # Also dump the innerText of the first card to see the text layout
    card_text = page.evaluate("""
        () => {
            const cards = document.querySelectorAll('div.border.rounded-md.p-4');
            if (cards.length > 0) return cards[0].innerText;
            return 'NO CARDS';
        }
    """)
    print("\n=== FIRST CARD TEXT ===")
    print(card_text)

    browser.close()
    pw.stop()

if __name__ == "__main__":
    main()
