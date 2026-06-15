#!/usr/bin/env python3
"""
Enrich leads with company data (bio, size, website, location) via Apify.

Two-stage flow:
  1. Personal profiles (/in/): dev_fusion/Linkedin-Profile-Scraper →
     company LinkedIn URL + person email/location/title.
  2. Companies (/company/): dev_fusion/Linkedin-Company-Scraper →
     bio, size, website, HQ location.

Company-page authors (linkedin_url already /company/) skip stage 1.

Usage:
  python3 enrich_company_data.py --input .tmp/list_a_classified.json --output .tmp/list_a_enriched.json
  python3 enrich_company_data.py --input .tmp/list_a_classified.json --test   # first 5 only
"""

import os
import sys
import json
import argparse
import time
from dotenv import load_dotenv
from apify_client import ApifyClient

load_dotenv()

PROFILE_ACTOR = "dev_fusion/Linkedin-Profile-Scraper"
COMPANY_ACTOR = "dev_fusion/Linkedin-Company-Scraper"
BATCH = 5


def company_token(url):
    """Reduce a company URL to its identifying slug/id token (lowercased)."""
    if not url or "/company/" not in url:
        return ""
    tok = url.split("/company/", 1)[1]
    tok = tok.split("/")[0]          # drop /posts, /about, trailing slash
    tok = tok.split("?")[0].strip().lower()
    return tok


def is_company_url(url):
    return bool(url) and "/company/" in url


def normalize_company_url(url):
    """Strip suffixes like /posts so the company scraper accepts it."""
    tok = company_token(url)
    return f"https://www.linkedin.com/company/{tok}" if tok else url


def format_size(item):
    rng = item.get("employeeCountRange") or {}
    start, end = rng.get("start"), rng.get("end")
    if start and end:
        return f"{start}-{end}"
    if start and not end:
        return f"{start}+"
    cnt = item.get("employeeCount")
    return str(cnt) if cnt else ""


def format_location(item):
    hq = item.get("headquarter") or {}
    parts = [hq.get("city"), hq.get("geographicArea"), hq.get("country")]
    return ", ".join(p for p in parts if p)


def batched(seq, n):
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def scrape_profiles(urls, client):
    """Return {profile_url_lower: {company_name, company_linkedin, job_title, email, location, about}}."""
    out = {}
    batches = list(batched(urls, BATCH))
    for bi, batch in enumerate(batches, 1):
        print(f"  Profile batch {bi}/{len(batches)} ({len(batch)} urls)...")
        try:
            run = client.actor(PROFILE_ACTOR).call(run_input={"profileUrls": batch})
            items = list(client.dataset(run["defaultDatasetId"]).iterate_items())
        except Exception as e:
            print(f"    Error: {e}")
            items = []
        for it in items:
            url = (it.get("linkedinUrl") or it.get("linkedinPublicUrl") or "").split("?")[0].rstrip("/").lower()
            if not url:
                continue
            out[url] = {
                "company_name": it.get("companyName") or "",
                "company_linkedin": it.get("companyLinkedin") or "",
                "job_title": it.get("jobTitle") or it.get("headline") or "",
                "email": it.get("email") or "",
                "location": it.get("addressWithCountry") or it.get("addressCountryOnly") or "",
            }
        if bi < len(batches):
            time.sleep(2)
    return out


def scrape_companies(urls, client):
    """Return token -> {company_bio, company_size, company_website, company_location}."""
    out = {}
    batches = list(batched(urls, BATCH))
    for bi, batch in enumerate(batches, 1):
        print(f"  Company batch {bi}/{len(batches)} ({len(batch)} urls)...")
        try:
            run = client.actor(COMPANY_ACTOR).call(run_input={"profileUrls": batch})
            items = list(client.dataset(run["defaultDatasetId"]).iterate_items())
        except Exception as e:
            print(f"    Error: {e}")
            items = []
        for it in items:
            data = {
                "company_bio": it.get("description") or "",
                "company_size": format_size(it),
                "company_website": it.get("websiteUrl") or "",
                "company_location": format_location(it),
            }
            # Key by every identifier the result exposes, so leads match by slug OR numeric id
            keys = set()
            if it.get("companyId"):
                keys.add(str(it["companyId"]).lower())
            if it.get("universalName"):
                keys.add(str(it["universalName"]).lower())
            keys.add(company_token(it.get("url") or ""))
            for k in keys:
                if k:
                    out[k] = data
        if bi < len(batches):
            time.sleep(2)
    return out


