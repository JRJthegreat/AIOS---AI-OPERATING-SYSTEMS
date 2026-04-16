#!/usr/bin/env python3
"""
Find missing founder/co-founder names for companies using LinkedIn company employee data.

Uses:
- harvestapi/linkedin-company-employees (Apify) to pull employees from company LinkedIn pages
- Filters by Owner/Partner seniority + founder-related job titles
- Writes results back to Google Sheet

Usage:
    python3 .claude/skills/scrape-leads/scripts/find_founders.py \
        --sheet_url "https://docs.google.com/spreadsheets/d/SHEET_ID/edit?gid=GID" \
        --test  # first 3 companies only
"""

import os
import sys
import json
import argparse
import re
import time
from dotenv import load_dotenv
from apify_client import ApifyClient
import gspread
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

load_dotenv()

CHECKPOINT_FILE = '.tmp/founders_checkpoint.json'

# Titles that indicate a founder
FOUNDER_TITLE_PATTERNS = [
    r'\bfounder\b',
    r'\bco-founder\b',
    r'\bcofounder\b',
    r'\bco\s+founder\b',
    r'\bowner\b',
]


def is_founder_title(title):
    """Check if a job title indicates a founder/co-founder."""
    title_lower = title.lower()
    return any(re.search(p, title_lower) for p in FOUNDER_TITLE_PATTERNS)


def extract_sheet_id(url):
    if '/d/' in url:
        return url.split('/d/')[1].split('/')[0]
    return url


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
            print("Error: No valid credentials. Run setup_google_auth.py first.", file=sys.stderr)
            sys.exit(1)
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
    return creds


def read_sheet(sheet_url, worksheet_name=None):
    """Read companies from Google Sheet. Returns (worksheet, records, headers)."""
    creds = get_credentials()
    client = gspread.authorize(creds)
    sheet_id = extract_sheet_id(sheet_url)
    spreadsheet = client.open_by_key(sheet_id)

    if worksheet_name:
        worksheet = spreadsheet.worksheet(worksheet_name)
    else:
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

    records = worksheet.get_all_records()
    headers = [h.strip() for h in worksheet.row_values(1)]
    print(f"Read {len(records)} rows from sheet.")
    return worksheet, records, headers


def find_missing_founders(records):
    """Return list of (row_index, company_name, linkedin_url) for rows missing founders."""
    missing = []
    for i, record in enumerate(records):
        founders = record.get('Founders', '').strip()
        if not founders:
            company = record.get('Organization Name', '').strip()
            linkedin = record.get('LinkedIn', '').strip()
            if company and linkedin:
                missing.append((i, company, linkedin))
            elif company:
                print(f"  WARNING: {company} has no LinkedIn URL — skipping")
    return missing


def load_checkpoint():
    if os.path.exists(CHECKPOINT_FILE):
        with open(CHECKPOINT_FILE) as f:
            return json.load(f)
    return {}


def save_checkpoint(data):
    os.makedirs('.tmp', exist_ok=True)
    with open(CHECKPOINT_FILE, 'w') as f:
        json.dump(data, f, indent=2)


def normalize_linkedin_url(url):
    """Normalize a LinkedIn company URL."""
    url = url.strip().rstrip('/')
    if not url.startswith('http'):
        url = 'https://' + url
    url = url.replace('://www.linkedin.com', '://linkedin.com')
    return url


def extract_company_slug(url):
    """Extract the company slug from a LinkedIn company URL for exact matching."""
    url = normalize_linkedin_url(url)
    # Pattern: https://linkedin.com/company/SLUG or .../company/SLUG/...
    parts = url.split('/company/')
    if len(parts) > 1:
        return parts[1].split('/')[0].lower().rstrip('/')
    return url.lower()


