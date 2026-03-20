#!/usr/bin/env python3
"""
10+ Automation Tool — CLI entry point & pipeline orchestrator.

Automates the AI Validation 10+ report pipeline:
  1. Login to ProBook admin dashboard
  2. Navigate to Audit > AI Validation > Dataset Builder
  3. Build dataset for a date range
  4. Run AI Validation
  5. Configure diff view, scroll to load all jobs, scrape data
  6. (Optional) QA a sample of jobs in ServiceTitan
  7. Generate formatted Excel report

Usage:
    python 10plus_automation.py \\
        --customer "Dyess Air" \\
        --start-date 2024-01-01 \\
        --end-date 2024-01-31 \\
        [--qa] \\
        [--output-dir .]
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from scraper import ProBookScraper
from report_generator import generate_report
from google_upload import upload_to_google_sheets


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="10+ Automation Tool — Automate AI Validation 10+ reports from ProBook.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python 10plus_automation.py --customer "Dyess Air" --start-date 2024-01-01 --end-date 2024-01-31
  python 10plus_automation.py --customer "Dyess Air" --start-date 2024-01-01 --end-date 2024-01-31 --qa
  python 10plus_automation.py --customer "Dyess Air" --start-date 2024-01-01 --end-date 2024-01-31 --qa --output-dir ./reports
        """,
    )
    parser.add_argument(
        "--customer",
        required=True,
        help="Customer name as it appears in the ProBook dropdown (e.g., 'Dyess Air')",
    )
    parser.add_argument(
        "--start-date",
        required=True,
        help="Dataset start date in YYYY-MM-DD format",
    )
    parser.add_argument(
        "--end-date",
        required=True,
        help="Dataset end date in YYYY-MM-DD format",
    )
    parser.add_argument(
        "--qa",
        action="store_true",
        default=False,
        help="Run ServiceTitan QA phase on a sample of flagged jobs",
    )
    parser.add_argument(
        "--output-dir",
        default=".",
        help="Directory for output files (default: current directory)",
    )
    parser.add_argument(
        "--google-sheets",
        action="store_true",
        default=False,
        help="Upload the report to Google Drive as a Google Sheet.",
    )
    parser.add_argument(
        "--no-interactive",
        action="store_true",
        default=False,
        help="Run without input() pauses (for non-interactive shells). Uses timed waits instead.",
    )

    return parser.parse_args()


def validate_date(date_str: str, label: str) -> None:
    """Validate that a date string is in YYYY-MM-DD format."""
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        print(f"ERROR: {label} '{date_str}' is not in YYYY-MM-DD format.")
        sys.exit(1)


def select_qa_jobs(jobs, max_count: int = 10) -> list[str]:
    """Select up to max_count jobs for QA: prioritize missed, then pad with extra."""
    missed = [j for j in jobs if j.ten_plus_status == "AI Missed 10+"]
    extra = [j for j in jobs if j.ten_plus_status == "AI Added 10+"]

    qa_jobs = []

    # Prioritize missed
    for job in missed:
        if len(qa_jobs) >= max_count:
            break
        qa_jobs.append(job.job_id)

    # Pad with extra
    for job in extra:
        if len(qa_jobs) >= max_count:
            break
        qa_jobs.append(job.job_id)

    return qa_jobs


def print_summary(jobs) -> None:
    """Print a summary of the scraping results to the console."""
    relevant = [j for j in jobs if j.ai_has_10plus or j.disp_has_10plus]
    missed = sum(1 for j in relevant if j.ten_plus_status == "AI Missed 10+")
    extra = sum(1 for j in relevant if j.ten_plus_status == "AI Added 10+")
    extra_unknown = sum(1 for j in relevant if j.ten_plus_status == "AI Added 10+" and j.unknown_age)
    matched = sum(1 for j in relevant if j.ten_plus_status == "Match")

    print("\n" + "=" * 50)
    print("  10+ TAG REPORT SUMMARY")
    print("=" * 50)
    print(f"  Total jobs scraped:     {len(jobs)}")
    print(f"  Jobs with 10+ tag:      {len(relevant)}")
    print(f"  ─────────────────────────────")
    print(f"  AI Missed 10+:          {missed}")
    print(f"  AI Added 10+:           {extra}  (Unknown Age: {extra_unknown})")
    print(f"  Match:                  {matched}")
    print("=" * 50 + "\n")


def main() -> None:
    args = parse_args()

    # Validate inputs
    validate_date(args.start_date, "--start-date")
    validate_date(args.end_date, "--end-date")

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    qa_dir = output_dir / "qa_screenshots"

    scraper = ProBookScraper(
        customer_name=args.customer,
        start_date=args.start_date,
        end_date=args.end_date,
        qa_dir=str(qa_dir),
        interactive=not args.no_interactive,
    )

    try:
        # Phase 1: Launch & Login
        scraper.launch()
        scraper.login_and_select_customer()

        # Phase 2: Navigate to Audit
        scraper.navigate_to_audit()

        # Phase 3: Build Dataset
        scraper.build_dataset()

        # Phase 4: Run Validation
        scraper.run_validation()

        # Phase 5: Navigate to Diffs Dashboard, Scroll, Scrape
        scraper.navigate_to_diffs()
        scraper.scroll_and_load_all_jobs()
        jobs = scraper.scrape_all_jobs()

        # Phase 6: Enrich mismatched jobs with LangSmith trace reasons
        scraper.enrich_jobs_with_trace_reasons()

        # Save JSON backup
        json_path = scraper.save_json_backup(output_dir=str(output_dir))
        print(f"JSON backup: {json_path}")

        # Phase 7 (optional): ServiceTitan QA
        qa_records = None
        if args.qa:
            qa_job_ids = select_qa_jobs(jobs, max_count=10)
            if qa_job_ids:
                qa_records = scraper.qa_in_servicetitan(qa_job_ids)
            else:
                print("No jobs flagged for QA — skipping ServiceTitan phase.")

        # Generate Excel report
        report_path = generate_report(
            jobs=jobs,
            customer_name=args.customer,
            output_dir=str(output_dir),
            qa_records=qa_records,
        )
        print(f"Report saved: {report_path}")

        # Upload to Google Sheets if requested
        if args.google_sheets:
            try:
                sheet_url = upload_to_google_sheets(jobs, args.customer)
                print(f"Google Sheet: {sheet_url}")
            except Exception as e:
                print(f"Google Sheets upload failed: {e}")

        # Print summary
        print_summary(jobs)

    except KeyboardInterrupt:
        print("\nInterrupted by user.")

    except Exception as e:
        print(f"\nERROR: {e}")

        # Attempt to save partial data
        if scraper.jobs:
            try:
                partial_path = scraper.save_json_backup(output_dir=str(output_dir))
                print(f"Partial data saved: {partial_path}")
            except Exception:
                print("Could not save partial data.")

        raise

    finally:
        scraper.close()


if __name__ == "__main__":
    main()
