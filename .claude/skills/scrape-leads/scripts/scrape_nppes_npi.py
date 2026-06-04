#!/usr/bin/env python3
from __future__ import annotations
"""
Scrape the CMS NPPES NPI Registry for healthcare staffing/nursing care agencies.

Uses the free, unauthenticated NPI Registry REST API.
Taxonomy code 251J00000X = Nursing Care Agency (~8,000 registered orgs).
Also pulls 251B00000X (Psychiatric Residential Treatment Facility) and related.

No API key required. Output: JSON list of organizations.

Pattern from build-scrapers/05-government-data.md
"""

import json
import time
import argparse
import sys
from datetime import datetime

import requests

NPPES_API = "https://npiregistry.cms.hhs.gov/api/"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; research-bot/1.0)",
    "Accept": "application/json",
}

# Taxonomy codes for healthcare staffing organizations
TAXONOMY_CODES = [
    ("251J00000X", "Nursing Care Agency"),
    ("251B00000X", "Case Management Agency"),
    ("261QH0700X", "Health Maintenance Organization"),
    ("313M00000X", "Nursing Facility"),  # Excluded later — actual nursing homes
]

# Staffing-focused taxonomy queries (text search, not code)
TAXONOMY_QUERIES = [
    "Nursing Care",
    "Staffing Agency",
    "Home Health",
    "Allied Health",
]

# States to skip when filtering hospitals/facilities (we want agencies, not facilities)
FACILITY_KEYWORDS = {
    "hospital", "medical center", "health system", "health systems",
    "clinic", "pharmacy", "laboratory", "hospice", "assisted living",
    "rehabilitation", "rehab center", "nursing home", "skilled nursing",
    "long term care", "ltc", "surgery center", "diagnostic",
    "imaging center", "dialysis", "therapy center",
}

PAGE_SIZE = 200
DELAY = 0.5  # seconds between requests — CMS is permissive but be respectful


def is_likely_staffing_agency(org_name: str, taxonomy_desc: str = "") -> bool:  # noqa: ARG001
    name_lower = org_name.lower()
    # Keep if name contains staffing signals
    staffing_signals = {
        "staffing", "staff", "agency", "healthcare", "health care",
        "nursing", "nurse", "travel", "locum", "allied", "per diem",
        "placement", "recruitment", "recruiting", "solutions",
        "services", "resource", "medical", "clinical",
    }
    has_signal = any(s in name_lower for s in staffing_signals)
    has_facility = any(f in name_lower for f in FACILITY_KEYWORDS)
    # Keep if has signal and not clearly a facility
    return has_signal and not has_facility


def fetch_page(taxonomy_desc: str, skip: int) -> dict:
    params = {
        "version": "2.1",
        "enumeration_type": "NPI-2",
        "taxonomy_description": taxonomy_desc,
        "limit": PAGE_SIZE,
        "skip": skip,
    }
    resp = requests.get(NPPES_API, params=params, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.json()


def extract_record(result: dict) -> dict | None:
    basic = result.get("basic", {})
    org_name = basic.get("organization_name", "").strip()
    if not org_name:
        return None

    # Get taxonomy info
    taxonomies = result.get("taxonomies", [])
    taxonomy_desc = ""
    taxonomy_code = ""
    for t in taxonomies:
        if t.get("primary"):
            taxonomy_desc = t.get("description", "")
            taxonomy_code = t.get("code", "")
            break
    if not taxonomy_desc and taxonomies:
        taxonomy_desc = taxonomies[0].get("description", "")
        taxonomy_code = taxonomies[0].get("code", "")

    # Filter out obvious facilities
    if not is_likely_staffing_agency(org_name, taxonomy_desc):
        return None

    # Get address
    addresses = result.get("addresses", [])
    address = city = state = zip_code = phone = ""
    for addr in addresses:
        if addr.get("address_purpose") == "LOCATION":
            address = addr.get("address_1", "")
            city = addr.get("city", "").title()
            state = addr.get("state", "")
            zip_code = addr.get("postal_code", "")[:5]
            phone = addr.get("telephone_number", "")
            break
    if not address and addresses:
        a = addresses[0]
        address = a.get("address_1", "")
        city = a.get("city", "").title()
        state = a.get("state", "")
        zip_code = a.get("postal_code", "")[:5]
        phone = a.get("telephone_number", "")

    npi = result.get("number", "")

    return {
        "company_name": org_name.title(),
        "address": address.title(),
        "city": city,
        "state": state,
        "zip": zip_code,
        "phone": phone,
        "npi_number": npi,
        "taxonomy_code": taxonomy_code,
        "taxonomy_description": taxonomy_desc,
        "source": "nppes_npi",
        "date_scraped": datetime.now().strftime("%Y-%m-%d"),
    }


def scrape_taxonomy(taxonomy_query: str, max_records: int) -> list[dict]:
    records = []
    seen_npis: set[str] = set()
    skip = 0

    print(f"  Querying '{taxonomy_query}'...")
    while len(records) < max_records:
        try:
            data = fetch_page(taxonomy_query, skip)
        except requests.RequestException as e:
            print(f"  Error at skip={skip}: {e}", file=sys.stderr)
            break

        results = data.get("results", [])
        if not results:
            break

        for result in results:
            npi = result.get("number", "")
            if npi in seen_npis:
                continue
            seen_npis.add(npi)
            record = extract_record(result)
            if record:
                records.append(record)

        result_count = data.get("result_count", 0)
        skip += PAGE_SIZE
        if skip >= result_count:
            break
        time.sleep(DELAY)

    print(f"  → {len(records)} agencies extracted")
    return records


def main():
    parser = argparse.ArgumentParser(description="Scrape NPPES NPI Registry for healthcare staffing agencies")
    parser.add_argument("--queries", nargs="+", default=["Nursing Care", "Staffing Agency"],
                        help="Taxonomy description search terms")
    parser.add_argument("--max-per-query", type=int, default=5000, help="Max records per taxonomy query")
    parser.add_argument("--output", default=".tmp/source_d_nppes_npi.json", help="Output JSON file")
    parser.add_argument("--test", action="store_true", help="Test mode: fetch 1 page only")
    args = parser.parse_args()

    import os
    os.makedirs(".tmp", exist_ok=True)

    if args.test:
        args.max_per_query = PAGE_SIZE
        print("TEST MODE: fetching 1 page per query")

    all_records: list[dict] = []
    seen_npis: set[str] = set()

    for query in args.queries:
        records = scrape_taxonomy(query, args.max_per_query)
        new = 0
        for r in records:
            npi = r["npi_number"]
            if npi not in seen_npis:
                seen_npis.add(npi)
                all_records.append(r)
                new += 1
        if new != len(records):
            print(f"  Deduped: {len(records) - new} cross-query duplicates removed")

    with open(args.output, "w") as f:
        json.dump(all_records, f, indent=2)

    # State breakdown
    from collections import Counter
    states = Counter(r["state"] for r in all_records)
    print(f"\nDone. {len(all_records)} NPI agencies → {args.output}")
    print("Top states:", ", ".join(f"{s}:{c}" for s, c in states.most_common(10)))


if __name__ == "__main__":
    main()
