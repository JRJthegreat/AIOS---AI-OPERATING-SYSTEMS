"""
Phase 2: Keep ONLY rows where a B2B company is hiring an individual-contributor
(frontline) sales/BD rep. Everything else is dropped.

This runs PER ROW (per posting), not per company — because seniority is a
property of the posting. A company can post both an "SDR" (keep) and a "Sales
Manager" (drop); judging at the company level would mishandle that.

Three layers:
  1. Title regex (free, no LLM) — drops unambiguous LEADERSHIP titles
     (VP / Director / Head of / Chief / President...). "Manager" alone is NOT
     auto-dropped (Territory/Account/BDM managers are often ICs) — the LLM judges those.
  2. Company-name regex (free) — drops unambiguous recruiting-agency names.
  3. Azure OpenAI (gpt-4.1) — judges the rest into:
     TARGET (keep), AGENCY, MANAGER, B2C, OFF_TARGET, UNCERTAIN (all drop but TARGET).

Buckets:
  - TARGET            B2B direct employer hiring an IC sales/BD rep            [KEEP]
  - recruiting_agency staffing / recruiting / RPO posting for a client        [DROP]
  - manager_role      people-management / sales-leadership role               [DROP]
  - b2c_company       company sells primarily to consumers                    [DROP]
  - off_target_role   B2B employer but the role isn't sales                   [DROP]
  - uncertain         not enough evidence                                     [DROP]

Usage:
  python3 classify_companies.py --sheet_url "URL"            # dry run (report only)
  python3 classify_companies.py --sheet_url "URL" --apply    # delete non-TARGET rows
"""

import os
import re
import sys
import json
import time
import argparse
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed

from openai import AzureOpenAI
from dotenv import load_dotenv
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "..", "..", ".."))
ENV_PATH = os.path.join(PROJECT_ROOT, ".env")
TOKEN_PATH = os.path.join(PROJECT_ROOT, "token.json")
load_dotenv(ENV_PATH)

AZURE_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_API_KEY = os.getenv("AZURE_OPENAI_API_KEY")
AZURE_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION", "2024-10-21")
MODEL = os.getenv("AZURE_OPENAI_DEPLOYMENT_FAST", "gpt-4.1")
LLM_WORKERS = 8

TAB_NAME = "Leads"
COL_JOB_TITLE = 1      # B
COL_JOB_DESC = 9       # J
COL_COMPANY_NAME = 10  # K
COL_COMPANY_DESC = 15  # P

KEEP_CATEGORY = "target"
DROP_CATEGORIES = {"recruiting_agency", "manager_role", "account_exec", "b2c_company", "commission_only", "off_target_role", "uncertain"}
ALL_CATEGORIES = ["target", "recruiting_agency", "manager_role", "account_exec", "b2c_company", "commission_only", "off_target_role", "uncertain"]

# Layer 1 — unambiguous LEADERSHIP titles (never an IC rep). Safe to auto-drop.
# "Manager" alone is intentionally excluded (Territory/Account/Business-Dev
# managers are frequently ICs) — handed to the LLM instead.
MANAGER_TITLE_PATTERNS = [
    r"\bvp\b", r"\bv\.p\.\b", r"\bvice president\b", r"\bsvp\b", r"\bevp\b", r"\bavp\b",
    r"\bdirector\b", r"\bhead of\b", r"\bchief\b",
    r"\bcro\b", r"\bcso\b", r"\bcmo\b", r"\bceo\b", r"\bpresident\b",
]
_MANAGER_RE = re.compile("|".join(MANAGER_TITLE_PATTERNS), re.IGNORECASE)

# Layer 2 — unambiguous agency names. Ambiguous terms (talent, workforce,
# personnel) are left OUT and handed to the LLM to avoid false positives.
AGENCY_NAME_PATTERNS = [
    r"\bstaffing\b",
    r"\brecruit(ing|ment|ers?)?\b",
    r"\bheadhunt\w*\b",
    r"\brpo\b",
    r"\blocum\b",
    r"\bsearch partners?\b",
    r"\bsearch group\b",
    r"\bexecutive search\b",
    r"\btemp agency\b",
    r"\bemployment agency\b",
    r"\bstaffing solutions\b",
]
_AGENCY_RE = re.compile("|".join(AGENCY_NAME_PATTERNS), re.IGNORECASE)

