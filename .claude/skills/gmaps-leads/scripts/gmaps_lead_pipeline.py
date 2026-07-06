#!/usr/bin/env python3
"""
Google Maps Lead Generation Pipeline

End-to-end pipeline that:
1. Scrapes Google Maps for businesses matching search criteria
2. Enriches each business by scraping their website for contact info
3. Uses Claude to extract structured contact data
4. Saves everything to a persistent Google Sheet

Usage:
    python3 execution/gmaps_lead_pipeline.py --search "plumbers in Austin TX" --limit 10
    python3 execution/gmaps_lead_pipeline.py --search "dentists" --location "Miami FL" --limit 25 --sheet-url "https://..."
"""

import os
import re
import sys
import json
import argparse
import hashlib
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv

import gspread
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

# Import our modules
from scrape_google_maps import scrape_google_maps
from extract_website_contacts import scrape_website_contacts

load_dotenv()

# Google Sheets config
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

# Default sheet name for leads
DEFAULT_SHEET_NAME = "GMaps Lead Database"

# Lead schema - columns for the Google Sheet
LEAD_COLUMNS = [
    "lead_id",
    "scraped_at",
    "search_query",
    # Business basics from Google Maps
    "business_name",
    "category",
    "address",
    "city",
    "state",
    "zip_code",
    "country",
    "phone",
    "website",
    "google_maps_url",
    "place_id",
    # Ratings & reviews
    "rating",
    "review_count",
    "price_level",
    # Extracted contact info
    "emails",
    "additional_phones",
    "business_hours",
    # Social media
    "facebook",
    "twitter",
    "linkedin",
    "instagram",
    "youtube",
    "tiktok",
    # Owner/key person info
    "owner_name",
    "owner_title",
    "owner_email",
    "owner_phone",
    "owner_linkedin",
    # Team contacts (JSON string for multiple people)
    "team_contacts",
    # Additional data
    "additional_contact_methods",
    "pages_scraped",
    "search_enriched",
    "enrichment_status",
]


def generate_lead_id(business_name: str, address: str) -> str:
    """Generate a unique ID for a lead based on name and address."""
    unique_string = f"{business_name}|{address}".lower()
    return hashlib.md5(unique_string.encode()).hexdigest()[:12]


