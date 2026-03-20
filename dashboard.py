#!/usr/bin/env python3
"""
10+ Automation Dashboard — Local web UI for running the pipeline.

Usage:
    python dashboard.py          # starts on http://localhost:8000
    python dashboard.py --port 3000
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from queue import Queue, Empty

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse, FileResponse
from fastapi.templating import Jinja2Templates

import uvicorn

load_dotenv()

# ─── Org List ────────────────────────────────────────────────────────────────

ORGS = [
    "A-Star",
    "A1 Garage",
    "AA Service Company",
    "AB May",
    "Absolute/Carbon Valley/R Buck/Welzig",
    "AC Doctors",
    "Academy Air & Morrison Heating",
    "Ace Albuquerque",
    "Ace Phoenix/Prescott/Pride Tucson",
    "Air Assurance",
    "Air Services",
    "AirCo",
    "Airco Tulsa",
    "AireServ",
    "Allied",
    "AllKlear",
    "AllPro",
    "AllTech",
    "Anthony's",
    "Apex Plumbing",
    "Apex Pros",
    "Apollo Home",
    "Arctic Air",
    "Art",
    "Art CSR",
    "ASP Mechanical",
    "Assurance Power Systems",
    "Astacio",
    "Auchanachie",
    "AZ Air",
    "Best Home Services",
    "Best Virginia",
    "Black Haak",
    "Blake Brothers",
    "Blaze",
    "Boulden Brothers",
    "C&C Myers",
    "Canfield Plumbing",
    "Cardinal Plumbing",
    "Cardinal Service",
    "Champion Comfort",
    "Christian",
    "Curran Plumbing",
    "Davison Home Services/Cregger Plumbing",
    "Del-Air",
    "Dilling",
    "Dipple",
    "Direct AC",
    "Done",
    "Drexler",
    "Dyess Air",
    "E Dennis",
    "Eco Plumbers",
    "Elevate",
    "F. H. Furr",
    "F.H. Furr Ashland",
    "F.H. Furr Georgetown",
    "Fantes",
    "Frank Gay",
    "GAC Services",
    "Goettl",
    "Golden Rule",
    "Guaranteed Service",
    "Haley Mechanical",
    "Half Moon",
    "Hero",
    "High 5 Plumbing",
    "HL Bowman",
    "Hockers",
    "Holt",
    "HomeFirst",
    "Hoover",
    "Integrity",
    "J & W",
    "J&J",
    "Jackson Comfort",
    "Jazz",
    "John Henry's",
    "John Moore Services",
    "Jolly Plumbing",
    "Jones Services",
    "JSP Home Services",
    "KB Complete",
    "Kellam",
    "Ken Hall Plumbers",
    "Landry Mechanical",
    "Lee's Air",
    "Legacy Air",
    "Len the Plumber",
    "Lion Home Services",
    "Logan Services",
    "Mainstream",
    "Mathews CCAC",
    "Mauzy",
    "Metro Plumbing",
    "Mr. Electric",
    "Mr. Electric Cleveland",
    "Mr. Electric Land of Lakes",
    "MSP Plumbing",
    "My Plumber",
    "Network Tradies",
    "Oceanside Service",
    "Ontime Service Pros",
    "Ostrom",
    "Peak Performance",
    "Perfect Home",
    "Peterman Brothers",
    "Pioneer Comfort Systems",
    "Precision Today",
    "Prime Plumbing",
    "Pronto Plumbing",
    "Quality Heating and Cooling",
    "REEIS",
    "Rescue Air",
    "Revolution Services",
    "Ricky Heath",
    "Rowell's Services",
    "Rowland Air",
    "SafeAire",
    "Salt Air",
    "Schneller Knochelmann",
    "ServiceOne",
    "ServiceToday",
    "ServiceToday CSR Login",
    "Sila Boston",
    "Skradski",
    "Snyder Jacksonville",
    "Snyder South Florida",
    "Stan's",
    "Static Electrics",
    "Streamline Services",
    "Stuart",
    "Sullivan",
    "Summers",
    "Swan",
    "T. Webber",
    "Teds",
    "TF Obrien",
    "The Meridian",
    "Thompson & Thompson",
    "TR Miller",
    "Wagner",
    "Walter Danley",
    "We Care",
    "West Allis",
    "Wilson",
    "Woodfin",
    "WyattWorks",
    "WyattWorks CSR Agent",
    "Zephyr",
]

# ─── Pipeline Runner ─────────────────────────────────────────────────────────

class PipelineRun:
    """Wraps a single pipeline execution with event streaming."""

    def __init__(self, org: str, start_date: str, end_date: str, comparison_side: str = "dispatcher", max_trace_jobs: int = 0):
        self.id = uuid.uuid4().hex[:8]
        self.org = org
        self.start_date = start_date
        self.end_date = end_date
        self.comparison_side = comparison_side
        self.max_trace_jobs = max_trace_jobs
        self.status = "pending"
        self.pipeline_type = "10plus"
        self.events: Queue = Queue()
        self.result: dict | None = None

    def _emit(self, event_type: str, **kwargs):
        self.events.put({"type": event_type, **kwargs})

    def _log(self, msg: str):
        ts = datetime.now().strftime("%H:%M:%S")
        self._emit("log", message=f"[{ts}] {msg}")

    def run(self):
        self.status = "running"
        self._emit("status", status="running")

        # Import here to avoid circular issues at module load
        from scraper import ProBookScraper
        from report_generator import generate_report
        from google_upload import upload_to_google_sheets

        output_dir = Path(".")
        scraper = None

        try:
            scraper = ProBookScraper(
                customer_name=self.org,
                start_date=self.start_date,
                end_date=self.end_date,
                interactive=False,
            )

            # Patch _print_status to capture output to our event stream
            original_print = scraper._print_status

            def patched_print(msg):
                original_print(msg)
                self._log(msg)

            scraper._print_status = patched_print

            # Phase 1: Launch & Login
            scraper.launch()
            scraper.login_and_select_customer()

            # Phase 2: Navigate
            scraper.navigate_to_audit()

            # Phase 3: Build Dataset
            scraper.build_dataset()

            # Phase 4: Run Validation
            scraper.run_validation()

            # Phase 5: Scrape
            scraper.navigate_to_diffs()
            if self.comparison_side == "csr":
                scraper.switch_comparison_column("csr")
            scraper.scroll_and_load_all_jobs()
            jobs = scraper.scrape_all_jobs()

            # Phase 6: Trace enrichment
            self._log(f"Enriching jobs with LangSmith trace reasons (max={self.max_trace_jobs or 'all'})...")
            scraper.enrich_jobs_with_trace_reasons(max_jobs=self.max_trace_jobs)

            # JSON backup
            json_path = scraper.save_json_backup(output_dir=str(output_dir))
            self._log(f"JSON backup: {json_path}")

            # Generate Excel
            report_path = generate_report(
                jobs=jobs,
                customer_name=self.org,
                output_dir=str(output_dir),
            )
            self._log(f"Excel report: {report_path}")

            # Google Sheets upload
            self._log("Uploading to Google Sheets...")
            sheet_url = upload_to_google_sheets(jobs, self.org)
            self._log(f"Google Sheet: {sheet_url}")

            # Compute summary
            relevant = [j for j in jobs if j.ai_has_10plus or j.disp_has_10plus]
            missed = sum(1 for j in relevant if j.category == "Dispatcher placed 10+ tag that Probook Missed")
            added = sum(1 for j in relevant if j.category == "Probook placed 10+ tag that CSR/Dispatch Missed")
            job_type_mm = sum(1 for j in relevant if j.category == "10+ Job Type Mismatch")
            tag_mm = sum(1 for j in relevant if j.category == "10+ Tag Mismatch")
            priority_mm = sum(1 for j in relevant if j.category == "10+ Priority Mismatch")
            matched = sum(1 for j in relevant if j.category == "Match")

            self.result = {
                "sheet_url": sheet_url,
                "excel_path": report_path,
                "json_path": json_path,
                "total_jobs": len(jobs),
                "relevant_jobs": len(relevant),
                "missed": missed,
                "added": added,
                "job_type_mismatch": job_type_mm,
                "tag_mismatch": tag_mm,
                "priority_mismatch": priority_mm,
                "matched": matched,
            }

            self.status = "complete"
            self._emit("status", status="complete", result=self.result)
            self._log("Pipeline complete!")

        except Exception as e:
            self._log(f"ERROR: {e}")
            self.status = "error"
            self._emit("status", status="error", error=str(e))

        finally:
            if scraper:
                try:
                    scraper.close()
                except Exception:
                    pass
            # Signal end of stream
            self._emit("done")


# ─── Scrape-Only Pipeline Runner ──────────────────────────────────────────────

class ScrapeOnlyRun:
    """Scrape-only mode: login → navigate to existing validation results → scrape → report.

    Skips dataset build and validation — assumes the user already ran validation
    manually and the results are available on the Jobs/Diffs page.
    """

    def __init__(self, org: str, comparison_side: str = "dispatcher", max_trace_jobs: int = 0):
        self.id = uuid.uuid4().hex[:8]
        self.org = org
        self.start_date = ""
        self.end_date = ""
        self.comparison_side = comparison_side
        self.max_trace_jobs = max_trace_jobs
        self.status = "pending"
        self.pipeline_type = "10plus"
        self.events: Queue = Queue()
        self.result: dict | None = None

    def _emit(self, event_type: str, **kwargs):
        self.events.put({"type": event_type, **kwargs})

    def _log(self, msg: str):
        ts = datetime.now().strftime("%H:%M:%S")
        self._emit("log", message=f"[{ts}] {msg}")

    def run(self):
        self.status = "running"
        self._emit("status", status="running")

        from scraper import ProBookScraper
        from report_generator import generate_report
        from google_upload import upload_to_google_sheets

        output_dir = Path(".")
        scraper = None

        try:
            scraper = ProBookScraper(
                customer_name=self.org,
                start_date="",
                end_date="",
                interactive=False,
            )

            original_print = scraper._print_status
            def patched_print(msg):
                original_print(msg)
                self._log(msg)
            scraper._print_status = patched_print

            # Phase 1: Launch & Login
            scraper.launch()
            scraper.login_and_select_customer()

            # Phase 2: Navigate to Audit > AI Validation
            self._log("Navigating to Audit > AI Validation...")
            scraper.page.get_by_role("tab", name="Audit").click()
            scraper._wait_for_react_idle()
            scraper.page.get_by_role("tab", name="AI Validation").click()
            scraper._wait_for_react_idle()
            scraper.page.wait_for_timeout(2000)

            # Phase 3: Select the correct dataset (required before Jobs/Diffs shows data)
            self._log("Selecting dataset...")
            try:
                dataset_cards = scraper.page.locator('[data-slot="button"]').filter(has_text="Past Dataset")
                count = dataset_cards.count()
                self._log(f"  Found {count} dataset cards")

                # Find the dataset matching "02/24 - 03/10" or the most recent with "Zephyr"
                selected = None
                for i in range(count):
                    card_text = dataset_cards.nth(i).text_content()
                    self._log(f"  Card {i}: {card_text.strip()[:100]}")
                    # Match the 02/24 to 03/10 dataset
                    if "2026-02-24" in card_text and "2026-03-10" in card_text:
                        selected = dataset_cards.nth(i)
                        self._log(f"  >>> Selecting card {i} (matches date range)")
                        break

                if selected is None and count > 0:
                    selected = dataset_cards.first
                    self._log("  No exact match — selecting first card")

                if selected:
                    selected.click()
                    scraper.page.wait_for_timeout(2000)
                    self._log("  Dataset selected.")
            except Exception as e:
                self._log(f"  WARNING: Could not select dataset: {e}")

            # Phase 3b: Select the Production rule config
            self._log("Selecting Production rule config...")
            try:
                scraper.page.evaluate("window.scrollBy(0, 400)")
                scraper.page.wait_for_timeout(500)
                version3 = scraper.page.locator('div.cursor-pointer').filter(has_text="Version 3").first
                version3.scroll_into_view_if_needed()
                scraper.page.wait_for_timeout(300)
                version3.click()
                scraper.page.wait_for_timeout(1500)
                self._log("  Rule config (Version 3) selected.")
            except Exception as e:
                self._log(f"  WARNING: Could not select rule config: {e} — proceeding anyway")

            scraper.page.wait_for_timeout(3000)

            # Phase 4: Go to Jobs / Diffs Dashboard
            self._log("Going to Jobs / Diffs Dashboard (scrape-only mode)...")
            try:
                diffs_tab = scraper.page.get_by_text("Jobs / Diffs Dashboard", exact=True).first
                diffs_tab.click()
                scraper.page.wait_for_timeout(5000)
                self._log("  Clicked Jobs / Diffs tab, waiting for content...")
            except Exception as e:
                self._log(f"  Jobs/Diffs tab click error: {e}")
                # Try alternate approach
                scraper.page.wait_for_timeout(2000)

            # Check page state
            try:
                url = scraper.page.url
                self._log(f"  Current URL: {url}")
                body_text = scraper.page.evaluate("() => document.body.innerText.substring(0, 500)")
                self._log(f"  Page text preview: {body_text[:200]}")
            except Exception as e:
                self._log(f"  Could not read page state: {e}")
                raise

            # Phase 4: Scroll and scrape
            if self.comparison_side == "csr":
                scraper.switch_comparison_column("csr")
            scraper.scroll_and_load_all_jobs()
            jobs = scraper.scrape_all_jobs()

            # Trace enrichment
            self._log(f"Enriching jobs with LangSmith trace reasons (max={self.max_trace_jobs or 'all'})...")
            scraper.enrich_jobs_with_trace_reasons(max_jobs=self.max_trace_jobs)

            # JSON backup
            json_path = scraper.save_json_backup(output_dir=str(output_dir))
            self._log(f"JSON backup: {json_path}")

            # Generate Excel
            report_path = generate_report(
                jobs=jobs,
                customer_name=self.org,
                output_dir=str(output_dir),
            )
            self._log(f"Excel report: {report_path}")

            # Google Sheets upload
            self._log("Uploading to Google Sheets...")
            sheet_url = upload_to_google_sheets(jobs, self.org)
            self._log(f"Google Sheet: {sheet_url}")

            # Compute summary
            relevant = [j for j in jobs if j.ai_has_10plus or j.disp_has_10plus]
            missed = sum(1 for j in relevant if j.category == "Dispatcher placed 10+ tag that Probook Missed")
            added = sum(1 for j in relevant if j.category == "Probook placed 10+ tag that CSR/Dispatch Missed")
            job_type_mm = sum(1 for j in relevant if j.category == "10+ Job Type Mismatch")
            tag_mm = sum(1 for j in relevant if j.category == "10+ Tag Mismatch")
            priority_mm = sum(1 for j in relevant if j.category == "10+ Priority Mismatch")
            matched = sum(1 for j in relevant if j.category == "Match")

            self.result = {
                "sheet_url": sheet_url,
                "excel_path": report_path,
                "json_path": json_path,
                "total_jobs": len(jobs),
                "relevant_jobs": len(relevant),
                "missed": missed,
                "added": added,
                "job_type_mismatch": job_type_mm,
                "tag_mismatch": tag_mm,
                "priority_mismatch": priority_mm,
                "matched": matched,
            }

            self.status = "complete"
            self._emit("status", status="complete", result=self.result)
            self._log("Pipeline complete!")

        except Exception as e:
            self._log(f"ERROR: {e}")
            self.status = "error"
            self._emit("status", status="error", error=str(e))

        finally:
            if scraper:
                try:
                    scraper.close()
                except Exception:
                    pass
            self._emit("done")


# ─── ROI Pipeline Runner ─────────────────────────────────────────────────────

class ROIPipelineRun:
    """Wraps an ROI pipeline execution: ST scraper → Excel template fill."""

    def __init__(
        self,
        org: str,
        st_username: str,
        st_password: str,
        pre_start: str,
        pre_end: str,
        post_start: str,
        post_end: str,
        go_live_date: str = "",
        trades: list[str] | None = None,
        business_units: dict[str, list[str]] | None = None,
    ):
        self.id = uuid.uuid4().hex[:8]
        self.org = org
        self.st_username = st_username
        self.st_password = st_password
        self.pre_start = pre_start
        self.pre_end = pre_end
        self.post_start = post_start
        self.post_end = post_end
        self.go_live_date = go_live_date
        self.trades = trades or ["HVAC", "Plumbing", "Electrical", "Drains"]
        self.business_units = business_units or {}
        self.status = "pending"
        self.pipeline_type = "roi"
        self.events: Queue = Queue()
        self.result: dict | None = None

        # MFA handling
        self.mfa_code: str = ""
        self.mfa_event: threading.Event = threading.Event()

    def _emit(self, event_type: str, **kwargs):
        self.events.put({"type": event_type, **kwargs})

    def _log(self, msg: str):
        ts = datetime.now().strftime("%H:%M:%S")
        self._emit("log", message=f"[{ts}] {msg}")

    def _get_mfa_code(self) -> str:
        """
        3-tier MFA retrieval:
        1. Auto-read from Slack #mfa channel
        2. Poll for fresh code after ST triggers MFA
        3. Manual fallback via dashboard modal
        """
        slack_token = os.getenv("SLACK_BOT_TOKEN")

        if slack_token:
            try:
                code = self._read_mfa_from_slack(slack_token)
                if code:
                    self._log(f"MFA code auto-read from Slack.")
                    return code
            except Exception as e:
                self._log(f"Slack auto-read failed: {e}")

            # Tier 2: Poll for fresh message
            self._log("Polling Slack for fresh MFA code...")
            for _ in range(12):  # 60s total (5s intervals)
                time.sleep(5)
                try:
                    code = self._read_mfa_from_slack(slack_token, max_age_seconds=30)
                    if code:
                        self._log(f"MFA code received from Slack.")
                        return code
                except Exception:
                    pass

        # Tier 3: Manual entry via dashboard
        self._log("Requesting MFA code from dashboard...")
        self._emit("mfa_needed")
        self.mfa_event.clear()
        self.mfa_event.wait(timeout=300)  # 5 min timeout

        if self.mfa_code:
            self._log("MFA code received from dashboard.")
            return self.mfa_code

        raise RuntimeError("MFA code not provided within timeout.")

    def _read_mfa_from_slack(self, token: str, max_age_seconds: int = 120) -> str | None:
        """Read 6-digit MFA code from Slack #mfa channel."""
        from slack_sdk import WebClient

        client = WebClient(token=token)
        # Find #mfa channel
        result = client.conversations_list(types="public_channel,private_channel", limit=200)
        mfa_channel = None
        for ch in result["channels"]:
            if ch["name"] == "mfa":
                mfa_channel = ch["id"]
                break

        if not mfa_channel:
            return None

        # Read recent messages
        now = time.time()
        history = client.conversations_history(
            channel=mfa_channel,
            oldest=str(now - max_age_seconds),
            limit=10,
        )

        for msg in history.get("messages", []):
            text = msg.get("text", "")
            match = re.search(r'\b(\d{6})\b', text)
            if match:
                return match.group(1)

        return None

    def _upload_to_google_drive(self, file_path: str) -> str:
        """Upload Excel file to Google Drive as a Google Sheet. Returns the URL."""
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload

        token_path = Path(__file__).parent / "google_token.json"
        creds_path = Path(__file__).parent / "google_credentials.json"
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive.file",
        ]

        creds = Credentials.from_authorized_user_file(str(token_path), scopes)
        if not creds.valid:
            if creds.expired and creds.refresh_token:
                creds.refresh(Request())
                token_path.write_text(creds.to_json())
            else:
                raise RuntimeError("Google token expired and cannot refresh. Re-run auth flow.")

        service = build("drive", "v3", credentials=creds)
        file_name = Path(file_path).stem  # e.g. "TR_Miller_ROI_Report_2026-03-10"
        file_metadata = {
            "name": file_name,
            "mimeType": "application/vnd.google-apps.spreadsheet",
        }
        media = MediaFileUpload(
            file_path,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        result = service.files().create(
            body=file_metadata, media_body=media, fields="id,webViewLink"
        ).execute()
        return result.get("webViewLink", "")

    def run(self):
        self.status = "running"
        self._emit("status", status="running")

        from roi_scraper import ServiceTitanScraper, pull_roi_data, TradeMetrics
        from roi_report import generate_roi_report

        scraper = None
        try:
            scraper = ServiceTitanScraper(
                st_username=self.st_username,
                st_password=self.st_password,
                log_fn=self._log,
            )

            # Launch & Login
            scraper.launch()
            scraper.login(mfa_code_fn=self._get_mfa_code)

            # Build trade → BU map
            trade_bus = {}
            for trade in self.trades:
                trade_bus[trade] = self.business_units.get(trade, [])

            # Compute natural delta dates from go-live if provided
            natural_y1_start = natural_y1_end = None
            natural_y2_start = natural_y2_end = None
            natural_y1_label = natural_y2_label = ""

            if self.go_live_date:
                try:
                    gl = datetime.strptime(self.go_live_date, "%Y-%m-%d")
                    # Natural Y1: same period as pre, but 1 year earlier
                    pre_s = datetime.strptime(self.pre_start, "%Y-%m-%d")
                    pre_e = datetime.strptime(self.pre_end, "%Y-%m-%d")
                    from dateutil.relativedelta import relativedelta
                    ny1_s = pre_s - relativedelta(years=1)
                    ny1_e = pre_e - relativedelta(years=1)
                    natural_y1_start = ny1_s.strftime("%m/%d/%Y")
                    natural_y1_end = ny1_e.strftime("%m/%d/%Y")
                    natural_y1_label = f"{ny1_s.strftime('%m/%d/%y')} - {ny1_e.strftime('%m/%d/%y')}"

                    # Natural Y2: same as pre period (already 1 year later than Y1)
                    natural_y2_start = pre_s.strftime("%m/%d/%Y")
                    natural_y2_end = pre_e.strftime("%m/%d/%Y")
                    natural_y2_label = f"{pre_s.strftime('%m/%d/%y')} - {pre_e.strftime('%m/%d/%y')}"
                except Exception as e:
                    self._log(f"Could not compute natural delta dates: {e}")

            # Convert dates to MM/DD/YYYY for ServiceTitan
            pre_s_fmt = _reformat_date(self.pre_start)
            pre_e_fmt = _reformat_date(self.pre_end)
            post_s_fmt = _reformat_date(self.post_start)
            post_e_fmt = _reformat_date(self.post_end)

            # Pull data
            data = pull_roi_data(
                scraper=scraper,
                trades=trade_bus,
                pre_start=pre_s_fmt,
                pre_end=pre_e_fmt,
                post_start=post_s_fmt,
                post_end=post_e_fmt,
                org_name=self.org,
                natural_y1_start=natural_y1_start,
                natural_y1_end=natural_y1_end,
                natural_y2_start=natural_y2_start,
                natural_y2_end=natural_y2_end,
            )

            # Generate Excel
            self._log("Generating ROI Excel report...")
            pre_label = f"{self.pre_start} - {self.pre_end}"
            post_label = f"{self.post_start} - {self.post_end}"

            report_path = generate_roi_report(
                data=data,
                org_name=self.org,
                pre_start=self.pre_start,
                pre_end=self.pre_end,
                post_start=self.post_start,
                post_end=self.post_end,
                natural_y1_label=natural_y1_label if natural_y1_start else "",
                natural_y2_label=natural_y2_label if natural_y2_start else "",
                output_dir=".",
            )
            self._log(f"ROI report saved: {report_path}")

            # Upload to Google Drive
            google_url = ""
            try:
                self._log("Uploading to Google Drive...")
                google_url = self._upload_to_google_drive(report_path)
                self._log(f"Google Sheet: {google_url}")
            except Exception as e:
                self._log(f"Google Drive upload failed (non-fatal): {e}")

            # Build per-trade summary for frontend
            from dataclasses import asdict
            trade_summary = {}
            for trade_name, trade_data in data.get("basic", {}).items():
                trade_summary[trade_name] = {
                    "pre": asdict(trade_data["pre"]),
                    "post": asdict(trade_data["post"]),
                }

            hl_pre = asdict(data.get("high_level_pre", TradeMetrics()))
            hl_post = asdict(data.get("high_level_post", TradeMetrics()))

            trades_done = len(data.get("basic", {}))
            self.result = {
                "excel_path": report_path,
                "google_url": google_url,
                "trades_processed": trades_done,
                "trades": list(data.get("basic", {}).keys()),
                "trade_summary": trade_summary,
                "high_level_pre": hl_pre,
                "high_level_post": hl_post,
            }

            self.status = "complete"
            self._emit("status", status="complete", result=self.result)
            self._log("ROI pipeline complete!")

        except Exception as e:
            self._log(f"ERROR: {e}")
            self.status = "error"
            self._emit("status", status="error", error=str(e))

        finally:
            if scraper:
                try:
                    scraper.close()
                except Exception:
                    pass
            self._emit("done")


def _reformat_date(date_str: str) -> str:
    """Convert YYYY-MM-DD to MM/DD/YYYY for ServiceTitan."""
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        return dt.strftime("%m/%d/%Y")
    except ValueError:
        return date_str


# ─── In-memory run store ─────────────────────────────────────────────────────

runs: dict[str, PipelineRun | ROIPipelineRun] = {}

# ─── FastAPI App ─────────────────────────────────────────────────────────────

app = FastAPI(title="10+ Automation Dashboard")
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("dashboard.html", {"request": request})


@app.get("/api/orgs")
async def get_orgs():
    return ORGS


@app.post("/api/run")
async def start_run(request: Request):
    data = await request.json()
    org = data.get("org", "").strip()
    start_date = data.get("start_date", "").strip()
    end_date = data.get("end_date", "").strip()
    comparison_side = data.get("comparison_side", "dispatcher").strip()
    max_trace_jobs = int(data.get("max_trace_jobs", 0))

    if not org or not start_date or not end_date:
        return JSONResponse({"error": "org, start_date, and end_date are required"}, status_code=400)

    if org not in ORGS:
        return JSONResponse({"error": f"Unknown org: {org}"}, status_code=400)

    run = PipelineRun(org, start_date, end_date, comparison_side=comparison_side, max_trace_jobs=max_trace_jobs)
    runs[run.id] = run

    thread = threading.Thread(target=run.run, daemon=True)
    thread.start()

    return {"run_id": run.id}


@app.get("/api/run/{run_id}/events")
async def run_events(run_id: str):
    run = runs.get(run_id)
    if not run:
        return JSONResponse({"error": "Run not found"}, status_code=404)

    async def event_stream():
        while True:
            try:
                event = run.events.get_nowait()
                yield f"data: {json.dumps(event)}\n\n"
                if event.get("type") == "done":
                    break
            except Empty:
                await asyncio.sleep(0.5)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.get("/api/runs")
async def list_runs():
    """Return recent runs for the history panel."""
    result = []
    for run in reversed(list(runs.values())):
        entry = {
            "id": run.id,
            "org": run.org,
            "status": run.status,
            "result": run.result,
            "pipeline_type": getattr(run, "pipeline_type", "10plus"),
        }
        if hasattr(run, "start_date"):
            entry["start_date"] = run.start_date
            entry["end_date"] = run.end_date
        else:
            entry["start_date"] = getattr(run, "pre_start", "")
            entry["end_date"] = getattr(run, "post_end", "")
        result.append(entry)
    return result[:20]


# ─── Scrape-Only Route ──────────────────────────────────────────────────────

@app.post("/api/scrape-only")
async def start_scrape_only(request: Request):
    """Scrape-only mode: login → navigate to existing validation results → scrape → report."""
    data = await request.json()
    org = data.get("org", "").strip()

    if not org:
        return JSONResponse({"error": "org is required"}, status_code=400)

    if org not in ORGS:
        return JSONResponse({"error": f"Unknown org: {org}"}, status_code=400)

    run = ScrapeOnlyRun(org)
    runs[run.id] = run

    thread = threading.Thread(target=run.run, daemon=True)
    thread.start()

    return {"run_id": run.id}


# ─── ROI Pipeline Routes ────────────────────────────────────────────────────

@app.post("/api/roi/run")
async def start_roi_run(request: Request):
    data = await request.json()
    org = data.get("org", "").strip()
    st_username = data.get("st_username", "").strip()
    st_password = data.get("st_password", "").strip()
    pre_start = data.get("pre_start", "").strip()
    pre_end = data.get("pre_end", "").strip()
    post_start = data.get("post_start", "").strip()
    post_end = data.get("post_end", "").strip()
    go_live_date = data.get("go_live_date", "").strip()
    trades = data.get("trades", ["HVAC", "Plumbing", "Electrical", "Drains"])
    business_units = data.get("business_units", {})

    if not org or not st_username or not st_password:
        return JSONResponse(
            {"error": "org, st_username, and st_password are required"},
            status_code=400,
        )
    if not pre_start or not pre_end or not post_start or not post_end:
        return JSONResponse(
            {"error": "All four date fields are required (pre_start, pre_end, post_start, post_end)"},
            status_code=400,
        )

    run = ROIPipelineRun(
        org=org,
        st_username=st_username,
        st_password=st_password,
        pre_start=pre_start,
        pre_end=pre_end,
        post_start=post_start,
        post_end=post_end,
        go_live_date=go_live_date,
        trades=trades,
        business_units=business_units,
    )
    runs[run.id] = run

    thread = threading.Thread(target=run.run, daemon=True)
    thread.start()

    return {"run_id": run.id}


@app.post("/api/roi/mfa/{run_id}")
async def submit_mfa_code(run_id: str, request: Request):
    """Submit MFA code for an ROI pipeline run."""
    run = runs.get(run_id)
    if not run or not isinstance(run, ROIPipelineRun):
        return JSONResponse({"error": "ROI run not found"}, status_code=404)

    data = await request.json()
    code = data.get("code", "").strip()
    if not code:
        return JSONResponse({"error": "code is required"}, status_code=400)

    run.mfa_code = code
    run.mfa_event.set()
    return {"ok": True}


@app.get("/api/download/{filename}")
async def download_file(filename: str):
    """Download a generated report file."""
    file_path = Path(".") / filename
    if not file_path.exists():
        return JSONResponse({"error": "File not found"}, status_code=404)
    return FileResponse(
        path=str(file_path),
        filename=filename,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


# ─── Main ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="10+ Automation Dashboard")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()

    print(f"\n  10+ Automation Dashboard")
    print(f"  http://{args.host}:{args.port}\n")

    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
