#!/usr/bin/env python3
"""
Find emails for all founders in the Middle East tech companies sheet using AnyMailFinder.

Reads Founder 1-5 First/Last Name columns + Website column,
calls AnyMailFinder API, writes emails to new Founder 1-5 Email columns.
"""

import os
import sys
import json
import argparse
import time
from urllib.parse import urlparse
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests as http_requests
import gspread
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

load_dotenv()

CHECKPOINT_FILE = '.tmp/founder_emails_checkpoint.json'
MAX_FOUNDERS = 5


def extract_domain(url):
    """Extract clean domain from a website URL."""
    if not url:
        return ''
    url = url.strip()
    if not url.startswith('http'):
        url = 'https://' + url
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        if domain.startswith('www.'):
            domain = domain[4:]
        return domain
    except Exception:
        return ''


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
    """Read the sheet and return (worksheet, all_values, headers)."""
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
    return worksheet, all_values, headers


def find_email(first_name, last_name, domain, company_name):
    """Query AnyMailFinder API for a single person's email."""
    api_key = os.getenv("ANYMAILFINDER_API_KEY")
    if not api_key:
        print("Error: ANYMAILFINDER_API_KEY not found in .env", file=sys.stderr)
        sys.exit(1)

    url = "https://api.anymailfinder.com/v5.1/find-email/person"
    headers = {
        "Authorization": api_key,
        "Content-Type": "application/json"
    }

    body = {}
    if first_name:
        body["first_name"] = first_name
    if last_name:
        body["last_name"] = last_name
    if first_name and last_name:
        body["full_name"] = f"{first_name} {last_name}"
    if domain:
        body["domain"] = domain
    if company_name:
        body["company_name"] = company_name

    has_name = first_name and last_name
    has_company = domain or company_name

    if not has_name or not has_company:
        return None

    try:
        response = http_requests.post(url, headers=headers, json=body, timeout=180)
        response.raise_for_status()
        data = response.json()

        if data.get("email") and data.get("email_status") in ["valid", "risky"]:
            return data["email"]
        return None

    except Exception as e:
        print(f"  Error for {first_name} {last_name}: {e}")
        return None


def load_checkpoint():
    if os.path.exists(CHECKPOINT_FILE):
        with open(CHECKPOINT_FILE) as f:
            return json.load(f)
    return {}


def save_checkpoint(data):
    os.makedirs('.tmp', exist_ok=True)
    with open(CHECKPOINT_FILE, 'w') as f:
        json.dump(data, f, indent=2)


