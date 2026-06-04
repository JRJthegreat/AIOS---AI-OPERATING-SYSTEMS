#!/usr/bin/env python3
from __future__ import annotations
"""
Scrape ASA (American Staffing Association) member directory for healthcare staffing firms.

The search interface is JS-rendered (Salesforce Experience Cloud).
Individual member profile pages are static HTML and contain:
  company name, address, phone, fax, website, job types

Strategy:
  1. Use Playwright to load the search page and filter by "Health Care" job type
  2. Collect all member profile URLs from the JS-rendered search results
  3. Use requests to scrape each static profile page (much faster than Playwright)

Confirmed profile URL pattern: /members-directory/[company-slug]-[salesforce-id]/

Pattern from build-scrapers/04-js-rendered-sites.md
"""

import json
import time
import argparse
import sys
import re
from datetime import datetime
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

ASA_BASE = "https://americanstaffing.net"
ASA_DIRECTORY = "https://americanstaffing.net/asa-member-directory/"
MEMBER_URL_PATTERN = re.compile(r"/members-directory/[a-z0-9\-]+-[a-z0-9]{15,}/", re.I)


def get_member_urls_playwright(test: bool = False) -> list[str]:
    """Use Playwright to get member profile URLs from the JS-rendered search."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("  [ASA] playwright not installed", file=sys.stderr)
        return []

    urls = set()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        )
        page = context.new_page()

        try:
            print("  [ASA] Loading member directory (JS-rendered)...")
            page.goto(ASA_DIRECTORY, wait_until="networkidle", timeout=45000)
            time.sleep(3)

            # Try to find and interact with the "Health Care" job type filter
            # ASA uses Salesforce Experience Cloud — filter may be a checkbox or dropdown
            try:
                # Look for "Health Care" filter option
                health_care_filter = page.query_selector("text=Health Care")
                if health_care_filter:
                    health_care_filter.click()
                    page.wait_for_load_state("networkidle", timeout=15000)
                    time.sleep(2)
                    print("  [ASA] Applied 'Health Care' filter")
            except Exception as e:
                print(f"  [ASA] Could not apply filter: {e} — scraping all members", file=sys.stderr)

            # Paginate through results
            page_count = 0
            max_pages = 3 if test else 100

            while page_count < max_pages:
                html = page.content()
                soup = BeautifulSoup(html, "lxml")

                # Extract member profile links
                new_urls = []
                for a in soup.find_all("a", href=MEMBER_URL_PATTERN):
                    href = a["href"]
                    if not href.startswith("http"):
                        href = ASA_BASE + href
                    if href not in urls:
                        urls.add(href)
                        new_urls.append(href)

                print(f"  [ASA] Page {page_count + 1}: {len(new_urls)} new profiles (total: {len(urls)})")

                if not new_urls and page_count > 0:
                    break

                # Try to go to next page
                next_btn = page.query_selector("[aria-label='Next'], .slds-button__next, a.next-page, [title='Next']")
                if not next_btn:
                    # Look for numbered pagination
                    current_page_el = page.query_selector(".current-page, [aria-current='page']")
                    if current_page_el:
                        try:
                            next_page = int(current_page_el.inner_text().strip()) + 1
                            next_btn = page.query_selector(f"[aria-label='{next_page}'], [title='{next_page}']")
                        except Exception:
                            pass

                if not next_btn:
                    break

                next_btn.click()
                page.wait_for_load_state("networkidle", timeout=15000)
                time.sleep(2)
                page_count += 1

        except Exception as e:
            print(f"  [ASA] Playwright error: {e}", file=sys.stderr)
        finally:
            browser.close()

    return list(urls)


def get_member_urls_static() -> list[str]:
    """Fallback: try to get member URLs from static HTML (may be limited)."""
    try:
        resp = requests.get(ASA_DIRECTORY, headers=HEADERS, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"  [ASA] Static fallback error: {e}", file=sys.stderr)
        return []

    soup = BeautifulSoup(resp.text, "lxml")
    urls = set()
    for a in soup.find_all("a", href=MEMBER_URL_PATTERN):
        href = a["href"]
        if not href.startswith("http"):
            href = ASA_BASE + href
        urls.add(href)

    return list(urls)


def scrape_profile(url: str) -> dict | None:
    """Scrape a single ASA member profile page (static HTML)."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        resp.raise_for_status()
    except requests.RequestException:
        return None

    soup = BeautifulSoup(resp.text, "lxml")

    # Company name — typically in h1 or prominent heading
    name = ""
    for el in soup.find_all(["h1", "h2"]):
        text = el.get_text(strip=True)
        if text and len(text) > 2 and len(text) < 200:
            name = text
            break

    if not name:
        return None

    # Extract structured fields — ASA profiles use definition lists or labeled fields
    fields: dict[str, str] = {}
    page_text = soup.get_text(separator="\n")
    lines = [l.strip() for l in page_text.split("\n") if l.strip()]

    # Look for labeled data: "Phone:", "Website:", "Address:" etc.
    label_patterns = {
        "phone": re.compile(r"(?:phone|tel)[:\s]+([+\d\s\(\)\-\.]{7,20})", re.I),
        "fax": re.compile(r"fax[:\s]+([+\d\s\(\)\-\.]{7,20})", re.I),
        "website": re.compile(r"(?:website|web|url)[:\s]+(https?://[^\s<>\"]+|www\.[^\s<>\"]+)", re.I),
        "address": re.compile(r"address[:\s]+(.+?)(?:\n|phone|fax|$)", re.I),
    }

    for field, pattern in label_patterns.items():
        match = pattern.search(page_text)
        if match:
            fields[field] = match.group(1).strip()

    # Try extracting website from actual anchor tags
    if not fields.get("website"):
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if href.startswith("http") and "americanstaffing.net" not in href:
                if not any(domain in href for domain in ["linkedin.com", "facebook.com", "twitter.com"]):
                    fields["website"] = href
                    break

    # Extract city/state from address or structured data
    city = state = zip_code = ""
    address_text = fields.get("address", "")
    city_state_match = re.search(r"([A-Za-z\s]+),\s*([A-Z]{2})\s*(\d{5})?", address_text)
    if city_state_match:
        city = city_state_match.group(1).strip()
        state = city_state_match.group(2)
        zip_code = city_state_match.group(3) or ""

    # Extract domain from website
    website = fields.get("website", "")
    domain = ""
    if website:
        try:
            parsed = urlparse(website if "://" in website else f"https://{website}")
            domain = parsed.netloc.lstrip("www.")
        except Exception:
            pass

    return {
        "company_name": name,
        "website": website,
        "company_domain": domain,
        "address": fields.get("address", ""),
        "city": city,
        "state": state,
        "zip": zip_code,
        "phone": fields.get("phone", ""),
        "asa_profile_url": url,
        "source": "asa_members",
        "date_scraped": datetime.now().strftime("%Y-%m-%d"),
    }


