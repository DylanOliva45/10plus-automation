#!/usr/bin/env python3
"""Full ROI pull for Dyess — 3 HVAC location trades with per-trade BU filters and date ranges."""
import time
from roi_scraper import (
    ServiceTitanScraper, TECH_PERF_COLUMNS,
    ST_COL_TO_METRIC, TradeMetrics, DriveTimeMetrics,
)
from roi_report import generate_roi_report

# ─── Config ──────────────────────────────────────────────────────────────────

ORG_NAME = "Dyess"

# Each trade has its own BUs, date ranges, and report URL
TRADES = {
    "HVAC Bluffton": {
        "bus": [
            "Bluffton HVAC Member Check Ups",
            "Bluffton HVAC Service",
        ],
        "report_url": "https://go.servicetitan.com/#/new/reports/47929159",
        "pre_start": "11/11/2023",
        "pre_end": "11/10/2024",
        "post_start": "11/11/2024",
        "post_end": "12/22/2025",
        "natural_y1_start": "11/11/2022",
        "natural_y1_end": "11/10/2023",
        "natural_y2_start": "11/11/2023",
        "natural_y2_end": "11/10/2024",
    },
    "HVAC Claxton": {
        "bus": [
            "Claxton HVAC Member Check Ups",
            "Claxton HVAC Service",
        ],
        "report_url": "https://go.servicetitan.com/#/new/reports/47929159",
        "pre_start": "11/10/2023",
        "pre_end": "11/10/2024",
        "post_start": "12/16/2024",
        "post_end": "12/20/2025",
        "natural_y1_start": "11/10/2022",
        "natural_y1_end": "11/10/2023",
        "natural_y2_start": "11/10/2023",
        "natural_y2_end": "11/10/2024",
    },
    "HVAC Hilton": {
        "bus": [
            "Hilton Head HVAC Member Check Ups",
            "Hilton Head HVAC Service",
        ],
        "report_url": "https://go.servicetitan.com/#/new/reports/171066718",
        "pre_start": "11/10/2023",
        "pre_end": "11/10/2024",
        "post_start": "11/11/2024",
        "post_end": "11/11/2025",
        "natural_y1_start": "11/09/2022",
        "natural_y1_end": "11/09/2023",
        "natural_y2_start": "11/10/2023",
        "natural_y2_end": "11/10/2024",
    },
}


def _parse_number(raw):
    import re
    if not raw:
        return 0
    cleaned = re.sub(r'[^0-9.\-]', '', str(raw))
    try:
        return float(cleaned)
    except ValueError:
        return 0


def _data_to_metrics(data):
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


def _add_metrics(target, source):
    target.total_sales += source.total_sales
    target.total_tech_lead_sales += source.total_tech_lead_sales
    target.completed_revenue += source.completed_revenue
    target.completed_jobs += source.completed_jobs
    target.opportunities += source.opportunities
    target.sales_opportunities += source.sales_opportunities
    target.leads_set += source.leads_set
    target.converted_jobs += source.converted_jobs


def _read_mfa_from_slack(max_age_seconds=120):
    """Read 6-digit MFA code from Slack #mfa channel."""
    import os, re
    from datetime import datetime, timezone
    from dotenv import load_dotenv
    load_dotenv()
    token = os.getenv("SLACK_BOT_TOKEN")
    if not token:
        return None
    from slack_sdk import WebClient
    client = WebClient(token=token)
    # Find #mfa channel
    channels = client.conversations_list(types="public_channel,private_channel", limit=200)
    mfa_channel = None
    for ch in channels["channels"]:
        if ch["name"] == "mfa":
            mfa_channel = ch["id"]
            break
    if not mfa_channel:
        print("No #mfa channel found")
        return None
    # Read recent messages
    msgs = client.conversations_history(channel=mfa_channel, limit=5)
    now = datetime.now(timezone.utc).timestamp()
    for msg in msgs.get("messages", []):
        ts = float(msg.get("ts", 0))
        age = now - ts
        if age <= max_age_seconds:
            text = msg.get("text", "")
            match = re.search(r'\b(\d{6})\b', text)
            if match:
                return match.group(1)
    return None


def _get_mfa_code():
    """Poll file for MFA code (written externally by Claude or user)."""
    import os
    mfa_file = "/Users/dylanoliva/Projects/10plus-automation/mfa_code.txt"
    # Clear any old file
    if os.path.exists(mfa_file):
        os.remove(mfa_file)
    print(f"MFA NEEDED — waiting for code in {mfa_file}")
    for i in range(120):  # 10 minutes total
        time.sleep(5)
        if os.path.exists(mfa_file):
            with open(mfa_file) as f:
                code = f.read().strip()
            if code and len(code) >= 6:
                os.remove(mfa_file)
                print(f"MFA code received: {code}")
                return code
        if i % 12 == 11:
            print(f"  Still waiting for MFA... ({(i+1)*5}s)")
    raise RuntimeError("No MFA code received within 10 minutes")


