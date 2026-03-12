# 10+ Automation Pipeline

Automates the AI Validation 10+ report workflow from ProBook and ServiceTitan. Built with Playwright browser automation, outputs formatted Excel reports.

## Overview

This tool automates what would otherwise be a manual, multi-hour process of:
1. Logging into ProBook admin dashboard
2. Building datasets and running AI Validation
3. Scraping the Jobs/Diffs results
4. Cross-referencing with ServiceTitan
5. Generating formatted Excel reports

## Project Structure

### Core Pipeline
| File | Purpose |
|------|---------|
| `scraper.py` | ProBook Playwright automation — login, dataset building, AI validation, diff scraping. Main engine. |
| `10plus_automation.py` | CLI entry point for **single-brand** 10+ tag reports |
| `report_generator.py` | Excel report generator — 10+ Tag Report, Summary, and QA tabs with color-coded rows |
| `recapture_report.py` | **Batch runner** for AI Val Recapture reports across multiple brands (e.g., all Midwest) |

### ROI Reports
| File | Purpose |
|------|---------|
| `roi_scraper.py` | ServiceTitan Playwright automation — Technician Performance & Timesheet report scraping |
| `roi_report.py` | Fills the ROI Excel template (`roi_template.xlsx`) with scraped data |
| `roi_template.xlsx` | Excel template with formulas for ROI/Drive Time calculations |

### Integrations
| File | Purpose |
|------|---------|
| `google_upload.py` | Upload reports to Google Drive as Google Sheets |
| `google_sheets.py` | Google Sheets API helper |
| `dashboard.py` | Dashboard functionality |

### Templates
| File | Purpose |
|------|---------|
| `templates/dashboard.html` | HTML dashboard template |
| `roi_template.xlsx` | ROI report Excel template (formulas pre-built) |

## Setup

```bash
# 1. Clone the repo
git clone https://github.com/DylanOliva45/10plus-automation.git
cd 10plus-automation

# 2. Create virtual environment
python3 -m venv venv
source venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Install Playwright browsers
playwright install chromium

# 5. Create .env file with credentials
cat > .env << 'EOF'
PROBOOK_USERNAME=your_email@example.com
PROBOOK_PASSWORD=your_password
EOF

# 6. (Optional) For Google Sheets upload, add google_credentials.json
#    from Google Cloud Console (OAuth 2.0 Client ID)
```

## Usage

### Single-Brand 10+ Report
```bash
python 10plus_automation.py \
    --customer "Dyess Air" \
    --start-date 2026-02-01 \
    --end-date 2026-02-28
```

Options:
- `--qa` — Run ServiceTitan QA phase on flagged jobs
- `--google-sheets` — Upload report to Google Drive
- `--no-interactive` — Skip manual pauses (uses timed waits)

### Midwest Batch Recapture Report
```bash
python recapture_report.py \
    --start-date 2026-02-01 \
    --end-date 2026-02-28
```

This runs all 16 Midwest brands and generates one master spreadsheet.

**Brands included:** AB May, Holt, ServiceOne, KB Complete, Air Services, Academy Morrison, Haley, Davison/Cregger, Meridian, Canfield, Hero, ASP, Swick, PRT, West Allis, Hockers

**Report criteria:**
- Missed 10+ Maintenances (excluding Service 10+ to Maintenance 10+ reclassifications)
- Missed 10+ Services
- Missed PL - Water Heater 8+

**QA filtering (no cheap wins):**
- Excludes First Time Customer / Unknown Age cases
- Excludes cases where dispatcher has a defensible position (e.g., summary said 5-10 years, DSR put 5-9, Validator said 10+)

**Output columns:** Date, Brand, CSR/DSR Verification Result, AI Validator Result, Reason for Change, Link to ST

Options:
- `--brands "AB May" "Holt"` — Run specific brands only
- `--no-interactive` — Skip manual pauses

### ROI Report
```bash
python roi_scraper.py  # Scrape ServiceTitan data
python roi_report.py   # Generate filled Excel template
```

## How It Works

### ProBook Scraper Flow (`scraper.py`)
1. **Launch** — Opens headed Chromium browser via Playwright
2. **Login** — Auto-login from `.env` credentials (falls back to manual)
3. **Select Customer** — Picks the org from the ProBook dashboard
4. **Navigate** — Audit > AI Validation > Dataset Builder
5. **Build Dataset** — Fills date range, creates dataset (waits up to 5 min)
6. **Run Validation** — Starts AI Validation, polls progress until 100% (up to 25 min)
7. **Scrape Diffs** — Goes to Jobs/Diffs Dashboard, infinite-scrolls to load all cards, bulk-extracts via DOM JS
8. **(Optional) QA** — Opens jobs in ServiceTitan, checks equipment/ages, screenshots

### Data Model
- `JobRecord` — One per job: contains AI prediction side and Dispatcher verified side
- `JobSide` — Business unit, job type, priority, tags, first call flag, arrival window
- Derived fields: `ai_has_10plus`, `disp_has_10plus`, `unknown_age`, `ten_plus_status`

### Recapture Report Logic (`recapture_report.py`)
- Categorizes diffs into: Missed 10+ Maintenance, Missed 10+ Service, Missed PL Water Heater 8+
- Filters out cheap wins: first-time customers, unknown age, defensible dispatcher positions
- Consolidates all brands into one master Excel with Summary tab

## Important Notes

- **Timing:** Each brand takes ~20-30 min (validation + diffs loading). Full 16-brand batch = ~6-8 hours.
- **Validation must hit 100%** before moving to diffs. The scraper polls and waits automatically.
- **Diffs page needs time to load** — the batch runner waits 15 min per brand for full load.
- **Browser is headed** (not headless) — you can see what it's doing and intervene if needed.
- **Interruption safe** — Ctrl+C generates a partial report with whatever was collected. JSON backups saved per brand.
- **No secrets in repo** — `.env`, `google_credentials.json`, and `google_token.json` are gitignored.

## Dependencies

- Python 3.9+
- Playwright (Chromium)
- openpyxl (Excel generation)
- python-dotenv (credential management)
- gspread + google-auth (Google Sheets integration)
