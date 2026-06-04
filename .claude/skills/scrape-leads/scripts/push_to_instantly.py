#!/usr/bin/env python3
"""
Push founder leads to an Instantly campaign.

Reads the Google Sheet, generates personalized email bodies,
creates an Instantly campaign, and adds all leads with custom variables.

Usage:
    python3 .claude/skills/scrape-leads/scripts/push_to_instantly.py \
        --sheet_url "https://docs.google.com/spreadsheets/d/SHEET_ID/edit?gid=GID" \
        --campaign_name "GCC Founders - Recruitment" \
        --test  # first 3 leads only
"""

import os
import sys
import json
import argparse
import time
from dotenv import load_dotenv
import requests
import gspread
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

load_dotenv()

INSTANTLY_API_BASE = "https://api.instantly.ai/api/v2"

EMAIL_TEMPLATE = """Hey {first_name},

Been staying close to {startup_type} in the GCC building up their team after a new funding round.

Most of them prefer private access to pre-vetted {talent_type} pools before the recruiting waves begin, and I connect them with {recruiter_type} who understand the {talent_type} landscape and can give them an edge before the roles are live.

If this is timely for you, happy to share more details."""


def get_credentials():
    scopes = [
        'https://www.googleapis.com/auth/spreadsheets',
        'https://www.googleapis.com/auth/drive'
    ]
    creds = None
    if os.path.exists('token.json'):
        try:
            with open('token.json', 'r') as token:
                token_data = json.load(token)
                creds = Credentials.from_authorized_user_info(token_data, scopes)
        except Exception as e:
            print(f"Error loading token: {e}")

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            print("Error: No valid credentials.", file=sys.stderr)
            sys.exit(1)
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
    return creds


def read_sheet(sheet_url):
    """Read the sheet and return (all_values, headers)."""
    creds = get_credentials()
    client = gspread.authorize(creds)

    if '/d/' in sheet_url:
        sheet_id = sheet_url.split('/d/')[1].split('/')[0]
    else:
        sheet_id = sheet_url

    spreadsheet = client.open_by_key(sheet_id)

    gid = None
    if 'gid=' in sheet_url:
        gid = sheet_url.split('gid=')[1].split('#')[0].split('&')[0]

    if gid:
        for ws in spreadsheet.worksheets():
            if str(ws.id) == gid:
                worksheet = ws
                break
        else:
            worksheet = spreadsheet.sheet1
    else:
        worksheet = spreadsheet.sheet1

    all_values = worksheet.get_all_values()
    headers = all_values[0] if all_values else []
    print(f"Read {len(all_values) - 1} rows from sheet.")
    return all_values, headers


def extract_leads(all_values, headers):
    """Extract one lead per founder who has an email. Returns list of lead dicts."""
    col = {h: i for i, h in enumerate(headers)}

    leads = []
    for row_idx, row in enumerate(all_values[1:], start=2):
        def val(col_name):
            idx = col.get(col_name)
            if idx is not None and len(row) > idx:
                return row[idx].strip()
            return ''

        company_name = val('Organization Name')
        company_linkedin = val('LinkedIn')
        last_funding_type = val('Last Funding Type')
        last_funding_date = val('Last Funding Date')
        startup_type = val('Startup Type')
        talent_type = val('Type of Talent')
        recruiter_type = val('Type of Recruiters')

        if not company_name:
            continue

        # Iterate through up to 5 founders
        for f in range(1, 6):
            first = val(f'Founder {f} First Name')
            last = val(f'Founder {f} Last Name')
            email = val(f'Founder {f} Email')

            if not email:
                continue

            # Generate personalized email body
            personalized_email = EMAIL_TEMPLATE.format(
                first_name=first,
                startup_type=startup_type,
                talent_type=talent_type,
                recruiter_type=recruiter_type,
            )

            leads.append({
                'email': email,
                'first_name': first,
                'last_name': last,
                'company_name': company_name,
                'company_linkedin': company_linkedin,
                'last_funding_type': last_funding_type,
                'last_funding_date': last_funding_date,
                'startup_type': startup_type,
                'talent_type': talent_type,
                'recruiter_type': recruiter_type,
                'personalized_email': personalized_email,
            })

    return leads


def create_campaign(campaign_name):
    """Create an Instantly campaign with the email template. Returns campaign ID."""
    api_key = os.getenv("INSTANTLY_API_KEY")
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    # Use personalized_email variable — each lead has their own pre-built body
    body_html = "<p>{{personalized_email}}</p>"

    from datetime import datetime, timedelta
    start_date = datetime.now().strftime("%Y-%m-%d")
    end_date = (datetime.now() + timedelta(days=365)).strftime("%Y-%m-%d")

    payload = {
        "name": campaign_name,
        "sequences": [
            {
                "steps": [
                    {
                        "type": "email",
                        "delay": 0,
                        "variants": [
                            {
                                "subject": "quick question on hiring",
                                "body": body_html
                            }
                        ]
                    }
                ]
            }
        ],
        "campaign_schedule": {
            "start_date": start_date,
            "end_date": end_date,
            "schedules": [
                {
                    "name": "Weekday Schedule",
                    "days": {"1": True, "2": True, "3": True, "4": True, "5": True},
                    "timing": {"from": "09:00", "to": "17:00"},
                    "timezone": "America/Chicago"
                }
            ]
        }
    }

    response = requests.post(
        f"{INSTANTLY_API_BASE}/campaigns",
        headers=headers,
        json=payload,
        timeout=60
    )

    if response.status_code not in [200, 201]:
        print(f"Error creating campaign: {response.status_code} - {response.text}", file=sys.stderr)
        sys.exit(1)

    result = response.json()
    campaign_id = result.get('id')
    print(f"Created campaign: {campaign_name} (ID: {campaign_id})")
    return campaign_id


