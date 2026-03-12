#!/usr/bin/env python3
"""Test script to select dataset + rule config and verify blue highlighting."""

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

    # We're on Dataset Builder. Dump ALL buttons with their full text
    print("\n=== ALL data-slot='button' ELEMENTS ===")
    slot_buttons = page.locator('[data-slot="button"]')
    for i in range(slot_buttons.count()):
        try:
            text = slot_buttons.nth(i).text_content().strip()[:120]
            visible = slot_buttons.nth(i).is_visible()
            classes = slot_buttons.nth(i).evaluate("e => e.className")[:80]
            has_primary = "bg-primary" in classes
            print(f"  [{i}] vis={visible} primary={has_primary} text='{text}'")
        except:
            pass

    # Find the Production Version 3 card specifically
    print("\n=== LOOKING FOR PRODUCTION CARDS ===")
    all_btns = page.locator('[data-slot="button"]')
    prod_indices = []
    for i in range(all_btns.count()):
        try:
            text = all_btns.nth(i).text_content().strip()
            if "Production" in text and "Version" in text:
                visible = all_btns.nth(i).is_visible()
                print(f"  [{i}] visible={visible} text='{text}'")
                if visible:
                    prod_indices.append(i)
        except:
            pass

    # Click the first dataset card
    print("\n=== SELECTING DATASET ===")
    dataset_btns = []
    for i in range(all_btns.count()):
        try:
            text = all_btns.nth(i).text_content().strip()
            if "Past Dataset" in text and all_btns.nth(i).is_visible():
                dataset_btns.append(i)
        except:
            pass

    if dataset_btns:
        print(f"  Clicking dataset at index {dataset_btns[0]}")
        all_btns.nth(dataset_btns[0]).click()
        page.wait_for_timeout(1000)

        # Check if it got bg-primary
        classes = all_btns.nth(dataset_btns[0]).evaluate("e => e.className")
        print(f"  After click, has bg-primary: {'bg-primary' in classes}")
        print(f"  Classes: {classes[:150]}")

    # Now scroll to rule configs and click Production Version 3
    print("\n=== SELECTING PRODUCTION VERSION 3 ===")
    if prod_indices:
        idx = prod_indices[0]  # First one = Version 3
        print(f"  Scrolling to and clicking index {idx}")
        all_btns.nth(idx).scroll_into_view_if_needed()
        page.wait_for_timeout(500)
        all_btns.nth(idx).click()
        page.wait_for_timeout(1000)

        # Check highlighting
        classes = all_btns.nth(idx).evaluate("e => e.className")
        print(f"  After click, has bg-primary: {'bg-primary' in classes}")
        print(f"  Classes: {classes[:150]}")

        # Try clicking again if not highlighted
        if "bg-primary" not in classes:
            print("  Not highlighted! Trying double-click...")
            all_btns.nth(idx).dblclick()
            page.wait_for_timeout(1000)
            classes = all_btns.nth(idx).evaluate("e => e.className")
            print(f"  After dblclick: {'bg-primary' in classes}")

        # Check inline style too
        style = all_btns.nth(idx).evaluate("e => e.style.cssText")
        bg = all_btns.nth(idx).evaluate("e => window.getComputedStyle(e).backgroundColor")
        border = all_btns.nth(idx).evaluate("e => window.getComputedStyle(e).borderColor")
        print(f"  Style: '{style}'")
        print(f"  Computed bg: '{bg}'")
        print(f"  Computed border: '{border}'")

    page.screenshot(path="test_selection.png", full_page=True)
    print("\nSaved: test_selection.png")

    # Now try going to Jobs / Diffs Dashboard
    print("\n=== TRYING JOBS / DIFFS DASHBOARD ===")
    page.get_by_text("Jobs / Diffs Dashboard", exact=False).first.click()
    page.wait_for_timeout(5000)
    page.screenshot(path="test_diffs_after_select.png", full_page=True)
    print("Saved: test_diffs_after_select.png")

    # Check what's on the diffs page now
    content = page.locator('[data-slot="card-content"]').first
    if content.is_visible():
        text = content.text_content().strip()[:300]
        print(f"  Card content: '{text}'")

    browser.close()
    pw.stop()

if __name__ == "__main__":
    main()
