"""
ServiceTitanScraper — Playwright browser automation for ROI report data extraction.

Pulls Technician Performance and Timesheet reports from ServiceTitan,
handling login + MFA, date range filtering, and BU filtering per trade.
"""

from __future__ import annotations

import csv
import io
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from playwright.sync_api import sync_playwright, Page, Browser, BrowserContext, Playwright


# ─── Data Models ─────────────────────────────────────────────────────────────

@dataclass
class TradeMetrics:
    total_sales: float = 0
    total_tech_lead_sales: float = 0
    completed_revenue: float = 0
    completed_jobs: int = 0
    opportunities: int = 0
    sales_opportunities: int = 0
    leads_set: int = 0
    converted_jobs: int = 0


@dataclass
class DriveTimeMetrics:
    total_drives: int = 0
    jobs: int = 0
    drive_time_hours: float = 0
    idle_time_hours: float = 0
    working_time_hours: float = 0


# Trade → list of BU names (configured per org)
DEFAULT_TRADE_BUS: dict[str, list[str]] = {
    "HVAC": [],
    "Plumbing": [],
    "Electrical": [],
    "Drains": [],
}

# Column labels as they appear in ServiceTitan's column picker
# ST uses singular "Opportunity" / "Sales Opportunity" (not plural)
# ST uses "Total Sales from TGL" (not "Total Tech Lead Sales")
TECH_PERF_COLUMNS = [
    "Total Sales",
    "Total Sales from TGL",
    "Completed Revenue",
    "Completed Jobs",
    "Opportunity",
    "Sales Opportunity",
    "Leads Set",
    "Converted Jobs",
]

# Map from ST column names → our internal metric names (for data extraction & template)
ST_COL_TO_METRIC = {
    "Total Sales": "Total Sales",
    "Total Sales from TGL": "Total Tech Lead Sales",
    "Completed Revenue": "Completed Revenue",
    "Completed Jobs": "Completed Jobs",
    "Opportunity": "Opportunities",
    "Sales Opportunity": "Sales Opportunities",
    "Leads Set": "Leads Set",
    "Converted Jobs": "Converted Jobs",
}

# Plumbing & Electrical don't have Tech Lead Sales or Leads Set
PLUMBING_COLUMNS = [
    "Total Sales",
    "Completed Revenue",
    "Completed Jobs",
    "Opportunity",
    "Sales Opportunity",
    "Converted Jobs",
]

ELECTRICAL_COLUMNS = PLUMBING_COLUMNS


# ─── Scraper Class ───────────────────────────────────────────────────────────

