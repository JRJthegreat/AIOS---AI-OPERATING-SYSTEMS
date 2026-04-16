#!/usr/bin/env python3
"""
Enrich leads in a Google Sheet with LinkedIn profile and company data via Apify.

Uses:
- dev_fusion/Linkedin-Profile-Scraper for profile summaries
- dev_fusion/Linkedin-Company-Scraper for company descriptions
"""

import os
import sys
import json
import argparse
import time
from dotenv import load_dotenv
from apify_client import ApifyClient
import gspread
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

load_dotenv()

CHECKPOINT_FILE = '.tmp/linkedin_enrichment_checkpoint.json'

# Column names for auto-detection
PROFILE_URL_CANDIDATES = [
    'Linkedin', 'LinkedIn', 'LinkedIn Profile', 'LinkedIn Profile URL',
    'linkedin_profile', 'Profile URL', 'LinkedIn URL', 'linkedin_url',
]
COMPANY_URL_CANDIDATES = [
    'company_linkedin_url', 'LinkedIn Company', 'LinkedIn Company URL',
    'Company LinkedIn', 'company_linkedin', 'LinkedIn Company Page',
]


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
            creds_file = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "credentials.json")
            flow = InstalledAppFlow.from_client_secrets_file(creds_file, scopes)
            creds = flow.run_local_server(port=0)
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
    return creds


def find_column(headers, candidates):
    """Find a column name from a list of candidates."""
    for c in candidates:
        if c in headers:
            return c
    return None


def read_leads(sheet_url, worksheet_name=None):
    """Read leads from Google Sheet. Returns (worksheet, records, headers)."""
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
    print(f"Read {len(records)} rows. Headers: {headers}")
    return worksheet, records, headers


def ensure_column(worksheet, headers, col_name):
    """Ensure a column exists in the sheet. Returns 1-based column index."""
    if col_name in headers:
        return headers.index(col_name) + 1
    # Append new column — expand grid if needed
    new_col_idx = len(headers) + 1
    if new_col_idx > worksheet.col_count:
        worksheet.resize(cols=new_col_idx)
    worksheet.update_cell(1, new_col_idx, col_name)
    headers.append(col_name)
    print(f"  Added new column '{col_name}' at position {new_col_idx}")
    return new_col_idx


def load_checkpoint():
    if os.path.exists(CHECKPOINT_FILE):
        with open(CHECKPOINT_FILE) as f:
            return json.load(f)
    return {'profiles': {}, 'companies': {}, 'errors': {}}


def save_checkpoint(data):
    os.makedirs('.tmp', exist_ok=True)
    with open(CHECKPOINT_FILE, 'w') as f:
        json.dump(data, f, indent=2)


def extract_profile_fields(item):
    """Extract profile summary/about from Apify result."""
    summary = (
        item.get('about') or
        item.get('summary') or
        item.get('description') or
        item.get('profileSummary') or
        ''
    )
    return {'description': str(summary).strip()}


def extract_company_fields(item):
    """Extract company description from Apify result."""
    description = (
        item.get('description') or
        item.get('about') or
        item.get('summary') or
        item.get('companyDescription') or
        ''
    )
    return {'description': str(description).strip()}


def normalize_linkedin_url(url):
    """Normalize a LinkedIn URL for consistent matching."""
    url = url.strip().rstrip('/')
    if url.startswith('http://'):
        url = 'https://' + url[7:]
    # Remove www. for consistent matching
    url = url.replace('://www.linkedin.com', '://linkedin.com')
    return url


def scrape_linkedin_profiles(profile_urls, batch_num, total_batches):
    """Scrape LinkedIn profiles via Apify. Returns {url: {description: ...}}."""
    api_token = os.getenv("APIFY_API_TOKEN")
    if not api_token:
        print("Error: APIFY_API_TOKEN not found", file=sys.stderr)
        sys.exit(1)

    client = ApifyClient(api_token)
    urls_input = [normalize_linkedin_url(u) for u in profile_urls]

    run_input = {
        "profileUrls": urls_input,
    }

    print(f"  Profile batch {batch_num}/{total_batches}: Scraping {len(profile_urls)} profiles...")

    try:
        run = client.actor("dev_fusion/Linkedin-Profile-Scraper").call(run_input=run_input)
    except Exception as e:
        print(f"  Error in profile batch {batch_num}: {e}")
        return {}

    if not run:
        print(f"  Profile batch {batch_num} failed to start")
        return {}

    results = list(client.dataset(run["defaultDatasetId"]).iterate_items())
    print(f"  Profile batch {batch_num}: Got {len(results)} results")

    # Map results back to input URLs
    profile_data = {}
    for item in results:
        # Try to match result back to input URL
        result_url = (
            item.get('linkedinUrl') or
            item.get('url') or
            item.get('profileUrl') or
            item.get('linkedin_url') or
            ''
        )
        if result_url:
            result_url = normalize_linkedin_url(result_url)

        fields = extract_profile_fields(item)
        if fields['description']:
            if result_url:
                profile_data[result_url] = fields
            elif len(urls_input) == 1:
                # Single URL batch — safe to assume it's the one we sent
                profile_data[urls_input[0]] = fields

    print(f"  Profile batch {batch_num}: Extracted {len(profile_data)} descriptions")
    return profile_data


