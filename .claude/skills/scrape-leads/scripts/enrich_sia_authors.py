#!/usr/bin/env python3
"""
Enrich LinkedIn post authors with full profile data + company domain via Apify.

Input:  .tmp/sia_post_authors.json   (output of scrape_linkedin_posts.py)
Output: .tmp/sia_leads_enriched.json

Usage:
  python3 enrich_sia_authors.py \
    --input .tmp/sia_post_authors.json \
    --output .tmp/sia_leads_enriched.json

  # Test on 5 records first:
  python3 enrich_sia_authors.py --input .tmp/sia_post_authors.json --test
"""

import os
import sys
import json
import argparse
import time
from urllib.parse import urlparse
from dotenv import load_dotenv
from apify_client import ApifyClient

load_dotenv()

PROFILE_ACTOR = "dev_fusion/Linkedin-Profile-Scraper"
COMPANY_ACTOR = "dev_fusion/Linkedin-Company-Scraper"
DEFAULT_BATCH = 5


def normalize_url(url):
    if not url:
        return ""
    return url.strip().rstrip("/").replace("://www.linkedin.com", "://linkedin.com")


def extract_domain(url):
    if not url:
        return ""
    try:
        parsed = urlparse(url if "://" in url else "https://" + url)
        return parsed.netloc.lstrip("www.")
    except Exception:
        return ""


def scrape_profiles(urls, batch_num, total, client):
    normalized = [normalize_url(u) for u in urls]
    print(f"  Profile batch {batch_num}/{total}: {len(urls)} profiles...")

    try:
        run = client.actor(PROFILE_ACTOR).call(run_input={"profileUrls": normalized})
    except Exception as e:
        print(f"  Error: {e}")
        return {}

    if not run:
        print(f"  Batch {batch_num} failed to start")
        return {}

    items = list(client.dataset(run["defaultDatasetId"]).iterate_items())
    out = {}
    for item in items:
        url = normalize_url(
            item.get("linkedinUrl") or item.get("url") or item.get("profileUrl") or ""
        )
        first = (item.get("firstName") or "").strip()
        last = (item.get("lastName") or "").strip()
        headline = (item.get("headline") or item.get("title") or "").strip()
        company = (
            item.get("companyName") or
            item.get("currentCompany") or
            item.get("positions", [{}])[0].get("companyName", "") if item.get("positions") else ""
        )
        company_url = (item.get("companyLinkedinUrl") or item.get("currentCompanyUrl") or "").strip()

        record = {
            "first_name": first,
            "last_name": last,
            "job_title": headline,
            "company_name": str(company).strip(),
            "company_linkedin_url": company_url,
        }

        if url:
            out[url] = record
        elif len(normalized) == 1:
            out[normalized[0]] = record

    print(f"  Got {len(out)} profiles enriched")
    return out


def scrape_companies(urls, batch_num, total, client):
    normalized = [normalize_url(u) for u in urls]
    print(f"  Company batch {batch_num}/{total}: {len(urls)} companies...")

    try:
        run = client.actor(COMPANY_ACTOR).call(run_input={"profileUrls": normalized})
    except Exception as e:
        print(f"  Error: {e}")
        return {}

    if not run:
        print(f"  Batch {batch_num} failed to start")
        return {}

    items = list(client.dataset(run["defaultDatasetId"]).iterate_items())
    out = {}
    for item in items:
        url = normalize_url(
            item.get("url") or item.get("companyUrl") or item.get("linkedinUrl") or ""
        )
        website = (item.get("website") or item.get("companyWebsite") or "").strip()
        domain = extract_domain(website)

        record = {"company_domain": domain, "company_website": website}
        if url:
            out[url] = record
        elif len(normalized) == 1:
            out[normalized[0]] = record

    print(f"  Got {len(out)} companies enriched")
    return out


def main():
    parser = argparse.ArgumentParser(description="Enrich LinkedIn post authors with profile + company data")
    parser.add_argument("--input", default=".tmp/sia_post_authors.json")
    parser.add_argument("--output", default=".tmp/sia_leads_enriched.json")
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH)
    parser.add_argument("--test", action="store_true", help="Only process first 5 authors")
    args = parser.parse_args()

    api_token = os.getenv("APIFY_API_TOKEN")
    if not api_token:
        print("Error: APIFY_API_TOKEN not set", file=sys.stderr)
        sys.exit(1)

    with open(args.input) as f:
        authors = json.load(f)

    if args.test:
        authors = authors[:5]
        print(f"TEST MODE: processing {len(authors)} authors")
    else:
        print(f"Loaded {len(authors)} authors from {args.input}")

    client = ApifyClient(api_token)

    # Step 1: enrich profiles
    profile_urls = [a["linkedin_url"] for a in authors if a.get("linkedin_url")]
    unique_profile_urls = list(dict.fromkeys(profile_urls))
    print(f"\n=== Step 1: Enriching {len(unique_profile_urls)} LinkedIn profiles ===")

    profile_data = {}
    batches = [unique_profile_urls[i:i + args.batch_size]
               for i in range(0, len(unique_profile_urls), args.batch_size)]
    for i, batch in enumerate(batches, 1):
        profile_data.update(scrape_profiles(batch, i, len(batches), client))
        if i < len(batches):
            time.sleep(2)

    # Step 2: collect company LinkedIn URLs from enriched profiles → enrich companies
    company_urls = []
    for url in unique_profile_urls:
        p = profile_data.get(normalize_url(url), {})
        cu = p.get("company_linkedin_url", "")
        if cu:
            company_urls.append(cu)
    unique_company_urls = list(dict.fromkeys(company_urls))
    print(f"\n=== Step 2: Enriching {len(unique_company_urls)} company pages ===")

    company_data = {}
    if unique_company_urls:
        batches = [unique_company_urls[i:i + args.batch_size]
                   for i in range(0, len(unique_company_urls), args.batch_size)]
        for i, batch in enumerate(batches, 1):
            company_data.update(scrape_companies(batch, i, len(batches), client))
            if i < len(batches):
                time.sleep(2)

    # Step 3: merge
    results = []
    for author in authors:
        record = dict(author)
        url = normalize_url(author.get("linkedin_url", ""))
        profile = profile_data.get(url, {})

        if profile:
            record["first_name"] = profile.get("first_name") or record.get("first_name", "")
            record["last_name"] = profile.get("last_name") or record.get("last_name", "")
            record["job_title"] = profile.get("job_title") or record.get("job_title", "")
            record["company_name"] = profile.get("company_name") or record.get("company_name", "")
            record["company_linkedin_url"] = profile.get("company_linkedin_url", "")

        co_url = normalize_url(record.get("company_linkedin_url", ""))
        company = company_data.get(co_url, {})
        record["company_domain"] = company.get("company_domain", "")
        record["company_website"] = company.get("company_website", "")
        record["email"] = ""

        results.append(record)

    os.makedirs(".tmp", exist_ok=True)
    with open(args.output, "w") as f:
        json.dump(results, f, indent=2)

    enriched_count = sum(1 for r in results if r.get("company_domain"))
    print(f"\n=== Done ===")
    print(f"Total records: {len(results)}")
    print(f"With company domain: {enriched_count}")
    print(f"Saved → {args.output}")


if __name__ == "__main__":
    main()
