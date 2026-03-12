"""
Report Generator — Produces formatted Excel reports for 10+ Tag audits.

Tabs:
  1. "10+ Tag Report" — per-job breakdown with color-coded rows
  2. "Summary"         — aggregate counts and aging logic
  3. "QA"              — ServiceTitan QA results (optional)
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from scraper import JobRecord, QARecord


# ─── Colors ───────────────────────────────────────────────────────────────────

HEADER_FILL = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
HEADER_FONT = Font(color="FFFFFF", bold=True, size=11)

RED_FILL = PatternFill(start_color="FFC7CE", end_color="FFC7CE", fill_type="solid")       # AI Missed 10+
YELLOW_FILL = PatternFill(start_color="FFEB9C", end_color="FFEB9C", fill_type="solid")     # AI Added 10+
GREEN_FILL = PatternFill(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid")      # Match
BLUE_FILL = PatternFill(start_color="BDD7EE", end_color="BDD7EE", fill_type="solid")       # Unknown Age highlight

THIN_BORDER = Border(
    left=Side(style="thin"),
    right=Side(style="thin"),
    top=Side(style="thin"),
    bottom=Side(style="thin"),
)

STATUS_FILLS = {
    "AI Missed 10+": RED_FILL,
    "AI Added 10+": YELLOW_FILL,
    "Match": GREEN_FILL,
}


# ─── Main Entry Point ────────────────────────────────────────────────────────

def generate_report(
    jobs: list[JobRecord],
    customer_name: str,
    output_dir: str = ".",
    qa_records: Optional[list[QARecord]] = None,
) -> str:
    """Generate the 10+ Tag Report Excel file.

    Args:
        jobs: All scraped JobRecords (will be filtered to 10+ relevant).
        customer_name: Customer name for the filename.
        output_dir: Directory to write the report.
        qa_records: Optional QA results from ServiceTitan.

    Returns:
        Path to the generated Excel file.
    """
    # Filter to jobs where at least one side has Opportunity 10+
    relevant_jobs = [j for j in jobs if j.ai_has_10plus or j.disp_has_10plus]
    relevant_jobs.sort(key=lambda j: j.ten_plus_status)

    wb = Workbook()

    _build_report_tab(wb, relevant_jobs)
    _build_summary_tab(wb, relevant_jobs)

    if qa_records:
        _build_qa_tab(wb, qa_records)

    # Save
    safe_name = customer_name.replace(" ", "_")
    date_str = datetime.now().strftime("%Y-%m-%d")
    filename = f"{safe_name}_10Plus_Report_{date_str}.xlsx"
    filepath = Path(output_dir) / filename
    wb.save(str(filepath))

    return str(filepath)


# ─── Tab 1: 10+ Tag Report ───────────────────────────────────────────────────

REPORT_COLUMNS = [
    "Job ID",
    "Business Unit",
    "AI Job Type",
    "Dispatcher Job Type",
    "AI Tags",
    "Dispatcher Tags",
    "AI Has 10+",
    "Disp Has 10+",
    "Unknown Age Tag",
    "10+ Status",
    "Notes",
]


def _build_report_tab(wb: Workbook, jobs: list[JobRecord]) -> None:
    ws = wb.active
    ws.title = "10+ Tag Report"

    # Header row
    for col_idx, header in enumerate(REPORT_COLUMNS, start=1):
        cell = ws.cell(row=1, column=col_idx, value=header)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center", wrap_text=True)
        cell.border = THIN_BORDER

    # Data rows
    for row_idx, job in enumerate(jobs, start=2):
        values = [
            job.job_id,
            job.business_unit,
            job.ai_prediction.job_type,
            job.dispatcher_verified.job_type,
            ", ".join(job.ai_prediction.tags),
            ", ".join(job.dispatcher_verified.tags),
            "Yes" if job.ai_has_10plus else "No",
            "Yes" if job.disp_has_10plus else "No",
            "Yes" if job.unknown_age else "No",
            job.ten_plus_status,
            job.notes,
        ]

        row_fill = STATUS_FILLS.get(job.ten_plus_status)

        for col_idx, value in enumerate(values, start=1):
            cell = ws.cell(row=row_idx, column=col_idx, value=value)
            cell.border = THIN_BORDER
            cell.alignment = Alignment(vertical="top", wrap_text=True)

            # Row-level color based on status
            if row_fill:
                cell.fill = row_fill

            # Blue highlight on Unknown Age column where "Yes"
            if col_idx == 9 and job.unknown_age:  # "Unknown Age Tag" column
                cell.fill = BLUE_FILL
                cell.font = Font(bold=True)

    # Freeze header row
    ws.freeze_panes = "A2"

    # Auto-filter
    if jobs:
        last_col = get_column_letter(len(REPORT_COLUMNS))
        ws.auto_filter.ref = f"A1:{last_col}{len(jobs) + 1}"

    # Auto-width columns
    _auto_width(ws, REPORT_COLUMNS)


# ─── Tab 2: Summary ──────────────────────────────────────────────────────────

def _build_summary_tab(wb: Workbook, jobs: list[JobRecord]) -> None:
    ws = wb.create_sheet("Summary")

    missed = [j for j in jobs if j.ten_plus_status == "AI Missed 10+"]
    extra = [j for j in jobs if j.ten_plus_status == "AI Added 10+"]
    extra_unknown = [j for j in extra if j.unknown_age]
    extra_known = [j for j in extra if not j.unknown_age]
    matched = [j for j in jobs if j.ten_plus_status == "Match"]

    summary_data = [
        ("10+ Tag Report Summary", ""),
        ("", ""),
        ("Category", "Count"),
        ("AI Missed 10+ (Dispatcher tagged, AI did not)", len(missed)),
        ("AI Added 10+ — Unknown Age", len(extra_unknown)),
        ("AI Added 10+ — Known Age", len(extra_known)),
        ("Match (Both sides tagged 10+)", len(matched)),
        ("", ""),
        ("Total Jobs with 10+ Tag", len(jobs)),
        ("", ""),
        ("Aging Logic Note:", ""),
        (
            "\"Unknown Age\" means the system could not determine equipment age. "
            "AI may tag 10+ based on other signals. These cases should be reviewed "
            "to determine if the 10+ tag is appropriate despite missing age data.",
            "",
        ),
    ]

    for row_idx, (label, value) in enumerate(summary_data, start=1):
        label_cell = ws.cell(row=row_idx, column=1, value=label)
        value_cell = ws.cell(row=row_idx, column=2, value=value)
        label_cell.border = THIN_BORDER
        value_cell.border = THIN_BORDER

        if row_idx == 1:
            label_cell.font = Font(bold=True, size=14)
        elif row_idx == 3:
            label_cell.font = Font(bold=True, size=11)
            label_cell.fill = HEADER_FILL
            label_cell.font = HEADER_FONT
            value_cell.fill = HEADER_FILL
            value_cell.font = HEADER_FONT
        elif row_idx == 4:
            label_cell.fill = RED_FILL
            value_cell.fill = RED_FILL
        elif row_idx in (5, 6):
            label_cell.fill = YELLOW_FILL
            value_cell.fill = YELLOW_FILL
        elif row_idx == 7:
            label_cell.fill = GREEN_FILL
            value_cell.fill = GREEN_FILL
        elif row_idx == 11:
            label_cell.font = Font(bold=True, italic=True)

    ws.column_dimensions["A"].width = 55
    ws.column_dimensions["B"].width = 12


# ─── Tab 3: QA ───────────────────────────────────────────────────────────────

QA_COLUMNS = ["Job ID", "Equipment Found", "Ages Found", "Screenshot Path", "Notes"]


def _build_qa_tab(wb: Workbook, qa_records: list[QARecord]) -> None:
    ws = wb.create_sheet("QA")

    # Header row
    for col_idx, header in enumerate(QA_COLUMNS, start=1):
        cell = ws.cell(row=1, column=col_idx, value=header)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center", wrap_text=True)
        cell.border = THIN_BORDER

    # Data rows
    for row_idx, qa in enumerate(qa_records, start=2):
        values = [
            qa.job_id,
            "Yes" if qa.equipment_found else "No",
            ", ".join(qa.ages_found) if qa.ages_found else "None found",
            qa.screenshot_path,
            qa.notes,
        ]

        for col_idx, value in enumerate(values, start=1):
            cell = ws.cell(row=row_idx, column=col_idx, value=value)
            cell.border = THIN_BORDER
            cell.alignment = Alignment(vertical="top", wrap_text=True)

    # Freeze header row
    ws.freeze_panes = "A2"

    # Auto-width
    _auto_width(ws, QA_COLUMNS)


# ─── Utilities ────────────────────────────────────────────────────────────────

def _auto_width(ws, columns: list[str], min_width: int = 12, max_width: int = 45) -> None:
    """Set column widths based on header length (capped)."""
    for col_idx, header in enumerate(columns, start=1):
        width = min(max(len(header) + 4, min_width), max_width)
        ws.column_dimensions[get_column_letter(col_idx)].width = width