def main():
    parser = argparse.ArgumentParser(description="Enrich leads with company data")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", default=".tmp/list_a_enriched.json")
    parser.add_argument("--test", action="store_true", help="Process first 5 leads only")
    args = parser.parse_args()

    api_token = os.getenv("APIFY_API_TOKEN")
    if not api_token:
        print("Error: APIFY_API_TOKEN not set", file=sys.stderr)
        sys.exit(1)

    with open(args.input) as f:
        leads = json.load(f)
    if args.test:
        leads = leads[:5]
    print(f"Loaded {len(leads)} leads")

    client = ApifyClient(api_token)

    # Stage 1: personal profiles → company URL + person fields
    personal_urls = list({
        l["linkedin_url"].split("?")[0].rstrip("/")
        for l in leads
        if l.get("linkedin_url") and not is_company_url(l["linkedin_url"])
    })
    print(f"\n=== Stage 1: {len(personal_urls)} personal profiles ===")
    profile_data = scrape_profiles(personal_urls, client) if personal_urls else {}

    # Resolve each lead's company URL
    for lead in leads:
        url = (lead.get("linkedin_url") or "").split("?")[0].rstrip("/")
        if is_company_url(url):
            lead["_company_url"] = normalize_company_url(url)
        else:
            p = profile_data.get(url.lower(), {})
            if p:
                lead["company_name"] = p["company_name"] or lead.get("company_name", "")
                lead["job_title"] = lead.get("job_title") or p["job_title"]
                lead["email"] = p.get("email", "") or lead.get("email", "")
                lead["company_location"] = p.get("location", "")
                lead["_company_url"] = normalize_company_url(p["company_linkedin"])
            else:
                lead["_company_url"] = ""

    # Stage 2: companies → bio, size, website, HQ location
    company_urls = list({l["_company_url"] for l in leads if l.get("_company_url")})
    print(f"\n=== Stage 2: {len(company_urls)} unique companies ===")
    company_data = scrape_companies(company_urls, client) if company_urls else {}

    # Merge company data into leads
    for lead in leads:
        tok = company_token(lead.get("_company_url", ""))
        cdata = company_data.get(tok, {})
        lead["company_bio"] = cdata.get("company_bio", "")
        lead["company_size"] = cdata.get("company_size", "")
        lead["company_website"] = cdata.get("company_website", "")
        # Prefer company HQ location; fall back to person location from stage 1
        lead["company_location"] = cdata.get("company_location", "") or lead.get("company_location", "")

    # Final schema
    final = []
    for lead in leads:
        final.append({
            "first_name": lead.get("first_name", ""),
            "last_name": lead.get("last_name", ""),
            "job_title": lead.get("job_title", ""),
            "company_name": lead.get("company_name", ""),
            "linkedin_url": lead.get("linkedin_url", ""),
            "company_bio": lead.get("company_bio", ""),
            "company_size": lead.get("company_size", ""),
            "company_website": lead.get("company_website", ""),
            "company_location": lead.get("company_location", ""),
            "post_snippet": lead.get("post_snippet", ""),
            "post_date": lead.get("post_date", ""),
            "email": lead.get("email", ""),
        })

    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    with open(args.output, "w") as f:
        json.dump(final, f, indent=2)

    with_company = sum(1 for r in final if r["company_size"] or r["company_website"])
    print(f"\n=== Done ===")
    print(f"Total: {len(final)} | With company data: {with_company}")
    print(f"Saved → {args.output}")


if __name__ == "__main__":
    main()
