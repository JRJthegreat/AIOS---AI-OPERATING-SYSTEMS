"""
Phase 5: Push the generated leads + emails into a new Instantly campaign.

Reads the b2b Leads sheet, takes every row with a valid email AND a generated body
(col Z), creates an Instantly campaign whose single step uses {{subject}} / {{personalization}},
and adds the leads with these personalization fields:
  email, first_name, last_name, and custom_variables:
    title, company_name, company_website, dm_linkedin, subject, personalization (clean HTML
    body — paragraphs joined by a single <br><br>, no stray newlines).

The campaign is created but NOT launched — review + start it in Instantly.

Usage:
  python3 push_emails_to_instantly.py --dry_run                 # show what would push, no API
  python3 push_emails_to_instantly.py --test                    # create campaign + push first 3
  python3 push_emails_to_instantly.py --campaign_name "NEXAM — Sales-Hiring Signal"
  python3 push_emails_to_instantly.py --campaign_id <id>        # add leads to an existing campaign
"""

import os
import re
import sys
import json
import time
import argparse
from datetime import datetime, timedelta
import requests
from dotenv import load_dotenv
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "..", "..", ".."))
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))
TOKEN_PATH = os.path.join(PROJECT_ROOT, "token.json")

INSTANTLY_API_BASE = "https://api.instantly.ai/api/v2"
DEFAULT_SHEET = "https://docs.google.com/spreadsheets/d/1g2X-qSv-Y3A5A8Z83cftAD-9Af5PO0XQJTVjH6yq5PQ/edit"
TAB_NAME = "Leads"
# column indexes (0-based)
COL_COMPANY = 10   # K
COL_WEBSITE = 11   # L
COL_TITLE = 20     # U  (DM Title)
COL_LINKEDIN = 21  # V
COL_EMAIL = 22     # W
COL_FIRST = 23     # X
COL_LAST = 24      # Y
COL_BODY = 25      # Z
COL_SUBJECT = 30   # AE


def get_service():
    with open(TOKEN_PATH) as f:
        td = json.load(f)
    creds = Credentials(
        token=td["token"], refresh_token=td["refresh_token"], token_uri=td["token_uri"],
        client_id=td["client_id"], client_secret=td["client_secret"],
        scopes=td.get("scopes", ["https://www.googleapis.com/auth/spreadsheets"]),
    )
    if creds.expired:
        creds.refresh(Request())
        td["token"] = creds.token
        with open(TOKEN_PATH, "w") as f:
            json.dump(td, f)
    return build("sheets", "v4", credentials=creds)


def sheet_id_from_url(url):
    return url.split("/d/")[1].split("/")[0] if "/d/" in url else url


def format_body_html(body):
    """Plain-text body (col Z, paragraphs split by blank lines) -> clean email HTML.

    Join paragraphs with a single <br><br> and leave NO literal newlines: Instantly
    converts stray \\n to <br> on its own, so keeping them doubled every paragraph break.
    """
    paras = [p.strip().replace("\n", "<br>") for p in re.split(r"\n\s*\n", body) if p.strip()]
    return "<br><br>".join(paras)


def read_leads(sheet_url):
    svc = get_service()
    sid = sheet_id_from_url(sheet_url)
    rows = svc.spreadsheets().values().get(
        spreadsheetId=sid, range=f"{TAB_NAME}!A2:AE50000"
    ).execute().get("values", [])
    leads = []
    for row in rows:
        def c(i):
            return (row[i] if len(row) > i else "").strip()
        email, body = c(COL_EMAIL), c(COL_BODY)
        if not email or not body:
            continue
        leads.append({
            "email": email,
            "first_name": c(COL_FIRST),
            "last_name": c(COL_LAST),
            "company_name": c(COL_COMPANY),
            "title": c(COL_TITLE),
            "company_website": c(COL_WEBSITE),
            "dm_linkedin": c(COL_LINKEDIN),
            "subject": c(COL_SUBJECT) or "quick question on your sales hire",
            # plain text → clean email HTML, exposed as the {{personalization}} variable
            "personalization": format_body_html(body),
        })
    return leads