def scrape_linkedin_companies(company_urls, batch_num, total_batches):
    """Scrape LinkedIn companies via Apify. Returns {url: {description: ...}}."""
    api_token = os.getenv("APIFY_API_TOKEN")
    if not api_token:
        print("Error: APIFY_API_TOKEN not found", file=sys.stderr)
        sys.exit(1)

    client = ApifyClient(api_token)
    urls_input = [normalize_linkedin_url(u) for u in company_urls]

    run_input = {
        "profileUrls": urls_input,
    }

    print(f"  Company batch {batch_num}/{total_batches}: Scraping {len(company_urls)} companies...")

    try:
        run = client.actor("dev_fusion/Linkedin-Company-Scraper").call(run_input=run_input)
    except Exception as e:
        print(f"  Error in company batch {batch_num}: {e}")
        return {}

    if not run:
        print(f"  Company batch {batch_num} failed to start")
        return {}

    results = list(client.dataset(run["defaultDatasetId"]).iterate_items())
    print(f"  Company batch {batch_num}: Got {len(results)} results")

    company_data = {}
    for item in results:
        result_url = (
            item.get('url') or
            item.get('companyUrl') or
            item.get('linkedinUrl') or
            item.get('linkedin_url') or
            ''
        )
        if result_url:
            result_url = normalize_linkedin_url(result_url)

        fields = extract_company_fields(item)
        if fields['description']:
            if result_url:
                company_data[result_url] = fields
            elif len(urls_input) == 1:
                company_data[urls_input[0]] = fields

    print(f"  Company batch {batch_num}: Extracted {len(company_data)} descriptions")
    return company_data


def update_sheet_enrichment(worksheet, records, profile_url_col, company_url_col,
                            desc_col_idx, company_desc_col_idx,
                            profile_data, company_data):
    """Write enriched data back to the sheet."""
    updates = []

    for i, record in enumerate(records):
        row = i + 2  # 1-based + header

        # Profile description
        if profile_url_col and desc_col_idx:
            url = record.get(profile_url_col, '').strip()
            if url:
                normalized = normalize_linkedin_url(url)
                data = profile_data.get(normalized)
                if data and data.get('description'):
                    updates.append(gspread.Cell(row, desc_col_idx, data['description']))

        # Company description
        if company_url_col and company_desc_col_idx:
            url = record.get(company_url_col, '').strip()
            if url:
                normalized = normalize_linkedin_url(url)
                data = company_data.get(normalized)
                if data and data.get('description'):
                    updates.append(gspread.Cell(row, company_desc_col_idx, data['description']))

    if not updates:
        print("No data to update in sheet.")
        return

    # Batch update in chunks of 1000
    batch_size = 1000
    for start in range(0, len(updates), batch_size):
        batch = updates[start:start + batch_size]
        worksheet.update_cells(batch, value_input_option='RAW')
        print(f"  Updated cells {start + 1}-{start + len(batch)}")
        if start + batch_size < len(updates):
            time.sleep(1)

    print(f"Successfully updated {len(updates)} cells in sheet.")