def main():
    parser = argparse.ArgumentParser(description="Scrape ASA member directory for healthcare staffing firms")
    parser.add_argument("--output", default=".tmp/source_g_asa_members.json", help="Output JSON file")
    parser.add_argument("--test", action="store_true", help="Test mode: 3 pages max + 5 profiles")
    parser.add_argument("--skip-playwright", action="store_true", help="Skip Playwright, use static fallback")
    args = parser.parse_args()

    import os
    os.makedirs(".tmp", exist_ok=True)

    print("Step 1: Collecting member profile URLs...")
    if args.skip_playwright:
        member_urls = get_member_urls_static()
    else:
        member_urls = get_member_urls_playwright(test=args.test)
        if not member_urls:
            print("  Playwright returned no URLs, trying static fallback...")
            member_urls = get_member_urls_static()

    print(f"  Found {len(member_urls)} member profile URLs")

    if args.test:
        member_urls = member_urls[:5]
        print(f"  TEST MODE: scraping {len(member_urls)} profiles only")

    print(f"\nStep 2: Scraping {len(member_urls)} member profiles...")
    records = []
    for i, url in enumerate(member_urls):
        record = scrape_profile(url)
        if record:
            records.append(record)
        if (i + 1) % 10 == 0:
            print(f"  {i + 1}/{len(member_urls)} scraped, {len(records)} valid")
        time.sleep(0.5)

    with open(args.output, "w") as f:
        json.dump(records, f, indent=2)

    print(f"\nDone. {len(records)} ASA healthcare members → {args.output}")
    if records:
        print("Sample records:")
        for r in records[:3]:
            print(f"  {r['company_name']} | {r.get('website', 'no website')} | {r.get('phone', 'no phone')}")


if __name__ == "__main__":
    main()
