"""
Shared helpers + standalone dataset puller for the SEO/AEO-hiring pipeline.

Scrapes Indeed JOB POSTINGS (via the `valig/indeed-jobs-scraper` actor) for
US companies actively hiring an IN-HOUSE SEO / organic / AEO (answer-engine /
generative-engine optimisation) role. An open in-house SEO/AEO req is the
high-intent signal for PN Digital's displacement pitch (a programme that ALSO
wins AI-search visibility, for less than the loaded cost of that one hire).

`scrape_and_pull.py` imports the helpers here; this file can also be run
directly against an existing Apify dataset.

Column layout (32 cols):
  Job Info    A-J: Job_Id, Job Title, Job Type, Occupations, Date Published,
                   Salary Min, Salary Max, Salary Period, Apply URL, Job Description
  Company     K-Q: Company Name, Company Website, Company Size, Revenue,
                   CEO Name, Company Description, Benefits
  Location    R-S: City, State
  Outreach    T-AA: DM Name, DM Title, LinkedIn URL, Email,
                    First Name, Last Name, Email Body, Added to Instantly
  Derived     AB-AF: Role Type, Indeed URL, Tier, Employer Type, ICP Fit

Auth: reads token.json + .env from the AIOS project root (4 levels up), so the
scripts work regardless of the current working directory.
"""

import os
import re
import json
import time
import argparse
import requests
from datetime import date
from urllib.parse import urlparse
from dotenv import load_dotenv
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "..", "..", ".."))
ENV_PATH = os.path.join(PROJECT_ROOT, ".env")
TOKEN_PATH = os.path.join(PROJECT_ROOT, "token.json")
load_dotenv(ENV_PATH)

APIFY_API_TOKEN = os.getenv("APIFY_API_TOKEN")
APIFY_BASE = "https://api.apify.com/v2/datasets"
APIFY_PAGE_SIZE = 1000

BATCH_SIZE = 10
TAB_NAME = "Leads"
SHEET_TITLE = "SEO/AEO-Hiring Leads — Indeed"

HEADERS = [
    # Job Info (A-J)
    "Job_Id",              # A
    "Job Title",           # B
    "Job Type",            # C
    "Occupations",         # D
    "Date Published",      # E
    "Salary Min",          # F
    "Salary Max",          # G
    "Salary Period",       # H
    "Apply URL",           # I
    "Job Description",     # J
    # Company (K-Q)
    "Company Name",        # K
    "Company Website",     # L
    "Company Size",        # M
    "Revenue",             # N
    "CEO Name",            # O
    "Company Description", # P
    "Benefits",            # Q
    # Location (R-S)
    "City",                # R
    "State",               # S
    # Outreach (T-AA) — blank, filled by downstream phase-2 enrichment
    "DM Name",             # T
    "DM Title",            # U
    "LinkedIn URL",        # V
    "Email",               # W
    "First Name",          # X
    "Last Name",           # Y
    "Email Body",          # Z
    "Added to Instantly",  # AA
    # Derived columns
    "Role Type",           # AB — AEO/GEO / SEO / Organic Growth / Content (from title)
    "Indeed URL",          # AC — https://www.indeed.com/viewjob?jk={Job_Id}
    "Tier",                # AD — A (AI-search-aware) / B (traditional SEO), from title+desc
    "Employer Type",       # AE — TARGET / AGENCY / OFF_TARGET (filled by classify_companies.py)
    "ICP Fit",             # AF — b2b_saas / multi_location_services / other (filled by classify)
]

# --- Title-relevance gate (deterministic; applied at ingestion) --------------
# Indeed's `title` search broad-matches the whole posting, so most rows aren't
# real SEO roles. Keep only postings whose TITLE signals SEO/organic/AEO
# ownership. High precision; the LLM step then judges agency-vs-end-company.
TITLE_RELEVANCE_RE = re.compile(
    r"\bseo\b|organic|\baeo\b|\bgeo\b|search engine|search marketing|\bsem\b|"
    r"generative engine|answer engine",
    re.IGNORECASE,
)

