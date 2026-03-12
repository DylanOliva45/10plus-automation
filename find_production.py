#!/usr/bin/env python3
"""Find the actual DOM elements for Production rule config cards."""

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
    page.wait_for_timeout(3000)

    # Find ALL elements containing "Production" text
    print("=== ALL ELEMENTS WITH 'Production' TEXT ===")
    results = page.evaluate("""
        () => {
            const results = [];
            const walker = document.createTreeWalker(
                document.body,
                NodeFilter.SHOW_ELEMENT,
                null
            );
            while (walker.nextNode()) {
                const el = walker.currentNode;
                const text = el.textContent?.trim() || '';
                if (text.includes('Production') && text.includes('Version')) {
                    // Only include elements where the direct text (not children) contains it
                    // or where total text is short enough to be the card itself
                    if (text.length < 200) {
                        results.push({
                            tag: el.tagName,
                            text: text.substring(0, 100),
                            classes: (el.className || '').substring(0, 120),
                            outerHTML: el.outerHTML.substring(0, 400),
                            isVisible: el.offsetParent !== null,
                            clickable: el.tagName === 'BUTTON' || el.tagName === 'A' ||
                                       el.getAttribute('role') === 'button' ||
                                       window.getComputedStyle(el).cursor === 'pointer'
                        });
                    }
                }
            }
            return results;
        }
    """)

    for i, r in enumerate(results):
        print(f"\n  [{i}] <{r['tag']}> visible={r['isVisible']} clickable={r['clickable']}")
        print(f"       text='{r['text']}'")
        print(f"       class='{r['classes']}'")
        print(f"       html='{r['outerHTML']}'")

    # Also find the "Rule Configurations" section and dump its children
    print("\n=== RULE CONFIGURATIONS SECTION CHILDREN ===")
    rule_html = page.evaluate("""
        () => {
            const headers = document.querySelectorAll('[data-slot="card-title"]');
            for (const h of headers) {
                if (h.textContent.includes('Rule Config')) {
                    // Get the parent card
                    const card = h.closest('[data-slot="card"]');
                    if (card) {
                        const content = card.querySelector('[data-slot="card-content"]');
                        return content ? content.innerHTML.substring(0, 3000) : card.innerHTML.substring(0, 3000);
                    }
                }
            }
            return 'NOT FOUND';
        }
    """)
    print(rule_html)

    # Click the first Production card
    print("\n=== ATTEMPTING TO CLICK PRODUCTION VERSION 3 ===")
    # Try using the text directly
    prod_text = page.get_by_text("Version 3", exact=False)
    count = prod_text.count()
    print(f"  Found {count} elements with 'Version 3'")
    if count > 0:
        prod_text.first.click()
        page.wait_for_timeout(1000)
        page.screenshot(path="test_prod_clicked.png", full_page=True)
        print("  Saved: test_prod_clicked.png")

        # Check what happened
        classes = prod_text.first.evaluate("e => e.className")
        parent_classes = prod_text.first.evaluate("e => e.parentElement?.className || ''")
        grandparent_classes = prod_text.first.evaluate("e => e.parentElement?.parentElement?.className || ''")
        print(f"  Element class: {classes[:100]}")
        print(f"  Parent class: {parent_classes[:100]}")
        print(f"  Grandparent class: {grandparent_classes[:100]}")

    browser.close()
    pw.stop()

if __name__ == "__main__":
    main()
