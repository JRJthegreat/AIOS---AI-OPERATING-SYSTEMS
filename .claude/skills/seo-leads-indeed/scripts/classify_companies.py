"""
Phase 2: Keep ONLY rows where a real END company is hiring a hands-on,
individual-contributor SEO / organic / AEO EXECUTOR — then ICP-tag those. Drop
everything else.

Runs PER ROW (per posting), not per company — seniority is a property of the
posting. A company can post both an "SEO Specialist" (keep) and a "Head of SEO"
(drop); judging per company would mishandle that.

Why the LLM owns seniority (not a title regex): a title regex can't tell a solo
"SEO Manager" who actually executes from one who leads a team. The LLM reads the
description and decides. The regex only fast-paths UNAMBIGUOUS leadership
(VP/Director/Head/Chief/Team Lead) to save LLM calls.

Three layers:
  1. Title regex (free) — drops unambiguous LEADERSHIP titles. Bare "Manager" /
     "Lead" / "Principal" are NOT auto-dropped (a solo IC can carry those) —
     handed to the LLM.
  2. Company-name regex (free) — drops unambiguous staffing/recruiting names.
  3. Azure OpenAI (gpt-4.1, temp 0) — judges the rest into TARGET / AGENCY /
     MANAGER / OFF_TARGET / UNCERTAIN, plus an ICP tag for TARGET.

Buckets:
  - target            end company hiring a hands-on IC SEO/AEO executor   [KEEP + ICP tag]
  - recruiting_agency staffing/recruiting OR SEO/marketing agency         [DROP]
  - manager_role      people-management / strategic-leadership role       [DROP]
  - off_target_role   end employer but role isn't SEO/organic/AEO exec    [DROP]
  - uncertain         not enough evidence                                 [DROP]

Per agreed approach all ICP types are KEPT (b2b_saas / multi_location_services /
other) — the ICP tag is for send prioritisation, not a drop reason.

Usage:
  python3 classify_companies.py --sheet_url "URL"            # dry run (report only)
  python3 classify_companies.py --sheet_url "URL" --apply    # tag TARGET + delete the rest
"""

import os
import re
import sys
import time
import json
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
COL_JOB_TITLE = 1       # B
COL_JOB_DESC = 9        # J
COL_COMPANY_NAME = 10   # K
COL_COMPANY_DESC = 15   # P
EMPLOYER_TYPE_A1 = "AE"
ICP_A1 = "AF"

KEEP_CATEGORY = "target"
DROP_CATEGORIES = {"recruiting_agency", "manager_role", "off_target_role", "uncertain"}
ALL_CATEGORIES = ["target", "recruiting_agency", "manager_role", "off_target_role", "uncertain"]

# Layer 1 — UNAMBIGUOUS leadership titles (never a hands-on IC). Safe to auto-drop.
# Bare "manager" / "lead" / "principal" are intentionally EXCLUDED: a solo SEO
# Manager or a Principal SEO can be an IC executor — the LLM judges those from
# the description. "Team Lead/Leader" IS dropped (always a team role).
MANAGER_TITLE_PATTERNS = [
    r"\bvp\b", r"\bv\.p\.\b", r"\bvice president\b", r"\bsvp\b", r"\bevp\b", r"\bavp\b",
    r"\bdirector\b", r"\bhead of\b", r"\bhead\b", r"\bchief\b",
    r"\bcro\b", r"\bcmo\b", r"\bceo\b", r"\bcoo\b", r"\bpresident\b",
    r"\bteam lead(er)?\b",
]
_MANAGER_RE = re.compile("|".join(MANAGER_TITLE_PATTERNS), re.IGNORECASE)

# Layer 2 — unambiguous staffing/recruiting names. SEO/marketing-agency
# detection is left to the LLM ("X Digital"/"X Media" are often real companies).
AGENCY_NAME_PATTERNS = [
    r"\bstaffing\b",
    r"\brecruit(ing|ment|ers?)?\b",
    r"\bheadhunt\w*\b",
    r"\brpo\b",
    r"\bsearch partners?\b",
    r"\bexecutive search\b",
    r"\btalent acquisition\b",
    r"\btemp agency\b",
    r"\bemployment agency\b",
]
_AGENCY_RE = re.compile("|".join(AGENCY_NAME_PATTERNS), re.IGNORECASE)


def looks_like_leadership_title(title):
    return bool(_MANAGER_RE.search(title or ""))


def looks_like_agency_name(name):
    return bool(_AGENCY_RE.search(name or ""))


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

