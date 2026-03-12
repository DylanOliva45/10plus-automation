"""Upload Excel report to Google Drive as a Google Sheet."""

from __future__ import annotations

import os
from pathlib import Path

import gspread
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
]

TOKEN_PATH = Path(__file__).parent / "google_token.json"
CREDS_PATH = Path(__file__).parent / "google_credentials.json"


def get_gspread_client() -> gspread.Client:
    """Authenticate and return a gspread client.

    First run: opens browser for OAuth2 consent.
    Subsequent runs: uses saved token.
    """
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


def upload_to_google_sheets(xlsx_path: str, folder_id: str | None = None) -> str:
    """Upload an Excel file to Google Drive as a Google Sheet.

    Args:
        xlsx_path: Path to the .xlsx file.
        folder_id: Optional Google Drive folder ID to upload into.

    Returns:
        URL of the created Google Sheet.
    """
    client = get_gspread_client()
    spreadsheet = client.import_spreadsheet(xlsx_path, folder_id=folder_id)
    url = spreadsheet.url
    print(f"Uploaded to Google Sheets: {url}")
    return url
