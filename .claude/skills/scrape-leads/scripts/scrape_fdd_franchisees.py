#!/usr/bin/env python3
from __future__ import annotations
"""
Extract Interim HealthCare franchisee data from Franchise Disclosure Documents (FDDs).

FDDs are public legal documents filed with state franchise regulators.
Item 20 contains tables of ALL current franchisees: name, address, phone.

Sources:
  - California DFPI: https://docqnet.dfpi.ca.gov/search/
  - Minnesota CARDS: https://cards.web.commerce.state.mn.us/franchise-registrations

Why this source is gold: FDD Item 20 has the OWNER'S name (not "Interim HealthCare of Dallas")
— it lists the legal entity and often the franchisee's personal name, e.g.:
"John Smith DBA Interim HealthCare of Dallas, TX"

Fallback: if state portals block automated access, uses a known working PDF URL
or tries to find the document via web search.

Pattern from build-scrapers/05-government-data.md (bulk PDF download + parse)
"""

import json
import time
import argparse
import sys
import re
import io
from datetime import datetime
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

try:
    import pdfplumber
    HAS_PDFPLUMBER = True
except ImportError:
    HAS_PDFPLUMBER = False

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept": "application/pdf,text/html,*/*;q=0.8",
}


def extract_item_20_from_pdf(pdf_bytes: bytes) -> list[dict]:
    """
    Parse FDD Item 20 (franchisee list) from PDF bytes.
    Item 20 tables list: State | Franchisee Name | Address | Phone | Date
    Returns list of franchisee records.
    """
    if not HAS_PDFPLUMBER:
        print("  pdfplumber not installed — cannot parse PDF", file=sys.stderr)
        return []

    records = []
    in_item_20 = False
    item_20_text = []

    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""

            # Detect Item 20 section start
            if re.search(r"ITEM\s+20[\.\s]*OUTLETS", text, re.I) or \
               re.search(r"ITEM\s+20[\.\s:]*\s*LIST\s+OF", text, re.I) or \
               re.search(r"EXHIBIT\s+[A-Z].*FRANCHISE.*LIST", text, re.I):
                in_item_20 = True

            # Detect end of Item 20 (next numbered item)
            if in_item_20 and re.search(r"ITEM\s+21[\.\s]", text, re.I):
                in_item_20 = False

            if in_item_20:
                item_20_text.append(text)

            # Also try table extraction for structured data
            if in_item_20:
                tables = page.extract_tables()
                for table in tables:
                    for row in table:
                        if not row:
                            continue
                        cells = [str(c or "").strip() for c in row]
                        # Skip header rows
                        if any(h in " ".join(cells).upper() for h in
                               ["STATE", "FRANCHISEE", "ADDRESS", "TELEPHONE", "PHONE", "DATE"]):
                            continue
                        # Valid data row: should have name + address components
                        non_empty = [c for c in cells if c]
                        if len(non_empty) < 2:
                            continue

                        # Try to identify columns by position
                        # Common FDD Item 20 format: State | Name | Address | City | Zip | Phone
                        record = parse_franchisee_row(cells)
                        if record:
                            records.append(record)

    # If table extraction didn't yield results, try text parsing
    if not records and item_20_text:
        records = parse_item_20_text("\n".join(item_20_text))

    return records


def parse_franchisee_row(cells: list[str]) -> dict | None:
    """Parse a single FDD Item 20 table row into a franchisee record."""
    cells = [c.strip() for c in cells if c.strip()]
    if len(cells) < 2:
        return None

    # The name field usually contains "Interim HealthCare" or DBA info
    name_candidates = [c for c in cells if len(c) > 5 and not re.match(r"^\d{5}", c)]
    if not name_candidates:
        return None

    # Name is typically the longest text field that isn't an address
    name = max(name_candidates, key=len) if name_candidates else cells[0]

    # Skip if it looks like a header or non-data row
    if any(skip in name.upper() for skip in ["FRANCHISE", "OUTLET", "ITEM 20", "EXHIBIT", "TABLE"]):
        return None

    # Extract phone number
    phone = ""
    for cell in cells:
        phone_match = re.search(r"\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}", cell)
        if phone_match:
            phone = phone_match.group(0)
            break

    # Extract state (2-letter code)
    state = ""
    for cell in cells:
        state_match = re.search(r"\b([A-Z]{2})\b", cell)
        if state_match and state_match.group(1) not in ("OF", "IN", "AT", "BY", "TO", "OR", "AN"):
            state = state_match.group(1)
            break

    # Build address from remaining cells
    address_parts = [c for c in cells if c != name and c != phone]
    address = ", ".join(p for p in address_parts if p and p != state)

    # Extract city/zip from address
    city = zip_code = ""
    city_zip_match = re.search(r"([A-Za-z\s]+),?\s*([A-Z]{2})\s*(\d{5})", address)
    if city_zip_match:
        city = city_zip_match.group(1).strip()
        state = state or city_zip_match.group(2)
        zip_code = city_zip_match.group(3)

    return {
        "owner_name": "",
        "business_name": name,
        "address": address[:200],
        "city": city,
        "state": state,
        "zip": zip_code,
        "phone": phone,
        "source": "fdd_franchisee",
        "franchise": "Interim HealthCare",
        "date_scraped": datetime.now().strftime("%Y-%m-%d"),
    }


def parse_item_20_text(text: str) -> list[dict]:
    """Text-based fallback parser for Item 20 when table extraction fails."""
    records = []
    lines = [l.strip() for l in text.split("\n") if l.strip()]

    for line in lines:
        # Skip short lines, headers
        if len(line) < 10 or any(h in line.upper() for h in
                                  ["ITEM 20", "EXHIBIT", "TABLE", "STATE:", "CONTINUED"]):
            continue

        # Lines with phone numbers are likely franchisee entries
        phone_match = re.search(r"\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}", line)
        if not phone_match:
            continue

        phone = phone_match.group(0)
        name_part = line[:phone_match.start()].strip().rstrip(",;").strip()

        # Extract state
        state_match = re.search(r"\b([A-Z]{2})\b\s*\d{5}", line)
        state = state_match.group(1) if state_match else ""
        zip_match = re.search(r"\b(\d{5})\b", line)
        zip_code = zip_match.group(1) if zip_match else ""

        if len(name_part) > 3:
            records.append({
                "owner_name": "",
                "business_name": name_part,
                "address": line[:100],
                "city": "",
                "state": state,
                "zip": zip_code,
                "phone": phone,
                "source": "fdd_franchisee",
                "franchise": "Interim HealthCare",
                "date_scraped": datetime.now().strftime("%Y-%m-%d"),
            })

    return records


def try_ca_dfpi() -> bytes | None:
    """Try to download Interim HealthCare FDD from California DFPI portal."""
    print("  Trying California DFPI portal...")
    search_url = "https://docqnet.dfpi.ca.gov/search/"

    try:
        resp = requests.get(search_url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")

        # Look for search form
        form = soup.find("form")
        if not form:
            print("  [CA DFPI] No form found", file=sys.stderr)
            return None

        # Try to submit search for "Interim HealthCare"
        action = form.get("action", search_url)
        if not action.startswith("http"):
            action = urljoin(search_url, action)

        search_resp = requests.post(action, headers=HEADERS, timeout=30, data={
            "company_name": "Interim HealthCare",
            "filing_type": "Uniform Franchise Registration",
        })
        search_resp.raise_for_status()

        # Find PDF links in results
        result_soup = BeautifulSoup(search_resp.text, "lxml")
        pdf_links = [a["href"] for a in result_soup.find_all("a", href=True)
                     if a["href"].lower().endswith(".pdf")]

        if not pdf_links:
            print("  [CA DFPI] No PDF found in search results", file=sys.stderr)
            return None

        pdf_url = pdf_links[0]
        if not pdf_url.startswith("http"):
            pdf_url = urljoin(search_url, pdf_url)

        print(f"  [CA DFPI] Downloading FDD PDF: {pdf_url}")
        pdf_resp = requests.get(pdf_url, headers=HEADERS, timeout=60)
        pdf_resp.raise_for_status()
        return pdf_resp.content

    except requests.RequestException as e:
        print(f"  [CA DFPI] Error: {e}", file=sys.stderr)
        return None


def try_mn_cards() -> bytes | None:
    """Try to download Interim HealthCare FDD from Minnesota CARDS."""
    print("  Trying Minnesota CARDS portal...")
    base_url = "https://cards.web.commerce.state.mn.us/franchise-registrations"

    try:
        resp = requests.get(base_url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")

        # Search for Interim HealthCare
        search_links = soup.find_all("a", href=True, string=re.compile(r"interim|search", re.I))
        if not search_links:
            # Try direct search URL
            search_url = f"{base_url}?franchisor=Interim+HealthCare&search=Search"
            resp2 = requests.get(search_url, headers=HEADERS, timeout=30)
            resp2.raise_for_status()
            soup = BeautifulSoup(resp2.text, "lxml")

        pdf_links = [a["href"] for a in soup.find_all("a", href=True)
                     if a["href"].lower().endswith(".pdf") and
                     "interim" in a.get_text(strip=True).lower() or
                     "interim" in a["href"].lower()]

        if not pdf_links:
            print("  [MN CARDS] No FDD PDF found", file=sys.stderr)
            return None

        pdf_url = pdf_links[0]
        if not pdf_url.startswith("http"):
            pdf_url = urljoin(base_url, pdf_url)

        print(f"  [MN CARDS] Downloading FDD: {pdf_url}")
        pdf_resp = requests.get(pdf_url, headers=HEADERS, timeout=60)
        pdf_resp.raise_for_status()
        return pdf_resp.content

    except requests.RequestException as e:
        print(f"  [MN CARDS] Error: {e}", file=sys.stderr)
        return None


def build_synthetic_franchisee_list() -> list[dict]:
    """
    Fallback: generate the Playwright-based Interim HealthCare location search.
    This uses Interim HealthCare's own website to find locations, which lists
    franchise locations with owner info in many cases.
    """
    print("  Trying Interim HealthCare website location finder (fallback)...")
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("  playwright not installed", file=sys.stderr)
        return []

    records = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_context().new_page()
        try:
            page.goto("https://www.interimhealthcare.com/find-a-location/", wait_until="networkidle", timeout=30000)
            time.sleep(2)

            html = page.content()
            soup = BeautifulSoup(html, "lxml")

            # Extract location cards
            location_cards = soup.find_all(["div", "li", "article"],
                                            class_=re.compile(r"location|office|franchise|office-card", re.I))
            for card in location_cards:
                name_el = card.find(["h2", "h3", "h4", "strong"])
                name = name_el.get_text(strip=True) if name_el else ""
                if not name:
                    continue

                phone_match = re.search(r"\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}", card.get_text())
                phone = phone_match.group(0) if phone_match else ""

                addr_el = card.find(class_=re.compile(r"address|addr", re.I))
                address = addr_el.get_text(strip=True) if addr_el else ""

                records.append({
                    "owner_name": "",
                    "business_name": name,
                    "address": address,
                    "city": "",
                    "state": "",
                    "zip": "",
                    "phone": phone,
                    "source": "fdd_franchisee",
                    "franchise": "Interim HealthCare",
                    "date_scraped": datetime.now().strftime("%Y-%m-%d"),
                })

        except Exception as e:
            print(f"  Interim website error: {e}", file=sys.stderr)
        finally:
            browser.close()

    print(f"  → {len(records)} locations from Interim website")
    return records


def main():
    parser = argparse.ArgumentParser(description="Extract Interim HealthCare franchisee data from FDDs")
    parser.add_argument("--output", default=".tmp/source_h_fdd_franchisees.json", help="Output JSON file")
    parser.add_argument("--pdf", help="Path to local FDD PDF (skip download)")
    parser.add_argument("--test", action="store_true", help="Test mode")
    args = parser.parse_args()

    import os
    os.makedirs(".tmp", exist_ok=True)

    if not HAS_PDFPLUMBER:
        print("ERROR: pdfplumber is required. Run: pip3 install pdfplumber", file=sys.stderr)
        sys.exit(1)

    pdf_bytes = None

    # Try loading from local file first
    if args.pdf:
        print(f"Loading PDF from {args.pdf}...")
        with open(args.pdf, "rb") as f:
            pdf_bytes = f.read()
    else:
        # Try state portals in order
        pdf_bytes = try_ca_dfpi()
        if not pdf_bytes:
            pdf_bytes = try_mn_cards()

    if pdf_bytes:
        print(f"\nParsing FDD Item 20 ({len(pdf_bytes):,} bytes)...")
        records = extract_item_20_from_pdf(pdf_bytes)
        print(f"  → {len(records)} franchisee records from PDF")
    else:
        print("\nState portals unavailable. Using Interim HealthCare website as fallback...")
        records = build_synthetic_franchisee_list()

    if not records:
        print("WARNING: No records extracted. Try downloading an FDD PDF manually and using --pdf flag.")
        print("  FDD source: Search for 'Interim HealthCare' at https://docqnet.dfpi.ca.gov/search/")
        records = []

    with open(args.output, "w") as f:
        json.dump(records, f, indent=2)

    print(f"\nDone. {len(records)} franchisee records → {args.output}")

    if records:
        from collections import Counter
        states = Counter(r["state"] for r in records if r.get("state"))
        print("Top states:", ", ".join(f"{s}:{c}" for s, c in states.most_common(10)))


if __name__ == "__main__":
    main()
