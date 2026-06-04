#!/usr/bin/env python3
"""
Scrape niche travel healthcare staffing directories.

Sources:
  NATHO      — https://www.natho.org/Current-NATHO-Members (static HTML, 130 member agencies)
  Vivian     — https://www.vivian.com/agencies/ (JS-rendered, Playwright)
  BluePipes  — https://www.bluepipes.com/company/page/N (HTML pagination)
  TNSource   — https://www.travelnursesource.com/all-travel-nursing-agencies-in-[state]

All 4 are travel healthcare-specific — near-zero Apollo overlap.
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
    "Accept-Language": "en-US,en;q=0.5",
}


def make_record(company_name: str, website: str = "", agency_type: str = "", source_tag: str = "") -> dict:
    domain = ""
    if website:
        try:
            parsed = urlparse(website if "://" in website else f"https://{website}")
            domain = parsed.netloc.lstrip("www.") or parsed.path.lstrip("www.")
        except Exception:
            domain = ""
    return {
        "company_name": company_name.strip(),
        "website": website.strip(),
        "company_domain": domain,
        "agency_type": agency_type,
        "source": f"niche_directory_{source_tag}",
        "date_scraped": datetime.now().strftime("%Y-%m-%d"),
    }


# ─── NATHO ────────────────────────────────────────────────────────────────────

def scrape_natho(test: bool = False) -> list[dict]:
    print("  [NATHO] Scraping member directory...")
    url = "https://www.natho.org/Current-NATHO-Members"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"  [NATHO] Error: {e}", file=sys.stderr)
        return []

    soup = BeautifulSoup(resp.text, "lxml")
    records = []

    # NATHO page lists members as links or plain text with optional website links
    # Look for member sections (Full Members / Associate Members)
    member_sections = soup.find_all(["div", "section", "ul", "ol"],
                                     class_=re.compile(r"member|directory|list", re.I))

    all_links = soup.find_all("a", href=True)
    seen_names: set[str] = set()

    for a in all_links:
        href = a.get("href", "")
        text = a.get_text(strip=True)
        # Skip navigation, social, and internal links
        if not text or len(text) < 3:
            continue
        if any(skip in href for skip in ["natho.org/page", "natho.org/event", "mailto:", "tel:",
                                          "facebook", "twitter", "linkedin.com/in", "#"]):
            continue
        # Member links typically point to external company websites or NATHO profiles
        if "natho.org" in href and "/profile" not in href and "/PublicProfile" not in href:
            continue

        # Clean up the name
        name = re.sub(r"\s+", " ", text).strip()
        if len(name) < 4 or name.lower() in ("home", "about", "contact", "login", "join"):
            continue

        name_key = name.lower()
        if name_key in seen_names:
            continue
        seen_names.add(name_key)

        # Extract website from href if it's external
        website = ""
        if href and "natho.org" not in href and href.startswith("http"):
            website = href

        records.append(make_record(name, website=website, agency_type="Travel Healthcare Staffing", source_tag="natho"))
        if test and len(records) >= 10:
            break

    # Fallback: if link approach yielded nothing, try text parsing
    if not records:
        text_blocks = soup.find_all(["p", "li", "td"])
        for block in text_blocks:
            text = block.get_text(strip=True)
            if len(text) > 4 and len(text) < 100:
                name_key = text.lower()
                if name_key not in seen_names:
                    seen_names.add(name_key)
                    records.append(make_record(text, agency_type="Travel Healthcare Staffing", source_tag="natho"))
            if test and len(records) >= 10:
                break

    print(f"  [NATHO] → {len(records)} members")
    return records


# ─── VIVIAN HEALTH ────────────────────────────────────────────────────────────

def scrape_vivian(test: bool = False) -> list[dict]:
    print("  [Vivian] Scraping agency directory (Playwright)...")
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("  [Vivian] playwright not installed, skipping", file=sys.stderr)
        return []

    records = []
    max_pages = 2 if test else 50

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        )
        page = context.new_page()

        try:
            page.goto("https://www.vivian.com/agencies/", wait_until="networkidle", timeout=30000)
            time.sleep(2)

            for page_num in range(1, max_pages + 1):
                html = page.content()
                soup = BeautifulSoup(html, "lxml")

                # Agency cards — look for agency name elements
                agency_items = soup.find_all(["div", "li", "article"],
                                              class_=re.compile(r"agency|employer|card|item", re.I))

                if not agency_items:
                    # Broader search for any text that looks like an agency name
                    links = soup.find_all("a", href=re.compile(r"/agencies/[a-z]"))
                    for a in links:
                        name = a.get_text(strip=True)
                        # Strip job count from name (e.g., "LanceSoft (14005)")
                        name = re.sub(r"\s*\(\d+\)\s*$", "", name).strip()
                        if name and len(name) > 2:
                            href = a.get("href", "")
                            records.append(make_record(name, agency_type="Travel Healthcare", source_tag="vivian"))
                else:
                    for item in agency_items:
                        name_el = item.find(["h2", "h3", "h4", "strong", "span"],
                                            class_=re.compile(r"name|title|company", re.I))
                        if not name_el:
                            name_el = item.find(["h2", "h3", "h4"])
                        if name_el:
                            name = name_el.get_text(strip=True)
                            name = re.sub(r"\s*\(\d+\)\s*$", "", name).strip()
                            if name and len(name) > 2:
                                records.append(make_record(name, agency_type="Travel Healthcare", source_tag="vivian"))

                # Navigate to next page
                next_btn = page.query_selector("[aria-label='Next page'], .pagination-next, a[rel='next']")
                if not next_btn or page_num >= max_pages:
                    break
                next_btn.click()
                page.wait_for_load_state("networkidle", timeout=15000)
                time.sleep(1)

        except Exception as e:
            print(f"  [Vivian] Error: {e}", file=sys.stderr)
        finally:
            browser.close()

    # Deduplicate
    seen: set[str] = set()
    deduped = []
    for r in records:
        key = r["company_name"].lower()
        if key not in seen:
            seen.add(key)
            deduped.append(r)

    print(f"  [Vivian] → {len(deduped)} agencies")
    return deduped


# ─── BLUEPIPES ────────────────────────────────────────────────────────────────

def scrape_bluepipes(test: bool = False) -> list[dict]:
    print("  [BluePipes] Scraping company directory...")
    base_url = "https://www.bluepipes.com/company/page"
    records = []
    seen: set[str] = set()
    max_pages = 2 if test else 20

    for page_num in range(1, max_pages + 1):
        url = f"{base_url}/{page_num}" if page_num > 1 else "https://www.bluepipes.com/company"
        try:
            resp = requests.get(url, headers=HEADERS, timeout=30)
            if resp.status_code == 404:
                break
            resp.raise_for_status()
        except requests.RequestException as e:
            print(f"  [BluePipes] Error on page {page_num}: {e}", file=sys.stderr)
            break

        soup = BeautifulSoup(resp.text, "lxml")
        # Company cards typically have name + classification + size
        company_cards = soup.find_all(["div", "article", "li"],
                                       class_=re.compile(r"company|employer|card|listing", re.I))

        if not company_cards:
            # Try broader: any h2/h3 that looks like a company name
            headings = soup.find_all(["h2", "h3"])
            for h in headings:
                name = h.get_text(strip=True)
                if name and len(name) > 3:
                    key = name.lower()
                    if key not in seen:
                        seen.add(key)
                        records.append(make_record(name, agency_type="Healthcare Staffing", source_tag="bluepipes"))
        else:
            for card in company_cards:
                name_el = card.find(["h2", "h3", "h4", "strong"],
                                    class_=re.compile(r"name|title", re.I))
                if not name_el:
                    name_el = card.find(["h2", "h3", "h4"])
                if name_el:
                    name = name_el.get_text(strip=True)
                    if not name or len(name) < 3:
                        continue
                    # Only keep healthcare staffing companies
                    card_text = card.get_text().lower()
                    if not any(kw in card_text for kw in ["healthcare", "staffing", "nursing", "medical", "health"]):
                        continue
                    key = name.lower()
                    if key not in seen:
                        seen.add(key)
                        records.append(make_record(name, agency_type="Healthcare Staffing", source_tag="bluepipes"))

        if not company_cards and not soup.find("a", href=re.compile(r"/company/page/\d+")):
            break
        time.sleep(1)

    print(f"  [BluePipes] → {len(records)} companies")
    return records


# ─── TRAVELNURSESOURCE ────────────────────────────────────────────────────────

US_STATES_TNS = [
    "alabama", "alaska", "arizona", "arkansas", "california", "colorado",
    "connecticut", "delaware", "florida", "georgia", "hawaii", "idaho",
    "illinois", "indiana", "iowa", "kansas", "kentucky", "louisiana",
    "maine", "maryland", "massachusetts", "michigan", "minnesota",
    "mississippi", "missouri", "montana", "nebraska", "nevada",
    "new-hampshire", "new-jersey", "new-mexico", "new-york",
    "north-carolina", "north-dakota", "ohio", "oklahoma", "oregon",
    "pennsylvania", "rhode-island", "south-carolina", "south-dakota",
    "tennessee", "texas", "utah", "vermont", "virginia", "washington",
    "west-virginia", "wisconsin", "wyoming"
]

# Use high-volume states for test; all for full run
TEST_STATES_TNS = ["texas", "florida", "california", "new-york"]


def scrape_travelnursesource(test: bool = False) -> list[dict]:
    print("  [TravelNurseSource] Scraping agency directory by state...")
    base_url = "https://www.travelnursesource.com/all-travel-nursing-agencies-in-"
    states = TEST_STATES_TNS if test else US_STATES_TNS
    records = []
    seen: set[str] = set()

    for state in states:
        url = f"{base_url}{state}"
        try:
            resp = requests.get(url, headers=HEADERS, timeout=30)
            if resp.status_code == 404:
                continue
            resp.raise_for_status()
        except requests.RequestException as e:
            print(f"  [TNSource] Error for {state}: {e}", file=sys.stderr)
            time.sleep(2)
            continue

        soup = BeautifulSoup(resp.text, "lxml")
        # Agency listings — look for agency name links or list items
        agency_links = soup.find_all("a", href=re.compile(r"/travel-nursing-agency/"))
        if agency_links:
            for a in agency_links:
                name = a.get_text(strip=True)
                website_el = a.get("href", "")
                if not name or len(name) < 3:
                    continue
                key = name.lower()
                if key not in seen:
                    seen.add(key)
                    records.append(make_record(name, agency_type="Travel Nursing Agency", source_tag="travelnursesource"))
        else:
            # Fallback text extraction
            for heading in soup.find_all(["h2", "h3", "h4"]):
                name = heading.get_text(strip=True)
                if name and len(name) > 3 and name.lower() not in ("home", "about", "contact"):
                    key = name.lower()
                    if key not in seen:
                        seen.add(key)
                        records.append(make_record(name, agency_type="Travel Nursing Agency", source_tag="travelnursesource"))

        time.sleep(1.5)

    print(f"  [TravelNurseSource] → {len(records)} agencies")
    return records


# ─── MAIN ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Scrape niche travel healthcare staffing directories")
    parser.add_argument("--sources", nargs="+",
                        default=["natho", "vivian", "bluepipes", "travelnursesource"],
                        choices=["natho", "vivian", "bluepipes", "travelnursesource"],
                        help="Which directories to scrape")
    parser.add_argument("--output", default=".tmp/source_f_niche_directories.json", help="Output JSON file")
    parser.add_argument("--test", action="store_true", help="Test mode: minimal pages/records per source")
    args = parser.parse_args()

    import os
    os.makedirs(".tmp", exist_ok=True)

    all_records = []
    scraper_map = {
        "natho": scrape_natho,
        "vivian": scrape_vivian,
        "bluepipes": scrape_bluepipes,
        "travelnursesource": scrape_travelnursesource,
    }

    for source in args.sources:
        print(f"\nScraping {source}...")
        records = scraper_map[source](test=args.test)
        all_records.extend(records)

    # Final dedup across all sources by name
    seen_names: set[str] = set()
    deduped = []
    for r in all_records:
        key = r["company_name"].lower().strip()
        if key not in seen_names:
            seen_names.add(key)
            deduped.append(r)

    with open(args.output, "w") as f:
        json.dump(deduped, f, indent=2)

    from collections import Counter
    by_source = Counter(r["source"] for r in deduped)
    print(f"\nDone. {len(deduped)} unique agencies → {args.output}")
    for src, count in sorted(by_source.items()):
        print(f"  {src}: {count}")


if __name__ == "__main__":
    main()