def scrape_company_employees(linkedin_urls, company_map):
    """
    Scrape employees from LinkedIn company pages using harvestapi/linkedin-company-employees.

    linkedin_urls: list of LinkedIn company URLs
    company_map: {normalized_url: company_name}

    Returns: {company_name: [{"firstName": ..., "lastName": ..., "title": ...}, ...]}
    """
    api_token = os.getenv("APIFY_API_TOKEN")
    if not api_token:
        print("Error: APIFY_API_TOKEN not found in .env", file=sys.stderr)
        sys.exit(1)

    client = ApifyClient(api_token)

    # Build slug-based lookup for exact matching
    slug_to_company = {}
    for url, name in company_map.items():
        slug = extract_company_slug(url)
        slug_to_company[slug] = name

    # Process one company at a time to ensure accurate matching
    all_results = {}

    for batch_num, url in enumerate(linkedin_urls, 1):
        total_batches = len(linkedin_urls)
        batch_urls = [url]
        company_name = company_map.get(url, 'unknown')

        print(f"  [{batch_num}/{total_batches}] Scraping {company_name}...")

        run_input = {
            "companies": batch_urls,
            "profileScraperMode": "Short ($4 per 1k)",
            "companyBatchMode": "all_at_once",
            "maxItems": 25,
        }

        try:
            run = client.actor("harvestapi/linkedin-company-employees").call(run_input=run_input)
        except Exception as e:
            print(f"  Error in batch {batch_num}: {e}")
            continue

        if not run:
            print(f"  Batch {batch_num} failed to start")
            continue

        results = list(client.dataset(run["defaultDatasetId"]).iterate_items())
        print(f"  Batch {batch_num}: Got {len(results)} employee profiles")

        # Group results by company using currentPositions companyLinkedinUrl
        # (In all_at_once mode, _meta.query.currentCompanies lists ALL companies,
        # so we must match via the employee's actual current position instead)
        for item in results:
            matched_company = None
            matched_title = ''

            for pos in item.get('currentPositions', []):
                comp_url = pos.get('companyLinkedinUrl', '')
                if comp_url:
                    slug = extract_company_slug(comp_url)
                    if slug in slug_to_company:
                        matched_company = slug_to_company[slug]
                        matched_title = pos.get('title', '')
                        break

            # Fallback for profiles without companyLinkedinUrl:
            # use _meta only if there's exactly one company in the query
            if not matched_company:
                query_companies = item.get('_meta', {}).get('query', {}).get('currentCompanies', [])
                if len(query_companies) == 1:
                    slug = extract_company_slug(query_companies[0])
                    if slug in slug_to_company:
                        matched_company = slug_to_company[slug]
                        positions = item.get('currentPositions', [])
                        if positions:
                            matched_title = positions[0].get('title', '')

            if not matched_company:
                continue

            first_name = item.get('firstName', '').strip()
            last_name = item.get('lastName', '').strip()
            title = matched_title

            if first_name:
                if matched_company not in all_results:
                    all_results[matched_company] = []
                all_results[matched_company].append({
                    'firstName': first_name,
                    'lastName': last_name,
                    'title': title,
                    'linkedinUrl': item.get('linkedinUrl', ''),
                })

        if batch_num < total_batches:
            time.sleep(2)

    return all_results


def filter_founders(employees_by_company):
    """
    Filter employee results to only founders/co-founders.
    Returns: {company_name: ["First Last", ...]}
    """
    founders_by_company = {}

    for company, employees in employees_by_company.items():
        founders = []
        for emp in employees:
            title = emp.get('title', '')
            if is_founder_title(title):
                full_name = f"{emp['firstName']} {emp['lastName']}".strip()
                if full_name:
                    founders.append(full_name)

        if founders:
            founders_by_company[company] = founders

    return founders_by_company


def split_founder_name(full_name):
    """Split a full name into (first_name, last_name)."""
    parts = full_name.split()
    if len(parts) == 0:
        return ('', '')
    elif len(parts) == 1:
        return (parts[0], '')
    else:
        return (parts[0], ' '.join(parts[1:]))


def update_sheet_founders(worksheet, headers, founder_results, row_mapping):
    """
    Write founder data back to the sheet.
    founder_results: {company_name: ["Full Name 1", "Full Name 2", ...]}
    row_mapping: {company_name: row_index}
    """
    MAX_FOUNDERS = 5

    founders_col = headers.index('Founders') + 1 if 'Founders' in headers else None

    split_cols = {}
    for i in range(1, MAX_FOUNDERS + 1):
        fn_name = f'Founder {i} First Name'
        ln_name = f'Founder {i} Last Name'
        if fn_name in headers and ln_name in headers:
            split_cols[i] = {
                'first': headers.index(fn_name) + 1,
                'last': headers.index(ln_name) + 1,
            }

    if not founders_col and not split_cols:
        print("Error: Could not find Founders columns in sheet", file=sys.stderr)
        return

    updates = []
    for company, founders in founder_results.items():
        row_indices = row_mapping.get(company, [])
        if not row_indices:
            continue
        for row_idx in row_indices:
            row = row_idx + 2  # +1 for header, +1 for 1-based

            # Update combined Founders column
            if founders_col and founders:
                combined = ', '.join(founders)
                updates.append(gspread.Cell(row, founders_col, combined))

            # Update split columns
            for i in range(1, MAX_FOUNDERS + 1):
                if i in split_cols:
                    if i <= len(founders):
                        first, last = split_founder_name(founders[i - 1])
                        updates.append(gspread.Cell(row, split_cols[i]['first'], first))
                        updates.append(gspread.Cell(row, split_cols[i]['last'], last))

    if not updates:
        print("No founder data to update.")
        return

    batch_size = 1000
    for start in range(0, len(updates), batch_size):
        batch = updates[start:start + batch_size]
        worksheet.update_cells(batch, value_input_option='RAW')
        print(f"  Updated cells {start + 1}-{start + len(batch)}")
        if start + batch_size < len(updates):
            time.sleep(1)

    print(f"Successfully updated {len(updates)} cells for {len(founder_results)} companies.")


