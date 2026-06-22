"""
Phase 3: Dedupe by company — keep one row per company.

A company often posts the same role across multiple cities (or posts SEO
Manager + Head of SEO at once). We want one outreach target per company.

Rules:
  1. Group rows by normalized company name (strips corp suffixes/punctuation).
  2. Winner = Tier A over Tier B (an AI-search-aware req is the stronger,
     more on-message signal), then most recent Date Published (freshest =
     still live, not yet filled).

Dry-run by default — prints plan. Re-run with --apply to delete losers.
Safety: reads all rows, decides in-memory, deletes bottom-up so indices stay stable.

Usage:
  python3 dedupe_by_company.py --sheet_url "URL"           # dry run
  python3 dedupe_by_company.py --sheet_url "URL" --apply   # delete dupes
"""

import os
import re
import json
import argparse
from urllib.parse import urlparse
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "..", "..", ".."))
TOKEN_PATH = os.path.join(PROJECT_ROOT, "token.json")

TAB_NAME = "Leads"

# Column indices (0-based; see pull_dataset.py HEADERS)
COL_JOB_TITLE = 1       # B
COL_DATE_PUBLISHED = 4  # E
COL_COMPANY_NAME = 10   # K
COL_TIER = 29           # AD


COMPANY_SUFFIX_PATTERNS = [
    r"\binc\.?\b", r"\bincorporated\b",
    r"\bllc\b", r"\bl\.l\.c\.?\b",
    r"\bltd\.?\b", r"\blimited\b", r"\blp\b", r"\bllp\b",
    r"\bcorp\.?\b", r"\bcorporation\b",
    r"\bpllc\b", r"\bpc\b",
    r"\bco\.?\b", r"\bcompany\b",
    r"\bgroup\b", r"\bholdings?\b", r"\binternational\b",
    r"\b&\s*co\b", r"\band\s+co\b",
    r"\bthe\b",
    r"\(usa\)", r"\busa\b",
]


def normalize_company(name):
    if not name:
        return ""
    s = name.lower().strip()
    for p in COMPANY_SUFFIX_PATTERNS:
        s = re.sub(p, " ", s)
    s = re.sub(r"[^\w\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def winner_sort_key(item):
    """Tier A beats B; then most recent date. Higher tuple sorts first."""
    tier_rank = 1 if (item["tier"] or "").upper() == "A" else 0
    return (tier_rank, item["date"])


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


def main():
    parser = argparse.ArgumentParser(description="Dedup SEO/AEO leads by company")
    parser.add_argument("--sheet_url", required=True)
    parser.add_argument("--apply", action="store_true", help="Actually delete losers. Default: dry run.")
    args = parser.parse_args()

    spreadsheet_id = get_sheet_id_from_url(args.sheet_url)
    service = get_service()
    tab_sheet_id = get_tab_sheet_id(service, spreadsheet_id, TAB_NAME)

    mode = "LIVE" if args.apply else "DRY RUN"
    print(f"=== Dedup by Company ({mode}) ===")
    print(f"Sheet: {spreadsheet_id}\n")

    rows = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id, range=f"{TAB_NAME}!A2:AF10000"
    ).execute().get("values", [])
    print(f"Total rows: {len(rows)}")

    def cell(row, idx):
        return row[idx] if len(row) > idx else ""

    plan = []
    for i, row in enumerate(rows):
        company = cell(row, COL_COMPANY_NAME)
        plan.append({
            "sheet_row": i + 2,
            "title": cell(row, COL_JOB_TITLE),
            "company_raw": company,
            "company_norm": normalize_company(company),
            "date": (cell(row, COL_DATE_PUBLISHED) or "").strip(),
            "tier": cell(row, COL_TIER),
        })

    groups = {}
    for p in plan:
        key = p["company_norm"] or f"__row_{p['sheet_row']}__"
        groups.setdefault(key, []).append(p)

    losers, winners = [], []
    for key, items in groups.items():
        items.sort(key=winner_sort_key, reverse=True)  # Tier A, then freshest
        items[0]["action"] = "KEEP"
        winners.append(items[0])
        for loser in items[1:]:
            loser["action"] = "REMOVE_DUPE"
            losers.append(loser)

    print(f"Unique companies: {len(groups)}")
    print(f"Winners (keep):   {len(winners)}")
    print(f"Losers (remove):  {len(losers)}\n")

    multi = sorted([(k, v) for k, v in groups.items() if len(v) > 1], key=lambda kv: -len(kv[1]))
    print(f"Companies with >1 posting: {len(multi)}")
    print("Sample (top 10 by # of postings):")
    for key, items in multi[:10]:
        win = items[0]
        print(f"\n  {win['company_raw']!r}  ({len(items)} postings)")
        print(f"    WINNER  tier={win['tier']}  {win['date']}  {win['title']!r}")
        for loser in items[1:]:
            print(f"    drop    tier={loser['tier']}  {loser['date']}  {loser['title']!r}")

    if not args.apply:
        print("\n[DRY RUN] No changes made. Re-run with --apply to delete losers.")
        return

    to_delete = sorted([l["sheet_row"] for l in losers], reverse=True)
    if not to_delete:
        print("\nNo duplicate rows to delete.")
        print("=== Done ===")
        return

    print(f"\nDeleting {len(to_delete)} rows (bottom-up)...")
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
            spreadsheetId=spreadsheet_id, body={"requests": requests_body[i:i + BATCH]}
        ).execute()
        print(f"  Deleted chunk {i // BATCH + 1}/{(len(requests_body) + BATCH - 1) // BATCH}")

    remaining = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id, range=f"{TAB_NAME}!A2:A10000"
    ).execute()
    print(f"\nRows remaining: {len(remaining.get('values', []))}")
    print("=== Done ===")


if __name__ == "__main__":
    main()
