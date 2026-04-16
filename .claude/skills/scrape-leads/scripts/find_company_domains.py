#!/usr/bin/env python3
"""
Find company domains for a list of UK recruitment companies in a Google Sheet.

Uses Apify's Google Search scraper to search each company name,
then extracts the domain from the top organic result.
Validates domains via HTTP HEAD requests.
"""

import os
import sys
import json
import argparse
import time
import asyncio
from urllib.parse import urlparse
from dotenv import load_dotenv
from apify_client import ApifyClient
import gspread
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

load_dotenv()

# Domains to skip when extracting from search results
EXCLUDED_DOMAINS = {
    'linkedin.com', 'facebook.com', 'twitter.com', 'instagram.com',
    'indeed.com', 'glassdoor.com', 'reed.co.uk', 'totaljobs.com',
    'youtube.com', 'wikipedia.org', 'crunchbase.com', 'endole.co.uk',
    'companies-house.gov.uk', 'companieshouse.gov.uk',
    'google.com', 'google.co.uk', 'bing.com',
    'pinterest.com', 'tiktok.com', 'reddit.com',
    'amazon.com', 'amazon.co.uk', 'ebay.com', 'ebay.co.uk',
    'yell.com', 'yelp.com', 'trustpilot.com',
    'cv-library.co.uk', 'monster.co.uk', 'monster.com',
    'cwjobs.co.uk', 'jobsite.co.uk', 's1jobs.com',
    'checkatrade.com', 'bark.com', 'thebestof.co.uk',
    'apple.com', 'apps.apple.com', 'play.google.com',
    'bloomberg.com', 'ft.com', 'bbc.co.uk', 'theguardian.com',
}

CHECKPOINT_FILE = '.tmp/domains_checkpoint.json'
SEARCH_QUERY_SUFFIX = "UK recruitment agency"


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


def read_companies(sheet_url, worksheet_name=None, company_column=None):
    """Read company names from a Google Sheet. Returns (worksheet, records, company_col_name, website_col_index)."""
    creds = get_credentials()
    client = gspread.authorize(creds)
    sheet_id = extract_sheet_id(sheet_url)
    spreadsheet = client.open_by_key(sheet_id)

    if worksheet_name:
        worksheet = spreadsheet.worksheet(worksheet_name)
    else:
        # Try to find worksheet by gid from URL
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

    # Find company name column
    if company_column:
        col_name = company_column
    else:
        candidates = ['Company Name', 'company_name', 'Company', 'company', 'companyName']
        col_name = None
        for c in candidates:
            if c in headers:
                col_name = c
                break
        if not col_name:
            print(f"Error: Could not find company name column. Headers: {headers}", file=sys.stderr)
            sys.exit(1)

    # Find or note Website column index (1-based for gspread)
    website_col_name = 'Website'
    if website_col_name in headers:
        website_col_idx = headers.index(website_col_name) + 1
    else:
        website_col_idx = None

    print(f"Found {len(records)} rows. Company column: '{col_name}'. Website column index: {website_col_idx}")
    return worksheet, records, col_name, website_col_idx


def load_checkpoint():
    """Load checkpoint of already-found domains. Always returns {company: domain_string}."""
    if os.path.exists(CHECKPOINT_FILE):
        with open(CHECKPOINT_FILE) as f:
            data = json.load(f)
        # Normalize: if values are dicts (from a previous validated run), extract domain strings
        normalized = {}
        for k, v in data.items():
            if isinstance(v, dict):
                normalized[k] = v.get('domain', '')
            else:
                normalized[k] = v
        return normalized
    return {}


def save_checkpoint(domains):
    """Save checkpoint to disk. Expects {company: domain_string}."""
    os.makedirs('.tmp', exist_ok=True)
    with open(CHECKPOINT_FILE, 'w') as f:
        json.dump(domains, f, indent=2)


def extract_domain(url):
    """Extract clean domain from a URL."""
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        if not domain:
            parsed = urlparse('https://' + url)
            domain = parsed.netloc.lower()
        if domain.startswith('www.'):
            domain = domain[4:]
        return domain
    except Exception:
        return None


def is_excluded(domain):
    """Check if domain is in the exclusion list."""
    if not domain:
        return True
    for excluded in EXCLUDED_DOMAINS:
        if domain == excluded or domain.endswith('.' + excluded):
            return True
    return False


