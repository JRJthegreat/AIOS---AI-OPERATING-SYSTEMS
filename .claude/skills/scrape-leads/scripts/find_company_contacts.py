#!/usr/bin/env python3
"""
For company-page leads (firms with no individual contact), pull employees from each
company's LinkedIn page, then keep only decision-makers (buying authority for a
client-acquisition vendor).

Reuses:
- find_founders.scrape_company_employees  (proven employee scrape + company matching)
- classify_decision_makers.classify_one    (DM/NOT seniority filter)

Each output record carries the firm's enriched fields (size, location, website, bio,
post_url) so the new contacts slot straight into the decision-makers tab.

Usage:
  python3 find_company_contacts.py \
    --input .tmp/list_a_decision_makers.company_pages.json \
    --output .tmp/list_a_company_contacts.json
  # add --test to run on the first 3 firms only
"""

import os
import sys
import json
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from find_founders import scrape_company_employees, normalize_linkedin_url
from classify_decision_makers import classify_one, make_client

load_dotenv()

MAX_WORKERS = 10


def main():
    parser = argparse.ArgumentParser(description="Find decision-maker contacts at company-page firms")
    parser.add_argument("--input", required=True, help="company_pages JSON")
    parser.add_argument("--output", default=".tmp/list_a_company_contacts.json")
    parser.add_argument("--test", action="store_true", help="First 3 firms only")
    args = parser.parse_args()

    with open(args.input) as f:
        firms = json.load(f)
    if args.test:
        firms = firms[:3]

    # Build inputs for the employee scraper, keyed by company LinkedIn URL
    linkedin_urls, company_map, firm_by_name = [], {}, {}
    for firm in firms:
        url = firm.get("linkedin_url", "")
        name = firm.get("company_name", "")
        if not url or not name:
            continue
        norm = normalize_linkedin_url(url)
        linkedin_urls.append(norm)
        company_map[norm] = name
        firm_by_name[name] = firm

    print(f"Scraping employees for {len(linkedin_urls)} firms...")
    employees_by_company = scrape_company_employees(linkedin_urls, company_map)

    # Build candidate contact records, inheriting each firm's enriched fields
    candidates = []
    for company, emps in employees_by_company.items():
        firm = firm_by_name.get(company, {})
        for e in emps:
            if not e.get("firstName"):
                continue
            candidates.append({
                "first_name": e.get("firstName", ""),
                "last_name": e.get("lastName", ""),
                "job_title": e.get("title", ""),
                "company_name": company,
                "company_size": firm.get("company_size", ""),
                "company_location": firm.get("company_location", ""),
                "company_website": firm.get("company_website", ""),
                "company_bio": firm.get("company_bio", ""),
                "linkedin_url": e.get("linkedinUrl", ""),
                "post_url": firm.get("post_url", ""),
                "post_snippet": firm.get("post_snippet", ""),
                "post_date": firm.get("post_date", ""),
                "email": "",
            })

    print(f"Found {len(candidates)} total employees across firms")
    if not candidates:
        json.dump([], open(args.output, "w"))
        print("No candidates to classify.")
        return

    # Filter to decision-makers
    print(f"Classifying {len(candidates)} for buying authority...")
    client = make_client()
    deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT_FAST") or os.getenv("AZURE_OPENAI_DEPLOYMENT")
    decisions = {}
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = [ex.submit(classify_one, client, deployment, i, c)
                   for i, c in enumerate(candidates)]
        for fut in as_completed(futures):
            idx, decision = fut.result()
            decisions[idx] = decision

    dms = [c for i, c in enumerate(candidates) if decisions.get(i) == "DM"]

    # Dedup by person LinkedIn URL
    seen, deduped = set(), []
    for c in dms:
        key = (c.get("linkedin_url") or (c["first_name"] + c["last_name"])).lower()
        if key not in seen:
            seen.add(key)
            deduped.append(c)

    # Report per-firm coverage
    firms_with = {c["company_name"] for c in deduped}
    print(f"\n{'='*40}")
    print(f"Decision-makers found: {len(deduped)} across {len(firms_with)} firms")
    missing = [f["company_name"] for f in firms if f["company_name"] not in firms_with]
    if missing:
        print(f"No DM found for {len(missing)} firms: {', '.join(missing[:10])}{'...' if len(missing) > 10 else ''}")

    json.dump(deduped, open(args.output, "w"), indent=2)
    print(f"Saved → {args.output}")


if __name__ == "__main__":
    main()