def main():
    scraper = ServiceTitanScraper("dyess-support", "N7!qZ4@P$wM9rK2#Lx", log_fn=print)

    results = {
        "basic": {},
        "natural": {},
        "high_level_pre": TradeMetrics(),
        "high_level_post": TradeMetrics(),
        "drive_time_pre": DriveTimeMetrics(),
        "drive_time_post": DriveTimeMetrics(),
    }

    current_report_url = None

    try:
        scraper.launch()
        scraper.login(mfa_code_fn=_get_mfa_code)

        for trade, config in TRADES.items():
            print(f"\n{'='*60}")
            print(f"=== {trade} ({len(config['bus'])} BUs) ===")
            print(f"{'='*60}")

            # Navigate to the correct report if different from current
            report_url = config["report_url"]
            if report_url != current_report_url:
                print(f"\n--- Navigating to report: {report_url} ---")
                scraper.page.goto(report_url, wait_until="domcontentloaded", timeout=30000)
                time.sleep(5)
                current_report_url = report_url
                print(f"  Report page loaded: {scraper.page.url}")

            # Set BU filter
            scraper.set_business_unit_filter(config["bus"])
            time.sleep(2)

            # --- PRE-PB ---
            print(f"\n--- {trade} PRE: {config['pre_start']} - {config['pre_end']} ---")
            scraper.set_date_range(config["pre_start"], config["pre_end"])
            pre_data = scraper.run_and_export(TECH_PERF_COLUMNS)
            pre_metrics = _data_to_metrics(pre_data)
            print(f"  Pre data: {pre_data}")

            # --- POST-PB ---
            print(f"\n--- {trade} POST: {config['post_start']} - {config['post_end']} ---")
            scraper.set_date_range(config["post_start"], config["post_end"])
            post_data = scraper.run_and_export(TECH_PERF_COLUMNS)
            post_metrics = _data_to_metrics(post_data)
            print(f"  Post data: {post_data}")

            results["basic"][trade] = {"pre": pre_metrics, "post": post_metrics}
            _add_metrics(results["high_level_pre"], pre_metrics)
            _add_metrics(results["high_level_post"], post_metrics)

            # --- NATURAL Y1 ---
            print(f"\n--- {trade} Natural Y1: {config['natural_y1_start']} - {config['natural_y1_end']} ---")
            scraper.set_date_range(config["natural_y1_start"], config["natural_y1_end"])
            nat_y1_data = scraper.run_and_export(TECH_PERF_COLUMNS)
            nat_y1_metrics = _data_to_metrics(nat_y1_data)
            print(f"  Natural Y1 data: {nat_y1_data}")

            # --- NATURAL Y2 ---
            print(f"\n--- {trade} Natural Y2: {config['natural_y2_start']} - {config['natural_y2_end']} ---")
            scraper.set_date_range(config["natural_y2_start"], config["natural_y2_end"])
            nat_y2_data = scraper.run_and_export(TECH_PERF_COLUMNS)
            nat_y2_metrics = _data_to_metrics(nat_y2_data)
            print(f"  Natural Y2 data: {nat_y2_data}")

            results["natural"][trade] = {"y1": nat_y1_metrics, "y2": nat_y2_metrics}

            # Reset BU filter for next trade
            scraper.set_business_unit_filter([])
            time.sleep(2)

        # ── Generate Excel ──
        print(f"\n{'='*60}")
        print("=== Generating ROI Excel Report ===")
        print(f"{'='*60}")

        report_path = generate_roi_report(
            data=results,
            org_name=ORG_NAME,
            pre_start="varies",
            pre_end="varies",
            post_start="varies",
            post_end="varies",
            output_dir=".",
        )
        print(f"\nReport saved: {report_path}")

        # ── Print summary ──
        print(f"\n{'='*60}")
        print("=== SUMMARY ===")
        print(f"{'='*60}")
        for trade, data in results["basic"].items():
            pre = data["pre"]
            post = data["post"]
            print(f"\n{trade}:")
            print(f"  Pre:  Total Sales=${pre.total_sales:,.2f}  Jobs={pre.completed_jobs}  Opps={pre.opportunities}")
            print(f"  Post: Total Sales=${post.total_sales:,.2f}  Jobs={post.completed_jobs}  Opps={post.opportunities}")

        for trade, data in results["natural"].items():
            y1 = data["y1"]
            y2 = data["y2"]
            print(f"\n{trade} Natural:")
            print(f"  Y1: Total Sales=${y1.total_sales:,.2f}  Jobs={y1.completed_jobs}  Opps={y1.opportunities}")
            print(f"  Y2: Total Sales=${y2.total_sales:,.2f}  Jobs={y2.completed_jobs}  Opps={y2.opportunities}")

        hl_pre = results["high_level_pre"]
        hl_post = results["high_level_post"]
        print(f"\nHigh Level (All Trades):")
        print(f"  Pre:  Total Sales=${hl_pre.total_sales:,.2f}  Jobs={hl_pre.completed_jobs}  Opps={hl_pre.opportunities}")
        print(f"  Post: Total Sales=${hl_post.total_sales:,.2f}  Jobs={hl_post.completed_jobs}  Opps={hl_post.opportunities}")

    finally:
        scraper.close()


if __name__ == "__main__":
    main()