# UNAMBIGUOUS leadership titles — dropped at INGEST so they never reach the
# sheet (a "Head of SEO" / "Director of SEO" / "VP" is never a hands-on
# executor). Bare "manager" / "lead" / "principal" are NOT dropped here — a solo
# one can be an IC, so classify_companies.py's LLM judges those from the
# description. (classify also re-checks these as a backstop.)
INGEST_LEADERSHIP_RE = re.compile(
    r"\bvp\b|\bsvp\b|\bevp\b|\bavp\b|\bvice president\b|\bdirector\b|\bhead of\b|"
    r"\bhead\b|\bchief\b|\bcro\b|\bcmo\b|\bceo\b|\bcoo\b|\bpresident\b|\bteam lead(er)?\b",
    re.IGNORECASE,
)


def title_is_relevant(job_title):
    """Keep SEO/organic/AEO-relevant titles, minus unambiguous leadership.
    Relevant AND not obvious-leadership. The nuanced IC-vs-manager call (bare
    'Manager'/'Lead', or a 'Specialist' who really manages a team) is left to
    classify_companies.py's LLM, which reads the job description."""
    t = job_title or ""
    if INGEST_LEADERSHIP_RE.search(t):
        return False
    return bool(TITLE_RELEVANCE_RE.search(t))


# --- AI-search / AEO signal (decides Tier A vs B on title + description) ------
# Strong, low-false-positive signals only. Bare "geo" is EXCLUDED on purpose:
# in an SEO job description it almost always means geographic/local SEO.
AI_SIGNAL_PATTERNS = [
    r"\baeo\b",
    r"answer engine",
    r"generative engine",
    r"generative search",
    r"\bai[\s\-]?search\b",
    r"ai overview",
    r"ai[\s\-]?powered search",
    r"\bchatgpt\b",
    r"\bperplexity\b",
    r"google gemini",
    r"search generative experience",
    r"\bsge\b",
    r"\bllm\b",
    r"large language model",
]
_AI_SIGNAL_RE = re.compile("|".join(AI_SIGNAL_PATTERNS), re.IGNORECASE)


def classify_tier(job_title, description):
    """Tier A if any AI-search/AEO signal in title or description, else Tier B."""
    blob = f"{job_title or ''}\n{description or ''}"
    return "A" if _AI_SIGNAL_RE.search(blob) else "B"


def classify_role_type(job_title):
    """Coarse role label from the job title (title gate guarantees a match)."""
    t = (job_title or "").lower().strip()
    if not t:
        return ""
    if re.search(r"\baeo\b|\bgeo\b|answer engine|generative engine", t):
        return "AEO/GEO"
    if "organic" in t:
        return "Organic Growth"
    if re.search(r"\bseo\b|search engine|search marketing|\bsem\b", t):
        return "SEO"
    if "content" in t:
        return "Content"
    return "SEO"


def get_sheet_id_from_url(url):
    parsed = urlparse(url)
    if "docs.google.com" in parsed.netloc:
        parts = parsed.path.split("/")
        if "d" in parts:
            return parts[parts.index("d") + 1]
    return url


def get_google_service():
    with open(TOKEN_PATH) as f:
        token_data = json.load(f)
    creds = Credentials(
        token=token_data["token"],
        refresh_token=token_data["refresh_token"],
        token_uri=token_data["token_uri"],
        client_id=token_data["client_id"],
        client_secret=token_data["client_secret"],
        scopes=token_data.get("scopes", ["https://www.googleapis.com/auth/spreadsheets"]),
    )
    if creds.expired:
        creds.refresh(Request())
        token_data["token"] = creds.token
        with open(TOKEN_PATH, "w") as f:
            json.dump(token_data, f)
    return build("sheets", "v4", credentials=creds)


def create_sheet(service, title):
    resp = service.spreadsheets().create(
        body={"properties": {"title": title}},
        fields="spreadsheetId",
    ).execute()
    sheet_id = resp["spreadsheetId"]
    print(f"  Created: https://docs.google.com/spreadsheets/d/{sheet_id}/edit")
    return sheet_id


