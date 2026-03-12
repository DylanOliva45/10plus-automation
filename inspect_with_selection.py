#!/usr/bin/env python3
"""Select a dataset + config, then inspect the Jobs / Diffs Dashboard with actual data."""

import os
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

load_dotenv()

def main():
    pw = sync_playwright().start()
    browser = pw.chromium.launch(headless=False, slow_mo=100)
    context = browser.new_context(viewport={"width": 1440, "height": 900})
    page = context.new_page()

    # Login
    page.goto("https://admin.probook.ai", wait_until="networkidle")
    email = page.locator('input[type="email"], input[name="email"], input[id*="email"]').first
    email.fill(os.getenv("PROBOOK_USERNAME", ""))
    pw_field = page.locator('input[type="password"]').first
    pw_field.fill(os.getenv("PROBOOK_PASSWORD", ""))
    page.locator('button[type="submit"]').first.click()
    page.wait_for_timeout(5000)

    # Select customer
    page.get_by_text("Dyess Air", exact=False).first.click()
    page.wait_for_timeout(2000)

    # Navigate: Audit > AI Validation > Dataset Builder
    page.get_by_text("Audit", exact=False).first.click()
    page.wait_for_timeout(2000)
    page.get_by_text("AI Validation", exact=False).first.click()
    page.wait_for_timeout(2000)

    # We should be on Dataset Builder by default
    page.screenshot(path="inspect_step1_dataset_builder.png", full_page=True)
    print("Saved: inspect_step1_dataset_builder.png")

    # Dump the Existing Datasets section
    print("\n=== EXISTING DATASET CARDS ===")
    # Look for cards in the Existing Datasets section
    all_buttons = page.locator('button')
    for i in range(all_buttons.count()):
        try:
            btn = all_buttons.nth(i)
            text = btn.text_content().strip()
            if "Past Dataset" in text or "dataset" in text.lower():
                classes = btn.evaluate("e => e.className")[:100]
                html = btn.evaluate("e => e.outerHTML.substring(0, 500)")
                print(f"\n  [{i}] text='{text}'")
                print(f"       class='{classes}'")
                print(f"       html='{html}'")
        except:
            pass

    # Look for card-like divs that might be dataset cards
    print("\n=== CARD DIVS ===")
    cards = page.locator('[data-slot="card"], [class*="card" i]')
    for i in range(min(cards.count(), 20)):
        try:
            text = cards.nth(i).text_content().strip()[:150]
            classes = cards.nth(i).evaluate("e => e.className")[:100]
            is_vis = cards.nth(i).is_visible()
            print(f"  [{i}] visible={is_vis} text='{text}'")
            print(f"       class='{classes}'")
        except:
            pass

    # Click the first existing dataset (if any)
    print("\n=== CLICKING FIRST DATASET ===")
    try:
        # The dataset cards contain "Past Dataset" text
        dataset_cards = page.locator('text=Past Dataset')
        if dataset_cards.count() > 0:
            # Click the parent clickable element
            first_card = dataset_cards.first
            parent = first_card.locator("xpath=ancestor::button | ancestor::div[@role='button']").first
            if parent.is_visible():
                parent.click()
                print("  Clicked parent button/div of first 'Past Dataset'")
            else:
                first_card.click()
                print("  Clicked 'Past Dataset' text directly")
            page.wait_for_timeout(1000)
        else:
            print("  No 'Past Dataset' cards found")
    except Exception as e:
        print(f"  Error clicking dataset: {e}")

    page.screenshot(path="inspect_step2_dataset_selected.png", full_page=True)
    print("Saved: inspect_step2_dataset_selected.png")

    # Now dump the state to check if blue highlight appeared
    print("\n=== SELECTED/HIGHLIGHTED ELEMENTS ===")
    highlighted = page.locator('[class*="selected" i], [aria-selected="true"], [class*="ring" i], [class*="border-primary"]')
    for i in range(min(highlighted.count(), 20)):
        try:
            text = highlighted.nth(i).text_content().strip()[:100]
            classes = highlighted.nth(i).evaluate("e => e.className")[:120]
            print(f"  [{i}] text='{text}'")
            print(f"       class='{classes}'")
        except:
            pass

    # Click Production Version 3 rule config
    print("\n=== CLICKING RULE CONFIG ===")
    try:
        prod_cards = page.get_by_text("Production", exact=False)
        # Find the one with "Version 3"
        for i in range(prod_cards.count()):
            text = prod_cards.nth(i).text_content().strip()
            if "Version 3" in text:
                prod_cards.nth(i).click()
                print(f"  Clicked: '{text}'")
                break
        page.wait_for_timeout(1000)
    except Exception as e:
        print(f"  Error clicking rule config: {e}")

    page.screenshot(path="inspect_step3_both_selected.png", full_page=True)
    print("Saved: inspect_step3_both_selected.png")

    # Now click "Jobs / Diffs Dashboard" tab
    print("\n=== SWITCHING TO JOBS / DIFFS DASHBOARD ===")
    page.get_by_text("Jobs / Diffs Dashboard", exact=False).first.click()
    page.wait_for_timeout(5000)

    page.screenshot(path="inspect_step4_diffs_page.png", full_page=True)
    print("Saved: inspect_step4_diffs_page.png")

    # Dump all visible elements on the diffs page
    print("\n=== DIFFS PAGE CONTENT ===")
    # Look for any table, list, or job data
    for selector in ['table', 'tr', 'td', 'th', '[class*="accordion"]', '[class*="Accordion"]',
                     '[class*="job"]', '[class*="Job"]', '[class*="diff"]', '[class*="Diff"]',
                     'select', '[role="combobox"]', '[role="listbox"]',
                     '[class*="dropdown"]', '[class*="column"]', '[class*="Column"]']:
        count = page.locator(selector).count()
        if count > 0 and count < 100:
            print(f"\n  '{selector}' => {count} matches")
            for j in range(min(count, 5)):
                try:
                    text = page.locator(selector).nth(j).text_content().strip()[:120]
                    if text:
                        print(f"    [{j}] '{text}'")
                except:
                    pass

    # Dump the full page HTML (trimmed)
    html = page.evaluate("() => document.body.innerHTML.substring(0, 15000)")
    with open("inspect_step4_diffs_html.html", "w") as f:
        f.write(html)
    print("\nSaved: inspect_step4_diffs_html.html")

    browser.close()
    pw.stop()

if __name__ == "__main__":
    main()
