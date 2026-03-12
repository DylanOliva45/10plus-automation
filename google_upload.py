"""
Google Sheets Upload — Creates a formatted Google Sheet mirroring the Excel report.

Tabs:
  1. "10+ Tag Report" — per-job breakdown with color-coded rows
  2. "Summary"         — aggregate counts and aging logic

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

HEADER_BG = {"red": 0.267, "green": 0.447, "blue": 0.769}      # #4472C4
HEADER_FG = {"red": 1, "green": 1, "blue": 1}                   # white

RED_BG = {"red": 1, "green": 0.78, "blue": 0.808}               # #FFC7CE
YELLOW_BG = {"red": 1, "green": 0.922, "blue": 0.612}           # #FFEB9C
GREEN_BG = {"red": 0.776, "green": 0.937, "blue": 0.808}        # #C6EFCE
BLUE_BG = {"red": 0.741, "green": 0.843, "blue": 0.933}         # #BDD7EE
WHITE_BG = {"red": 1, "green": 1, "blue": 1}
BLACK_FG = {"red": 0, "green": 0, "blue": 0}

THIN_BORDER = {
    "top":    {"style": "SOLID", "color": BLACK_FG},
    "bottom": {"style": "SOLID", "color": BLACK_FG},
    "left":   {"style": "SOLID", "color": BLACK_FG},
    "right":  {"style": "SOLID", "color": BLACK_FG},
}

STATUS_CELL_BG = {"red": 1, "green": 0.95, "blue": 0.80}       # light cream for status cell

STATUS_COLORS = {
    "AI Missed 10+": RED_BG,
    "AI Added 10+": YELLOW_BG,
    "Match": GREEN_BG,
}

REPORT_COLUMNS = [
    "Job ID", "Business Unit", "AI Job Type", "Dispatcher Job Type",
    "AI Tags", "Dispatcher Tags", "AI Has 10+", "Disp Has 10+",
    "Unknown Age Tag", "10+ Status", "Notes",
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
    """Create a formatted Google Sheet with 10+ Tag Report and Summary tabs.

    Args:
        jobs: All scraped JobRecords (will be filtered to 10+ relevant).
        customer_name: Customer name for the sheet title.

    Returns:
        URL of the created Google Sheet.
    """
    relevant = [j for j in jobs if j.ai_has_10plus or j.disp_has_10plus]
    relevant.sort(key=lambda j: j.ten_plus_status)

    client = _get_client()

    date_str = datetime.now().strftime("%Y-%m-%d")
    title = f"{customer_name} 10+ Report {date_str}"

    sh = client.create(title)
    print(f"  Created Google Sheet: {title}")

    # Build Tab 1: 10+ Tag Report
    _build_report_sheet(sh, relevant)

    # Build Tab 2: Summary
    _build_summary_sheet(sh, relevant)

    # Delete the default "Sheet1" if it still exists
    try:
        default = sh.worksheet("Sheet1")
        sh.del_worksheet(default)
    except gspread.exceptions.WorksheetNotFound:
        pass

    url = sh.url
    print(f"  Google Sheet URL: {url}")
    return url


# ─── Tab 1: 10+ Tag Report ──────────────────────────────────────────────────

def _build_report_sheet(sh: gspread.Spreadsheet, jobs: list[JobRecord]) -> None:
    ws = sh.add_worksheet("10+ Tag Report", rows=len(jobs) + 1, cols=len(REPORT_COLUMNS))

    # Prepare all data
    rows = [REPORT_COLUMNS]
    for job in jobs:
        rows.append([
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
        ])

    # Batch write all data
    ws.update(rows, "A1")
    print(f"  Wrote {len(jobs)} rows to '10+ Tag Report'")

    # ── Formatting via batch_format ──
    formats = []

    # Header row: blue background, white bold text, borders
    formats.append({
        "range": f"A1:{_col_letter(len(REPORT_COLUMNS))}1",
        "format": {
            "backgroundColor": HEADER_BG,
            "textFormat": {"foregroundColor": HEADER_FG, "bold": True, "fontSize": 11},
            "horizontalAlignment": "CENTER",
            "wrapStrategy": "WRAP",
            "borders": THIN_BORDER,
        },
    })

    # Data rows: white background, borders, vertical alignment TOP
    for i, job in enumerate(jobs):
        row_num = i + 2
        row_range = f"A{row_num}:{_col_letter(len(REPORT_COLUMNS))}{row_num}"

        formats.append({
            "range": row_range,
            "format": {
                "backgroundColor": WHITE_BG,
                "borders": THIN_BORDER,
                "verticalAlignment": "TOP",
                "wrapStrategy": "WRAP",
            },
        })

        # Only the 10+ Status cell (col J) gets colored + bold for "AI Added 10+"
        if job.ten_plus_status == "AI Added 10+":
            formats.append({
                "range": f"J{row_num}",
                "format": {
                    "backgroundColor": STATUS_CELL_BG,
                    "textFormat": {"bold": True},
                },
            })

    ws.batch_format(formats)

    # Auto-filter on header row
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

    # Freeze header row (only if there are data rows below)
    if len(jobs) > 0:
        ws.freeze(rows=1)

    # Set column widths
    _set_column_widths(ws, [
        80,   # Job ID
        200,  # Business Unit
        200,  # AI Job Type
        200,  # Dispatcher Job Type
        250,  # AI Tags
        250,  # Dispatcher Tags
        80,   # AI Has 10+
        80,   # Disp Has 10+
        80,   # Unknown Age
        120,  # 10+ Status
        250,  # Notes
    ])


# ─── Tab 2: Summary ─────────────────────────────────────────────────────────

def _build_summary_sheet(sh: gspread.Spreadsheet, jobs: list[JobRecord]) -> None:
    ws = sh.add_worksheet("Summary", rows=15, cols=2)

    missed = sum(1 for j in jobs if j.ten_plus_status == "AI Missed 10+")
    extra_unknown = sum(1 for j in jobs if j.ten_plus_status == "AI Added 10+" and j.unknown_age)
    extra_known = sum(1 for j in jobs if j.ten_plus_status == "AI Added 10+" and not j.unknown_age)
    matched = sum(1 for j in jobs if j.ten_plus_status == "Match")

    data = [
        ["10+ Tag Report Summary", ""],
        ["", ""],
        ["Category", "Count"],
        ["AI Missed 10+ (Dispatcher tagged, AI did not)", missed],
        ["AI Added 10+ — Unknown Age", extra_unknown],
        ["AI Added 10+ — Known Age", extra_known],
        ["Match (Both sides tagged 10+)", matched],
        ["", ""],
        ["Total Jobs with 10+ Tag", len(jobs)],
        ["", ""],
        ["Aging Logic Note:", ""],
        [
            '"Unknown Age" means the system could not determine equipment age. '
            "AI may tag 10+ based on other signals. These cases should be reviewed "
            "to determine if the 10+ tag is appropriate despite missing age data.",
            "",
        ],
    ]

    ws.update(data, "A1")

    formats = [
        # Borders on all summary data cells
        {"range": "A1:B12", "format": {"borders": THIN_BORDER, "verticalAlignment": "TOP", "wrapStrategy": "WRAP"}},
        # Title
        {"range": "A1", "format": {"textFormat": {"bold": True, "fontSize": 14}, "borders": THIN_BORDER}},
        # Header row
        {
            "range": "A3:B3",
            "format": {
                "backgroundColor": HEADER_BG,
                "textFormat": {"foregroundColor": HEADER_FG, "bold": True, "fontSize": 11},
                "borders": THIN_BORDER,
            },
        },
        # AI Missed = red
        {"range": "A4:B4", "format": {"backgroundColor": RED_BG, "borders": THIN_BORDER}},
        # AI Added = yellow
        {"range": "A5:B5", "format": {"backgroundColor": YELLOW_BG, "borders": THIN_BORDER}},
        {"range": "A6:B6", "format": {"backgroundColor": YELLOW_BG, "borders": THIN_BORDER}},
        # Match = green
        {"range": "A7:B7", "format": {"backgroundColor": GREEN_BG, "borders": THIN_BORDER}},
        # Note label
        {"range": "A11", "format": {"textFormat": {"bold": True, "italic": True}, "borders": THIN_BORDER}},
    ]

    ws.batch_format(formats)

    _set_column_widths(ws, [420, 100])

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