def setup_tab(service, sheet_id):
    meta = service.spreadsheets().get(spreadsheetId=sheet_id).execute()
    default_sheet_id = meta["sheets"][0]["properties"]["sheetId"]
    default_title = meta["sheets"][0]["properties"]["title"]

    if default_title != TAB_NAME:
        service.spreadsheets().batchUpdate(
            spreadsheetId=sheet_id,
            body={"requests": [{"updateSheetProperties": {
                "properties": {"sheetId": default_sheet_id, "title": TAB_NAME},
                "fields": "title",
            }}]},
        ).execute()

    # Pre-size the grid and pin 18px rows — appends keep the pinned height
    # when they land inside the existing grid (project convention: 18px rows)
    service.spreadsheets().batchUpdate(
        spreadsheetId=sheet_id,
        body={"requests": [
            {"updateSheetProperties": {
                "properties": {"sheetId": default_sheet_id,
                               "gridProperties": {"rowCount": 30000}},
                "fields": "gridProperties.rowCount",
            }},
            {"updateDimensionProperties": {
                "range": {"sheetId": default_sheet_id, "dimension": "ROWS",
                          "startIndex": 0, "endIndex": 30000},
                "properties": {"pixelSize": 18},
                "fields": "pixelSize",
            }},
        ]},
    ).execute()

    service.spreadsheets().values().update(
        spreadsheetId=sheet_id,
        range=f"'{TAB_NAME}'!A1",
        valueInputOption="RAW",
        body={"values": [HEADERS]},
    ).execute()
    print(f"  Headers written ({len(HEADERS)} columns)")


def fetch_dataset(dataset_id):
    all_items = []
    offset = 0
    while True:
        resp = requests.get(
            f"{APIFY_BASE}/{dataset_id}/items",
            params={"token": APIFY_API_TOKEN, "format": "json",
                    "limit": APIFY_PAGE_SIZE, "offset": offset},
            timeout=60,
        )
        if resp.status_code != 200:
            print(f"  ERROR (offset={offset}): HTTP {resp.status_code}")
            break
        items = resp.json()
        if not items:
            break
        all_items.extend(items)
        print(f"  Fetched {len(all_items)}...", end="\r")
        if len(items) < APIFY_PAGE_SIZE:
            break
        offset += APIFY_PAGE_SIZE
    print(f"  Fetched {len(all_items)} total items    ")
    return all_items


def parse_iso_date_safe(s):
    """Parse an ISO date prefix (YYYY-MM-DD) to a date, or None."""
    if not s:
        return None
    try:
        return date.fromisoformat(str(s)[:10])
    except (ValueError, TypeError):
        return None


def fmt_salary(val):
    if val is None:
        return ""
    try:
        return str(int(round(float(val))))
    except (ValueError, TypeError):
        return str(val)


