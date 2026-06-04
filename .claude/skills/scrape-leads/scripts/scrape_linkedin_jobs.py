#!/usr/bin/env python3
"""
Scrape LinkedIn's unauthenticated Jobs Guest API to find healthcare staffing
companies actively posting jobs in the last 7 days.

This uses LinkedIn's public /jobs-guest/ endpoint — no login required.
Output: JSON list of unique company names + job counts (warm activity signal).

Pattern from build-scrapers/03-api-scraper.md
"""

import json
import time
import argparse
import re
import sys
from datetime import datetime
from urllib.parse import urlencode

import requests

LINKEDIN_JOBS_URL = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

# Healthcare staffing queries — cast wide net across sub-niches
DEFAULT_QUERIES = [
    "travel nurse recruiter",
    "locum tenens recruiter",
    "allied health staffing",
    "per diem nursing agency",
    "physician recruitment",
    "healthcare travel staffing",
    "CNA recruiter staffing",
    "nursing agency recruiter",
]

# f_TPR codes (time filter)
TIME_FILTERS = {
    "day":   "r86400",
    "3days": "r259200",
    "week":  "r604800",
    "month": "r2592000",
}


def build_url(query: str, location: str, start: int, time_filter: str) -> str:
    params = {
        "keywords": query,
        "start": start,
    }
    if location:
        params["location"] = location
    if time_filter:
        params["f_TPR"] = time_filter
    return f"{LINKEDIN_JOBS_URL}?{urlencode(params)}"


def decode_entities(text: str) -> str:
    if not text:
        return ""
    return (text
            .replace("&amp;", "&")
            .replace("&lt;", "<")
            .replace("&gt;", ">")
            .replace("&quot;", '"')
            .replace("&#39;", "'")
            .replace("&nbsp;", " ")
            .strip())


def extract_between(html: str, class_name: str, end_marker: str = "<") -> str:
    idx = html.find(class_name)
    if idx == -1:
        return ""
    tag_close = html.find(">", idx)
    if tag_close == -1:
        return ""
    start = tag_close + 1
    end = html.find(end_marker, start)
    return html[start:end].strip() if end != -1 else html[start:].strip()


def extract_company(html: str) -> str:
    subtitle_idx = html.find("base-search-card__subtitle")
    if subtitle_idx == -1:
        return ""
    region = html[subtitle_idx:subtitle_idx + 500]
    match = re.search(r"<a[^>]*>([^<]+)</a>", region)
    if match:
        return match.group(1).strip()
    # Fallback: text between > and <
    tag_close = region.find(">")
    if tag_close != -1:
        text_start = tag_close + 1
        text_end = region.find("<", text_start)
        if text_end != -1:
            return region[text_start:text_end].strip()
    return ""


def parse_job_cards(html: str, query: str) -> list[dict]:
    jobs = []
    # Split on card boundaries
    chunks = re.split(r'(?=<(?:li|div)[^>]*class="[^"]*base-card[^"]*")', html)
    for chunk in chunks:
        if "base-card" not in chunk:
            continue
        company = decode_entities(extract_company(chunk))
        title = decode_entities(extract_between(chunk, "base-search-card__title"))
        if not company:
            continue
        jobs.append({
            "company_name": company,
            "latest_job_title": title,
            "search_query": query,
        })
    return jobs


def scrape_query(query: str, location: str, time_filter: str, max_per_query: int, delay: float) -> dict:
    """Returns {company_name: {job_count, latest_job_title, search_queries}}."""
    companies: dict[str, dict] = {}
    start = 0
    consecutive_empty = 0
    page_size = 25

    while len(companies) < max_per_query and consecutive_empty < 3:
        url = build_url(query, location, start, time_filter)
        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
        except requests.RequestException as e:
            print(f"  Request error at start={start}: {e}", file=sys.stderr)
            break

        if resp.status_code == 429:
            print(f"  Rate limited — waiting 30s", file=sys.stderr)
            time.sleep(30)
            continue

        if not resp.ok:
            print(f"  HTTP {resp.status_code} at start={start}, stopping", file=sys.stderr)
            break

        html = resp.text
        if len(html.strip()) < 100:
            consecutive_empty += 1
            start += page_size
            time.sleep(delay)
            continue

        cards = parse_job_cards(html, query)
        if not cards:
            consecutive_empty += 1
            start += page_size
            time.sleep(delay)
            continue

        consecutive_empty = 0
        for card in cards:
            name = card["company_name"]
            if not name:
                continue
            key = name.lower().strip()
            if key in companies:
                companies[key]["job_count"] += 1
            else:
                companies[key] = {
                    "company_name": name,
                    "job_count": 1,
                    "latest_job_title": card["latest_job_title"],
                    "search_queries": [query],
                }
            if query not in companies[key]["search_queries"]:
                companies[key]["search_queries"].append(query)

        start += page_size
        time.sleep(delay)

    return companies


def main():
    parser = argparse.ArgumentParser(description="Scrape LinkedIn Jobs Guest API for healthcare staffing companies")
    parser.add_argument("--queries", nargs="+", default=DEFAULT_QUERIES, help="Search queries")
    parser.add_argument("--location", default="United States", help="Location filter")
    parser.add_argument("--time-filter", default="week", choices=list(TIME_FILTERS.keys()), help="Time window for postings")
    parser.add_argument("--max-per-query", type=int, default=300, help="Max companies to collect per query")
    parser.add_argument("--delay", type=float, default=1.5, help="Seconds between page requests")
    parser.add_argument("--output", default=".tmp/source_c_linkedin_jobs.json", help="Output JSON file")
    args = parser.parse_args()

    import os
    os.makedirs(".tmp", exist_ok=True)

    time_filter_code = TIME_FILTERS[args.time_filter]
    all_companies: dict[str, dict] = {}

    for i, query in enumerate(args.queries):
        print(f"\n[{i+1}/{len(args.queries)}] Query: '{query}'")
        results = scrape_query(query, args.location, time_filter_code, args.max_per_query, args.delay)
        new_count = 0
        for key, data in results.items():
            if key in all_companies:
                all_companies[key]["job_count"] += data["job_count"]
                for q in data["search_queries"]:
                    if q not in all_companies[key]["search_queries"]:
                        all_companies[key]["search_queries"].append(q)
            else:
                all_companies[key] = data
                new_count += 1
        print(f"  Found {len(results)} companies ({new_count} new, {len(results)-new_count} already seen)")

    output = []
    for data in sorted(all_companies.values(), key=lambda x: -x["job_count"]):
        output.append({
            "company_name": data["company_name"],
            "job_count": data["job_count"],
            "latest_job_title": data["latest_job_title"],
            "search_queries": ", ".join(data["search_queries"]),
            "source": "linkedin_jobs",
            "date_scraped": datetime.now().strftime("%Y-%m-%d"),
        })

    with open(args.output, "w") as f:
        json.dump(output, f, indent=2)

    print(f"\nDone. {len(output)} unique companies → {args.output}")
    print(f"Top 10 by job count:")
    for r in output[:10]:
        print(f"  {r['company_name']}: {r['job_count']} jobs")


if __name__ == "__main__":
    main()