class ServiceTitanScraper:
    """Automates ServiceTitan report extraction via Playwright."""

    def __init__(
        self,
        st_username: str,
        st_password: str,
        log_fn: Callable[[str], None] | None = None,
    ):
        self.username = st_username
        self.password = st_password
        self.log = log_fn or print
        self._pw: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None

    # ── Lifecycle ──

    def launch(self):
        """Launch Chromium browser (visible for debugging)."""
        self.log("Launching browser...")
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=False, slow_mo=300)
        self._context = self._browser.new_context(
            viewport={"width": 1440, "height": 900},
            accept_downloads=True,
        )
        self.page = self._context.new_page()
        self.page.set_default_timeout(30000)
        self.log("Browser launched.")

    def close(self):
        """Cleanup browser resources."""
        try:
            if self._context:
                self._context.close()
            if self._browser:
                self._browser.close()
            if self._pw:
                self._pw.stop()
        except Exception:
            pass

    # ── Login + MFA ──

    def login(self, mfa_code_fn: Callable[[], str]):
        """
        Login to go.servicetitan.com.
        mfa_code_fn: callable that returns the 6-digit MFA code (may block).
        """
        self.log("Navigating to ServiceTitan login...")
        self.page.goto("https://go.servicetitan.com/", wait_until="domcontentloaded", timeout=30000)
        time.sleep(5)

        # Username (ST uses name="username" with placeholder "Username")
        self.log("Entering username...")
        username_input = self.page.wait_for_selector(
            'input[name="username"], input[placeholder="Username"]',
            timeout=15000,
        )
        username_input.click()
        username_input.fill(self.username)

        # Password (same page — ST shows both fields at once)
        self.log("Entering password...")
        pw_input = self.page.wait_for_selector(
            'input[name="password"], input[type="password"]',
            timeout=10000,
        )
        pw_input.click()
        pw_input.fill(self.password)

        # Wait a moment for Cloudflare Turnstile to resolve
        self.log("Waiting for captcha to resolve...")
        time.sleep(3)

        # Click Sign In
        sign_in_btn = self.page.query_selector('button:has-text("Sign In")')
        if not sign_in_btn:
            sign_in_btn = self.page.query_selector('button[type="submit"]')
        if sign_in_btn:
            sign_in_btn.click()
        self.log("Sign In clicked, waiting for response...")
        time.sleep(5)

        # Wait for any navigation to settle after sign-in
        # ST redirects multiple times after login — wait for page to stabilize
        for _ in range(10):
            try:
                self.page.wait_for_load_state("domcontentloaded", timeout=5000)
            except Exception:
                pass
            time.sleep(1)
            # Check if page is stable (not mid-navigation)
            try:
                _ = self.page.url
                break
            except Exception:
                continue
        time.sleep(3)

        # Check for MFA — ST may redirect to an MFA page
        try:
            self._handle_mfa_if_needed(mfa_code_fn)
        except Exception as e:
            # If context was destroyed, wait and retry once
            self.log(f"MFA check failed ({e}), waiting for page to settle...")
            time.sleep(5)
            try:
                self.page.wait_for_load_state("domcontentloaded", timeout=10000)
            except Exception:
                pass
            time.sleep(3)
            self._handle_mfa_if_needed(mfa_code_fn)

        # Wait for the main app to load (look for sidebar or dashboard indicator)
        try:
            self.page.wait_for_selector(
                'nav, [data-testid*="sidebar"], .sidebar, #main-nav, a:has-text("Dashboard")',
                timeout=30000,
            )
        except Exception:
            # May already be on dashboard — check URL
            try:
                url = self.page.url
                if "go.servicetitan.com" in url and "/authorize" not in url:
                    pass
                else:
                    self.log(f"Warning: may not be fully logged in. Current URL: {url}")
            except Exception:
                self.log("Warning: could not check page URL after login")

        self.log(f"Logged into ServiceTitan. URL: {self.page.url}")

    def _handle_mfa_if_needed(self, mfa_code_fn: Callable[[], str]):
        """Detect and handle MFA challenge after Sign In."""
        # Look for MFA indicators on the current page
        mfa_input = self.page.query_selector(
            'input[name="Code"], input[name="code"], input[name="passcode"], '
            'input[placeholder*="code" i], input[placeholder*="verification" i], '
            'input[autocomplete="one-time-code"]'
        )
        page_text = self.page.evaluate('() => document.body ? document.body.innerText.substring(0, 1000) : ""')
        has_mfa_text = any(phrase in page_text.lower() for phrase in [
            "verification code", "enter code", "mfa", "multi-factor",
            "two-factor", "authenticator", "one-time",
        ])

        if not mfa_input and not has_mfa_text:
            self.log("No MFA prompt detected.")
            return

        self.log("MFA required — requesting code...")
        code = mfa_code_fn()
        if not code:
            raise RuntimeError("No MFA code provided")

        self.log("Entering MFA code...")
        if not mfa_input:
            # Try to find it now that we know MFA is needed
            mfa_input = self.page.wait_for_selector(
                'input[name="Code"], input[name="code"], input[name="passcode"], '
                'input[type="text"], input[type="tel"]',
                timeout=10000,
            )
        mfa_input.fill(code.strip())

        verify_btn = self.page.query_selector(
            'button:has-text("Verify"), button:has-text("Submit"), '
            'button:has-text("Continue"), button[type="submit"]'
        )
        if verify_btn:
            verify_btn.click()
        time.sleep(5)

    # ── Navigation ──

    def navigate_to_reports_page(self):
        """Navigate to the Reports section via top nav bar."""
        reports_link = self.page.query_selector('a[href*="/new/reports"]')
        if reports_link:
            reports_link.click()
            time.sleep(3)
        else:
            self.page.goto(
                "https://go.servicetitan.com/#/new/reports",
                wait_until="domcontentloaded",
                timeout=15000,
            )
            time.sleep(3)

    def navigate_to_report(self, report_name: str):
        """Search for an existing report by name in All Reports."""
        self.log(f"Searching for existing report: {report_name}")

        # Go to All Reports
        self.page.goto(
            "https://go.servicetitan.com/#/new/reports/all",
            wait_until="domcontentloaded",
            timeout=15000,
        )
        time.sleep(3)

        # Search
        search_input = self.page.wait_for_selector(
            'input[type="search"], input[placeholder="Search..."]',
            timeout=10000,
        )
        search_input.fill("")
        search_input.fill(report_name)
        time.sleep(3)

        # Click the matching report link
        report_link = self.page.query_selector(f'a:has-text("{report_name}")')
        if not report_link:
            report_link = self.page.query_selector(f'text="{report_name}"')
        if report_link:
            report_link.click()
            time.sleep(5)
            self.log(f"Opened report: {report_name} — URL: {self.page.url}")
            return True
        else:
            self.log(f"Report '{report_name}' not found in search results.")
            return False

    def create_report(self, report_name: str, template: str, columns: list[str]):
        """
        Create a new report:
        1. Reports → All Reports → Create Report button
        2. Choose report type (e.g. "Technicians") → template (e.g. "Technician Performance")
        3. Select columns
        4. Save with name, category Operations, uncheck Share
        """
        self.log(f"Creating new report: {report_name}")

        # Navigate to All Reports page
        self.page.goto(
            "https://go.servicetitan.com/#/new/reports/all",
            wait_until="domcontentloaded",
            timeout=15000,
        )
        time.sleep(4)

        # Click "Create Report" button (top-right blue button)
        self.page.locator('button:has-text("Create Report")').click()
        self.log("Clicked Create Report")
        time.sleep(4)

        # Step 1: Choose report type — wait for the wizard to load
        try:
            self.page.wait_for_selector('text="Technicians"', timeout=15000)
            self.page.locator('text="Technicians"').first.click()
            self.log("Selected category: Technicians")
            time.sleep(3)
        except Exception:
            self.log("WARNING: Could not find 'Technicians' category")

        # Step 2: Choose template
        try:
            self.page.wait_for_selector(f'text="{template}"', timeout=10000)
            self.page.locator(f'text="{template}"').first.click()
            self.log(f"Selected template: {template}")
            time.sleep(3)
        except Exception:
            self.log(f"WARNING: Could not find template '{template}'")

        # Wait for column picker to load (Step 3 of 5)
        # The column cards use class .qa-column-togglebox
        try:
            self.page.locator('.qa-column-togglebox').first.wait_for(
                state="visible", timeout=10000
            )
            self.log("Column picker loaded")
        except Exception:
            self.log("WARNING: Column picker did not load, checking page state...")
            self.log(f"  URL: {self.page.url}")
            # Take a debug screenshot
            try:
                self.page.screenshot(path="/tmp/roi_debug_columns.png")
                self.log("  Debug screenshot saved to /tmp/roi_debug_columns.png")
            except Exception:
                pass

        # Deselect all defaults
        deselect = self.page.locator('a:has-text("Deselect All")')
        if deselect.count() > 0 and deselect.first.is_visible():
            deselect.first.click()
            time.sleep(1)
            self.log("Deselected all default columns.")

        # Find the column search input
        search = self.page.locator('input[placeholder="Search columns"]')
        if search.count() == 0:
            search = self.page.locator('input[placeholder*="Search"]')
        has_search = search.count() > 0
        if has_search:
            self.log("Found column search input")
        else:
            self.log("WARNING: No column search input found")

        # Select each column by searching + clicking its togglebox
        for col in columns:
            if has_search:
                search.first.fill("")
                time.sleep(0.3)
                search.first.fill(col)
                time.sleep(2)

            # Find all visible togglebox cards and match by exact text
            cards = self.page.locator('.qa-column-togglebox')
            count = cards.count()
            clicked = False

            for i in range(count):
                card = cards.nth(i)
                if not card.is_visible():
                    continue
                # Get text from the Togglebox__content span
                content = card.locator('.Togglebox__content')
                if content.count() > 0:
                    text = content.first.text_content().strip()
                else:
                    text = card.text_content().strip()

                if text == col:
                    # Click the checkbox
                    cb = card.locator('input.Checkbox__input')
                    if cb.count() > 0:
                        if not cb.first.is_checked():
                            cb.first.click(force=True)
                        clicked = True
                        break
                    else:
                        card.click()
                        clicked = True
                        break

            if clicked:
                self.log(f"  Selected column: {col}")
                time.sleep(0.5)
            else:
                self.log(f"  WARNING: Column '{col}' not found ({count} cards visible)")

        # Clear search
        if has_search:
            search.first.fill("")
            time.sleep(0.5)

        # Verify columns were selected
        count_el = self.page.locator('.qa-selected-columns-count')
        if count_el.count() > 0:
            selected_text = count_el.first.text_content().strip()
            self.log(f"Column selection: {selected_text}")

        # Dismiss any Pendo banners/overlays that block clicks
        self._dismiss_pendo()

        # Click Next — button is disabled when 0 columns selected
        next_btn = self.page.locator('button:has-text("Next")')
        btn_class = next_btn.get_attribute("class") or ""
        if "disabled" in btn_class.lower():
            self.log("WARNING: Next button is disabled — no columns were selected")
            return
        next_btn.click(force=True)
        self.log("Clicked Next → Step 4 (Set Details)")
        time.sleep(4)

        # Step 4 of 5: Set Details — Name (required), Category (required), Share checkbox
        # Name input — first visible text input in the form
        name_inputs = self.page.locator('input[type="text"]')
        name_filled = False
        for i in range(name_inputs.count()):
            inp = name_inputs.nth(i)
            if inp.is_visible():
                inp.fill(report_name)
                name_filled = True
                self.log(f"Entered report name: {report_name}")
                time.sleep(0.5)
                break
        if not name_filled:
            self.log("WARNING: Could not find report name input")

        # Category — Semantic UI custom dropdown (not a native <select>)
        # Class: .qa-report-details-category contains .ui.selection.dropdown
        cat_dropdown = self.page.locator('.qa-report-details-category .ui.dropdown')
        if cat_dropdown.count() > 0 and cat_dropdown.first.is_visible():
            cat_dropdown.first.click()
            time.sleep(1)
            # Click "Operations" option in the dropdown menu
            ops_option = self.page.locator('[role="option"]:has-text("Operations")')
            if ops_option.count() == 0:
                ops_option = self.page.locator('.item:has-text("Operations")')
            if ops_option.count() > 0:
                ops_option.first.click()
                self.log("Selected category: Operations")
            else:
                # Fall back to any visible option
                any_option = self.page.locator('[role="option"]')
                if any_option.count() > 0:
                    any_option.first.click()
                    self.log("Selected category: (first available)")
            time.sleep(0.5)
        else:
            self.log("WARNING: Category dropdown not found")

        # Uncheck "Share this report" — use force=True because label intercepts clicks
        share_cb = self.page.locator('label:has-text("Share") input[type="checkbox"]')
        if share_cb.count() > 0 and share_cb.first.is_checked():
            share_cb.first.click(force=True)
            self.log("Unchecked Share")
            time.sleep(0.3)

        # Click Save
        self._dismiss_pendo()
        save_btn = self.page.locator('[data-cy="new-report-save-button"]')
        if save_btn.count() == 0:
            save_btn = self.page.locator('button:has-text("Save")')

        if save_btn.count() > 0:
            time.sleep(1)
            save_btn.first.click(force=True)
            self.log("Clicked Save")

            # Wait for redirect to the actual report page (URL should change from /new)
            time.sleep(5)

        current_url = self.page.url
        self.log(f"After save — URL: {current_url}")

        # If still on /reports/new, the save may have created the report but didn't redirect
        # Search for it by name
        if "/reports/new" in current_url:
            self.log("Save completed but still on create page — navigating to report...")
            found = self.navigate_to_report(report_name)
            if found:
                self.log(f"Opened saved report: {self.page.url}")
            else:
                self.log("WARNING: Could not find the saved report")

        # Wait for the report page to fully load — look for Run Report button
        try:
            self.page.locator('button:has-text("Run Report"), button:has-text("Run")').first.wait_for(
                state="visible", timeout=10000
            )
            self.log("Report page loaded with Run button")
        except Exception:
            self.log(f"Report page state — URL: {self.page.url}")

    def open_or_create_report(self, report_name: str, template: str, columns: list[str]):
        """Try to open existing report, create new if not found."""
        found = self.navigate_to_report(report_name)
        if not found:
            self.create_report(report_name, template, columns)

    # ── Filters ──

    def set_business_unit_filter(self, bu_list: list[str]):
        """Apply BU filter on the current report.

        The BU filter is an Anvil component:
        - Container: [data-criteria-name="BusinessUnitId"]
        - Trigger: div.Trigger (tabindex=0) showing "All" — click to open
        - Search: text input inside the dropdown panel (second visible text input)
        - Options: checkboxes with label text matching BU names
        - Apply: "Filter" button

        If bu_list is empty, resets the filter to "All" (unchecks everything).
        """
        if not bu_list:
            self.log("No BU filter to apply (resetting to All).")
            self._reset_bu_filter()
            return

        self.log(f"Setting BU filter: {bu_list}")
        self._open_bu_dropdown_and_select(bu_list)

    def _open_bu_dropdown_and_select(self, bu_list: list[str]):
        """Open the BU dropdown (Popper portal), uncheck old, select new, click Filter."""
        # Wait for filters to load
        try:
            self.page.locator('[data-criteria-name="BusinessUnitId"]').first.wait_for(
                state="visible", timeout=10000
            )
        except Exception:
            self.log("WARNING: BU filter not found after waiting")
            return

        # Click the Trigger to open the Popper dropdown
        bu_container = self.page.locator('[data-criteria-name="BusinessUnitId"]')
        trigger = bu_container.first.locator('.Trigger')
        if trigger.count() == 0:
            self.log("WARNING: BU filter Trigger not found")
            return
        trigger.first.click()
        time.sleep(2)

        # The dropdown renders as a Popper portal at body level
        # Wait for the Popper with OptionList to appear
        popper_found = False
        for attempt in range(3):
            try:
                self.page.locator('.Popper .OptionList').first.wait_for(
                    state="visible", timeout=5000
                )
                popper_found = True
                break
            except Exception:
                if attempt < 2:
                    self.log(f"  BU dropdown not open yet, retrying click... (attempt {attempt + 2})")
                    trigger.first.click()
                    time.sleep(2)
        if not popper_found:
            self.log("WARNING: BU dropdown did not open (no OptionList in Popper)")
            return

        # Uncheck all currently checked BUs inside the Popper
        self.page.evaluate('''() => {
            const popper = document.querySelector('.Popper .OptionList');
            if (!popper) return;
            popper.querySelectorAll('input[type="checkbox"]').forEach(cb => {
                if (cb.checked) cb.click();
            });
        }''')
        time.sleep(0.5)

        # Find the search input inside the Popper header (.Select__search input)
        search_selector = '.Popper .Select__search input'
        has_search = self.page.locator(search_selector).count() > 0

        # Select each BU
        for bu in bu_list:
            if has_search:
                search_el = self.page.locator(search_selector).first
                search_el.fill("")
                time.sleep(0.3)
                search_el.fill(bu)
                time.sleep(1.5)

            # Check the matching checkbox inside the Popper OptionList
            check_result = self.page.evaluate('''(buName) => {
                const popper = document.querySelector('.Popper .OptionList');
                if (!popper) return { found: false, error: 'no OptionList' };
                const labels = popper.querySelectorAll('label');
                for (const label of labels) {
                    const text = label.textContent.trim();
                    if (text === buName) {
                        const cb = label.querySelector('input[type="checkbox"]');
                        if (cb && !cb.checked) cb.click();
                        return { found: true, text: text };
                    }
                }
                return { found: false };
            }''', bu)

            if check_result.get("found"):
                self.log(f"  Selected BU: {bu}")
            else:
                self.log(f"  WARNING: BU '{bu}' not found in filter options")

            time.sleep(0.5)

        # Clear search
        if has_search:
            self.page.locator(search_selector).first.fill("")
            time.sleep(0.5)

        # Click "Filter" button inside the Popper
        filter_btn = self.page.locator('.Popper .Select__filter')
        if filter_btn.count() == 0:
            filter_btn = self.page.locator('.Popper button:has-text("Filter")')
        if filter_btn.count() > 0 and filter_btn.first.is_visible():
            filter_btn.first.click()
            time.sleep(2)
            self.log(f"BU filter applied: {bu_list}")
        else:
            self.page.keyboard.press("Escape")
            time.sleep(0.5)
            self.log(f"BU filter set (no Filter button found): {bu_list}")

    def _reset_bu_filter(self):
        """Reset BU filter to 'All' by unchecking all selections via the Popper dropdown."""
        try:
            self.page.locator('[data-criteria-name="BusinessUnitId"]').first.wait_for(
                state="visible", timeout=10000
            )
        except Exception:
            return

        bu_container = self.page.locator('[data-criteria-name="BusinessUnitId"]')
        trigger = bu_container.first.locator('.Trigger')
        if trigger.count() == 0:
            return
        trigger.first.click()
        time.sleep(2)

        # Wait for the Popper OptionList to appear
        try:
            self.page.locator('.Popper .OptionList').first.wait_for(
                state="visible", timeout=5000
            )
        except Exception:
            self.page.keyboard.press("Escape")
            self.log("BU filter reset skipped — dropdown did not open.")
            return

        # Uncheck all checked BUs inside the Popper
        self.page.evaluate('''() => {
            const popper = document.querySelector('.Popper .OptionList');
            if (!popper) return;
            popper.querySelectorAll('input[type="checkbox"]').forEach(cb => {
                if (cb.checked) cb.click();
            });
        }''')
        time.sleep(0.5)

        # Click Filter button inside the Popper
        filter_btn = self.page.locator('.Popper .Select__filter')
        if filter_btn.count() == 0:
            filter_btn = self.page.locator('.Popper button:has-text("Filter")')
        if filter_btn.count() > 0 and filter_btn.first.is_visible():
            filter_btn.first.click()
            # Wait for report to re-run after filter change
            time.sleep(5)
            try:
                self.page.wait_for_load_state("domcontentloaded", timeout=10000)
            except Exception:
                pass
            time.sleep(3)
        else:
            self.page.keyboard.press("Escape")
            time.sleep(0.5)

        self.log("BU filter reset to All.")

    def set_date_range(self, start: str, end: str):
        """
        Set custom date range on the current report.
        ST uses a single text input (class ta-center-i) showing "Dec 4, 2023 – Dec 11, 2023".
        We click it to open a date picker, then fill From/To fields.
        Dates in MM/DD/YYYY format.
        """
        self.log(f"Setting date range: {start} - {end}")

        # Find the date range input using JavaScript (avoids visibility issues)
        date_input = self.page.evaluate_handle('''() => {
            // Look for the date range text input by class or by value pattern
            const inputs = document.querySelectorAll('input[type="text"]');
            for (const inp of inputs) {
                if (inp.className.includes('ta-center') ||
                    (inp.value && /[A-Z][a-z]{2} \\d/.test(inp.value))) {
                    return inp;
                }
            }
            // Fallback: any text input with date-like value or date placeholder
            for (const inp of inputs) {
                if (inp.placeholder === '__/__/____' || /\\d{1,2}\\/\\d{1,2}\\/\\d{4}/.test(inp.value)) {
                    return inp;
                }
            }
            // Fallback: first visible text input in filter area
            for (const inp of inputs) {
                const rect = inp.getBoundingClientRect();
                if (rect.y > 100 && rect.y < 400 && rect.width > 80) {
                    return inp;
                }
            }
            return null;
        }''')

        is_null = self.page.evaluate('el => el === null', date_input)
        if is_null:
            self.log("WARNING: Could not find date range input, trying direct input approach")
            # Fallback: look for any visible date inputs directly
            direct_inputs = self.page.query_selector_all('input[placeholder="__/__/____"]')
            if len(direct_inputs) >= 2:
                direct_inputs[0].click(click_count=3)
                time.sleep(0.3)
                direct_inputs[0].fill(start)
                time.sleep(0.5)
                direct_inputs[1].click(click_count=3)
                time.sleep(0.3)
                direct_inputs[1].fill(end)
                time.sleep(0.5)
                apply = self.page.query_selector('button:has-text("Apply")')
                if apply:
                    apply.click()
                    time.sleep(2)
                self.log(f"Date range set (direct): {start} - {end}")
            else:
                self.log("WARNING: No date inputs found at all")
            return

        # Click via JS to avoid viewport issues
        self.page.evaluate('el => el.click()', date_input)
        time.sleep(2)

        # Kendo UI date picker popup with two text inputs (placeholder "__/__/____")
        # and an Apply button
        date_inputs = self.page.query_selector_all('input[placeholder="__/__/____"]')

        if len(date_inputs) >= 2:
            # From input
            date_inputs[0].click(click_count=3)
            time.sleep(0.3)
            date_inputs[0].fill(start)
            time.sleep(0.5)

            # To input
            date_inputs[1].click(click_count=3)
            time.sleep(0.3)
            date_inputs[1].fill(end)
            time.sleep(0.5)

            # Click Apply
            apply = self.page.query_selector('button:has-text("Apply")')
            if apply:
                apply.click()
                time.sleep(2)
        else:
            # Fallback: type into the main date input directly
            self.page.evaluate('el => { el.value = ""; el.focus(); }', date_input)
            time.sleep(0.3)
            self.page.keyboard.press("Meta+a")
            self.page.keyboard.type(f"{start} - {end}", delay=30)
            self.page.keyboard.press("Enter")
            time.sleep(1)

        self.log(f"Date range set: {start} - {end}")

    # ── Data Extraction ──

    def run_and_export(self, columns: list[str] | None = None) -> dict[str, float | int]:
        """
        Run the report and extract totals from the DOM.
        Returns dict of column_name → value.
        Falls back to CSV export if DOM parsing fails.
        """
        self.log("Running report and extracting data...")

        # Click Run Report button
        run_btn = self.page.query_selector(
            'button:has-text("Run Report"), button:has-text("Run")'
        )
        if run_btn:
            # Use JS click to avoid viewport issues
            self.page.evaluate('btn => btn.click()', run_btn)
            self.log("Run Report clicked, waiting for results...")
            # Wait for loading indicator to appear and disappear
            time.sleep(3)
            try:
                # Wait for any loading/spinner to disappear
                self.page.wait_for_selector(
                    '[class*="loading" i], [class*="spinner" i], [class*="Loading"]',
                    state="hidden",
                    timeout=30000,
                )
            except Exception:
                pass
            time.sleep(5)

        # Wait for table to appear
        time.sleep(3)

        # Try DOM extraction first
        try:
            data = self._extract_from_dom(columns)
            if data:
                self.log(f"Extracted from DOM: {data}")
                return data
        except Exception as e:
            self.log(f"DOM extraction failed: {e}, trying CSV export...")

        # Fallback: CSV export
        return self._extract_from_csv(columns)

    def _extract_from_dom(self, columns: list[str] | None) -> dict[str, float | int]:
        """Parse the summary/totals row from the report table."""
        result = self.page.evaluate("""() => {
            // Find the totals/summary row
            const rows = document.querySelectorAll('tr');
            let totalsRow = null;
            for (const row of rows) {
                const firstCell = row.querySelector('td, th');
                if (firstCell) {
                    const text = firstCell.textContent.trim().toLowerCase();
                    if (text === 'total' || text === 'totals' || text === 'grand total') {
                        totalsRow = row;
                        break;
                    }
                }
            }

            if (!totalsRow) {
                // Try last row of table body
                const tbody = document.querySelector('tbody');
                if (tbody) {
                    const allRows = tbody.querySelectorAll('tr');
                    totalsRow = allRows[allRows.length - 1];
                }
            }

            if (!totalsRow) return null;

            // Get header row to map column names
            const headerRow = document.querySelector('thead tr, tr:first-child');
            if (!headerRow) return null;

            const headers = Array.from(headerRow.querySelectorAll('th, td')).map(
                el => el.textContent.trim()
            );
            const cells = Array.from(totalsRow.querySelectorAll('td, th')).map(
                el => el.textContent.trim()
            );

            const result = {};
            for (let i = 0; i < headers.length && i < cells.length; i++) {
                result[headers[i]] = cells[i];
            }
            return result;
        }""")

        if not result:
            return {}

        # Parse numeric values, mapping ST column names to internal metric names
        parsed = {}
        target_cols = columns or TECH_PERF_COLUMNS
        for col in target_cols:
            raw = result.get(col, "0")
            # Map ST name to internal name (e.g. "Total Sales from TGL" → "Total Tech Lead Sales")
            metric_name = ST_COL_TO_METRIC.get(col, col)
            parsed[metric_name] = self._parse_number(raw)

        return parsed

    def _extract_from_csv(self, columns: list[str] | None) -> dict[str, float | int]:
        """Click Export → CSV, read the downloaded file, sum columns."""
        self.log("Exporting to CSV...")

        # Click export button
        export_btn = self.page.query_selector(
            'button:has-text("Export"), button:has-text("Download")'
        )
        if not export_btn:
            self.log("No export button found.")
            return {}

        with self.page.expect_download() as download_info:
            export_btn.click()
            # Look for CSV option
            csv_opt = self.page.query_selector(
                'li:has-text("CSV"), button:has-text("CSV"), a:has-text("CSV")'
            )
            if csv_opt:
                csv_opt.click()

        download = download_info.value
        path = download.path()
        self.log(f"Downloaded CSV: {path}")

        target_cols = columns or TECH_PERF_COLUMNS
        sums: dict[str, float] = {}
        for col in target_cols:
            metric_name = ST_COL_TO_METRIC.get(col, col)
            sums[metric_name] = 0
        row_count = 0

        with open(path, "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                row_count += 1
                for col in target_cols:
                    if col in row:
                        metric_name = ST_COL_TO_METRIC.get(col, col)
                        sums[metric_name] += self._parse_number(row[col])

        self.log(f"CSV parsed: {row_count} rows")
        return sums

    # ── Timesheet / Drive Time ──

    def extract_drive_time(
        self,
        start: str,
        end: str,
        activity_filter: str,
    ) -> tuple[int, float]:
        """
        On the Timesheet report, filter by activity type and date range.
        Returns (row_count, total_duration_hours).
        """
        self.log(f"Extracting drive time: {activity_filter} ({start} - {end})")

        self.set_date_range(start, end)
        time.sleep(1)

        # Filter by activity
        activity_btn = self.page.query_selector(
            'button:has-text("Activity"), [data-testid*="activity"], '
            'span:has-text("Timesheet Activity")'
        )
        if activity_btn:
            activity_btn.click()
            time.sleep(1)

            # Clear and select
            clear = self.page.query_selector('button:has-text("Clear"), a:has-text("Clear")')
            if clear:
                clear.click()
                time.sleep(0.3)

            option = self.page.query_selector(
                f'label:has-text("{activity_filter}"), [role="option"]:has-text("{activity_filter}")'
            )
            if option:
                option.click()
                time.sleep(0.3)

            apply = self.page.query_selector('button:has-text("Apply"), button:has-text("Done")')
            if apply:
                apply.click()
                time.sleep(1)

        # Run report
        run_btn = self.page.query_selector('button:has-text("Run"), button:has-text("Generate")')
        if run_btn:
            run_btn.click()
            time.sleep(5)
            self.page.wait_for_load_state("domcontentloaded")

        time.sleep(3)

        # Extract row count and duration sum from DOM
        result = self.page.evaluate("""() => {
            const rows = document.querySelectorAll('tbody tr');
            let totalDuration = 0;
            let rowCount = 0;

            // Find Duration column index from headers
            const headerRow = document.querySelector('thead tr');
            if (!headerRow) return { rowCount: 0, totalDuration: 0 };

            const headers = Array.from(headerRow.querySelectorAll('th')).map(
                el => el.textContent.trim().toLowerCase()
            );
            const durIdx = headers.findIndex(h => h.includes('duration'));

            for (const row of rows) {
                const cells = row.querySelectorAll('td');
                if (cells.length === 0) continue;

                // Skip totals row
                const firstText = cells[0]?.textContent?.trim().toLowerCase() || '';
                if (firstText === 'total' || firstText === 'totals') {
                    // Use the totals row duration if available
                    if (durIdx >= 0 && cells[durIdx]) {
                        const val = cells[durIdx].textContent.trim();
                        const match = val.match(/[\\d,.]+/);
                        if (match) totalDuration = parseFloat(match[0].replace(/,/g, ''));
                    }
                    continue;
                }

                rowCount++;

                if (durIdx >= 0 && cells[durIdx] && totalDuration === 0) {
                    const val = cells[durIdx].textContent.trim();
                    const match = val.match(/[\\d,.]+/);
                    if (match) totalDuration += parseFloat(match[0].replace(/,/g, ''));
                }
            }

            return { rowCount, totalDuration };
        }""")

        row_count = result.get("rowCount", 0) if result else 0
        total_duration = result.get("totalDuration", 0) if result else 0

        self.log(f"  {activity_filter}: {row_count} rows, {total_duration:.2f} hours")
        return row_count, total_duration

    # ── Helpers ──

    def _dismiss_pendo(self):
        """Dismiss any Pendo banners/tooltips that intercept pointer events."""
        self.page.evaluate('''() => {
            const pendo = document.getElementById('pendo-base');
            if (pendo) pendo.remove();
            // Also remove any other Pendo containers
            document.querySelectorAll('[id^="pendo-"]').forEach(el => {
                if (el.id !== 'pendo-designer-container') el.remove();
            });
        }''')

    @staticmethod
    def _parse_number(raw: str) -> float:
        """Parse a number from a formatted string like '$1,234.56' or '1234'."""
        if not raw:
            return 0
        cleaned = re.sub(r'[^0-9.\-]', '', str(raw))
        try:
            return float(cleaned)
        except ValueError:
            return 0


# ─── High-Level Extraction Orchestrator ──────────────────────────────────────

def pull_roi_data(
    scraper: ServiceTitanScraper,
    trades: dict[str, list[str]],
    pre_start: str,
    pre_end: str,
    post_start: str,
    post_end: str,
    org_name: str = "ROI",
    natural_y1_start: str | None = None,
    natural_y1_end: str | None = None,
    natural_y2_start: str | None = None,
    natural_y2_end: str | None = None,
) -> dict:
    """
    Pull all ROI data from ServiceTitan.

    Returns:
    {
        "basic": {trade: {"pre": TradeMetrics, "post": TradeMetrics}},
        "natural": {trade: {"y1": TradeMetrics, "y2": TradeMetrics}},  (if dates provided)
        "high_level": {"pre": TradeMetrics, "post": TradeMetrics},
        "drive_time": {"pre": DriveTimeMetrics, "post": DriveTimeMetrics},
    }
    """
    results = {
        "basic": {},
        "natural": {},
        "high_level_pre": TradeMetrics(),
        "high_level_post": TradeMetrics(),
        "drive_time_pre": DriveTimeMetrics(),
        "drive_time_post": DriveTimeMetrics(),
    }

    # ── Technician Performance Report ──
    scraper.log("=== Technician Performance Report ===")

    report_name = f"ROI Pull {org_name}"
    scraper.log("Opening/creating Technician Performance report...")
    scraper.open_or_create_report(
        report_name=report_name,
        template="Technician Performance",
        columns=TECH_PERF_COLUMNS,
    )

    for trade, bus in trades.items():
        scraper.log(f"--- {trade} ---")

        # Determine which columns this trade uses
        if trade in ("Plumbing", "Electrical"):
            cols = PLUMBING_COLUMNS
        else:
            cols = TECH_PERF_COLUMNS

        # Pre-PB period
        scraper.set_business_unit_filter(bus)
        scraper.set_date_range(pre_start, pre_end)
        pre_data = scraper.run_and_export(cols)
        pre_metrics = _data_to_metrics(pre_data)

        # Post-PB period
        scraper.set_date_range(post_start, post_end)
        post_data = scraper.run_and_export(cols)
        post_metrics = _data_to_metrics(post_data)

        results["basic"][trade] = {"pre": pre_metrics, "post": post_metrics}

        # Accumulate high-level totals
        _add_metrics(results["high_level_pre"], pre_metrics)
        _add_metrics(results["high_level_post"], post_metrics)

        # Natural delta periods (if provided)
        if natural_y1_start and natural_y1_end and natural_y2_start and natural_y2_end:
            scraper.set_date_range(natural_y1_start, natural_y1_end)
            y1_data = scraper.run_and_export(cols)
            y1_metrics = _data_to_metrics(y1_data)

            scraper.set_date_range(natural_y2_start, natural_y2_end)
            y2_data = scraper.run_and_export(cols)
            y2_metrics = _data_to_metrics(y2_data)

            results["natural"][trade] = {"y1": y1_metrics, "y2": y2_metrics}

        # Reset BU filter for next trade
        scraper.set_business_unit_filter([])
        time.sleep(2)

    # ── Drive Time (Timesheet report) ──
    try:
        scraper.log("=== Timesheet Report (Drive Time) ===")
        found = scraper.navigate_to_report("Timesheet")
        if not found:
            scraper.log("Timesheet report not found — skipping Drive Time.")
        else:
            for period_label, start, end, target_key in [
                ("Pre-PB", pre_start, pre_end, "drive_time_pre"),
                ("Post-PB", post_start, post_end, "drive_time_post"),
            ]:
                scraper.log(f"--- Drive Time: {period_label} ---")
                dt: DriveTimeMetrics = results[target_key]

                # Driving
                drive_count, drive_hours = scraper.extract_drive_time(start, end, "Driving")
                dt.total_drives = drive_count
                dt.drive_time_hours = drive_hours

                # Idle
                _, idle_hours = scraper.extract_drive_time(start, end, "Idle")
                dt.idle_time_hours = idle_hours

                # Working
                working_count, working_hours = scraper.extract_drive_time(start, end, "Working")
                dt.jobs = working_count
                dt.working_time_hours = working_hours
    except Exception as e:
        scraper.log(f"Drive Time extraction failed (non-fatal): {e}")

    scraper.log("=== Data extraction complete ===")
    return results


def _data_to_metrics(data: dict[str, float | int]) -> TradeMetrics:
    """Convert raw column dict to TradeMetrics."""
    return TradeMetrics(
        total_sales=data.get("Total Sales", 0),
        total_tech_lead_sales=data.get("Total Tech Lead Sales", 0),
        completed_revenue=data.get("Completed Revenue", 0),
        completed_jobs=int(data.get("Completed Jobs", 0)),
        opportunities=int(data.get("Opportunities", 0)),
        sales_opportunities=int(data.get("Sales Opportunities", 0)),
        leads_set=int(data.get("Leads Set", 0)),
        converted_jobs=int(data.get("Converted Jobs", 0)),
    )


def _add_metrics(target: TradeMetrics, source: TradeMetrics):
    """Accumulate source into target (for high-level totals)."""
    target.total_sales += source.total_sales
    target.total_tech_lead_sales += source.total_tech_lead_sales
    target.completed_revenue += source.completed_revenue
    target.completed_jobs += source.completed_jobs
    target.opportunities += source.opportunities
    target.sales_opportunities += source.sales_opportunities
    target.leads_set += source.leads_set
    target.converted_jobs += source.converted_jobs