def pick_best_domain(organic_results):
    """Pick the best domain from Google search organic results."""
    for result in organic_results:
        url = result.get('url') or result.get('link') or ''
        domain = extract_domain(url)
        if domain and not is_excluded(domain):
            return domain
    return None


def search_domains_batch(company_names, batch_num, total_batches):
    """Run Apify Google Search for a batch of company names."""
    api_token = os.getenv("APIFY_API_TOKEN")
    if not api_token:
        print("Error: APIFY_API_TOKEN not found in .env", file=sys.stderr)
        sys.exit(1)

    client = ApifyClient(api_token)

    # Build queries
    queries = [f"{name} {SEARCH_QUERY_SUFFIX}" for name in company_names]

    run_input = {
        "queries": "\n".join(queries),
        "maxPagesPerQuery": 1,
        "resultsPerPage": 5,
        "languageCode": "en",
        "countryCode": "gb",
        "mobileResults": False,
        "includeUnfilteredResults": False,
    }

    print(f"  Batch {batch_num}/{total_batches}: Searching {len(company_names)} companies...")

    try:
        run = client.actor("apify/google-search-scraper").call(run_input=run_input)
    except Exception as e:
        print(f"  Error in batch {batch_num}: {e}")
        return {}

    if not run:
        print(f"  Batch {batch_num} failed to start")
        return {}

    # Collect results
    results = list(client.dataset(run["defaultDatasetId"]).iterate_items())

    # Build a lookup from query term -> company name
    query_to_company = {}
    for name in company_names:
        query_to_company[f"{name} {SEARCH_QUERY_SUFFIX}"] = name

    # Map results back to company names by matching searchQuery.term
    domains = {}
    for result in results:
        query_term = result.get('searchQuery', {}).get('term', '')
        company = query_to_company.get(query_term)
        if not company:
            # Log unmatched results for debugging — don't guess
            print(f"  WARNING: Could not match query result back to company: '{query_term}'")
            continue
        organic = result.get('organicResults', [])
        domain = pick_best_domain(organic)
        if domain:
            domains[company] = domain

    found = len(domains)
    print(f"  Batch {batch_num}: Found {found}/{len(company_names)} domains")
    return domains


async def validate_domains(domain_map):
    """Validate domains via HTTP HEAD requests. Returns dict with validation status."""
    try:
        import aiohttp
    except ImportError:
        print("aiohttp not installed. Install with: pip install aiohttp", file=sys.stderr)
        sys.exit(1)

    validated = {}
    semaphore = asyncio.Semaphore(50)

    async def check_domain(session, company, domain):
        async with semaphore:
            # Try HEAD first, then GET as fallback (some servers block HEAD)
            for method in ['head', 'get']:
                for scheme in ['https', 'http']:
                    url = f"{scheme}://{domain}"
                    try:
                        request_fn = session.head if method == 'head' else session.get
                        async with request_fn(url, timeout=aiohttp.ClientTimeout(total=5),
                                              allow_redirects=True) as resp:
                            if resp.status < 400:
                                final_domain = extract_domain(str(resp.url))
                                if final_domain and is_excluded(final_domain):
                                    break  # Treat as invalid
                                validated[company] = {
                                    'domain': final_domain or domain,
                                    'status': 'VERIFIED',
                                    'http_status': resp.status,
                                }
                                return
                    except Exception:
                        continue
            validated[company] = {
                'domain': domain,
                'status': 'INVALID',
                'http_status': None,
            }

    async with aiohttp.ClientSession() as session:
        tasks = [check_domain(session, company, domain) for company, domain in domain_map.items()]
        await asyncio.gather(*tasks)

    return validated


def update_sheet_domains(worksheet, records, col_name, website_col_idx, domain_map):
    """Write validated domains back to the Website column in the sheet."""
    if not website_col_idx:
        print("Error: No 'Website' column found in sheet", file=sys.stderr)
        return

    # Build cell updates
    updates = []
    for i, record in enumerate(records):
        company = record.get(col_name, '').strip()
        if company in domain_map:
            entry = domain_map[company]
            if entry.get('status') == 'VERIFIED':
                row = i + 2  # +1 for header, +1 for 1-based
                updates.append(gspread.Cell(row, website_col_idx, entry['domain']))

    if not updates:
        print("No domains to update.")
        return

    # Batch update
    batch_size = 1000
    for start in range(0, len(updates), batch_size):
        batch = updates[start:start + batch_size]
        worksheet.update_cells(batch, value_input_option='RAW')
        print(f"  Updated rows {start + 1}-{start + len(batch)} in sheet")
        if start + batch_size < len(updates):
            time.sleep(1)

    print(f"Successfully updated {len(updates)} domains in sheet.")


