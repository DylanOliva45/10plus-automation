#!/usr/bin/env python3
"""Full automated test: ProBook → diffs → LangSmith trace enrichment → Excel."""

from scraper import ProBookScraper
from report_generator import generate_report

scraper = ProBookScraper(
    customer_name="Zephyr",
    start_date="2025-03-10",
    end_date="2025-03-16",
    interactive=False,
)

try:
    scraper.launch()
    scraper.login_and_select_customer()
    scraper.navigate_to_audit()

    # Skip build_dataset() and run_validation() — use existing dataset

    scraper.navigate_to_diffs()
    scraper.scroll_and_load_all_jobs()
    jobs = scraper.scrape_all_jobs()

    # Enrich with LangSmith trace reasons
    scraper.enrich_jobs_with_trace_reasons(max_jobs=30)

    scraper.save_json_backup()

    report_path = generate_report(
        jobs=jobs,
        customer_name="Zephyr",
    )
    print(f"\nReport saved: {report_path}")

except Exception as e:
    print(f"\nERROR: {e}")
    if scraper.jobs:
        scraper.save_json_backup()
    raise

finally:
    scraper.close()