def create_campaign(name):
    api_key = os.getenv("INSTANTLY_API_KEY")
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    start = datetime.now().strftime("%Y-%m-%d")
    end = (datetime.now() + timedelta(days=365)).strftime("%Y-%m-%d")
    payload = {
        "name": name,
        "sequences": [{"steps": [{
            "type": "email", "delay": 0,
            "variants": [{"subject": "{{subject}}", "body": "{{personalization}}"}],
        }]}],
        "campaign_schedule": {
            "start_date": start, "end_date": end,
            "schedules": [{
                "name": "Weekday Schedule",
                "days": {"1": True, "2": True, "3": True, "4": True, "5": True},
                "timing": {"from": "09:00", "to": "17:00"},
                "timezone": "America/Chicago",
            }],
        },
    }
    r = requests.post(f"{INSTANTLY_API_BASE}/campaigns", headers=headers, json=payload, timeout=60)
    if r.status_code not in (200, 201):
        print(f"Error creating campaign: {r.status_code} - {r.text}", file=sys.stderr)
        sys.exit(1)
    cid = r.json().get("id")
    print(f"Created campaign '{name}' (ID: {cid}) — created PAUSED, not sending.")
    return cid


def add_leads(campaign_id, leads):
    api_key = os.getenv("INSTANTLY_API_KEY")
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payloads = [{
        "email": ld["email"], "first_name": ld["first_name"], "last_name": ld["last_name"],
        "company_name": ld["company_name"],
        "custom_variables": {
            "title": ld["title"], "company_website": ld["company_website"],
            "dm_linkedin": ld["dm_linkedin"], "subject": ld["subject"],
            "personalization": ld["personalization"],
        },
    } for ld in leads]

    BATCH = 25  # small batches so Instantly processes each before Cloudflare's 524 timeout
    total = 0
    for s in range(0, len(payloads), BATCH):
        batch = payloads[s:s + BATCH]
        body = {"campaign_id": campaign_id, "leads": batch, "skip_if_in_campaign": True}
        for attempt in range(5):
            try:
                r = requests.post(f"{INSTANTLY_API_BASE}/leads/add", headers=headers, json=body, timeout=180)
            except requests.exceptions.RequestException as e:
                print(f"  batch {s+1}-{s+len(batch)} {type(e).__name__}, retry {attempt+1}")
                time.sleep(5 * (attempt + 1)); continue
            if r.status_code in (429, 500, 502, 503, 504, 524):
                print(f"  batch {s+1}-{s+len(batch)} HTTP {r.status_code}, retry {attempt+1}")
                time.sleep(min(30, 8 * (attempt + 1))); continue
            if r.status_code not in (200, 201):
                print(f"  Error batch {s+1}-{s+len(batch)}: {r.status_code} - {r.text[:160]}")
                break
            added = r.json().get("leads_added", len(batch))
            total += added
            print(f"  Added {s+1}-{s+len(batch)}: {added}")
            break
        time.sleep(1)
    return total


def main():
    ap = argparse.ArgumentParser(description="Push generated emails to an Instantly campaign")
    ap.add_argument("--sheet_url", default=DEFAULT_SHEET)
    ap.add_argument("--campaign_name", default="NEXAM — Sales-Hiring Signal")
    ap.add_argument("--campaign_id", help="Add to an existing campaign instead of creating one")
    ap.add_argument("--test", action="store_true", help="First 3 leads only")
    ap.add_argument("--dry_run", action="store_true", help="Show what would push; no API calls")
    args = ap.parse_args()

    api_key = os.getenv("INSTANTLY_API_KEY", "")
    if not args.dry_run and (not api_key or api_key.startswith("your_")):
        print("Error: INSTANTLY_API_KEY not set in .env", file=sys.stderr)
        sys.exit(1)

    leads = read_leads(args.sheet_url)
    print(f"Leads with email + generated body: {len(leads)}")
    if args.test:
        leads = leads[:3]
        print(f"TEST MODE — {len(leads)} leads")
    if not leads:
        print("Nothing to push.")
        return

    print("\nPreview (first 2):")
    for ld in leads[:2]:
        print(f"  {ld['first_name']} {ld['last_name']} | {ld['title']} | {ld['company_name']} "
              f"<{ld['email']}> | {ld['dm_linkedin'][:45]}")
        print(f"    subject: {ld['subject']}")
        print(f"    body: {ld['personalization'][:120]}...")

    if args.dry_run:
        print(f"\n[DRY RUN] Would push {len(leads)} leads. No campaign created.")
        return

    if args.campaign_id:
        cid = args.campaign_id
        print(f"\nUsing existing campaign {cid}")
    else:
        cid = create_campaign(args.campaign_name)

    print(f"\nAdding {len(leads)} leads...")
    total = add_leads(cid, leads)
    print(f"\n=== Done ===")
    print(f"Campaign ID: {cid}")
    print(f"Leads pushed: {total}/{len(leads)}")
    print("Campaign is PAUSED — review the copy/fields in Instantly, then launch it there.")


if __name__ == "__main__":
    main()