def main():
    parser = argparse.ArgumentParser(description="Find company domains via Google Search")
    parser.add_argument("--sheet_url", required=True, help="Google Sheet URL")
    parser.add_argument("--worksheet", help="Worksheet name")
    parser.add_argument("--column", help="Company name column")
    parser.add_argument("--batch_size", type=int, default=100, help="Queries per Apify run")
    parser.add_argument("--test", action="store_true", help="Run on first 5 companies only")
    parser.add_argument("--skip_validation", action="store_true", help="Skip HTTP validation")
    parser.add_argument("--resume", action="store_true", help="Resume from checkpoint")

    args = parser.parse_args()

    # Step 1: Read the sheet
    print("=== Step 1: Reading Google Sheet ===")
    worksheet, records, col_name, website_col_idx = read_companies(
        args.sheet_url, args.worksheet, args.column
    )

    # Step 2: Get unique company names that need domains
    companies_needing_domains = []
    seen = set()
    for record in records:
        company = record.get(col_name, '').strip()
        existing_website = record.get('Website', '').strip()
        if company and company not in seen and not existing_website:
            companies_needing_domains.append(company)
            seen.add(company)

    total_companies = len(seen)
    print(f"Companies needing domains: {total_companies}")

    if args.test:
        companies_needing_domains = companies_needing_domains[:5]
        print(f"TEST MODE: Limited to {len(companies_needing_domains)} companies")

    # Step 3: Load checkpoint if resuming
    all_domains = {}
    if args.resume:
        all_domains = load_checkpoint()
        companies_needing_domains = [c for c in companies_needing_domains if c not in all_domains]
        print(f"Resuming: {len(all_domains)} already found, {len(companies_needing_domains)} remaining")

    # Step 4: Search in batches via Apify
    if companies_needing_domains:
        print(f"\n=== Step 2: Searching domains via Apify Google Search ===")
        batches = []
        for i in range(0, len(companies_needing_domains), args.batch_size):
            batches.append(companies_needing_domains[i:i + args.batch_size])

        total_batches = len(batches)
        for batch_num, batch in enumerate(batches, 1):
            batch_domains = search_domains_batch(batch, batch_num, total_batches)
            all_domains.update(batch_domains)
            save_checkpoint(all_domains)

        print(f"\nSearch complete: {len(all_domains)} domains found")

    # Step 5: Validate domains
    if not args.skip_validation and all_domains:
        print(f"\n=== Step 3: Validating {len(all_domains)} domains via HTTP ===")
        validated = asyncio.run(validate_domains(all_domains))

        verified = sum(1 for v in validated.values() if v['status'] == 'VERIFIED')
        invalid = sum(1 for v in validated.values() if v['status'] == 'INVALID')
        print(f"Validation: {verified} VERIFIED, {invalid} INVALID")
    elif all_domains:
        validated = {k: {'domain': v, 'status': 'VERIFIED'} for k, v in all_domains.items()}
    else:
        validated = {}

    # Step 6: Write back to sheet
    if validated:
        print(f"\n=== Step 4: Updating Google Sheet ===")
        update_sheet_domains(worksheet, records, col_name, website_col_idx, validated)

    # Summary
    print(f"\n=== Summary ===")
    verified_count = sum(1 for v in validated.values() if v.get('status') == 'VERIFIED')
    invalid_count = sum(1 for v in validated.values() if v.get('status') == 'INVALID')
    not_found = total_companies - len(all_domains)
    print(f"Total unique companies: {total_companies}")
    print(f"Domains found: {len(all_domains)}")
    print(f"Verified (written to sheet): {verified_count}")
    print(f"Invalid (not written): {invalid_count}")
    print(f"Not found: {not_found}")


if __name__ == "__main__":
    main()