# Commission-only / 1099 / freelance signals in the title. "Commission" alone is
# NOT flagged (most B2B roles are base + commission) — only no-base markers.
COMMISSION_TITLE_PATTERNS = [
    r"\b1099\b",
    r"\bfreelance\b",
    r"\bindependent contractor\b",
    r"\bindependent sales\b",
    r"100\s*%\s*commission",
    r"commission[\s-]*based[\s-]*only",
    r"commission[\s-]*only",
    r"commission.{0,12}only",
]
_COMMISSION_RE = re.compile("|".join(COMMISSION_TITLE_PATTERNS), re.IGNORECASE)

# Account Executive / account-management titles — dropped per spec (we want
# frontline prospecting reps, not closers/farmers). "Account Manager" is left to
# the LLM (can be an IC hunter in some shops).
ACCOUNT_EXEC_TITLE_PATTERNS = [
    r"\baccount executive\b",
    r"\baccount exec\b",
]
_ACCOUNT_EXEC_RE = re.compile("|".join(ACCOUNT_EXEC_TITLE_PATTERNS), re.IGNORECASE)


def looks_like_leadership_title(title):
    return bool(_MANAGER_RE.search(title or ""))


def looks_like_agency_name(name):
    return bool(_AGENCY_RE.search(name or ""))


def looks_like_commission_only(title):
    return bool(_COMMISSION_RE.search(title or ""))


def looks_like_account_exec(title):
    return bool(_ACCOUNT_EXEC_RE.search(title or ""))


# --- Google Sheets ---

def get_sheet_id_from_url(url):
    parsed = urlparse(url)
    if "docs.google.com" in parsed.netloc:
        parts = parsed.path.split("/")
        if "d" in parts:
            return parts[parts.index("d") + 1]
    return url


def get_service():
    with open(TOKEN_PATH) as f:
        td = json.load(f)
    creds = Credentials(
        token=td["token"], refresh_token=td["refresh_token"],
        token_uri=td["token_uri"], client_id=td["client_id"], client_secret=td["client_secret"],
        scopes=td.get("scopes", ["https://www.googleapis.com/auth/spreadsheets"]),
    )
    if creds.expired:
        creds.refresh(Request())
        td["token"] = creds.token
        with open(TOKEN_PATH, "w") as f:
            json.dump(td, f)
    return build("sheets", "v4", credentials=creds)


def get_tab_sheet_id(service, spreadsheet_id, tab_name):
    meta = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    for s in meta["sheets"]:
        if s["properties"]["title"] == tab_name:
            return s["properties"]["sheetId"]
    raise RuntimeError(f"Tab {tab_name!r} not found")


# --- LLM classification ---

CLASSIFY_PROMPT = """You classify a US job posting from Indeed into ONE category. We want a B2B company (one that sells primarily to OTHER BUSINESSES) hiring an INDIVIDUAL-CONTRIBUTOR rep to do new-business sales.

TARGET = KEEP. BOTH must hold: (1) the COMPANY sells primarily to other businesses — SaaS/software, manufacturing, wholesale/distribution, logistics, industrial/equipment, commercial services, or B2B financial/medical/professional services; AND (2) the role is an IC frontline sales/BD rep — SDR, BDR, Business Development Rep, Outside/Inside/Territory/B2B Sales Rep — salaried (base, with or without commission), not a manager, not an Account Executive/account manager.

AGENCY = DROP. Staffing/recruiting/RPO/headhunter/job-placement company posting on behalf of a client or to build its own candidate roster.

MANAGER = DROP. People-management or sales-leadership: manages/leads a team, has direct reports, hires/coaches reps, or is a Sales Manager / Director / Head of Sales / VP / Chief.

ACCOUNT_EXEC = DROP. Account Executive, Account Manager, or any role focused on closing or managing/retaining existing accounts rather than frontline new-business prospecting.

B2C = DROP. The COMPANY sells primarily to CONSUMERS — drop regardless of the role title. Includes: retail, residential home services (lawn care, pools, roofing, HVAC, windows, remodeling/construction for homeowners, solar/pest control to homeowners), consumer insurance, residential real estate / mortgage, auto dealerships, gyms/fitness, restaurants/hospitality, home health / consumer healthcare, education-to-consumers, and DTC/consumer brands. If you can't tell who the company sells to but the role is door-to-door / in-home / residential, treat it as B2C.

COMMISSION_ONLY = DROP. No base salary — 100% commission, commission-only, draw-against-commission with no real base, 1099 independent contractor, or freelance sales.

OFF_TARGET = DROP. Not a frontline sales rep — customer/member service, call center, client success/retention, marketing / "marketer" / community liaison, sales support / sales coordinator / sales administrator, operations, legal, product.

UNCERTAIN = DROP. Use ONLY when you genuinely cannot tell whether the company is B2B and the role is an IC sales rep.

Choose TARGET only when it plausibly looks like a B2B company hiring an IC sales rep. When the company looks consumer-facing, choose B2C.

Company: {company}
Job title: {job_title}
{company_desc_block}Job description (first 800 chars):
{job_desc}

Respond with ONLY one word: TARGET, AGENCY, MANAGER, ACCOUNT_EXEC, B2C, COMMISSION_ONLY, OFF_TARGET, or UNCERTAIN"""