def main():
    parser = argparse.ArgumentParser(description="Find missing founder names via LinkedIn company employees")
    parser.add_argument("--sheet_url", required=True, help="Google Sheet URL")
    parser.add_argument("--worksheet", help="Worksheet name")
    parser.add_argument("--test", action="store_true", help="Run on first 3 companies only")
    parser.add_argument("--resume", action="store_true", help="Resume from checkpoint")
    parser.add_argument("--dry_run", action="store_true", help="Scrape but don't write to sheet")

    args = parser.parse_args()

    # Step 1: Read sheet
    print("=== Step 1: Reading Google Sheet ===")
    worksheet, records, headers = read_sheet(args.sheet_url, args.worksheet)

    # Step 2: Find rows missing founders
    missing = find_missing_founders(records)
    print(f"Companies missing founders: {len(missing)}")

    if not missing:
        print("All companies have founder data. Nothing to do.")
        return

    if args.test:
        missing = missing[:3]
        print(f"TEST MODE: Limited to {len(missing)} companies")

    for _, name, linkedin in missing:
        print(f"  - {name} ({linkedin})")

    # Step 3: Load checkpoint
    checkpoint = load_checkpoint()
    if args.resume:
        missing = [(i, n, l) for i, n, l in missing if n not in checkpoint]
        print(f"After resume filter: {len(missing)} remaining")

    if not missing:
        print("All companies already in checkpoint.")
        return

    # Build lookup maps
    linkedin_urls = []
    company_map = {}  # {normalized_url: company_name}
    row_mapping = {}  # {company_name: [row_indices]}

    for row_idx, company, linkedin in missing:
        norm_url = normalize_linkedin_url(linkedin)
        linkedin_urls.append(norm_url)
        company_map[norm_url] = company
        row_mapping.setdefault(company, []).append(row_idx)

    # Step 4: Scrape employees from LinkedIn
    print(f"\n=== Step 2: Scraping LinkedIn company employees ===")
    employees_by_company = scrape_company_employees(linkedin_urls, company_map)

    print(f"\nGot employee data for {len(employees_by_company)} companies")
    for company, employees in employees_by_company.items():
        print(f"  {company}: {len(employees)} employees found")

    # Step 5: Filter to founders only
    print(f"\n=== Step 3: Filtering for founders/co-founders ===")
    founder_results = filter_founders(employees_by_company)

    # Also check all employees for companies where no founder title was found
    # (sometimes founders have CEO/CTO title without "founder")
    for company in list(employees_by_company.keys()):
        if company not in founder_results:
            employees = employees_by_company[company]
            # Log all titles for manual review
            titles = [f"{e['firstName']} {e['lastName']} - {e['title']}" for e in employees]
            print(f"  {company}: No founder titles found. Employees: {titles}")

    # Update checkpoint
    for company, founders in founder_results.items():
        checkpoint[company] = founders
    # Mark companies with no founders found
    for row_idx, company, _ in missing:
        if company not in checkpoint:
            checkpoint[company] = []
    save_checkpoint(checkpoint)

    # Summary of findings
    for company, founders in founder_results.items():
        print(f"  {company}: {', '.join(founders)}")

    no_founders = [n for _, n, _ in missing if n not in founder_results]
    if no_founders:
        print(f"\n  No founders found for: {', '.join(no_founders)}")

    # Step 6: Write back to sheet
    if founder_results and not args.dry_run:
        print(f"\n=== Step 4: Updating Google Sheet ===")
        update_sheet_founders(worksheet, headers, founder_results, row_mapping)
    elif args.dry_run:
        print(f"\n=== DRY RUN: Would update {len(founder_results)} companies ===")

    # Final summary
    print(f"\n=== Summary ===")
    print(f"Companies searched: {len(missing)}")
    print(f"Founders found: {len(founder_results)}")
    print(f"Still missing: {len(no_founders)}")
    if no_founders:
        print(f"\nCompanies needing manual lookup:")
        for company in no_founders:
            print(f"  - {company}")


if __name__ == "__main__":
    main()
