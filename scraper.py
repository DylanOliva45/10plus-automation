"""
ProBookScraper — Playwright browser automation for AI Validation 10+ reports.

Phases:
  1. Launch browser & manual login
  2. Navigate to Audit > AI Validation > Dataset Builder
  3. Build dataset (date range)
  4. Run AI Validation
  5. Configure diff columns, infinite-scroll, bulk-scrape all jobs
  7. (Optional) QA jobs in ServiceTitan
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright, Page, Browser, BrowserContext, Playwright

load_dotenv()


# ─── Data Model ───────────────────────────────────────────────────────────────

@dataclass
class JobSide:
    job_type: str = ""
    priority: str = ""
    tags: list[str] = field(default_factory=list)
    is_first_call: Optional[bool] = None
    arrival_window: str = ""


@dataclass
class JobRecord:
    job_id: str = ""
    business_unit: str = ""
    ai_prediction: JobSide = field(default_factory=JobSide)
    dispatcher_verified: JobSide = field(default_factory=JobSide)
    # Derived fields — populated by compute_derived_fields()
    ai_has_10plus: bool = False
    disp_has_10plus: bool = False
    unknown_age: bool = False
    ten_plus_status: str = ""
    notes: str = ""

    def compute_derived_fields(self) -> None:
        self.ai_has_10plus = any("10+" in tag for tag in self.ai_prediction.tags)
        self.disp_has_10plus = any("10+" in tag for tag in self.dispatcher_verified.tags)
        self.unknown_age = "Unknown Age" in self.ai_prediction.tags or "Unknown Age" in self.dispatcher_verified.tags

        if self.ai_has_10plus and self.disp_has_10plus:
            self.ten_plus_status = "Match"
        elif self.disp_has_10plus and not self.ai_has_10plus:
            self.ten_plus_status = "AI Missed 10+"
        elif self.ai_has_10plus and not self.disp_has_10plus:
            self.ten_plus_status = "AI Added 10+"
        else:
            self.ten_plus_status = ""

        # Auto-note for unknown age cases
        if self.unknown_age and self.ten_plus_status == "AI Added 10+":
            self.notes = "Unknown Age — AI tagged 10+ but age data unavailable"


@dataclass
class QARecord:
    job_id: str = ""
    equipment_found: bool = False
    ages_found: list[str] = field(default_factory=list)
    screenshot_path: str = ""
    notes: str = ""


# ─── ProBookScraper ───────────────────────────────────────────────────────────

class ProBookScraper:
    """Automates ProBook admin dashboard for AI Validation 10+ auditing."""

    PROBOOK_URL = "https://admin.probook.ai"
    SERVICETITAN_URL = "https://go.servicetitan.com"

    def __init__(self, customer_name: str, start_date: str, end_date: str,
                 qa_dir: str = "qa_screenshots", interactive: bool = True):
        self.customer_name = customer_name
        self.start_date = start_date
        self.end_date = end_date
        self.interactive = interactive
        self.qa_dir = Path(qa_dir)
        self.qa_dir.mkdir(parents=True, exist_ok=True)

        self._username = os.getenv("PROBOOK_USERNAME", "")
        self._password = os.getenv("PROBOOK_PASSWORD", "")

        self._pw: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.jobs: list[JobRecord] = []
        self.qa_records: list[QARecord] = []
        self._dataset_name: str = ""

    # ── Phase 1: Launch & Login ───────────────────────────────────────────

    def launch(self) -> None:
        """Start headed Chromium browser."""
        self._print_status("Launching browser...")
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=False, slow_mo=100)
        self._context = self._browser.new_context(viewport={"width": 1440, "height": 900})
        self._context.set_default_timeout(30_000)
        self.page = self._context.new_page()

    def login_and_select_customer(self) -> None:
        """Navigate to ProBook, auto-login (with manual fallback), then select customer."""
        self._print_status("Navigating to ProBook admin...")
        self.page.goto(self.PROBOOK_URL, wait_until="networkidle")

        self._auto_login()

        # Give dashboard time to fully settle after login
        self._print_status("Waiting for dashboard to settle...")
        self.page.wait_for_timeout(3000)

        self._select_customer()

    def _pause(self, message: str, wait_seconds: int = 30) -> None:
        """Pause for user intervention — input() if interactive, timed wait otherwise."""
        if self.interactive:
            input(f"\n{message}\n")
        else:
            self._print_status(f"Non-interactive mode: waiting {wait_seconds}s — {message.strip()}")
            self.page.wait_for_timeout(wait_seconds * 1000)

    def _auto_login(self) -> None:
        """Attempt auto-login with .env credentials; fall back to manual pause on failure."""
        login_url = self.page.url

        if not self._username or not self._password:
            self._print_status("No credentials in .env — falling back to manual login.")
            self._pause(
                "╔══════════════════════════════════════════════╗\n"
                "║  Log in to ProBook in the browser, then      ║\n"
                "║  press ENTER here to continue...              ║\n"
                "╚══════════════════════════════════════════════╝",
                wait_seconds=30,
            )
            self.page.wait_for_timeout(2000)
            return

        try:
            self._print_status("Attempting auto-login...")

            # Find and fill username/email field
            email_field = self.page.locator(
                'input[type="email"], input[name="email"], input[name="username"], '
                'input[placeholder*="mail"], input[placeholder*="user"], '
                'input[id*="email"], input[id*="user"]'
            ).first
            email_field.wait_for(state="visible", timeout=10_000)
            email_field.fill(self._username)

            # Find and fill password field
            password_field = self.page.locator('input[type="password"]').first
            password_field.wait_for(state="visible", timeout=5_000)
            password_field.fill(self._password)

            # Click submit/login button
            submit = self.page.locator(
                'button[type="submit"], button:has-text("Log in"), button:has-text("Login"), '
                'button:has-text("Sign in"), input[type="submit"]'
            ).first
            submit.click()

            # Wait 5s for page to transition, then check if URL changed from login page
            self.page.wait_for_timeout(5000)

            current_url = self.page.url
            if current_url != login_url:
                self._print_status(f"Auto-login successful (URL changed to {current_url}).")
            else:
                self._print_status("URL unchanged after login attempt — may still be on login page.")
                # Not raising — let it continue, customer selection will catch real failures

            self._wait_for_react_idle()

        except Exception as e:
            self._print_status(f"Auto-login failed ({e}), please log in manually.")
            self._pause(
                "╔══════════════════════════════════════════════╗\n"
                "║  Auto-login failed. Please log in manually   ║\n"
                "║  in the browser, then press ENTER here...     ║\n"
                "╚══════════════════════════════════════════════╝",
                wait_seconds=30,
            )
            self.page.wait_for_timeout(2000)

    def _select_customer(self) -> None:
        """Select the customer/org from the dashboard dropdown. Falls back to manual."""
        self._print_status(f"Selecting customer: {self.customer_name}")

        try:
            # Strategy 1: Try clicking text that matches the customer name directly
            customer_link = self.page.get_by_text(self.customer_name, exact=False)
            if customer_link.first.is_visible(timeout=3000):
                customer_link.first.click()
                self.page.wait_for_timeout(2000)
                self._wait_for_react_idle()
                self._print_status("Customer selected via direct text match.")
                return
        except Exception:
            pass

        try:
            # Strategy 2: Look for any dropdown/select and try to pick the customer
            dropdown = self.page.locator(
                'select, [role="combobox"], [role="listbox"], '
                '[class*="dropdown"], [class*="select"], [class*="picker"], '
                '[class*="tenant"], [class*="customer"], [class*="org"]'
            ).first
            if dropdown.is_visible(timeout=3000):
                dropdown.click()
                self.page.wait_for_timeout(1000)
                # Now look for the customer name in the opened dropdown
                option = self.page.get_by_text(self.customer_name, exact=False)
                option.first.click()
                self.page.wait_for_timeout(2000)
                self._wait_for_react_idle()
                self._print_status("Customer selected via dropdown.")
                return
        except Exception:
            pass

        try:
            # Strategy 3: Look for a search/filter input, type the customer name, click result
            search_input = self.page.locator(
                'input[type="search"], input[placeholder*="earch"], input[placeholder*="ilter"], '
                'input[placeholder*="ustomer"], input[placeholder*="enant"]'
            ).first
            if search_input.is_visible(timeout=3000):
                search_input.fill(self.customer_name.split()[0])  # Type first word e.g. "Dyess"
                self.page.wait_for_timeout(1500)
                result = self.page.get_by_text(self.customer_name, exact=False)
                result.first.click()
                self.page.wait_for_timeout(2000)
                self._wait_for_react_idle()
                self._print_status("Customer selected via search.")
                return
        except Exception:
            pass

        # All strategies failed — manual fallback
        self._print_status("Could not auto-select customer.")
        self._pause(
            "╔══════════════════════════════════════════════╗\n"
            "║  Please select the customer manually in the  ║\n"
            "║  browser, then press ENTER here to continue. ║\n"
            "╚══════════════════════════════════════════════╝",
            wait_seconds=30,
        )
        self.page.wait_for_timeout(2000)

    # ── Phase 2: Navigate to Audit ────────────────────────────────────────

    def navigate_to_audit(self) -> None:
        """Navigate: Audit tab → AI Validation sub-tab → Dataset Builder sub-tab.

        Top-level and sidebar tabs are MUI Joy role="tab" elements.
        Content sub-tabs (Dataset Builder, Run AI Validation, etc.) are data-slot="button" elements.
        """
        self._print_status("Navigating to Audit > AI Validation > Dataset Builder...")

        # Top-level tab: "Audit" (MUI Joy Tab with role="tab")
        self.page.get_by_role("tab", name="Audit").click()
        self._wait_for_react_idle()

        # Left sidebar tab: "AI Validation" (MUI Joy Tab with role="tab")
        self.page.get_by_role("tab", name="AI Validation").click()
        self._wait_for_react_idle()

        # Content sub-tab: "Dataset Builder" (data-slot="button", not a role="tab")
        self.page.get_by_text("Dataset Builder", exact=True).first.click()
        self._wait_for_react_idle()

    # ── Phase 3: Build Dataset ────────────────────────────────────────────

    def build_dataset(self) -> None:
        """Fill start/end date inputs, enter dataset name, click Create Dataset, wait."""
        self._print_status(f"Building dataset for {self.start_date} to {self.end_date}...")

        # Fill native <input type="date"> fields by ID, then dispatch change events
        # so React picks up the new values
        self._fill_native_date("#start-date", self.start_date)
        self._fill_native_date("#end-date", self.end_date)

        # Fill dataset name
        dataset_name = f"{self.customer_name} {self.start_date} to {self.end_date}"
        self._dataset_name = dataset_name
        name_field = self.page.locator("#dataset-name")
        name_field.click()
        name_field.fill(dataset_name)
        name_field.dispatch_event("input")
        name_field.dispatch_event("change")
        self._print_status(f"  Dataset name: {dataset_name}")

        self.page.wait_for_timeout(2000)

        # Check if Create Dataset button is enabled — if not, dates didn't register
        create_btn = self.page.get_by_role("button", name="Create Dataset")
        try:
            self.page.wait_for_function(
                """() => {
                    const btn = [...document.querySelectorAll('button')]
                        .find(b => b.textContent.trim() === 'Create Dataset');
                    return btn && !btn.disabled;
                }""",
                timeout=5000,
            )
            self._print_status("  Create Dataset button is enabled.")
            create_btn.click()
        except Exception:
            # Button still disabled — try clicking dates to trigger React onChange
            self._print_status("  Create Dataset still disabled — retrying date entry...")
            # Click into each date field and press Enter to trigger React
            for sel in ["#start-date", "#end-date"]:
                field = self.page.locator(sel)
                field.click()
                self.page.wait_for_timeout(200)
                field.press("Enter")
                self.page.wait_for_timeout(200)
            # Also re-trigger the dataset name
            name_field = self.page.locator("#dataset-name")
            name_field.click()
            name_field.press("End")
            name_field.press("Backspace")
            name_field.type(dataset_name[-1])
            self.page.wait_for_timeout(1000)

            # Check again
            try:
                self.page.wait_for_function(
                    """() => {
                        const btn = [...document.querySelectorAll('button')]
                            .find(b => b.textContent.trim() === 'Create Dataset');
                        return btn && !btn.disabled;
                    }""",
                    timeout=5000,
                )
                self._print_status("  Create Dataset now enabled after retry.")
                create_btn.click()
            except Exception:
                self._print_status("  WARNING: Create Dataset still disabled — force-clicking...")
                self.page.evaluate("""
                    () => {
                        const btn = [...document.querySelectorAll('button')]
                            .find(b => b.textContent.trim() === 'Create Dataset');
                        if (btn) { btn.disabled = false; btn.click(); }
                    }
                """)

        # Wait up to 5 minutes for dataset build
        self._print_status("Waiting for dataset to build (up to 5 min)...")
        self.page.wait_for_function(
            "() => !document.querySelector('.spinner, .loading, [class*=skeleton], [class*=Spinner], [class*=Loading]')",
            timeout=300_000,
        )
        self._wait_for_react_idle()
        self._print_status("Dataset build complete.")

    def _fill_native_date(self, selector: str, date_str: str) -> None:
        """Fill a native <input type='date'> with verification and retry strategies."""
        field = self.page.locator(selector)

        # Convert MM/DD/YYYY to YYYY-MM-DD for native date input
        iso_date = date_str
        if "/" in date_str:
            parts = date_str.split("/")
            if len(parts) == 3:
                iso_date = f"{parts[2]}-{parts[0].zfill(2)}-{parts[1].zfill(2)}"

        # Use nativeInputValueSetter to trigger React state updates on date input
        self.page.evaluate(f"""
            () => {{
                const el = document.querySelector('{selector}');
                if (!el) return;
                const setter = Object.getOwnPropertyDescriptor(
                    window.HTMLInputElement.prototype, 'value'
                ).set;
                setter.call(el, '{iso_date}');
                el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                el.dispatchEvent(new Event('change', {{ bubbles: true }}));
            }}
        """)
        self.page.wait_for_timeout(500)

        # Verify
        actual = field.input_value()
        if actual == iso_date:
            self._print_status(f"  Set {selector} = {iso_date} ✓")
            return

        # Fallback: Playwright fill (works for DOM but may not trigger React)
        self._print_status(f"  JS setter got {actual}, trying Playwright fill...")
        field.click()
        field.fill(iso_date)
        field.dispatch_event("input")
        field.dispatch_event("change")
        self.page.wait_for_timeout(500)

        actual = field.input_value()
        if actual == iso_date:
            self._print_status(f"  Set {selector} = {iso_date} (fill) ✓")
        else:
            self._print_status(f"  WARNING: {selector} expected {iso_date} but got {actual}")

    # ── Phase 4: Run Validation ───────────────────────────────────────────

    def run_validation(self) -> None:
        """Select dataset + rule config, go to Run AI Validation tab, click Start.

        Actual UI layout (verified via DOM inspection):
        - Dataset cards: data-slot="button" elements with "Past Dataset" text.
          Selected = bg-primary class.
        - Rule config cards: div.cursor-pointer elements (NOT buttons).
          Selected = parent gets border-primary bg-primary/5.
        - Sub-tabs: data-slot="button" (Dataset Builder | Run AI Validation | ...)
        - Run button: "Start AI Validation" (not "Run")
        """
        self._print_status("Setting up validation run...")

        # Step 1: Select the dataset card matching our date range
        # Dataset cards are data-slot="button" elements containing "Past Dataset"
        try:
            dataset_cards = self.page.locator('[data-slot="button"]').filter(has_text="Past Dataset")
            count = dataset_cards.count()
            if count > 0:
                matched = None
                for i in range(count):
                    card = dataset_cards.nth(i)
                    card_text = card.text_content()
                    if self.start_date in card_text and self.end_date in card_text:
                        matched = card
                        self._print_status(f"  Matched dataset card: {card_text.strip()}")
                        break
                    if self._dataset_name and self._dataset_name in card_text:
                        matched = card
                        self._print_status(f"  Matched dataset card by name: {card_text.strip()}")
                        break

                if matched is None:
                    self._print_status("  WARNING: No exact match, using first card")
                    matched = dataset_cards.first

                matched.click()
                self.page.wait_for_timeout(1000)
                # Verify selection — should have bg-primary class
                classes = matched.evaluate("e => e.className")
                if "bg-primary" in classes:
                    self._print_status(f"  Dataset selected (of {count}) — confirmed highlighted.")
                else:
                    self._print_status(f"  Dataset clicked but not highlighted — clicking again...")
                    matched.click()
                    self.page.wait_for_timeout(500)
            else:
                self._print_status("  WARNING: No dataset cards found.")
        except Exception as e:
            self._print_status(f"  WARNING: Could not select dataset: {e}")

        # Step 2: Scroll down and select Production rule config
        # Rule configs are div.cursor-pointer elements (NOT buttons)
        # Try multiple search terms: "Production", "Version 3", "Version 2", "Version 1"
        self.page.evaluate("window.scrollBy(0, 400)")
        self.page.wait_for_timeout(1000)

        rule_selected = False
        search_terms = ["Production", "Version 3", "Version 2", "Version 1"]
        try:
            # First, log all visible rule config cards for debugging
            all_configs = self.page.locator('div.cursor-pointer')
            config_count = all_configs.count()
            self._print_status(f"  Found {config_count} rule config cards")
            for i in range(min(config_count, 8)):
                try:
                    text = all_configs.nth(i).text_content().strip()[:80]
                    self._print_status(f"    Config {i}: {text}")
                except Exception:
                    pass

            # Try each search term
            for term in search_terms:
                config_card = self.page.locator('div.cursor-pointer').filter(has_text=term)
                if config_card.count() > 0:
                    config_card.first.scroll_into_view_if_needed()
                    self.page.wait_for_timeout(300)
                    config_card.first.click()
                    self.page.wait_for_timeout(1000)
                    # Verify — parent should get border-primary
                    parent_class = config_card.first.evaluate("e => e.parentElement?.className || ''")
                    if "border-primary" in parent_class:
                        self._print_status(f"  Rule config '{term}' selected — confirmed highlighted.")
                        rule_selected = True
                        break
                    else:
                        # Try clicking again
                        config_card.first.click()
                        self.page.wait_for_timeout(500)
                        parent_class = config_card.first.evaluate("e => e.parentElement?.className || ''")
                        if "border-primary" in parent_class:
                            self._print_status(f"  Rule config '{term}' selected (2nd click) — confirmed.")
                            rule_selected = True
                            break

            # If none of the named searches worked, click the first config card
            if not rule_selected and config_count > 0:
                all_configs.first.scroll_into_view_if_needed()
                self.page.wait_for_timeout(300)
                all_configs.first.click()
                self.page.wait_for_timeout(1000)
                self._print_status("  Selected first available rule config.")
                rule_selected = True

        except Exception as e:
            self._print_status(f"  WARNING: Could not select rule config: {e}")

        if not rule_selected:
            self._pause(
                "Please select the Production rule config manually, then press ENTER.",
                wait_seconds=15,
            )

        # Step 3: Go to "Run AI Validation" sub-tab
        self.page.evaluate("window.scrollTo(0, 0)")
        self.page.wait_for_timeout(300)
        self.page.get_by_text("Run AI Validation", exact=True).first.click()
        self._wait_for_react_idle()
        self.page.wait_for_timeout(2000)

        # Step 4: Click "Start AI Validation"
        self._print_status("Starting AI Validation...")
        self._safe_click("Start AI Validation", role="button")

        # Give the validation time to actually start before checking for completion
        self._print_status("Waiting for validation to start...")
        self.page.wait_for_timeout(5000)

        # Check if a progress bar / running indicator appears
        validation_started = False
        for _ in range(6):  # Wait up to 30s for validation to kick off
            body_text = self.page.evaluate("() => document.body.innerText")
            if any(indicator in body_text.lower() for indicator in [
                "progress", "running", "processing", "validating", "queued",
            ]):
                validation_started = True
                self._print_status("  Validation is running...")
                break
            pct_match = re.search(r'(\d{1,3})\s*%', body_text)
            if pct_match and int(pct_match.group(1)) < 100:
                validation_started = True
                self._print_status(f"  Validation progress: {pct_match.group(1)}%")
                break
            self.page.wait_for_timeout(5000)

        if not validation_started:
            self._print_status("  WARNING: Could not confirm validation started — waiting anyway...")

        # Wait up to 25 minutes for validation to complete with progress logging
        self._print_status("Waiting for validation to complete (up to 25 min)...")
        max_wait = 1500  # 25 minutes
        poll_interval = 10  # seconds
        start = time.time()
        last_pct = -1
        last_heartbeat = start
        # Track if we've seen progress — only trust "results available" after progress was seen
        seen_progress = validation_started

        while time.time() - start < max_wait:
            elapsed = time.time() - start

            # Check for progress percentage on page
            body_text = self.page.evaluate("() => document.body.innerText")
            pct_match = re.search(r'(\d{1,3})\s*%', body_text)
            if pct_match:
                pct = int(pct_match.group(1))
                if pct != last_pct:
                    self._print_status(f"  Validation progress: {pct}%")
                    last_pct = pct
                    seen_progress = True
                if pct >= 100:
                    # Wait a bit more for results to render
                    self.page.wait_for_timeout(3000)
                    break

            # Check if progress reached 100%
            if last_pct >= 100:
                self._print_status("  Progress reached 100% — checking for results...")
                self.page.wait_for_timeout(3000)
                break

            # Check if progress was high (>90%) and then dropped/disappeared
            # — this means validation completed and page reset
            if last_pct > 90 and pct_match and int(pct_match.group(1)) < 10:
                self._print_status(f"  Progress dropped from {last_pct}% to {pct_match.group(1)}% — validation likely complete.")
                self.page.wait_for_timeout(5000)
                # Check for results
                if self.page.get_by_text("evaluation results", exact=False).is_visible():
                    self._print_status("  Evaluation results available.")
                    break

            # Check for "evaluation results" text after progress was seen and some time passed
            if seen_progress and elapsed > 60:
                if self.page.get_by_text("evaluation results available", exact=False).is_visible():
                    # Verify it's fresh — progress should no longer be increasing
                    self.page.wait_for_timeout(5000)
                    body_check = self.page.evaluate("() => document.body.innerText")
                    pct_check = re.search(r'(\d{1,3})\s*%', body_check)
                    # If no progress bar or it's at 0/100, results are real
                    if not pct_check or int(pct_check.group(1)) in (0, 100):
                        self._print_status("  Evaluation results available.")
                        break

            # If no progress percentage found and enough time has passed,
            # check for completion via results text (for orgs without progress bars)
            if last_pct == -1 and not seen_progress and elapsed > 120:
                if self.page.get_by_text("evaluation results available", exact=False).is_visible():
                    self._print_status("  Evaluation results available (no progress bar detected).")
                    break

            # Heartbeat every 60s
            if elapsed - (last_heartbeat - start) >= 60:
                self._print_status(f"  Still waiting... ({int(elapsed / 60)} min elapsed)")
                last_heartbeat = start + elapsed

            self.page.wait_for_timeout(poll_interval * 1000)
        else:
            self._print_status("WARNING: Validation timed out after 25 min — proceeding anyway")

        self._wait_for_react_idle()
        self._print_status("Validation complete.")

    # ── Phase 5: Navigate to Diffs, Scroll, Scrape ───────────────────────

    def navigate_to_diffs(self) -> None:
        """Go to Jobs / Diffs Dashboard tab.

        The column defaults (Validation Prediction / Dispatcher Verified Data)
        are already correct — no need to change them.
        """
        self._print_status("Navigating to Jobs / Diffs Dashboard...")
        self.page.get_by_text("Jobs / Diffs Dashboard", exact=True).first.click()
        self._wait_for_react_idle()
        self.page.wait_for_timeout(3000)

        # Verify we have results
        try:
            results_text = self.page.get_by_text("evaluation results", exact=False).first.text_content()
            self._print_status(f"  {results_text.strip()}")
        except Exception:
            self._print_status("  WARNING: Could not find evaluation results text.")

    def scroll_and_load_all_jobs(self) -> None:
        """Scroll the page to load all job cards.

        Job cards are in a div.space-y-3 container. Each card is a
        div.border.rounded-md.p-4 with bg-red-50 (mismatch) or bg-green-50 (match).
        """
        self._print_status("Loading all jobs via scroll...")

        # Count job cards using the actual DOM structure
        card_selector = 'div.border.rounded-md.p-4'
        prev_count = 0
        no_change_streak = 0
        max_scrolls = 100

        for i in range(max_scrolls):
            # Scroll the page down
            self.page.evaluate("window.scrollBy(0, 800)")
            self.page.wait_for_timeout(800)

            # Count job cards (filter to only those with Job ID text)
            current_count = self.page.locator(card_selector).filter(
                has_text="Job ID:"
            ).count()

            if current_count == prev_count:
                no_change_streak += 1
                if no_change_streak >= 3:
                    break
            else:
                no_change_streak = 0

            prev_count = current_count

            if i % 10 == 0:
                self._print_status(f"  Scroll {i}: {current_count} job cards loaded")

        self._print_status(f"All jobs loaded. Total visible: {prev_count}")

    def scrape_all_jobs(self) -> list[JobRecord]:
        """Extract all job data from the DOM in a single JS evaluate() call.

        Actual DOM structure (verified):
        - Each job card: div.border.rounded-md.p-4 with bg-red-50 or bg-green-50
        - Header: span with "Job ID: NNNNNN", span with Match/Mismatch badge
        - Two grid columns (grid-cols-2):
          - Left = Validation Prediction (AI)
          - Right = Dispatcher Verified
        - Each column has dt/dd-like pairs for: best_bu_name, best_job_type,
          best_priority, best_tags, best_is_first_call, best_arrival_window, etc.
        - Tags are shown as individual span badges
        """
        self._print_status("Scraping job data from DOM...")

        raw_data = self.page.evaluate("""
        () => {
            const jobs = [];
            const cards = document.querySelectorAll('div.border.rounded-md.p-4');

            cards.forEach(card => {
                try {
                    const text = card.textContent || '';
                    if (!text.includes('Job ID:')) return;

                    // Extract Job ID from header span
                    let jobId = '';
                    const headerSpans = card.querySelectorAll(':scope > div:first-child span');
                    for (const span of headerSpans) {
                        const t = span.textContent.trim();
                        if (t.startsWith('Job ID:')) {
                            jobId = t.replace('Job ID:', '').trim();
                            break;
                        }
                    }
                    if (!jobId) return;

                    // Find the two-column grid (grid-cols-1 lg:grid-cols-2)
                    const grid = card.querySelector('[class*="grid-cols"]');
                    if (!grid) return;
                    const columns = grid.children;
                    if (columns.length < 2) return;

                    function parseSide(colEl) {
                        const result = {
                            businessUnit: '',
                            jobType: '',
                            priority: '',
                            tags: [],
                            isFirstCall: null,
                            arrivalWindow: ''
                        };

                        // Each field is a div containing:
                        //   <div class="font-medium text-xs text-muted-foreground">Label</div>
                        //   <div>Value</div> or <div class="flex flex-wrap gap-1"><span>tag</span>...</div>
                        const fieldGroups = colEl.querySelectorAll(':scope > div > div');
                        // fieldGroups alternates: label, value, label, value, ...
                        // Actually each field is wrapped in its own div:
                        //   <div>  <-- field group
                        //     <div class="font-medium text-xs ...">Label</div>
                        //     <div>Value</div>
                        //   </div>
                        const fields = colEl.querySelectorAll(':scope > div.space-y-3 > div');

                        fields.forEach(fieldDiv => {
                            const labelEl = fieldDiv.querySelector('.font-medium.text-xs');
                            if (!labelEl) return;
                            const label = labelEl.textContent.trim();
                            const valueEl = fieldDiv.children[1]; // second child = value
                            if (!valueEl) return;

                            if (label === 'Business Unit') {
                                result.businessUnit = valueEl.textContent.trim();
                            } else if (label === 'Job Type') {
                                result.jobType = valueEl.textContent.trim();
                            } else if (label === 'Priority') {
                                result.priority = valueEl.textContent.trim();
                            } else if (label === 'Tags') {
                                // Tags are span badges inside a flex container
                                const tagSpans = valueEl.querySelectorAll('span');
                                tagSpans.forEach(s => {
                                    const t = s.textContent.trim();
                                    if (t) result.tags.push(t);
                                });
                            } else if (label === 'Is First Call') {
                                const v = valueEl.textContent.trim().toLowerCase();
                                result.isFirstCall = v === 'true';
                            } else if (label === 'Arrival Window') {
                                result.arrivalWindow = valueEl.textContent.trim();
                            }
                        });

                        return result;
                    }

                    const leftData = parseSide(columns[0]);
                    const rightData = parseSide(columns[1]);

                    jobs.push({
                        jobId: jobId,
                        businessUnit: leftData.businessUnit || rightData.businessUnit,
                        aiPrediction: {
                            jobType: leftData.jobType,
                            priority: leftData.priority,
                            tags: leftData.tags,
                            isFirstCall: leftData.isFirstCall,
                            arrivalWindow: leftData.arrivalWindow
                        },
                        dispatcherVerified: {
                            jobType: rightData.jobType,
                            priority: rightData.priority,
                            tags: rightData.tags,
                            isFirstCall: rightData.isFirstCall,
                            arrivalWindow: rightData.arrivalWindow
                        }
                    });
                } catch (e) {
                    // Skip malformed cards
                }
            });

            return jobs;
        }
        """)

        self._print_status(f"Extracted {len(raw_data)} raw job records from DOM.")

        self.jobs = []
        for item in raw_data:
            ai = item.get("aiPrediction", {})
            disp = item.get("dispatcherVerified", {})

            record = JobRecord(
                job_id=item.get("jobId", ""),
                business_unit=item.get("businessUnit", ""),
                ai_prediction=JobSide(
                    job_type=ai.get("jobType", ""),
                    priority=ai.get("priority", ""),
                    tags=ai.get("tags", []),
                    is_first_call=ai.get("isFirstCall"),
                    arrival_window=ai.get("arrivalWindow", ""),
                ),
                dispatcher_verified=JobSide(
                    job_type=disp.get("jobType", ""),
                    priority=disp.get("priority", ""),
                    tags=disp.get("tags", []),
                    is_first_call=disp.get("isFirstCall"),
                    arrival_window=disp.get("arrivalWindow", ""),
                ),
            )
            record.compute_derived_fields()
            self.jobs.append(record)

        relevant = [j for j in self.jobs if j.ai_has_10plus or j.disp_has_10plus]
        self._print_status(f"Total jobs: {len(self.jobs)}, with 10+ tag: {len(relevant)}")

        return self.jobs

    def save_json_backup(self, output_dir: str = ".") -> str:
        """Save raw scraped data as JSON backup."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_name = self.customer_name.replace(" ", "_")
        filename = f"{safe_name}_raw_data_{timestamp}.json"
        filepath = Path(output_dir) / filename

        data = []
        for job in self.jobs:
            data.append(asdict(job))

        filepath.write_text(json.dumps(data, indent=2, default=str))
        self._print_status(f"JSON backup saved: {filepath}")
        return str(filepath)

    # ── Phase 7: ServiceTitan QA ──────────────────────────────────────────

    def qa_in_servicetitan(self, job_ids: list[str]) -> list[QARecord]:
        """Open each job in ServiceTitan, navigate to equipment, screenshot, extract ages."""
        self._print_status(f"Starting ServiceTitan QA for {len(job_ids)} jobs...")

        # Open ServiceTitan in a new tab
        st_page = self._context.new_page()
        st_page.goto(self.SERVICETITAN_URL, wait_until="networkidle")

        self._pause(
            "╔══════════════════════════════════════════════╗\n"
            "║  Log in to ServiceTitan in the browser, then ║\n"
            "║  press ENTER here to continue...              ║\n"
            "╚══════════════════════════════════════════════╝",
            wait_seconds=30,
        )
        self.page.wait_for_timeout(2000)

        for job_id in job_ids:
            try:
                self._print_status(f"  QA: Checking job {job_id}...")
                record = QARecord(job_id=job_id)

                # Navigate to job page
                st_page.goto(
                    f"{self.SERVICETITAN_URL}/Job/Index/{job_id}",
                    wait_until="networkidle",
                    timeout=30_000,
                )

                # Click Equipment tab
                equip_tab = st_page.get_by_role("tab", name="Equipment")
                if equip_tab.count():
                    equip_tab.click()
                    st_page.wait_for_timeout(2000)

                    # Check if equipment is present
                    equipment_rows = st_page.locator(
                        '[class*="equipment"], [data-testid*="equipment"], '
                        'table tbody tr'
                    )
                    record.equipment_found = equipment_rows.count() > 0

                    # Extract ages from equipment data
                    age_elements = st_page.locator(
                        '[class*="age"], [class*="install-date"], [data-testid*="age"]'
                    )
                    for i in range(age_elements.count()):
                        age_text = age_elements.nth(i).text_content()
                        if age_text:
                            record.ages_found.append(age_text.strip())
                else:
                    record.notes = "Equipment tab not found"

                # Screenshot
                screenshot_path = self.qa_dir / f"qa_{job_id}.png"
                st_page.screenshot(path=str(screenshot_path), full_page=True)
                record.screenshot_path = str(screenshot_path)

                self.qa_records.append(record)

            except Exception as e:
                self._print_status(f"  QA ERROR for job {job_id}: {e}")
                self.qa_records.append(QARecord(
                    job_id=job_id,
                    notes=f"Error: {e}",
                ))

        st_page.close()
        self._print_status(f"QA complete. {len(self.qa_records)} records captured.")
        return self.qa_records

    # ── Cleanup ───────────────────────────────────────────────────────────

    def close(self) -> None:
        """Close browser and Playwright."""
        self._print_status("Closing browser...")
        try:
            if self._browser:
                self._browser.close()
        except Exception:
            pass
        try:
            if self._pw:
                self._pw.stop()
        except Exception:
            pass

    # ── Helper Methods ────────────────────────────────────────────────────

    def _wait_for_react_idle(self, timeout: int = 10_000) -> None:
        """Wait for network idle + no spinners/skeletons visible."""
        try:
            self.page.wait_for_load_state("networkidle", timeout=timeout)
        except Exception:
            pass  # networkidle can time out on long-poll connections

        # Extra check: wait for spinners/skeletons to disappear
        try:
            self.page.wait_for_function(
                "() => !document.querySelector('.spinner, .loading, [class*=skeleton], [class*=Spinner], [class*=Loading]')",
                timeout=timeout,
            )
        except Exception:
            pass

    def _safe_click(self, text: str, role: str = "button", retries: int = 2, force: bool = False) -> None:
        """Click an element with retries and fallback from role-based to text-based.

        Args:
            force: If True, use Playwright's force click (bypasses disabled/actionability checks).
        """
        last_error = None

        for attempt in range(retries + 1):
            try:
                # Primary: role-based locator
                locator = self.page.get_by_role(role, name=text)
                locator.wait_for(state="visible", timeout=10_000)
                locator.click(force=force)
                return
            except Exception as e:
                last_error = e
                if attempt < retries:
                    self.page.wait_for_timeout(500)

        # Fallback: text-based locator
        try:
            locator = self.page.get_by_text(text, exact=False)
            locator.first.click(force=force)
            return
        except Exception:
            pass

        # Last resort: JS click (bypasses all Playwright checks)
        if force:
            try:
                self.page.evaluate(f"""
                    () => {{
                        const el = [...document.querySelectorAll('button, [role="button"], a')]
                            .find(e => e.textContent.trim().includes('{text}'));
                        if (el) {{ el.disabled = false; el.click(); return true; }}
                        return false;
                    }}
                """)
                self._print_status(f"  Clicked '{text}' via JS force-click.")
                return
            except Exception:
                pass

        raise RuntimeError(f"Could not click '{text}' (role={role}) after {retries + 1} attempts: {last_error}")


    @staticmethod
    def _print_status(msg: str) -> None:
        """Print a timestamped status message."""
        ts = datetime.now().strftime("%H:%M:%S")
        print(f"[{ts}] {msg}")