def parse_classification(text):
    t = (text or "").strip().upper()
    if "AGENCY" in t:
        return "recruiting_agency"
    if "ACCOUNT_EXEC" in t or "ACCOUNT EXEC" in t or "ACCOUNTEXEC" in t:
        return "account_exec"
    if "MANAGER" in t or "MANAGEMENT" in t:
        return "manager_role"
    if "B2C" in t or "CONSUMER" in t:
        return "b2c_company"
    if "COMMISSION" in t:
        return "commission_only"
    if "OFF_TARGET" in t or "OFF TARGET" in t or "OFFTARGET" in t:
        return "off_target_role"
    if "TARGET" in t:  # checked after OFF_TARGET (substring)
        return "target"
    return "uncertain"


def classify_one(client, company, job_title, job_desc, company_desc):
    """Single Azure OpenAI call → classification string. Retries on 429."""
    company_desc_block = f"Company description: {company_desc}\n" if company_desc else ""
    prompt = CLASSIFY_PROMPT.format(
        company=company,
        job_title=job_title or "(unknown)",
        company_desc_block=company_desc_block,
        job_desc=(job_desc[:800] if job_desc else "(not available)"),
    )
    for attempt in range(6):
        try:
            resp = client.chat.completions.create(
                model=MODEL,
                max_tokens=10,
                temperature=0,
                messages=[{"role": "user", "content": prompt}],
            )
            return parse_classification(resp.choices[0].message.content)
        except Exception as e:
            if "429" in str(e) or "Too Many Requests" in str(e):
                time.sleep(2 ** attempt)
                continue
            return "uncertain"
    return "uncertain"


def classify_keys_with_llm(keys, key_data):
    """Classify unique (company, title) keys concurrently. Returns {key: classification}."""
    client = AzureOpenAI(
        azure_endpoint=AZURE_ENDPOINT,
        api_key=AZURE_API_KEY,
        api_version=AZURE_API_VERSION,
    )
    print(f"Classifying {len(keys)} unique company+role pairs with {MODEL} ({LLM_WORKERS} workers)...")

    def run(key):
        d = key_data[key]
        return key, classify_one(client, d["company"], d["title"], d["job_desc"], d["company_desc"])

    out = {}
    with ThreadPoolExecutor(max_workers=LLM_WORKERS) as ex:
        futures = [ex.submit(run, k) for k in keys]
        for i, fut in enumerate(as_completed(futures), 1):
            key, cls = fut.result()
            out[key] = cls
            if i % 25 == 0 or i == len(keys):
                print(f"  Classified {i}/{len(keys)}")
    return out


# --- Main ---

