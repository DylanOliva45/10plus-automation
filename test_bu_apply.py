#!/usr/bin/env python3
"""Test: Open saved report, apply BU filter for HVAC, set date range, run report, extract data."""
import json, time
from roi_scraper import ServiceTitanScraper

def main():
    scraper = ServiceTitanScraper("george_eli", "@esT0frEtEk5dLYEXi47", log_fn=print)
    try:
        scraper.launch()
        scraper.login(mfa_code_fn=lambda: input("MFA: "))

        # Open the existing saved report
        print("\n=== Opening saved report ===")
        scraper.page.goto(
            "https://go.servicetitan.com/#/new/reports/354643851",
            wait_until="domcontentloaded", timeout=15000
        )
        time.sleep(5)
        print(f"URL: {scraper.page.url}")

        # Apply BU filter for HVAC
        print("\n=== Applying BU filter: HVAC ===")
        scraper.set_business_unit_filter([
            "NL-HVAC: SVC",
            "NL-HVAC: Install",
            "NL-HVAC: Sales",
        ])

        # Set date range (last 3 weeks)
        print("\n=== Setting date range ===")
        scraper.set_date_range("02/17/2026", "03/10/2026")

        # Run report and extract
        print("\n=== Running report ===")
        from roi_scraper import TECH_PERF_COLUMNS
        data = scraper.run_and_export(TECH_PERF_COLUMNS)
        print(f"\nExtracted data (HVAC BUs):")
        for k, v in data.items():
            print(f"  {k}: {v}")

        # Now reset BU and try Plumbing
        print("\n=== Resetting BU filter ===")
        scraper.set_business_unit_filter([])  # reset to All

        print("\n=== Applying BU filter: Plumbing ===")
        scraper.set_business_unit_filter([
            "NL-Plumb: SVC",
            "NL-Plumb: Install",
            "NL-Plumb: Sales",
        ])

        # Run again
        print("\n=== Running report (Plumbing) ===")
        from roi_scraper import PLUMBING_COLUMNS
        data2 = scraper.run_and_export(PLUMBING_COLUMNS)
        print(f"\nExtracted data (Plumbing BUs):")
        for k, v in data2.items():
            print(f"  {k}: {v}")

        print("\n=== Done ===")

    finally:
        scraper.close()

if __name__ == "__main__":
    main()