def stringify_value(value) -> str:
    """Convert any value to a string suitable for Google Sheets."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (list, tuple)):
        # Filter out None values and convert to comma-separated string
        return ", ".join(str(v) for v in value if v)
    if isinstance(value, dict):
        # Convert dict to a readable string format
        parts = []
        for k, v in value.items():
            if v:
                parts.append(f"{k}: {v}")
        return "; ".join(parts) if parts else ""
    return str(value)


def parse_address(address: str) -> dict:
    """Parse an address string into components."""
    # Simple parsing - not perfect but handles common US formats
    parts = {
        "city": "",
        "state": "",
        "zip_code": "",
        "country": "USA"
    }

    if not address:
        return parts

    # Try to extract zip code
    import re
    zip_match = re.search(r'\b(\d{5}(?:-\d{4})?)\b', address)
    if zip_match:
        parts["zip_code"] = zip_match.group(1)

    # Try to extract state (2-letter code)
    state_match = re.search(r'\b([A-Z]{2})\b', address)
    if state_match:
        parts["state"] = state_match.group(1)

    # City is harder - take the part before the state
    if parts["state"]:
        city_match = re.search(rf',\s*([^,]+),?\s*{parts["state"]}', address)
        if city_match:
            parts["city"] = city_match.group(1).strip()

    return parts


def flatten_lead(gmaps_data: dict, contacts: dict, search_query: str) -> dict:
    """
    Flatten Google Maps data and extracted contacts into a single lead record.

    Args:
        gmaps_data: Raw data from Google Maps scraper
        contacts: Extracted contact data from website
        search_query: Original search query

    Returns:
        Flattened dictionary matching LEAD_COLUMNS schema
    """
    # Parse address components
    address = gmaps_data.get("address", "")
    addr_parts = parse_address(address)

    # Extract social media
    social = contacts.get("social_media", {}) or {}

    # Extract owner info
    owner = contacts.get("owner_info", {}) or {}

    # Format team contacts as JSON string
    team = contacts.get("team_members", []) or []
    team_json = json.dumps(team) if team else ""

    # Format lists as comma-separated strings
    emails = contacts.get("emails", []) or []
    phones = contacts.get("phone_numbers", []) or []
    additional_contacts = contacts.get("additional_contacts", []) or []

    # Generate lead ID
    lead_id = generate_lead_id(
        gmaps_data.get("title", ""),
        address
    )

    # Determine enrichment status
    enrichment_status = "success" if emails or owner.get("email") else "partial"
    if contacts.get("error"):
        enrichment_status = f"error: {contacts.get('error')}"

    return {
        "lead_id": lead_id,
        "scraped_at": datetime.now().isoformat(),
        "search_query": search_query,
        # Business basics
        "business_name": gmaps_data.get("title", ""),
        "category": gmaps_data.get("categoryName", ""),
        "address": address,
        "city": addr_parts["city"] or gmaps_data.get("city", ""),
        "state": addr_parts["state"] or gmaps_data.get("state", ""),
        "zip_code": addr_parts["zip_code"] or gmaps_data.get("postalCode", ""),
        "country": gmaps_data.get("countryCode", "USA"),
        "phone": gmaps_data.get("phone", ""),
        "website": gmaps_data.get("website", ""),
        "google_maps_url": gmaps_data.get("url", ""),
        "place_id": gmaps_data.get("placeId", ""),
        # Ratings
        "rating": gmaps_data.get("totalScore", ""),
        "review_count": gmaps_data.get("reviewsCount", ""),
        "price_level": gmaps_data.get("price", ""),
        # Extracted contacts
        "emails": stringify_value(emails),
        "additional_phones": stringify_value(phones),
        "business_hours": stringify_value(contacts.get("business_hours", "")),
        # Social media
        "facebook": stringify_value(social.get("facebook", "")),
        "twitter": stringify_value(social.get("twitter", "")),
        "linkedin": stringify_value(social.get("linkedin", "")),
        "instagram": stringify_value(social.get("instagram", "")),
        "youtube": stringify_value(social.get("youtube", "")),
        "tiktok": stringify_value(social.get("tiktok", "")),
        # Owner info
        "owner_name": stringify_value(owner.get("name", "")),
        "owner_title": stringify_value(owner.get("title", "")),
        "owner_email": stringify_value(owner.get("email", "")),
        "owner_phone": stringify_value(owner.get("phone", "")),
        "owner_linkedin": stringify_value(owner.get("linkedin", "")),
        # Team
        "team_contacts": team_json,
        # Additional
        "additional_contact_methods": stringify_value(additional_contacts),
        "pages_scraped": contacts.get("_pages_scraped", 0),
        "search_enriched": "yes" if contacts.get("_search_enriched") else "no",
        "enrichment_status": enrichment_status,
    }


def get_credentials():
    """Get OAuth2 credentials for Google Sheets API."""
    creds = None

    if os.path.exists('token.json'):
        try:
            with open('token.json', 'r') as token:
                token_data = json.load(token)
                creds = Credentials.from_authorized_user_info(token_data, SCOPES)
        except Exception as e:
            print(f"Error loading token: {e}")

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            from google_auth_oauthlib.flow import InstalledAppFlow
            creds_file = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "credentials.json")
            flow = InstalledAppFlow.from_client_secrets_file(creds_file, SCOPES)
            creds = flow.run_local_server(port=0)

        with open('token.json', 'w') as token:
            token.write(creds.to_json())

    return creds


def _init_worksheet_headers(worksheet):
    """Write header row, bold it, freeze it."""
    worksheet.update(values=[LEAD_COLUMNS], range_name='A1')
    worksheet.format('A1:AK1', {
        "textFormat": {"bold": True},
        "backgroundColor": {"red": 0.9, "green": 0.9, "blue": 0.9}
    })
    worksheet.freeze(rows=1)


def get_or_create_sheet(sheet_url: str = None, sheet_name: str = None,
                        worksheet_name: str = None) -> tuple:
    """
    Get existing sheet or create a new one. If worksheet_name is given, leads
    go to that tab (created if missing) so one spreadsheet can hold multiple
    categories.

    Returns:
        Tuple of (spreadsheet, worksheet, is_new)
    """
    creds = get_credentials()
    client = gspread.authorize(creds)

    if sheet_url:
        # Open existing sheet by URL
        if '/d/' in sheet_url:
            sheet_id = sheet_url.split('/d/')[1].split('/')[0]
        else:
            sheet_id = sheet_url

        spreadsheet = client.open_by_key(sheet_id)
        is_new = False
        print(f"Opened existing sheet: {spreadsheet.title}")
    else:
        name = sheet_name or DEFAULT_SHEET_NAME
        spreadsheet = client.create(name)
        is_new = True
        print(f"Created new sheet: {name}")
        print(f"Sheet URL: {spreadsheet.url}")

    if worksheet_name:
        try:
            worksheet = spreadsheet.worksheet(worksheet_name)
        except gspread.exceptions.WorksheetNotFound:
            if is_new:
                worksheet = spreadsheet.sheet1
                worksheet.update_title(worksheet_name)
            else:
                worksheet = spreadsheet.add_worksheet(
                    title=worksheet_name, rows=2000, cols=len(LEAD_COLUMNS))
            _init_worksheet_headers(worksheet)
    else:
        worksheet = spreadsheet.sheet1
        if is_new:
            _init_worksheet_headers(worksheet)

    return spreadsheet, worksheet, is_new


def get_existing_lead_ids(worksheet) -> set:
    """Get all existing lead IDs from the sheet to avoid duplicates."""
    try:
        # Get all values in column A (lead_id)
        lead_ids = worksheet.col_values(1)
        return set(lead_ids[1:])  # Skip header
    except Exception:
        return set()


def append_leads_to_sheet(worksheet, leads: list[dict], existing_ids: set) -> int:
    """
    Append new leads to the sheet, skipping duplicates.

    Returns:
        Number of leads added
    """
    # Filter out duplicates
    new_leads = [lead for lead in leads if lead["lead_id"] not in existing_ids]

    if not new_leads:
        print("No new leads to add (all duplicates)")
        return 0

    # Convert to rows
    rows = []
    for lead in new_leads:
        row = [lead.get(col, "") for col in LEAD_COLUMNS]
        rows.append(row)

    # Batch append
    worksheet.append_rows(rows, value_input_option='RAW')

    print(f"Added {len(new_leads)} new leads to sheet")
    return len(new_leads)


def enrich_businesses(businesses: list[dict], max_workers: int = 3) -> list[dict]:
    """
    Enrich businesses with website contact information.

    Args:
        businesses: List of business dicts from Google Maps
        max_workers: Parallel workers for website scraping

    Returns:
        List of dicts with added contact information
    """
    print(f"\nEnriching {len(businesses)} businesses with website data...")

    enriched = []

    # Filter to only businesses with websites
    with_websites = [b for b in businesses if b.get("website")]
    without_websites = [b for b in businesses if not b.get("website")]

    print(f"  {len(with_websites)} have websites, {len(without_websites)} do not")

    # Process businesses without websites
    for business in without_websites:
        enriched.append({
            "gmaps": business,
            "contacts": {"error": "No website available"}
        })

    # Process businesses with websites in parallel
    if with_websites:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_business = {
                executor.submit(
                    scrape_website_contacts,
                    business.get("website"),
                    business.get("title")
                ): business
                for business in with_websites
            }

            for i, future in enumerate(as_completed(future_to_business), 1):
                business = future_to_business[future]
                try:
                    contacts = future.result()
                    enriched.append({
                        "gmaps": business,
                        "contacts": contacts
                    })
                    print(f"  [{i}/{len(with_websites)}] Enriched: {business.get('title')}")
                except Exception as e:
                    print(f"  [{i}/{len(with_websites)}] Error enriching {business.get('title')}: {e}")
                    enriched.append({
                        "gmaps": business,
                        "contacts": {"error": str(e)}
                    })

    return enriched


def run_pipeline(
    search_query: str,
    max_results: int = 10,
    location: str = None,
    sheet_url: str = None,
    sheet_name: str = None,
    worksheet_name: str = None,
    include_regex: str = None,
    exclude_regex: str = None,
    require_website: bool = False,
    min_stars: str = None,
    from_raw: str = None,
    workers: int = 3,
    save_intermediate: bool = True,
) -> dict:
    """
    Run the full lead generation pipeline.

    Args:
        search_query: What to search for on Google Maps
        max_results: Maximum number of businesses to scrape
        location: Optional location filter
        sheet_url: Existing Google Sheet URL (creates new if not provided)
        sheet_name: Name for new sheet (if creating)
        workers: Parallel workers for website enrichment
        save_intermediate: Whether to save intermediate JSON files

    Returns:
        Dictionary with pipeline results
    """
    results = {
        "search_query": search_query,
        "started_at": datetime.now().isoformat(),
        "businesses_found": 0,
        "leads_enriched": 0,
        "leads_added": 0,
        "sheet_url": None,
        "errors": []
    }

    # Step 1: Scrape Google Maps
    print(f"\n{'='*60}")
    print(f"STEP 1: Scraping Google Maps for '{search_query}'")
    print(f"{'='*60}")

    if from_raw:
        with open(from_raw) as f:
            businesses = json.load(f)
        print(f"Loaded {len(businesses)} businesses from {from_raw} (no scrape)")
    else:
        businesses = scrape_google_maps(
            search_query=search_query,
            max_results=max_results,
            location=location,
            website_filter="withWebsite" if require_website else None,
            min_stars=min_stars,
        )

    if not businesses:
        results["errors"].append("No businesses found on Google Maps")
        return results

    results["businesses_found"] = len(businesses)
    print(f"Found {len(businesses)} businesses")

    # Drop noise rows by name/category BEFORE paying for enrichment
    if include_regex or exclude_regex:
        def _keep(b):
            text = f"{b.get('title', '')} {b.get('categoryName', '')}"
            if include_regex and not re.search(include_regex, text, re.I):
                return False
            if exclude_regex and re.search(exclude_regex, text, re.I):
                return False
            return True

        before = len(businesses)
        businesses = [b for b in businesses if _keep(b)]
        print(f"Noise filter: dropped {before - len(businesses)}, {len(businesses)} remain")

    # Rows without a website can't be enriched or emailed - optionally drop them
    if require_website:
        before = len(businesses)
        businesses = [b for b in businesses if b.get("website")]
        print(f"Website filter: dropped {before - len(businesses)}, {len(businesses)} remain")

    results["businesses_kept"] = len(businesses)
    if not businesses:
        results["errors"].append("All results dropped by filters")
        return results

    # Save intermediate results
    if save_intermediate:
        os.makedirs(".tmp", exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        with open(f".tmp/gmaps_raw_{timestamp}.json", "w") as f:
            json.dump(businesses, f, indent=2)

    # Open the sheet and drop already-scraped places BEFORE paying for enrichment
    try:
        spreadsheet, worksheet, is_new = get_or_create_sheet(sheet_url, sheet_name, worksheet_name)
        results["sheet_url"] = spreadsheet.url
        existing_ids = get_existing_lead_ids(worksheet)
    except Exception as e:
        results["errors"].append(f"Google Sheets error: {str(e)}")
        print(f"Error opening sheet: {e}")
        return results

    if existing_ids:
        before = len(businesses)
        businesses = [b for b in businesses
                      if generate_lead_id(b.get("title", ""), b.get("address", "")) not in existing_ids]
        print(f"Dedupe vs sheet: {before - len(businesses)} already present, {len(businesses)} to enrich")
        if not businesses:
            print("Nothing new to enrich.")
            return results

    # In from-raw mode, max_results caps AFTER dedupe: take the best-rated slice
    if from_raw and max_results and len(businesses) > max_results:
        businesses.sort(key=lambda b: (float(b.get("totalScore") or 0),
                                       int(b.get("reviewsCount") or 0)), reverse=True)
        businesses = businesses[:max_results]
        print(f"Capped to top {max_results} by rating/reviews")

    # Step 2: Enrich with website data
    print(f"\n{'='*60}")
    print(f"STEP 2: Enriching businesses with website contact data")
    print(f"{'='*60}")

    enriched = enrich_businesses(businesses, max_workers=workers)
    results["leads_enriched"] = len(enriched)

    # Step 3: Flatten to lead records
    print(f"\n{'='*60}")
    print(f"STEP 3: Processing lead records")
    print(f"{'='*60}")

    recorded_query = f"{search_query} [{location}]" if location else search_query
    leads = []
    for item in enriched:
        lead = flatten_lead(item["gmaps"], item["contacts"], recorded_query)
        leads.append(lead)

    # Save intermediate enriched data
    if save_intermediate:
        with open(f".tmp/leads_enriched_{timestamp}.json", "w") as f:
            json.dump(leads, f, indent=2)

    # Step 4: Save to Google Sheet
    print(f"\n{'='*60}")
    print(f"STEP 4: Saving to Google Sheet")
    print(f"{'='*60}")

    try:
        # Re-read ids in case another run appended while we were enriching
        existing_ids = get_existing_lead_ids(worksheet)
        added = append_leads_to_sheet(worksheet, leads, existing_ids)
        results["leads_added"] = added

    except Exception as e:
        results["errors"].append(f"Google Sheets error: {str(e)}")
        print(f"Error saving to sheet: {e}")

    # Summary
    results["completed_at"] = datetime.now().isoformat()

    print(f"\n{'='*60}")
    print("PIPELINE COMPLETE")
    print(f"{'='*60}")
    print(f"Businesses found: {results['businesses_found']}")
    print(f"Leads enriched: {results['leads_enriched']}")
    print(f"New leads added: {results['leads_added']}")
    if results["sheet_url"]:
        print(f"Sheet URL: {results['sheet_url']}")
    if results["errors"]:
        print(f"Errors: {results['errors']}")

    return results


def main():
    parser = argparse.ArgumentParser(
        description="Google Maps Lead Generation Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic search
  python3 execution/gmaps_lead_pipeline.py --search "plumbers in Austin TX" --limit 10

  # With specific location
  python3 execution/gmaps_lead_pipeline.py --search "dentists" --location "Miami FL" --limit 25

  # Append to existing sheet
  python3 execution/gmaps_lead_pipeline.py --search "lawyers" --limit 10 --sheet-url "https://docs.google.com/spreadsheets/d/..."
        """
    )

    parser.add_argument("--search", required=True, help="Search query for Google Maps")
    parser.add_argument("--limit", type=int, default=10, help="Max results to scrape (default: 10)")
    parser.add_argument("--location", help="Location to focus search")
    parser.add_argument("--sheet-url", help="Existing Google Sheet URL to append to")
    parser.add_argument("--sheet-name", help="Name for new sheet (if not using existing)")
    parser.add_argument("--tab", help="Worksheet/tab name inside the sheet (created if missing)")
    parser.add_argument("--include", help="Case-insensitive regex; keep only rows whose name/category matches")
    parser.add_argument("--exclude", help="Case-insensitive regex; drop rows whose name/category matches")
    parser.add_argument("--require-website", action="store_true", help="Drop rows without a website (actor-native filter)")
    parser.add_argument("--min-stars", help="Minimum Google rating, e.g. 4 or 4.5 (actor-native filter)")
    parser.add_argument("--from-raw", help="Skip scraping; load businesses from a raw JSON file (already-paid dataset)")
    parser.add_argument("--workers", type=int, default=3, help="Parallel workers for enrichment (default: 3)")
    parser.add_argument("--no-intermediate", action="store_true", help="Don't save intermediate JSON files")
    parser.add_argument("--json", action="store_true", help="Output results as JSON")

    args = parser.parse_args()

    results = run_pipeline(
        search_query=args.search,
        max_results=args.limit,
        location=args.location,
        sheet_url=args.sheet_url,
        sheet_name=args.sheet_name,
        worksheet_name=args.tab,
        include_regex=args.include,
        exclude_regex=args.exclude,
        require_website=args.require_website,
        min_stars=args.min_stars,
        from_raw=args.from_raw,
        workers=args.workers,
        save_intermediate=not args.no_intermediate,
    )

    if args.json:
        print(json.dumps(results, indent=2))

    # Exit with error if no leads were added
    if results["leads_added"] == 0 and results["errors"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
