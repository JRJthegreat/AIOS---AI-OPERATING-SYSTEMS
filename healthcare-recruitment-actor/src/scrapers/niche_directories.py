"""
Niche travel healthcare staffing directories.

Sources:
  NATHO            — static HTML, ~130 dues-paying members
  Vivian Health    — JS-rendered (Playwright), 200-300 agencies
  BluePipes        — HTML pagination, ~500 companies
  TravelNurseSource — state-by-state URL pattern, 500+ agencies
"""
from __future__ import annotations

import logging
import re
import time
from datetime import datetime
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

DEFAULT_SOURCES = ["natho", "vivian", "bluepipes", "travelnursesource"]

US_STATES = [
    "alabama", "alaska", "arizona", "arkansas", "california", "colorado",
    "connecticut", "delaware", "florida", "georgia", "hawaii", "idaho",
    "illinois", "indiana", "iowa", "kansas", "kentucky", "louisiana",
    "maine", "maryland", "massachusetts", "michigan", "minnesota",
    "mississippi", "missouri", "montana", "nebraska", "nevada",
    "new-hampshire", "new-jersey", "new-mexico", "new-york",
    "north-carolina", "north-dakota", "ohio", "oklahoma", "oregon",
    "pennsylvania", "rhode-island", "south-carolina", "south-dakota",
    "tennessee", "texas", "utah", "vermont", "virginia", "washington",
    "west-virginia", "wisconsin", "wyoming",
]
TEST_STATES = ["texas", "florida", "california", "new-york"]


def _make_record(company_name: str, website: str = "", agency_type: str = "", source_tag: str = "") -> dict:
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


def _scrape_natho(test: bool = False) -> list[dict]:
    log.info("  [NATHO] Scraping member directory")
    url = "https://www.natho.org/Current-NATHO-Members"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as e:
        log.warning(f"  [NATHO] Error: {e}")
        return []

    soup = BeautifulSoup(resp.text, "lxml")
    records = []
    seen: set[str] = set()

    for a in soup.find_all("a", href=True):
        href = a.get("href", "")
        text = a.get_text(strip=True)
        if not text or len(text) < 3:
            continue
        if any(skip in href for skip in ["natho.org/page", "natho.org/event", "mailto:", "tel:",
                                          "facebook", "twitter", "linkedin.com/in", "#"]):
            continue
        if "natho.org" in href and "/profile" not in href and "/PublicProfile" not in href:
            continue

        name = re.sub(r"\s+", " ", text).strip()
        if len(name) < 4 or name.lower() in ("home", "about", "contact", "login", "join"):
            continue

        name_key = name.lower()
        if name_key in seen:
            continue
        seen.add(name_key)

        website = href if href and "natho.org" not in href and href.startswith("http") else ""
        records.append(_make_record(name, website=website, agency_type="Travel Healthcare Staffing", source_tag="natho"))
        if test and len(records) >= 10:
            break

    # Fallback text extraction if link approach yielded nothing
    if not records:
        for block in soup.find_all(["p", "li", "td"]):
            text = block.get_text(strip=True)
            if 4 < len(text) < 100:
                name_key = text.lower()
                if name_key not in seen:
                    seen.add(name_key)
                    records.append(_make_record(text, agency_type="Travel Healthcare Staffing", source_tag="natho"))
            if test and len(records) >= 10:
                break

    log.info(f"  [NATHO] → {len(records)} members")
    return records


def _scrape_vivian(test: bool = False) -> list[dict]:
    log.info("  [Vivian] Scraping agency directory (Playwright)")
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        log.warning("  [Vivian] playwright not installed, skipping")
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

                agency_items = soup.find_all(["div", "li", "article"],
                                              class_=re.compile(r"agency|employer|card|item", re.I))
                if not agency_items:
                    for a in soup.find_all("a", href=re.compile(r"/agencies/[a-z]")):
                        name = re.sub(r"\s*\(\d+\)\s*$", "", a.get_text(strip=True)).strip()
                        if name and len(name) > 2:
                            records.append(_make_record(name, agency_type="Travel Healthcare", source_tag="vivian"))
                else:
                    for item in agency_items:
                        name_el = item.find(["h2", "h3", "h4", "strong", "span"],
                                            class_=re.compile(r"name|title|company", re.I))
                        if not name_el:
                            name_el = item.find(["h2", "h3", "h4"])
                        if name_el:
                            name = re.sub(r"\s*\(\d+\)\s*$", "", name_el.get_text(strip=True)).strip()
                            if name and len(name) > 2:
                                records.append(_make_record(name, agency_type="Travel Healthcare", source_tag="vivian"))

                next_btn = page.query_selector("[aria-label='Next page'], .pagination-next, a[rel='next']")
                if not next_btn or page_num >= max_pages:
                    break
                next_btn.click()
                page.wait_for_load_state("networkidle", timeout=15000)
                time.sleep(1)

        except Exception as e:
            log.error(f"  [Vivian] Error: {e}", exc_info=True)
        finally:
            browser.close()

    seen: set[str] = set()
    deduped = []
    for r in records:
        key = r["company_name"].lower()
        if key not in seen:
            seen.add(key)
            deduped.append(r)

    log.info(f"  [Vivian] → {len(deduped)} agencies")
    return deduped


