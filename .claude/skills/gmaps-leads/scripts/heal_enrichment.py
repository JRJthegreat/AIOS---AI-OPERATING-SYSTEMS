#!/usr/bin/env python3
"""
Re-enrich sheet rows whose website extraction failed (e.g. Azure 429 storms):
rows that have a website but ZERO extracted signals (no emails, no socials,
no owner, no team). Re-runs scrape_website_contacts (which now retries on 429)
and rewrites the extraction columns in place. Also blanks the dm_* columns for
healed rows so verify_email_persona.py picks them up again.

Usage:
  python3 heal_enrichment.py --sheet_url URL --tab "Golf Courses" [--workers 8] [--apply]
"""

import os
import sys
import json
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv

import gspread
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from extract_website_contacts import scrape_website_contacts
from gmaps_lead_pipeline import stringify_value

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "..", "..", ".."))
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))
TOKEN_PATH = os.path.join(PROJECT_ROOT, "token.json")
SCOPES = ["https://www.googleapis.com/auth/spreadsheets",
          "https://www.googleapis.com/auth/drive"]

# Extraction-derived columns, in LEAD_COLUMNS order starting at "emails"
EXTRACT_COLS = ["emails", "additional_phones", "business_hours", "facebook",
                "twitter", "linkedin", "instagram", "youtube", "tiktok",
                "owner_name", "owner_title", "owner_email", "owner_phone",
                "owner_linkedin", "team_contacts", "additional_contact_methods",
                "pages_scraped", "search_enriched", "enrichment_status"]
DM_COLS = ["dm_first_name", "dm_last_name", "dm_name", "dm_title",
           "dm_email", "dm_source", "dm_status"]


def col_letter(n: int) -> str:
    s = ""
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def contacts_to_cells(contacts: dict) -> list:
    social = contacts.get("social_media", {}) or {}
    owner = contacts.get("owner_info", {}) or {}
    team = contacts.get("team_members", []) or []
    emails = contacts.get("emails", []) or []
    status = "success" if emails or owner.get("email") else "partial"
    if contacts.get("error"):
        status = f"error: {contacts.get('error')}"
    return [
        stringify_value(emails),
        stringify_value(contacts.get("phone_numbers", []) or []),
        stringify_value(contacts.get("business_hours", "")),
        stringify_value(social.get("facebook", "")),
        stringify_value(social.get("twitter", "")),
        stringify_value(social.get("linkedin", "")),
        stringify_value(social.get("instagram", "")),
        stringify_value(social.get("youtube", "")),
        stringify_value(social.get("tiktok", "")),
        stringify_value(owner.get("name", "")),
        stringify_value(owner.get("title", "")),
        stringify_value(owner.get("email", "")),
        stringify_value(owner.get("phone", "")),
        stringify_value(owner.get("linkedin", "")),
        json.dumps(team) if team else "",
        stringify_value(contacts.get("additional_contacts", []) or []),
        contacts.get("_pages_scraped", 0),
        "no",
        status,
    ]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sheet_url", required=True)
    ap.add_argument("--tab", required=True)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    with open(TOKEN_PATH) as f:
        creds = Credentials.from_authorized_user_info(json.load(f), SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    sheet_id = args.sheet_url.split("/d/")[1].split("/")[0] if "/d/" in args.sheet_url else args.sheet_url
    ws = gspread.authorize(creds).open_by_key(sheet_id).worksheet(args.tab)

    values = ws.get_all_values()
    header, data = values[0], values[1:]
    idx = {name: i for i, name in enumerate(header)}

    def cell(row, name):
        i = idx.get(name)
        return row[i] if i is not None and i < len(row) else ""

    candidates = []
    for rn, row in enumerate(data, start=2):
        if not cell(row, "website"):
            continue
        signals = [cell(row, c) for c in ("emails", "facebook", "instagram",
                                          "linkedin", "owner_name", "team_contacts")]
        if any(signals):
            continue
        candidates.append((rn, cell(row, "business_name"), cell(row, "website")))

    if args.limit:
        candidates = candidates[:args.limit]
    print(f"{args.tab}: {len(data)} rows, {len(candidates)} need healing")
    if not candidates:
        return
    if not args.apply:
        for rn, name, site in candidates[:20]:
            print(f"  would heal [{rn}] {name} ({site})")
        print("DRY RUN - re-run with --apply")
        return

    ext_start = idx["emails"]
    ext_end = idx["enrichment_status"]
    dm_start = idx.get("dm_first_name")
    dm_end = idx.get("dm_status")

    def work(item):
        rn, name, site = item
        try:
            contacts = scrape_website_contacts(site, name)
        except Exception as e:
            contacts = {"error": str(e)}
        return rn, name, contacts

    healed, updates = 0, []
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = [ex.submit(work, c) for c in candidates]
        for n, f in enumerate(as_completed(futs), 1):
            rn, name, contacts = f.result()
            got_data = bool((contacts.get("emails") or contacts.get("team_members")
                             or (contacts.get("social_media") or {}).get("facebook")
                             or (contacts.get("owner_info") or {}).get("name")))
            cells = contacts_to_cells(contacts)
            updates.append({
                "range": f"{col_letter(ext_start + 1)}{rn}:{col_letter(ext_end + 1)}{rn}",
                "values": [cells]})
            if got_data and dm_start is not None:
                updates.append({
                    "range": f"{col_letter(dm_start + 1)}{rn}:{col_letter(dm_end + 1)}{rn}",
                    "values": [[""] * len(DM_COLS)]})
                healed += 1
            if n % 25 == 0:
                ws.batch_update(updates, value_input_option="RAW")
                updates = []
                print(f"  {n}/{len(candidates)} processed ({healed} recovered)")
    if updates:
        ws.batch_update(updates, value_input_option="RAW")
    print(f"Healed {healed}/{len(candidates)} rows with new data on '{args.tab}'.")


if __name__ == "__main__":
    main()