def map_to_row(item):
    emp = item.get("employer") or {}
    loc = item.get("location") or {}
    sal = item.get("baseSalary") or {}
    desc_obj = item.get("description") or {}
    job_types = item.get("jobTypes") or {}
    occupations = item.get("occupations") or {}
    benefits = item.get("benefits") or {}

    title = item.get("title", "")
    job_type = ", ".join(v for v in job_types.values() if v) if isinstance(job_types, dict) else str(job_types)
    occ_str = ", ".join(v for v in occupations.values() if v) if isinstance(occupations, dict) else str(occupations)
    date_raw = item.get("datePublished") or ""
    date_str = date_raw[:10] if date_raw else ""
    sal_min = fmt_salary(sal.get("min"))
    sal_max = fmt_salary(sal.get("max"))
    sal_unit = (sal.get("unitOfWork") or "").upper()
    description = (desc_obj.get("text") or "") if isinstance(desc_obj, dict) else str(desc_obj)
    benefits_str = ", ".join(list(benefits.values())[:8]) if isinstance(benefits, dict) else str(benefits)
    key = item.get("key", "")

    return [
        # Job Info (A-J)
        key,
        title,
        job_type,
        occ_str,
        date_str,
        sal_min,
        sal_max,
        sal_unit,
        item.get("jobUrl", ""),
        description,
        # Company (K-Q)
        emp.get("name", ""),
        emp.get("corporateWebsite", ""),
        emp.get("employeesCount", "") if isinstance(emp.get("employeesCount"), str) else str(emp.get("employeesCount", "")),
        emp.get("revenue", ""),
        emp.get("ceoName", ""),
        emp.get("briefDescription", ""),
        benefits_str,
        # Location (R-S)
        loc.get("city", ""),
        loc.get("admin1Code", ""),
        # Outreach (T-AA) — blank
        "", "", "", "", "", "", "", "",
        # Role Type (AB), Indeed URL (AC), Tier (AD) — derived
        classify_role_type(title),
        f"https://www.indeed.com/viewjob?jk={key}" if key else "",
        classify_tier(title, description),
        # Employer Type (AE), ICP Fit (AF) — blank until classify_companies.py
        "", "",
    ]


def write_rows(service, sheet_id, rows):
    total = len(rows)
    for i in range(0, total, BATCH_SIZE):
        batch = rows[i:i + BATCH_SIZE]
        service.spreadsheets().values().append(
            spreadsheetId=sheet_id,
            range=f"'{TAB_NAME}'!A1",
            valueInputOption="RAW",
            insertDataOption="INSERT_ROWS",
            body={"values": batch},
        ).execute()
        print(f"  Written {min(i + BATCH_SIZE, total)}/{total} rows...", end="\r")
        time.sleep(1.5)
    print(f"  Written {total} rows total.          ")


def main():
    parser = argparse.ArgumentParser(description="Pull Apify Indeed dataset → Google Sheet (SEO/AEO)")
    parser.add_argument("--dataset_id", required=True, help="Apify dataset ID")
    parser.add_argument("--sheet_url", help="Existing Google Sheet URL to append to")
    parser.add_argument("--sheet_title", default=SHEET_TITLE, help="Title for new sheet (ignored if --sheet_url)")
    parser.add_argument("--limit", type=int, default=0, help="Max items to pull (0 = all)")
    args = parser.parse_args()

    if not APIFY_API_TOKEN:
        print("ERROR: APIFY_API_TOKEN not set in .env")
        return

    print("=== Pull Apify Dataset → Google Sheet (SEO/AEO) ===\n")
    service = get_google_service()

    if args.sheet_url:
        sheet_id = get_sheet_id_from_url(args.sheet_url)
        print(f"  Using existing sheet: {sheet_id}")
    else:
        print("[1/3] Creating Google Sheet...")
        sheet_id = create_sheet(service, args.sheet_title)
        setup_tab(service, sheet_id)

    print(f"\n[2/3] Fetching dataset {args.dataset_id}...")
    items = fetch_dataset(args.dataset_id)

    skipped_no_company = 0
    skipped_off_title = 0
    rows = []
    for item in items:
        emp = item.get("employer") or {}
        if not (emp.get("name") or "").strip():
            skipped_no_company += 1
            continue
        if not title_is_relevant(item.get("title", "")):
            skipped_off_title += 1
            continue
        rows.append(map_to_row(item))
        if args.limit > 0 and len(rows) >= args.limit:
            break

    print(f"  Skipped (no company name): {skipped_no_company}")
    print(f"  Skipped (off-title):       {skipped_off_title}")
    print(f"  Kept: {len(rows)}")

    print(f"\n[3/3] Writing {len(rows)} rows...")
    if rows:
        write_rows(service, sheet_id, rows)
    else:
        print("  No rows to write.")

    sheet_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/edit"
    print(f"\n=== Done ===")
    print(f"Sheet:  {sheet_url}")
    print(f"Rows:   {len(rows)}")


if __name__ == "__main__":
    main()
