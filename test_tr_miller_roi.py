#!/usr/bin/env python3
"""Full ROI pull for TR Miller — 4 trades with BU filters."""
import time
from roi_scraper import (
    ServiceTitanScraper, TECH_PERF_COLUMNS, PLUMBING_COLUMNS, ELECTRICAL_COLUMNS,
    ST_COL_TO_METRIC, TradeMetrics, DriveTimeMetrics,
)
from roi_report import generate_roi_report

TRADES_BUS = {
    "HVAC": [
        "NL-HVAC: Inspection Special",
        "NL-HVAC: Membership Inspection",
        "NL-HVAC: Sales",
        "NL-HVAC: SVC",
        "PF-HVAC: Inspection Special",
        "PF-HVAC: Membership Inspection",
        "PF-HVAC: Sales",
        "PF-HVAC: SVC",
    ],
    "Plumbing": [
        "NL-Plumb: Inspection Special",
        "NL-Plumb: Membership Inspection",
        "NL-Plumb: SVC",
        "PF-Plumb: Inspection Special",
        "PF-Plumb: Membership Inspection",
        "PF-Plumb: SVC",
    ],
    "Electrical": [
        "PF-Elect: Inspection Special",
        "PF-Elect: Membership Inspection",
        "PF-Elect: SVC",
    ],
    "Drains": [
        "NL-Sewer: SVC",
        "PF-Sewer: Sales",
        "PF-Sewer: SVC",
    ],
}

PRE_START = "02/10/2026"
PRE_END = "02/24/2026"
POST_START = "02/24/2026"
POST_END = "03/10/2026"

ORG_NAME = "TR_Miller"


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


def main():
    scraper = ServiceTitanScraper("george_eli", "@esT0frEtEk5dLYEXi47", log_fn=print)

    results = {
        "basic": {},
        "natural": {},
        "high_level_pre": TradeMetrics(),
        "high_level_post": TradeMetrics(),
        "drive_time_pre": DriveTimeMetrics(),
        "drive_time_post": DriveTimeMetrics(),
    }

    try:
        scraper.launch()
        scraper.login(mfa_code_fn=lambda: input("MFA: "))

        # Open existing report
        print("\n=== Opening saved Technician Performance report ===")
        scraper.open_or_create_report(
            report_name="ROI Pull TR_Miller",
            template="Technician Performance",
            columns=TECH_PERF_COLUMNS,
        )
        time.sleep(3)

        for trade, bus in TRADES_BUS.items():
            print(f"\n{'='*60}")
            print(f"=== {trade} ({len(bus)} BUs) ===")
            print(f"{'='*60}")

            # Determine columns for this trade
            if trade in ("Plumbing", "Electrical"):
                cols = PLUMBING_COLUMNS
            else:
                cols = TECH_PERF_COLUMNS

            # --- PRE-PB ---
            print(f"\n--- {trade} PRE: {PRE_START} - {PRE_END} ---")
            scraper.set_business_unit_filter(bus)
            scraper.set_date_range(PRE_START, PRE_END)
            pre_data = scraper.run_and_export(cols)
            pre_metrics = _data_to_metrics(pre_data)
            print(f"  Pre data: {pre_data}")

            # --- POST-PB ---
            print(f"\n--- {trade} POST: {POST_START} - {POST_END} ---")
            scraper.set_date_range(POST_START, POST_END)
            post_data = scraper.run_and_export(cols)
            post_metrics = _data_to_metrics(post_data)
            print(f"  Post data: {post_data}")

            results["basic"][trade] = {"pre": pre_metrics, "post": post_metrics}
            _add_metrics(results["high_level_pre"], pre_metrics)
            _add_metrics(results["high_level_post"], post_metrics)

            # Reset BU filter for next trade
            scraper.set_business_unit_filter([])
            time.sleep(2)

        # Generate Excel
        print(f"\n{'='*60}")
        print("=== Generating ROI Excel Report ===")
        print(f"{'='*60}")

        report_path = generate_roi_report(
            data=results,
            org_name=ORG_NAME,
            pre_start="02/10/2026",
            pre_end="02/24/2026",
            post_start="02/24/2026",
            post_end="03/10/2026",
            output_dir=".",
        )
        print(f"\nReport saved: {report_path}")

        # Print summary
        print(f"\n{'='*60}")
        print("=== SUMMARY ===")
        print(f"{'='*60}")
        for trade, data in results["basic"].items():
            pre = data["pre"]
            post = data["post"]
            print(f"\n{trade}:")
            print(f"  Pre:  Total Sales=${pre.total_sales:,.2f}  Jobs={pre.completed_jobs}  Opps={pre.opportunities}")
            print(f"  Post: Total Sales=${post.total_sales:,.2f}  Jobs={post.completed_jobs}  Opps={post.opportunities}")

        hl_pre = results["high_level_pre"]
        hl_post = results["high_level_post"]
        print(f"\nHigh Level (All Trades):")
        print(f"  Pre:  Total Sales=${hl_pre.total_sales:,.2f}  Jobs={hl_pre.completed_jobs}  Opps={hl_pre.opportunities}")
        print(f"  Post: Total Sales=${hl_post.total_sales:,.2f}  Jobs={hl_post.completed_jobs}  Opps={hl_post.opportunities}")

    finally:
        scraper.close()


if __name__ == "__main__":
    main()
