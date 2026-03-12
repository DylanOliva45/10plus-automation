#!/usr/bin/env python3
"""Inspect actual job cards (with Job ID) from the diffs page."""

import os
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

load_dotenv()

def main():
    pw = sync_playwright().start()
    browser = pw.chromium.launch(headless=False, slow_mo=100)
    context = browser.new_context(viewport={"width": 1440, "height": 900})
    page = context.new_page()

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

    # Select first dataset with lots of data (3/2-2/6 test with 298 jobs)
    page.locator('[data-slot="button"]').filter(has_text="3/2-2/6 test").first.click()
    page.wait_for_timeout(1000)
    page.locator('div.cursor-pointer').filter(has_text="Version 3").first.click()
    page.wait_for_timeout(1000)

    page.get_by_text("Jobs / Diffs Dashboard", exact=True).first.click()
    page.wait_for_timeout(5000)

    # Get the first job card's full HTML
    result = page.evaluate("""
        () => {
            const cards = document.querySelectorAll('div.border.rounded-md.p-4');
            const output = [];
            for (const card of cards) {
                const text = card.textContent || '';
                if (text.includes('Job ID:')) {
                    output.push({
                        html: card.outerHTML.substring(0, 8000),
                        text: card.innerText.substring(0, 2000)
                    });
                    if (output.length >= 2) break;
                }
            }
            return output;
        }
    """)

    for i, item in enumerate(result):
        print(f"\n=== JOB CARD {i} TEXT ===")
        print(item["text"])
        with open(f"job_card_{i}.html", "w") as f:
            f.write(item["html"])
        print(f"Saved: job_card_{i}.html")

    browser.close()
    pw.stop()

if __name__ == "__main__":
    main()