def add_leads_to_campaign(campaign_id, leads):
    """Add leads to an Instantly campaign in batches."""
    api_key = os.getenv("INSTANTLY_API_KEY")
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    # Format leads for Instantly API
    instantly_leads = []
    for lead in leads:
        instantly_leads.append({
            "email": lead['email'],
            "first_name": lead['first_name'],
            "last_name": lead['last_name'],
            "company_name": lead['company_name'],
            "custom_variables": {
                "company_linkedin": lead['company_linkedin'],
                "last_funding_type": lead['last_funding_type'],
                "last_funding_date": lead['last_funding_date'],
                "startup_type": lead['startup_type'],
                "talent_type": lead['talent_type'],
                "recruiter_type": lead['recruiter_type'],
                "personalized_email": lead['personalized_email'],
            }
        })

    # Instantly accepts up to 1000 leads per request
    batch_size = 500
    total_added = 0

    for start in range(0, len(instantly_leads), batch_size):
        batch = instantly_leads[start:start + batch_size]

        payload = {
            "campaign_id": campaign_id,
            "leads": batch,
            "skip_if_in_campaign": True
        }

        response = requests.post(
            f"{INSTANTLY_API_BASE}/leads/add",
            headers=headers,
            json=payload,
            timeout=120
        )

        if response.status_code == 429:
            print("  Rate limited, waiting 30 seconds...")
            time.sleep(30)
            response = requests.post(
                f"{INSTANTLY_API_BASE}/leads/add",
                headers=headers,
                json=payload,
                timeout=120
            )

        if response.status_code not in [200, 201]:
            print(f"  Error adding leads batch: {response.status_code} - {response.text}")
            continue

        result = response.json()
        added = result.get('leads_added', len(batch))
        total_added += added
        print(f"  Added batch {start + 1}-{start + len(batch)}: {added} leads")

        if start + batch_size < len(instantly_leads):
            time.sleep(2)

    return total_added


def main():
    parser = argparse.ArgumentParser(description="Push founder leads to Instantly campaign")
    parser.add_argument("--sheet_url", required=True, help="Google Sheet URL")
    parser.add_argument("--campaign_name", default="GCC Founders - Recruitment", help="Instantly campaign name")
    parser.add_argument("--campaign_id", help="Existing campaign ID (skip creation)")
    parser.add_argument("--test", action="store_true", help="First 3 leads only")
    parser.add_argument("--dry_run", action="store_true", help="Show leads without pushing to Instantly")

    args = parser.parse_args()

    # Check API key
    api_key = os.getenv("INSTANTLY_API_KEY", "")
    if not args.dry_run and (not api_key or api_key.startswith("your_")):
        print("Error: INSTANTLY_API_KEY not configured in .env", file=sys.stderr)
        sys.exit(1)

    # Step 1: Read sheet
    print("=== Step 1: Reading Google Sheet ===")
    all_values, headers = read_sheet(args.sheet_url)

    # Step 2: Extract leads
    print("\n=== Step 2: Extracting leads ===")
    leads = extract_leads(all_values, headers)
    print(f"Total leads with emails: {len(leads)}")

    if args.test:
        leads = leads[:3]
        print(f"TEST MODE: Limited to {len(leads)} leads")

    if not leads:
        print("No leads with emails found.")
        return

    # Show preview
    print(f"\nPreview ({min(3, len(leads))} leads):")
    for lead in leads[:3]:
        print(f"\n  --- {lead['first_name']} {lead['last_name']} <{lead['email']}> @ {lead['company_name']} ---")
        print(f"  Company LinkedIn: {lead['company_linkedin']}")
        print(f"  Funding: {lead['last_funding_type']} ({lead['last_funding_date']})")
        print(f"  Variables: {lead['startup_type']} | {lead['talent_type']} | {lead['recruiter_type']}")
        print(f"\n  Email:")
        for line in lead['personalized_email'].split('\n'):
            print(f"    {line}")

    if args.dry_run:
        print(f"\n=== DRY RUN: Would push {len(leads)} leads ===")
        print(f"\nFull lead list:")
        for i, lead in enumerate(leads, 1):
            print(f"  {i}. {lead['first_name']} {lead['last_name']} <{lead['email']}> @ {lead['company_name']} ({lead['startup_type']})")
        return

    # Step 3: Create or reuse campaign
    if args.campaign_id:
        campaign_id = args.campaign_id
        print(f"\n=== Step 3: Using existing campaign {campaign_id} ===")
    else:
        print(f"\n=== Step 3: Creating Instantly campaign ===")
        campaign_id = create_campaign(args.campaign_name)

    # Step 4: Add leads
    print(f"\n=== Step 4: Adding {len(leads)} leads to campaign ===")
    total_added = add_leads_to_campaign(campaign_id, leads)

    # Summary
    print(f"\n=== Summary ===")
    print(f"Campaign: {args.campaign_name}")
    print(f"Campaign ID: {campaign_id}")
    print(f"Leads pushed: {total_added}/{len(leads)}")


if __name__ == "__main__":
    main()