CLASSIFY_PROMPT = """You classify a US Indeed job posting for PN Digital, an agency that sells AI-search visibility (GEO/AEO) + SEO programmes to END companies. We build outbound lists of companies hiring an in-house, HANDS-ON SEO/organic/AEO EXECUTOR — the displacement pitch is "use our programme instead of that hire", so we only want roles whose day-to-day EXECUTION a programme could replace. Classify the posting, then tag the company's ICP.

Return TWO fields separated by " | ".

FIELD 1 — CATEGORY (exactly one):
TARGET = KEEP. The direct employer (a real END company) is hiring an individual-contributor, hands-on SEO / organic search / content-SEO / AEO / GEO role — someone who personally DOES the execution (keyword research, on-page, technical SEO, content, link building, AEO/GEO optimisation).
AGENCY = DROP. An SEO / digital / marketing / content / growth / PR / advertising agency, consultancy, or freelancer marketplace doing this FOR CLIENTS — or a staffing/recruiting firm. PN's competitors, never buyers.
MANAGER = DROP. A people-management or strategic-leadership role — leads/manages a team, has direct reports, sets strategy or directs/oversees agencies rather than doing the work. Default to MANAGER for "Manager / Lead / Head / Director / VP / Chief" titles UNLESS the description clearly shows a solo individual contributor with NO direct reports doing the hands-on work.
OFF_TARGET = DROP. A real end employer, but the role does NOT own hands-on SEO/organic/AEO execution — e.g. paid-media/PPC only, social-media only, generic copywriter, PR, sales, customer success, analyst/engineer with no search remit. ALSO drop unpaid/volunteer/internship roles (no real hiring budget = no buying signal).
UNCERTAIN = DROP. Not enough info to confirm a hands-on SEO/AEO executor at an end company.

FIELD 2 — ICP (exactly one; best guess even if unsure):
b2b_saas = sells software / a platform to businesses.
multi_location_services = a services business with many physical sites / franchises / clinics / branches.
other = anything else (single-location SMB, ecommerce/DTC, media/publisher, nonprofit, enterprise non-SaaS).

Company: {company}
Job title: {job_title}
{company_desc_block}Job description (first 800 chars):
{job_desc}

Respond with ONLY: CATEGORY | ICP
Example: TARGET | b2b_saas"""


def parse_classification(text):
    """Return (category, icp) normalized."""
    raw = (text or "").strip()
    parts = raw.split("|")
    t = (parts[0] if parts else "").strip().upper()
    icp_raw = (parts[1] if len(parts) > 1 else "").strip().lower()

    if "AGENCY" in t:
        cat = "recruiting_agency"
    elif "MANAGER" in t or "MANAGEMENT" in t:
        cat = "manager_role"
    elif "OFF" in t:               # OFF_TARGET (before TARGET substring)
        cat = "off_target_role"
    elif "TARGET" in t:
        cat = "target"
    else:
        cat = "uncertain"

    if "b2b" in icp_raw or "saas" in icp_raw:
        icp = "b2b_saas"
    elif "multi" in icp_raw or "location" in icp_raw:
        icp = "multi_location_services"
    else:
        icp = "other"
    return cat, icp


def classify_one(client, company, job_title, job_desc, company_desc):
    """Single Azure OpenAI call → (category, icp). Retries on 429."""
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
                max_tokens=20,
                temperature=0,
                messages=[{"role": "user", "content": prompt}],
            )
            return parse_classification(resp.choices[0].message.content)
        except Exception as e:
            if "429" in str(e) or "Too Many Requests" in str(e):
                time.sleep(2 ** attempt)
                continue
            return ("uncertain", "other")
    return ("uncertain", "other")


def classify_keys_with_llm(keys, key_data):
    """Classify unique (company, title) keys concurrently. Returns {key: (cat, icp)}."""
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
            key, result = fut.result()
            out[key] = result
            if i % 25 == 0 or i == len(keys):
                print(f"  Classified {i}/{len(keys)}")
    return out


# --- Main ---

