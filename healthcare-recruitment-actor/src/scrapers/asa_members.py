"""
ASA (American Staffing Association) member directory — healthcare staffing firms.

Strategy:
  1. Playwright to load JS-rendered search, filter by "Health Care", collect profile URLs
  2. requests on each static profile page for company name, address, phone, website
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
}

ASA_BASE = "https://americanstaffing.net"
ASA_DIRECTORY = "https://americanstaffing.net/asa-member-directory/"
MEMBER_URL_PATTERN = re.compile(r"/members-directory/[a-z0-9\-]+-[a-z0-9]{15,}/", re.I)


def _get_urls_playwright(test: bool = False) -> list[str]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        log.warning("  [ASA] playwright not installed")
        return []

    urls: set[str] = set()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        )
        page = context.new_page()
        try:
            log.info("  [ASA] Loading member directory (JS-rendered)")
            page.goto(ASA_DIRECTORY, wait_until="networkidle", timeout=45000)
            time.sleep(3)

            try:
                health_care_filter = page.query_selector("text=Health Care")
                if health_care_filter:
                    health_care_filter.click()
                    page.wait_for_load_state("networkidle", timeout=15000)
                    time.sleep(2)
                    log.info("  [ASA] Applied 'Health Care' filter")
            except Exception as e:
                log.warning(f"  [ASA] Could not apply filter: {e} — scraping all members")

            max_pages = 3 if test else 100
            page_count = 0

            while page_count < max_pages:
                html = page.content()
                soup = BeautifulSoup(html, "lxml")

                new_urls = []
                for a in soup.find_all("a", href=MEMBER_URL_PATTERN):
                    href = a["href"]
                    if not href.startswith("http"):
                        href = ASA_BASE + href
                    if href not in urls:
                        urls.add(href)
                        new_urls.append(href)

                log.info(f"  [ASA] Page {page_count + 1}: {len(new_urls)} new profiles (total: {len(urls)})")
                if not new_urls and page_count > 0:
                    break

                next_btn = page.query_selector("[aria-label='Next'], .slds-button__next, a.next-page, [title='Next']")
                if not next_btn:
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
            log.error(f"  [ASA] Playwright error: {e}", exc_info=True)
        finally:
            browser.close()

    return list(urls)


def _get_urls_static() -> list[str]:
    try:
        resp = requests.get(ASA_DIRECTORY, headers=HEADERS, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as e:
        log.warning(f"  [ASA] Static fallback error: {e}")
        return []

    soup = BeautifulSoup(resp.text, "lxml")
    urls: set[str] = set()
    for a in soup.find_all("a", href=MEMBER_URL_PATTERN):
        href = a["href"]
        if not href.startswith("http"):
            href = ASA_BASE + href
        urls.add(href)
    return list(urls)


def _scrape_profile(url: str) -> dict | None:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        resp.raise_for_status()
    except requests.RequestException:
        return None

    soup = BeautifulSoup(resp.text, "lxml")

    name = ""
    for el in soup.find_all(["h1", "h2"]):
        text = el.get_text(strip=True)
        if text and 2 < len(text) < 200:
            name = text
            break

    if not name:
        return None

    page_text = soup.get_text(separator="\n")

    label_patterns = {
        "phone": re.compile(r"(?:phone|tel)[:\s]+([+\d\s\(\)\-\.]{7,20})", re.I),
        "website": re.compile(r"(?:website|web|url)[:\s]+(https?://[^\s<>\"]+|www\.[^\s<>\"]+)", re.I),
        "address": re.compile(r"address[:\s]+(.+?)(?:\n|phone|fax|$)", re.I),
    }

    fields: dict[str, str] = {}
    for field, pattern in label_patterns.items():
        match = pattern.search(page_text)
        if match:
            fields[field] = match.group(1).strip()

    if not fields.get("website"):
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if href.startswith("http") and "americanstaffing.net" not in href:
                if not any(d in href for d in ["linkedin.com", "facebook.com", "twitter.com"]):
                    fields["website"] = href
                    break

    address_text = fields.get("address", "")
    city = state = zip_code = ""
    city_state_match = re.search(r"([A-Za-z\s]+),\s*([A-Z]{2})\s*(\d{5})?", address_text)
    if city_state_match:
        city = city_state_match.group(1).strip()
        state = city_state_match.group(2)
        zip_code = city_state_match.group(3) or ""

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


def run(config: dict, test: bool = False) -> list[dict]:
    log.info("  ASA: collecting member profile URLs")

    member_urls = _get_urls_playwright(test=test)
    if not member_urls:
        log.info("  ASA: Playwright returned no URLs, trying static fallback")
        member_urls = _get_urls_static()

    log.info(f"  ASA: found {len(member_urls)} member profile URLs")

    if test:
        member_urls = member_urls[:5]

    records: list[dict] = []
    for i, url in enumerate(member_urls):
        record = _scrape_profile(url)
        if record:
            records.append(record)
        if (i + 1) % 20 == 0:
            log.info(f"  ASA: {i + 1}/{len(member_urls)} scraped, {len(records)} valid")
        time.sleep(0.5)

    log.info(f"  asa_members: {len(records)} members")
    return records
