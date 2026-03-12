#!/usr/bin/env python3
"""Quick script to inspect the ProBook UI and capture the date picker DOM."""

import os
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

load_dotenv()

def main():
    pw = sync_playwright().start()
    browser = pw.chromium.launch(headless=False, slow_mo=100)
    context = browser.new_context(viewport={"width": 1440, "height": 900})
    context.set_default_timeout(30_000)
    page = context.new_page()

    # Login
    page.goto("https://admin.probook.ai", wait_until="networkidle")

    username = os.getenv("PROBOOK_USERNAME", "")
    password = os.getenv("PROBOOK_PASSWORD", "")

    email_field = page.locator(
        'input[type="email"], input[name="email"], input[name="username"], '
        'input[placeholder*="mail"], input[placeholder*="user"], '
        'input[id*="email"], input[id*="user"]'
    ).first
    email_field.wait_for(state="visible", timeout=10_000)
    email_field.fill(username)

    password_field = page.locator('input[type="password"]').first
    password_field.fill(password)

    submit = page.locator(
        'button[type="submit"], button:has-text("Log in"), button:has-text("Login"), '
        'button:has-text("Sign in"), input[type="submit"]'
    ).first
    submit.click()

    page.wait_for_timeout(5000)
    print(f"Post-login URL: {page.url}")

    # Select customer
    try:
        customer_link = page.get_by_text("Dyess Air", exact=False)
        if customer_link.first.is_visible(timeout=3000):
            customer_link.first.click()
            page.wait_for_timeout(2000)
            print("Customer selected.")
    except Exception as e:
        print(f"Customer selection: {e}")

    # Navigate to Audit > AI Validation > Dataset Builder
    try:
        page.get_by_text("Audit", exact=False).first.click()
        page.wait_for_timeout(2000)
    except Exception as e:
        print(f"Audit click: {e}")

    try:
        page.get_by_text("AI Validation", exact=False).first.click()
        page.wait_for_timeout(2000)
    except Exception as e:
        print(f"AI Validation click: {e}")

    try:
        page.get_by_text("Dataset Builder", exact=False).first.click()
        page.wait_for_timeout(2000)
    except Exception as e:
        print(f"Dataset Builder click: {e}")

    page.wait_for_timeout(3000)

    # Screenshot the page
    page.screenshot(path="inspect_page.png", full_page=True)
    print("Saved: inspect_page.png")

    # Dump the full page HTML to a file for inspection
    html = page.content()
    with open("inspect_page.html", "w") as f:
        f.write(html)
    print("Saved: inspect_page.html")

    # Try to find all inputs, buttons, and interactive elements on the page
    elements_info = page.evaluate("""
    () => {
        const results = [];

        // All inputs
        document.querySelectorAll('input').forEach(el => {
            results.push({
                tag: 'input',
                type: el.type,
                name: el.name,
                id: el.id,
                placeholder: el.placeholder,
                ariaLabel: el.getAttribute('aria-label'),
                className: el.className.substring(0, 100),
                value: el.value,
                visible: el.offsetParent !== null
            });
        });

        // All buttons
        document.querySelectorAll('button').forEach(el => {
            results.push({
                tag: 'button',
                text: el.textContent.trim().substring(0, 80),
                type: el.type,
                id: el.id,
                ariaLabel: el.getAttribute('aria-label'),
                disabled: el.disabled,
                className: el.className.substring(0, 100),
                visible: el.offsetParent !== null
            });
        });

        // Anything with calendar/date in class or aria
        document.querySelectorAll('[class*="date" i], [class*="calendar" i], [class*="picker" i], [aria-label*="date" i], [aria-label*="calendar" i]').forEach(el => {
            results.push({
                tag: el.tagName.toLowerCase(),
                text: el.textContent.trim().substring(0, 80),
                id: el.id,
                ariaLabel: el.getAttribute('aria-label'),
                className: el.className.substring(0, 150),
                role: el.getAttribute('role'),
                visible: el.offsetParent !== null,
                _marker: 'DATE_RELATED'
            });
        });

        return results;
    }
    """)

    with open("inspect_elements.json", "w") as f:
        import json
        json.dump(elements_info, f, indent=2)
    print(f"Saved: inspect_elements.json ({len(elements_info)} elements)")

    # Keep browser open for 10 seconds so user can see the page
    page.wait_for_timeout(10000)

    browser.close()
    pw.stop()
    print("Done.")

if __name__ == "__main__":
    main()