def main():
    parser = argparse.ArgumentParser(description="Keep only end-companies hiring a hands-on IC SEO/AEO executor; ICP-tag them")
    parser.add_argument("--sheet_url", required=True)
    parser.add_argument("--apply", action="store_true", help="Tag TARGET rows + delete every non-TARGET row")
    parser.add_argument("--limit", type=int, default=0, help="Only classify first N rows (debug)")
    args = parser.parse_args()

    if not (AZURE_ENDPOINT and AZURE_API_KEY):
        print("ERROR: AZURE_OPENAI_ENDPOINT / AZURE_OPENAI_API_KEY not set in .env")
        sys.exit(1)

    spreadsheet_id = get_sheet_id_from_url(args.sheet_url)
    service = get_service()
    tab_sheet_id = get_tab_sheet_id(service, spreadsheet_id, TAB_NAME)

    print("=== Classify rows: end-company hiring a hands-on IC SEO/AEO executor ===")
    print(f"Sheet: {spreadsheet_id}")
    print(f"Model: {MODEL}")
    print(f"Mode:  {'APPLY (tag + delete rows)' if args.apply else 'DRY RUN'}\n")

    rows = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id, range=f"{TAB_NAME}!A2:AF10000"
    ).execute().get("values", [])
    if args.limit:
        rows = rows[:args.limit]
    print(f"Total rows: {len(rows)}")

    def safe_get(row, idx):
        return row[idx].strip() if len(row) > idx and row[idx] else ""

    # Per-row records keyed by (company, title) so identical postings classify once.
    row_meta = {}     # sheet_row -> {company, title, key}
    key_to_rows = {}  # key -> [sheet_row, ...]
    key_data = {}     # key -> representative {company, title, job_desc, company_desc}
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
    results = {}
    needs_llm = []
    n_leader = n_agency = 0
    for key in keys:
        company, title = key_data[key]["company"], key_data[key]["title"]
        if looks_like_leadership_title(title):
            results[key] = ("manager_role", "other")
            n_leader += 1
        elif looks_like_agency_name(company):
            results[key] = ("recruiting_agency", "other")
            n_agency += 1
        else:
            needs_llm.append(key)
    print(f"  Leadership title (regex):  {n_leader}")
    print(f"  Agency name (regex):       {n_agency}")
    print(f"  Sent to LLM:               {len(needs_llm)}\n")

    # Layer 3 — LLM for the rest
    if needs_llm:
        results.update(classify_keys_with_llm(needs_llm, key_data))

    # Tally per row
    rows_by_cat = {cat: [] for cat in ALL_CATEGORIES}
    for sheet_row, meta in row_meta.items():
        cat = results.get(meta["key"], ("uncertain", "other"))[0]
        if cat not in rows_by_cat:
            cat = "uncertain"
        rows_by_cat[cat].append(sheet_row)

    print("\n=== Report (by row) ===")
    for cat in ALL_CATEGORIES:
        srows = sorted(rows_by_cat[cat])
        label = "KEEP" if cat == KEEP_CATEGORY else "DROP"
        print(f"\n{cat.upper()} [{label}]: {len(srows)} rows")
        for sr in srows[:30]:
            m = row_meta[sr]
            icp = results.get(m["key"], ("", ""))[1]
            tag = f"  ({icp})" if cat == KEEP_CATEGORY else ""
            print(f"  {m['company'][:34]:34s} | {m['title'][:40]:40s}{tag}")
        if len(srows) > 30:
            print(f"  ... and {len(srows) - 30} more")

    kept_keys = [k for k in results if results[k][0] == KEEP_CATEGORY]
    icp_counts = {}
    for k in kept_keys:
        icp_counts[results[k][1]] = icp_counts.get(results[k][1], 0) + 1
    print(f"\nKEEP ICP split: {icp_counts}")

    if not args.apply:
        print("\n[DRY RUN] No changes made. Re-run with --apply to tag TARGET + delete the rest.")
        return

    # 1) Tag TARGET rows (Employer Type + ICP) before any deletion (indices valid)
    value_updates = []
    for sheet_row, meta in row_meta.items():
        cat, icp = results.get(meta["key"], ("uncertain", "other"))
        if cat == KEEP_CATEGORY:
            value_updates.append({
                "range": f"{TAB_NAME}!{EMPLOYER_TYPE_A1}{sheet_row}:{ICP_A1}{sheet_row}",
                "values": [["TARGET", icp]],
            })
    if value_updates:
        print(f"\nTagging {len(value_updates)} TARGET rows (Employer Type + ICP)...")
        BATCH = 500
        for i in range(0, len(value_updates), BATCH):
            service.spreadsheets().values().batchUpdate(
                spreadsheetId=spreadsheet_id,
                body={"valueInputOption": "RAW", "data": value_updates[i:i + BATCH]},
            ).execute()

    # 2) Delete non-TARGET rows (bottom-up so indices stay stable)
    to_delete = sorted(
        [sr for sr, m in row_meta.items()
         if results.get(m["key"], ("uncertain", "other"))[0] in DROP_CATEGORIES],
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
        spreadsheetId=spreadsheet_id, range=f"{TAB_NAME}!A2:A10000"
    ).execute()
    print(f"\nRows remaining (TARGET): {len(remaining.get('values', []))}")
    print("=== Done ===")


if __name__ == "__main__":
    main()