def main():
    parser = argparse.ArgumentParser(description="Enrich leads with LinkedIn data via Apify")
    parser.add_argument("--sheet_url", required=True, help="Google Sheet URL")
    parser.add_argument("--worksheet", help="Worksheet name")
    parser.add_argument("--batch_size", type=int, default=5, help="URLs per Apify run (default: 5)")
    parser.add_argument("--test", action="store_true", help="Run on first 3 rows only")
    parser.add_argument("--resume", action="store_true", help="Resume from checkpoint")
    parser.add_argument("--skip_profiles", action="store_true", help="Skip profile scraping")
    parser.add_argument("--skip_companies", action="store_true", help="Skip company scraping")

    args = parser.parse_args()

    # Step 1: Read sheet
    print("=== Step 1: Reading Google Sheet ===")
    worksheet, records, headers = read_leads(args.sheet_url, args.worksheet)

    # Auto-detect columns
    profile_url_col = find_column(headers, PROFILE_URL_CANDIDATES)
    company_url_col = find_column(headers, COMPANY_URL_CANDIDATES)

    if not profile_url_col and not args.skip_profiles:
        print(f"Warning: No LinkedIn profile URL column found. Skipping profiles.")
        args.skip_profiles = True
    if not company_url_col and not args.skip_companies:
        print(f"Warning: No LinkedIn company URL column found. Skipping companies.")
        args.skip_companies = True

    if args.skip_profiles and args.skip_companies:
        print("Nothing to scrape. Exiting.")
        return

    print(f"Profile URL column: {profile_url_col}")
    print(f"Company URL column: {company_url_col}")

    # Ensure output columns exist
    desc_col_idx = None
    company_desc_col_idx = None
    if not args.skip_profiles:
        desc_col_idx = ensure_column(worksheet, headers, 'Description')
    if not args.skip_companies:
        company_desc_col_idx = ensure_column(worksheet, headers, 'Company Description')

    # Step 2: Identify rows needing enrichment
    profiles_to_scrape = []
    companies_to_scrape = []

    for i, record in enumerate(records):
        if not args.skip_profiles and profile_url_col:
            url = record.get(profile_url_col, '').strip()
            already = record.get('Description', '').strip()
            if url and not already:
                profiles_to_scrape.append(url)

        if not args.skip_companies and company_url_col:
            url = record.get(company_url_col, '').strip()
            already = record.get('Company Description', '').strip()
            if url and not already:
                companies_to_scrape.append(url)

    # Deduplicate
    unique_profiles = list(dict.fromkeys(profiles_to_scrape))
    unique_companies = list(dict.fromkeys(companies_to_scrape))

    if args.test:
        unique_profiles = unique_profiles[:3]
        unique_companies = unique_companies[:3]
        print("TEST MODE: Limited to 3 URLs each")

    print(f"Profiles to scrape: {len(unique_profiles)} unique URLs")
    print(f"Companies to scrape: {len(unique_companies)} unique URLs")

    # Step 3: Load checkpoint
    checkpoint = load_checkpoint()
    if args.resume:
        unique_profiles = [u for u in unique_profiles
                          if normalize_linkedin_url(u) not in checkpoint['profiles']
                          and normalize_linkedin_url(u) not in checkpoint['errors']]
        unique_companies = [u for u in unique_companies
                           if normalize_linkedin_url(u) not in checkpoint['companies']
                           and normalize_linkedin_url(u) not in checkpoint['errors']]
        print(f"After resume filter - Profiles: {len(unique_profiles)}, Companies: {len(unique_companies)}")

    # Step 4: Scrape profiles
    if unique_profiles:
        print(f"\n=== Step 2: Scraping {len(unique_profiles)} LinkedIn profiles ===")
        batches = [unique_profiles[i:i + args.batch_size]
                   for i in range(0, len(unique_profiles), args.batch_size)]
        for batch_num, batch in enumerate(batches, 1):
            batch_results = scrape_linkedin_profiles(batch, batch_num, len(batches))
            checkpoint['profiles'].update(batch_results)
            for url in batch:
                norm = normalize_linkedin_url(url)
                if norm not in batch_results:
                    checkpoint['errors'][norm] = 'no_data_returned'
            save_checkpoint(checkpoint)
            if batch_num < len(batches):
                time.sleep(2)

    # Step 5: Scrape companies
    if unique_companies:
        print(f"\n=== Step 3: Scraping {len(unique_companies)} LinkedIn companies ===")
        batches = [unique_companies[i:i + args.batch_size]
                   for i in range(0, len(unique_companies), args.batch_size)]
        for batch_num, batch in enumerate(batches, 1):
            batch_results = scrape_linkedin_companies(batch, batch_num, len(batches))
            checkpoint['companies'].update(batch_results)
            for url in batch:
                norm = normalize_linkedin_url(url)
                if norm not in batch_results:
                    checkpoint['errors'][norm] = 'no_data_returned'
            save_checkpoint(checkpoint)
            if batch_num < len(batches):
                time.sleep(2)

    # Step 6: Write back to sheet
    all_profiles = checkpoint.get('profiles', {})
    all_companies = checkpoint.get('companies', {})

    if all_profiles or all_companies:
        print(f"\n=== Step 4: Updating Google Sheet ===")
        update_sheet_enrichment(
            worksheet, records,
            profile_url_col, company_url_col,
            desc_col_idx, company_desc_col_idx,
            all_profiles, all_companies
        )

    # Summary
    print(f"\n=== Summary ===")
    print(f"Profiles scraped: {len(checkpoint.get('profiles', {}))}")
    print(f"Companies scraped: {len(checkpoint.get('companies', {}))}")
    print(f"Errors: {len(checkpoint.get('errors', {}))}")


if __name__ == "__main__":
    main()