def _scrape_bluepipes(test: bool = False) -> list[dict]:
    log.info("  [BluePipes] Scraping company directory")
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
            log.warning(f"  [BluePipes] Error on page {page_num}: {e}")
            break

        soup = BeautifulSoup(resp.text, "lxml")
        company_cards = soup.find_all(["div", "article", "li"],
                                       class_=re.compile(r"company|employer|card|listing", re.I))

        if not company_cards:
            for h in soup.find_all(["h2", "h3"]):
                name = h.get_text(strip=True)
                if name and len(name) > 3:
                    key = name.lower()
                    if key not in seen:
                        seen.add(key)
                        records.append(_make_record(name, agency_type="Healthcare Staffing", source_tag="bluepipes"))
        else:
            for card in company_cards:
                name_el = card.find(["h2", "h3", "h4", "strong"],
                                    class_=re.compile(r"name|title", re.I))
                if not name_el:
                    name_el = card.find(["h2", "h3", "h4"])
                if not name_el:
                    continue
                name = name_el.get_text(strip=True)
                if not name or len(name) < 3:
                    continue
                card_text = card.get_text().lower()
                if not any(kw in card_text for kw in ["healthcare", "staffing", "nursing", "medical", "health"]):
                    continue
                key = name.lower()
                if key not in seen:
                    seen.add(key)
                    records.append(_make_record(name, agency_type="Healthcare Staffing", source_tag="bluepipes"))

        if not company_cards and not soup.find("a", href=re.compile(r"/company/page/\d+")):
            break
        time.sleep(1)

    log.info(f"  [BluePipes] → {len(records)} companies")
    return records


def _scrape_travelnursesource(test: bool = False) -> list[dict]:
    log.info("  [TravelNurseSource] Scraping agency directory by state")
    base_url = "https://www.travelnursesource.com/all-travel-nursing-agencies-in-"
    states = TEST_STATES if test else US_STATES
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
            log.warning(f"  [TNSource] Error for {state}: {e}")
            time.sleep(2)
            continue

        soup = BeautifulSoup(resp.text, "lxml")
        agency_links = soup.find_all("a", href=re.compile(r"/travel-nursing-agency/"))
        if agency_links:
            for a in agency_links:
                name = a.get_text(strip=True)
                if not name or len(name) < 3:
                    continue
                key = name.lower()
                if key not in seen:
                    seen.add(key)
                    records.append(_make_record(name, agency_type="Travel Nursing Agency", source_tag="travelnursesource"))
        else:
            for heading in soup.find_all(["h2", "h3", "h4"]):
                name = heading.get_text(strip=True)
                if name and len(name) > 3 and name.lower() not in ("home", "about", "contact"):
                    key = name.lower()
                    if key not in seen:
                        seen.add(key)
                        records.append(_make_record(name, agency_type="Travel Nursing Agency", source_tag="travelnursesource"))

        time.sleep(1.5)

    log.info(f"  [TravelNurseSource] → {len(records)} agencies")
    return records


_SCRAPER_MAP = {
    "natho": _scrape_natho,
    "vivian": _scrape_vivian,
    "bluepipes": _scrape_bluepipes,
    "travelnursesource": _scrape_travelnursesource,
}


def run(config: dict, test: bool = False) -> list[dict]:
    sources = config.get("nicheDirectorySources", DEFAULT_SOURCES)
    all_records: list[dict] = []

    for source in sources:
        fn = _SCRAPER_MAP.get(source)
        if fn is None:
            log.warning(f"  Unknown niche directory source '{source}' — skipping")
            continue
        try:
            records = fn(test=test)
            all_records.extend(records)
        except Exception as e:
            log.error(f"  [niche_directories/{source}] failed: {e}", exc_info=True)

    # Cross-source dedup by name
    seen: set[str] = set()
    deduped = []
    for r in all_records:
        key = r["company_name"].lower().strip()
        if key not in seen:
            seen.add(key)
            deduped.append(r)

    log.info(f"  niche_directories: {len(deduped)} unique agencies")
    return deduped
