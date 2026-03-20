"""
Google Sheets Upload — Creates a formatted Google Sheet mirroring the Excel report.

Tabs:
  1. "{Customer} 10+ Detail" — per-job breakdown with color-coded rows
  2. "Summary"               — aggregate counts and color legend

First run opens browser for Google OAuth consent. Token is saved for reuse.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional

import gspread
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

from scraper import JobRecord

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
]

PROJECT_DIR = Path(__file__).parent
TOKEN_PATH = PROJECT_DIR / "google_token.json"
CREDS_PATH = PROJECT_DIR / "google_credentials.json"

# ─── Colors (Google Sheets format: RGB dict) ─────────────────────────────────

HEADER_BG = {"red": 0.122, "green": 0.306, "blue": 0.475}      # #1F4E79
HEADER_FG = {"red": 1, "green": 1, "blue": 1}                   # white

RED_BG = {"red": 1, "green": 0.78, "blue": 0.808}               # #FFC7CE
YELLOW_BG = {"red": 1, "green": 1, "blue": 0}                   # #FFFF00
ORANGE_BG = {"red": 0.988, "green": 0.835, "blue": 0.706}       # #FCD5B4
BLUE_BG = {"red": 0.863, "green": 0.902, "blue": 0.945}         # #DCE6F1
GREEN_BG = {"red": 0.776, "green": 0.937, "blue": 0.808}        # #C6EFCE
WHITE_BG = {"red": 1, "green": 1, "blue": 1}
BLACK_FG = {"red": 0, "green": 0, "blue": 0}

LEGEND_YELLOW_BG = {"red": 1, "green": 0.922, "blue": 0.612}    # #FFEB9C

THIN_BORDER = {
    "top":    {"style": "SOLID", "color": BLACK_FG},
    "bottom": {"style": "SOLID", "color": BLACK_FG},
    "left":   {"style": "SOLID", "color": BLACK_FG},
    "right":  {"style": "SOLID", "color": BLACK_FG},
}

CATEGORY_COLORS = {
    "Dispatcher placed 10+ tag that Probook Missed": RED_BG,
    "Probook placed 10+ tag that CSR/Dispatch Missed": YELLOW_BG,
    "10+ Priority Mismatch": ORANGE_BG,
    "10+ Job Type Mismatch": BLUE_BG,
    "10+ Tag Mismatch": GREEN_BG,
}

CATEGORY_ORDER = [
    "Dispatcher placed 10+ tag that Probook Missed",
    "Probook placed 10+ tag that CSR/Dispatch Missed",
    "10+ Priority Mismatch",
    "10+ Job Type Mismatch",
    "10+ Tag Mismatch",
    "Match",
]

REPORT_COLUMNS = [
    "Job ID", "Reasons", "ST Link", "Category",
    "VP Business Unit", "VP Job Type", "VP Priority",
    "Disp Job Type", "Probook Tags", "Disp Business Unit",
    "Disp Priority", "Disp Tags", "VP 10+ Tags", "Disp 10+ Tags",
]


# ─── Auth ────────────────────────────────────────────────────────────────────

def _get_client() -> gspread.Client:
    """Authenticate and return a gspread client."""
    creds = None

    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not CREDS_PATH.exists():
                raise FileNotFoundError(
                    f"Google OAuth credentials not found at {CREDS_PATH}.\n"
                    "Download your OAuth 2.0 Client ID JSON from:\n"
                    "  https://console.cloud.google.com/apis/credentials\n"
                    "Save it as google_credentials.json in the project directory."
                )
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDS_PATH), SCOPES)
            creds = flow.run_local_server(port=0)

        TOKEN_PATH.write_text(creds.to_json())

    return gspread.authorize(creds)


# ─── Main Upload ─────────────────────────────────────────────────────────────

def upload_to_google_sheets(
    jobs: list[JobRecord],
    customer_name: str,
) -> str:
    """Create a formatted Google Sheet with Detail and Summary tabs."""
    relevant = [j for j in jobs if j.ai_has_10plus or j.disp_has_10plus]
    cat_sort = {c: i for i, c in enumerate(CATEGORY_ORDER)}
    relevant.sort(key=lambda j: cat_sort.get(j.category, 99))

    client = _get_client()

    date_str = datetime.now().strftime("%Y-%m-%d")
    title = f"{customer_name} 10+ Report {date_str}"

    sh = client.create(title)
    print(f"  Created Google Sheet: {title}")

    _build_report_sheet(sh, relevant, customer_name)
    _build_summary_sheet(sh, relevant, customer_name)

    # Delete the default "Sheet1" if it still exists
    try:
        default = sh.worksheet("Sheet1")
        sh.del_worksheet(default)
    except gspread.exceptions.WorksheetNotFound:
        pass

    url = sh.url
    print(f"  Google Sheet URL: {url}")
    return url


# ─── Tab 1: Detail ──────────────────────────────────────────────────────────

def _build_report_sheet(sh: gspread.Spreadsheet, jobs: list[JobRecord], customer_name: str) -> None:
    ws = sh.add_worksheet(f"{customer_name} 10+ Detail", rows=len(jobs) + 1, cols=len(REPORT_COLUMNS))

    rows = [REPORT_COLUMNS]
    for job in jobs:
        ai_10plus = ", ".join(t for t in job.ai_prediction.tags if "10+" in t) or "None"
        disp_10plus = ", ".join(t for t in job.dispatcher_verified.tags if "10+" in t) or "None"
        st_link = f"https://go.servicetitan.com/#/Job/Index/{job.job_id}"

        rows.append([
            job.job_id,
            job.hvac_system_age_reason,
            st_link,
            job.category,
            job.business_unit,
            job.ai_prediction.job_type,
            job.ai_prediction.priority,
            job.dispatcher_verified.job_type,
            ", ".join(job.ai_prediction.tags),
            job.business_unit,
            job.dispatcher_verified.priority,
            ", ".join(job.dispatcher_verified.tags),
            ai_10plus,
            disp_10plus,
        ])

    ws.update(rows, "A1")
    print(f"  Wrote {len(jobs)} rows to '{customer_name} 10+ Detail'")

    # ── Formatting ──
    formats = []

    # Header row
    formats.append({
        "range": f"A1:{_col_letter(len(REPORT_COLUMNS))}1",
        "format": {
            "backgroundColor": HEADER_BG,
            "textFormat": {"foregroundColor": HEADER_FG, "bold": True, "fontSize": 10},
            "horizontalAlignment": "CENTER",
            "wrapStrategy": "WRAP",
            "borders": THIN_BORDER,
        },
    })

    # Data rows — color by category
    for i, job in enumerate(jobs):
        row_num = i + 2
        row_range = f"A{row_num}:{_col_letter(len(REPORT_COLUMNS))}{row_num}"

        bg = CATEGORY_COLORS.get(job.category, WHITE_BG)
        formats.append({
            "range": row_range,
            "format": {
                "backgroundColor": bg,
                "borders": THIN_BORDER,
                "verticalAlignment": "TOP",
                "wrapStrategy": "WRAP",
            },
        })

    ws.batch_format(formats)

    # Auto-filter
    last_col = len(REPORT_COLUMNS) - 1
    sh.batch_update({"requests": [{
        "setBasicFilter": {
            "filter": {
                "range": {
                    "sheetId": ws.id,
                    "startRowIndex": 0,
                    "endRowIndex": len(jobs) + 1,
                    "startColumnIndex": 0,
                    "endColumnIndex": len(REPORT_COLUMNS),
                }
            }
        }
    }]})

    # Freeze header row
    if len(jobs) > 0:
        ws.freeze(rows=1)

    # Column widths (pixels)
    _set_column_widths(ws, [
        100,   # Job ID
        700,   # Reasons
        310,   # ST Link
        420,   # Category
        250,   # VP Business Unit
        210,   # VP Job Type
        70,    # VP Priority
        250,   # Disp Job Type
        350,   # Probook Tags
        250,   # Disp Business Unit
        70,    # Disp Priority
        620,   # Disp Tags
        175,   # VP 10+ Tags
        175,   # Disp 10+ Tags
    ])


# ─── Tab 2: Summary ─────────────────────────────────────────────────────────

def _build_summary_sheet(sh: gspread.Spreadsheet, jobs: list[JobRecord], customer_name: str) -> None:
    ws = sh.add_worksheet("Summary", rows=20, cols=3)

    counts = {}
    for cat in CATEGORY_ORDER:
        counts[cat] = sum(1 for j in jobs if j.category == cat)

    summary_labels = {
        "Dispatcher placed 10+ tag that Probook Missed": "MISSED 10+ (Probook under-classified)",
        "Probook placed 10+ tag that CSR/Dispatch Missed": "Probook placed 10+ tag that CSR/Dispatch Missed",
        "10+ Priority Mismatch": "10+ Priority Mismatch",
        "10+ Job Type Mismatch": "10+ Job Type Mismatch",
        "10+ Tag Mismatch": "10+ Tag Mismatch",
        "Match": "Match (Both sides agree)",
    }

    data = [
        [f"{customer_name} 10+ Mismatch Summary", "", ""],
        ["", "", ""],
        ["Category", "Count", "Color"],
    ]

    for cat in CATEGORY_ORDER:
        data.append([summary_labels[cat], counts[cat], ""])

    total_row_idx = len(data)  # 0-based index for the TOTAL row
    data.append(["TOTAL", f"=SUM(B4:B{total_row_idx})", ""])
    data.append(["", "", ""])
    data.append(["Color Legend:", "", ""])

    legend_items = [
        "Red — MISSED 10+: Probook did not classify as 10+ but Dispatcher confirmed 10+",
        "Yellow — Priority Mismatch: Both agree on 10+ Job Type but Priority differs",
        "Orange — Over-aged: Probook said 10+ but Dispatcher had different non-10+ Job Type",
        "Blue — Job Type Mismatch: Both 10+ but different specific 10+ Job Type",
        "Green — Tag differences or tag-only 10+ references",
    ]
    for text in legend_items:
        data.append([text, "", ""])

    ws.update(data, "A1")

    formats = [
        # Header row
        {
            "range": "A3:C3",
            "format": {
                "backgroundColor": HEADER_BG,
                "textFormat": {"foregroundColor": HEADER_FG, "bold": True, "fontSize": 10},
                "borders": THIN_BORDER,
            },
        },
        # Title
        {"range": "A1", "format": {"textFormat": {"bold": True, "fontSize": 14}}},
        # TOTAL row bold
        {"range": f"A{total_row_idx + 1}:B{total_row_idx + 1}", "format": {"textFormat": {"bold": True}}},
    ]

    # Legend colors
    legend_start = total_row_idx + 4  # 1-based row number
    legend_fills = [RED_BG, LEGEND_YELLOW_BG, ORANGE_BG, BLUE_BG, GREEN_BG]
    for i, fill in enumerate(legend_fills):
        row = legend_start + i
        formats.append({
            "range": f"A{row}",
            "format": {"backgroundColor": fill},
        })

    ws.batch_format(formats)

    _set_column_widths(ws, [500, 80, 70])

    print("  Wrote Summary tab")


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _col_letter(n: int) -> str:
    """Convert 1-based column number to letter (1=A, 26=Z, 27=AA)."""
    result = ""
    while n > 0:
        n, remainder = divmod(n - 1, 26)
        result = chr(65 + remainder) + result
    return result


def _set_column_widths(ws: gspread.Worksheet, widths: list[int]) -> None:
    """Set pixel widths for columns using the Sheets API."""
    requests = []
    for i, w in enumerate(widths):
        requests.append({
            "updateDimensionProperties": {
                "range": {
                    "sheetId": ws.id,
                    "dimension": "COLUMNS",
                    "startIndex": i,
                    "endIndex": i + 1,
                },
                "properties": {"pixelSize": w},
                "fields": "pixelSize",
            }
        })
    ws.spreadsheet.batch_update({"requests": requests})