def main():
    parser = argparse.ArgumentParser(description="Keep only B2B companies hiring IC sales reps; drop agencies/managers/B2C/off-target")
    parser.add_argument("--sheet_url", required=True)
    parser.add_argument("--apply", action="store_true", help="Delete every row that isn't TARGET")
    parser.add_argument("--limit", type=int, default=0, help="Only classify first N rows (debug)")
    args = parser.parse_args()

    if not (AZURE_ENDPOINT and AZURE_API_KEY):
        print("ERROR: AZURE_OPENAI_ENDPOINT / AZURE_OPENAI_API_KEY not set in .env")
        sys.exit(1)

    spreadsheet_id = get_sheet_id_from_url(args.sheet_url)
    service = get_service()
    tab_sheet_id = get_tab_sheet_id(service, spreadsheet_id, TAB_NAME)

    print("=== Classify rows: B2B + IC sales rep only ===")
    print(f"Sheet: {spreadsheet_id}")
    print(f"Model: {MODEL}")
    print(f"Mode:  {'APPLY (will delete rows)' if args.apply else 'DRY RUN'}\n")

    rows = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id, range=f"{TAB_NAME}!A2:AC50000"
    ).execute().get("values", [])
    if args.limit:
        rows = rows[:args.limit]
    print(f"Total rows: {len(rows)}")

    def safe_get(row, idx):
        return row[idx].strip() if len(row) > idx and row[idx] else ""

    # Build per-row records keyed by (company, title) so identical postings are
    # classified once. company/agency signals + role seniority both live here.
    row_meta = {}          # sheet_row -> {company, title, key}
    key_to_rows = {}       # key -> [sheet_row, ...]
    key_data = {}          # key -> representative {company, title, job_desc, company_desc}
    for i, r in enumerate(rows):
        sheet_row = i + 2
        company = safe_get(r, COL_COMPANY_NAME)
        if not company:
            continue
        title = safe_get(r, COL_JOB_TITLE)
        key = (company.lower(), title.lower())
        row_meta[sheet_row] = {"company": company, "title": title, "key": key}
        key_to_rows.setdefault(key, []).append(sheet_row)
        if key not in key_data:
            key_data[key] = {
                "company": company,
                "title": title,
                "job_desc": safe_get(r, COL_JOB_DESC),
                "company_desc": safe_get(r, COL_COMPANY_DESC),
            }

    keys = list(key_data.keys())
    print(f"Unique company+role pairs: {len(keys)}")

    # Layer 1 (title) + Layer 2 (company name) — free, deterministic
    classifications = {}
    needs_llm = []
    n_leader = n_commission = n_ae = n_agency = 0
    for key in keys:
        company, title = key_data[key]["company"], key_data[key]["title"]
        if looks_like_leadership_title(title):
            classifications[key] = "manager_role"
            n_leader += 1
        elif looks_like_account_exec(title):
            classifications[key] = "account_exec"
            n_ae += 1
        elif looks_like_commission_only(title):
            classifications[key] = "commission_only"
            n_commission += 1
        elif looks_like_agency_name(company):
            classifications[key] = "recruiting_agency"
            n_agency += 1
        else:
            needs_llm.append(key)
    print(f"  Leadership title (regex):    {n_leader}")
    print(f"  Account Exec title (regex):  {n_ae}")
    print(f"  Commission-only (regex):     {n_commission}")
    print(f"  Agency name (regex):         {n_agency}")
    print(f"  Sent to LLM:                 {len(needs_llm)}\n")

    # Layer 3 — LLM for the rest
    if needs_llm:
        classifications.update(classify_keys_with_llm(needs_llm, key_data))

    # Tally per row
    rows_by_class = {cat: [] for cat in ALL_CATEGORIES}
    for sheet_row, meta in row_meta.items():
        cls = classifications.get(meta["key"], "uncertain")
        if cls not in rows_by_class:
            cls = "uncertain"
        rows_by_class[cls].append(sheet_row)

    print("\n=== Report (by row) ===")
    for cls in ALL_CATEGORIES:
        srows = sorted(rows_by_class[cls])
        label = "KEEP" if cls == KEEP_CATEGORY else "DROP"
        print(f"\n{cls.upper()} [{label}]: {len(srows)} rows")
        sample = [r for r in srows][:30]
        for sr in sample:
            m = row_meta[sr]
            print(f"  {m['company'][:38]:38s} | {m['title'][:40]}")
        if len(srows) > 30:
            print(f"  ... and {len(srows) - 30} more")

    if not args.apply:
        print("\n[DRY RUN] No changes made. Re-run with --apply to delete every non-TARGET row.")
        return

    to_delete = sorted(
        [sr for sr, m in row_meta.items()
         if classifications.get(m["key"], "uncertain") in DROP_CATEGORIES],
        reverse=True,
    )
    if not to_delete:
        print("\nNo rows to delete.")
        print("=== Done ===")
        return

    print(f"\nDeleting {len(to_delete)} non-TARGET rows (bottom-up)...")
    requests_body = [
        {"deleteDimension": {"range": {
            "sheetId": tab_sheet_id, "dimension": "ROWS",
            "startIndex": r - 1, "endIndex": r,
        }}}
        for r in to_delete
    ]
    BATCH = 100
    for i in range(0, len(requests_body), BATCH):
        service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={"requests": requests_body[i:i + BATCH]},
        ).execute()
        print(f"  Deleted chunk {i // BATCH + 1}/{(len(requests_body) + BATCH - 1) // BATCH}")

    remaining = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id, range=f"{TAB_NAME}!A2:A50000"
    ).execute()
    print(f"\nRows remaining (TARGET): {len(remaining.get('values', []))}")
    print("=== Done ===")


if __name__ == "__main__":
    main()