def main():
    parser = argparse.ArgumentParser(description="Find founder emails via AnyMailFinder")
    parser.add_argument("--sheet_url", required=True, help="Google Sheet URL")
    parser.add_argument("--test", action="store_true", help="Run on first 3 rows only")
    parser.add_argument("--dry_run", action="store_true", help="Find emails but don't write to sheet")
    parser.add_argument("--resume", action="store_true", help="Resume from checkpoint")
    parser.add_argument("--workers", type=int, default=10, help="Concurrent API workers (default: 10)")

    args = parser.parse_args()

    # Step 1: Read sheet
    print("=== Step 1: Reading Google Sheet ===")
    worksheet, all_values, headers = read_sheet(args.sheet_url)

    # Find column indices
    col_indices = {}
    for i, h in enumerate(headers):
        col_indices[h] = i

    website_idx = col_indices.get('Website')
    org_idx = col_indices.get('Organization Name', 0)

    # Find founder column indices
    founder_cols = []
    for f in range(1, MAX_FOUNDERS + 1):
        fn_key = f'Founder {f} First Name'
        ln_key = f'Founder {f} Last Name'
        if fn_key in col_indices and ln_key in col_indices:
            founder_cols.append((f, col_indices[fn_key], col_indices[ln_key]))

    print(f"Found {len(founder_cols)} founder column pairs")

    # Step 2: Build lookup list
    lookups = []  # (row_num, founder_num, first_name, last_name, domain, company_name)

    for row_idx, row in enumerate(all_values[1:], start=2):  # row 2 = first data row
        website = row[website_idx] if website_idx is not None and len(row) > website_idx else ''
        domain = extract_domain(website)
        company = row[org_idx] if len(row) > org_idx else ''

        for f_num, fn_idx, ln_idx in founder_cols:
            first = row[fn_idx].strip() if len(row) > fn_idx else ''
            last = row[ln_idx].strip() if len(row) > ln_idx else ''
            if first:
                lookups.append((row_idx, f_num, first, last, domain, company))

    print(f"Total founder email lookups: {len(lookups)}")

    if args.test:
        # Only lookups from first 3 data rows
        lookups = [l for l in lookups if l[0] <= 4]
        print(f"TEST MODE: Limited to {len(lookups)} lookups")

    # Step 3: Load checkpoint
    checkpoint = load_checkpoint()
    if args.resume:
        before = len(lookups)
        lookups = [l for l in lookups if f"{l[0]}_{l[1]}" not in checkpoint]
        print(f"After resume filter: {len(lookups)} remaining (skipped {before - len(lookups)})")

    if not lookups:
        print("Nothing to look up.")
        return

    # Step 4: Ensure email columns exist
    email_col_indices = {}
    for f in range(1, MAX_FOUNDERS + 1):
        col_name = f'Founder {f} Email'
        if col_name in col_indices:
            email_col_indices[f] = col_indices[col_name] + 1  # 1-based for gspread
        else:
            # Add new column
            new_col = len(headers) + 1
            if new_col > worksheet.col_count:
                worksheet.resize(cols=new_col)
            worksheet.update_cell(1, new_col, col_name)
            email_col_indices[f] = new_col
            headers.append(col_name)
            col_indices[col_name] = new_col - 1
            print(f"  Added column '{col_name}' at position {new_col}")

    # Step 5: Find emails concurrently
    print(f"\n=== Step 2: Finding emails ({len(lookups)} lookups, {args.workers} workers) ===")

    results = {}  # {(row_num, founder_num): email}
    found_count = 0
    not_found_count = 0

    def process_lookup(lookup):
        row_num, f_num, first, last, domain, company = lookup
        key = f"{row_num}_{f_num}"

        # Check checkpoint
        if key in checkpoint:
            return key, checkpoint[key]

        email = find_email(first, last, domain, company)
        return key, email

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(process_lookup, l): l for l in lookups}

        for future in as_completed(futures):
            lookup = futures[future]
            row_num, f_num, first, last, domain, company = lookup
            key, email = future.result()

            checkpoint[key] = email
            save_checkpoint(checkpoint)

            if email:
                results[(row_num, f_num)] = email
                print(f"  Row {row_num}: {first} {last} @ {domain or company} -> {email}")
                found_count += 1
            else:
                print(f"  Row {row_num}: {first} {last} @ {domain or company} -> not found")
                not_found_count += 1

    # Step 6: Write emails to sheet
    if results and not args.dry_run:
        print(f"\n=== Step 3: Updating Google Sheet ===")
        updates = []
        for (row_num, f_num), email in results.items():
            col = email_col_indices.get(f_num)
            if col:
                updates.append(gspread.Cell(row_num, col, email))

        if updates:
            batch_size = 1000
            for start in range(0, len(updates), batch_size):
                batch = updates[start:start + batch_size]
                worksheet.update_cells(batch, value_input_option='RAW')
                print(f"  Updated cells {start + 1}-{start + len(batch)}")
                if start + batch_size < len(updates):
                    time.sleep(1)

        print(f"Successfully updated {len(updates)} email cells.")
    elif args.dry_run:
        print(f"\n=== DRY RUN: Would update {len(results)} cells ===")

    # Summary
    print(f"\n=== Summary ===")
    print(f"Total lookups: {len(lookups)}")
    print(f"Emails found: {found_count}")
    print(f"Not found: {not_found_count}")


if __name__ == "__main__":
    main()
