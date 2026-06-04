"""
Interim HealthCare franchisee data from Franchise Disclosure Documents (FDDs).

FDD Item 20 lists all current franchisees: owner name, address, phone.
Sources: CA DFPI → MN CARDS → Interim HealthCare website (fallback).
"""
from __future__ import annotations

import io
import logging
import re
import time
from datetime import datetime
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept": "application/pdf,text/html,*/*;q=0.8",
}


_BUSINESS_SIGNALS = re.compile(
    r"\b(llc|inc|corp|ltd|co\.|company|group|health|care|staffing|services|"
    r"interim|medical|nursing|home|dba|associates|partners|solutions)\b",
    re.I,
)

def _looks_like_business(name: str) -> bool:
    """Reject bare personal names like 'John Smith' with no business indicators."""
    if _BUSINESS_SIGNALS.search(name):
        return True
    # Reject: exactly two capitalized words with no numbers or punctuation
    if re.match(r"^[A-Z][a-z]+ [A-Z][a-z]+$", name.strip()):
        return False
    return len(name.strip()) > 5


def _parse_franchisee_row(cells: list[str]) -> dict | None:
    cells = [c.strip() for c in cells if c.strip()]
    if len(cells) < 2:
        return None

    name_candidates = [c for c in cells if len(c) > 5 and not re.match(r"^\d{5}", c)]
    if not name_candidates:
        return None

    name = max(name_candidates, key=len)
    if any(skip in name.upper() for skip in ["FRANCHISE", "OUTLET", "ITEM 20", "EXHIBIT", "TABLE"]):
        return None
    if not _looks_like_business(name):
        return None

    phone = ""
    for cell in cells:
        phone_match = re.search(r"\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}", cell)
        if phone_match:
            phone = phone_match.group(0)
            break

    state = ""
    for cell in cells:
        state_match = re.search(r"\b([A-Z]{2})\b", cell)
        if state_match and state_match.group(1) not in ("OF", "IN", "AT", "BY", "TO", "OR", "AN"):
            state = state_match.group(1)
            break

    address_parts = [c for c in cells if c != name and c != phone]
    address = ", ".join(p for p in address_parts if p and p != state)

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


def _parse_item_20_text(text: str) -> list[dict]:
    records = []
    for line in [l.strip() for l in text.split("\n") if l.strip()]:
        if len(line) < 10 or any(h in line.upper() for h in
                                  ["ITEM 20", "EXHIBIT", "TABLE", "STATE:", "CONTINUED"]):
            continue
        phone_match = re.search(r"\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}", line)
        if not phone_match:
            continue
        phone = phone_match.group(0)
        name_part = line[:phone_match.start()].strip().rstrip(",;").strip()
        state_match = re.search(r"\b([A-Z]{2})\b\s*\d{5}", line)
        state = state_match.group(1) if state_match else ""
        zip_match = re.search(r"\b(\d{5})\b", line)
        zip_code = zip_match.group(1) if zip_match else ""
        if len(name_part) > 3 and _looks_like_business(name_part):
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


def _extract_item_20_from_pdf(pdf_bytes: bytes) -> list[dict]:
    try:
        import pdfplumber
    except ImportError:
        log.warning("  pdfplumber not installed — cannot parse PDF")
        return []

    records = []
    in_item_20 = False
    item_20_text = []

    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""

            if re.search(r"ITEM\s+20[\.\s]*OUTLETS", text, re.I) or \
               re.search(r"ITEM\s+20[\.\s:]*\s*LIST\s+OF", text, re.I) or \
               re.search(r"EXHIBIT\s+[A-Z].*FRANCHISE.*LIST", text, re.I):
                in_item_20 = True

            if in_item_20 and re.search(r"ITEM\s+21[\.\s]", text, re.I):
                in_item_20 = False

            if in_item_20:
                item_20_text.append(text)
                for table in page.extract_tables():
                    for row in table:
                        if not row:
                            continue
                        cells = [str(c or "").strip() for c in row]
                        if any(h in " ".join(cells).upper() for h in
                               ["STATE", "FRANCHISEE", "ADDRESS", "TELEPHONE", "PHONE", "DATE"]):
                            continue
                        if len([c for c in cells if c]) < 2:
                            continue
                        record = _parse_franchisee_row(cells)
                        if record:
                            records.append(record)

    if not records and item_20_text:
        records = _parse_item_20_text("\n".join(item_20_text))

    return records


def _try_ca_dfpi() -> bytes | None:
    log.info("  Trying California DFPI portal")
    search_url = "https://docqnet.dfpi.ca.gov/search/"
    try:
        resp = requests.get(search_url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")
        form = soup.find("form")
        if not form:
            return None

        action = form.get("action", search_url)
        if not action.startswith("http"):
            action = urljoin(search_url, action)

        search_resp = requests.post(action, headers=HEADERS, timeout=30, data={
            "company_name": "Interim HealthCare",
            "filing_type": "Uniform Franchise Registration",
        })
        search_resp.raise_for_status()

        result_soup = BeautifulSoup(search_resp.text, "lxml")
        pdf_links = [a["href"] for a in result_soup.find_all("a", href=True)
                     if a["href"].lower().endswith(".pdf")]
        if not pdf_links:
            return None

        pdf_url = pdf_links[0]
        if not pdf_url.startswith("http"):
            pdf_url = urljoin(search_url, pdf_url)

        log.info(f"  [CA DFPI] Downloading FDD PDF")
        pdf_resp = requests.get(pdf_url, headers=HEADERS, timeout=60)
        pdf_resp.raise_for_status()
        return pdf_resp.content

    except requests.RequestException as e:
        log.warning(f"  [CA DFPI] Error: {e}")
        return None


def _try_mn_cards() -> bytes | None:
    log.info("  Trying Minnesota CARDS portal")
    base_url = "https://cards.web.commerce.state.mn.us/franchise-registrations"
    try:
        resp = requests.get(base_url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")

        search_url = f"{base_url}?franchisor=Interim+HealthCare&search=Search"
        resp2 = requests.get(search_url, headers=HEADERS, timeout=30)
        resp2.raise_for_status()
        soup = BeautifulSoup(resp2.text, "lxml")

        pdf_links = [a["href"] for a in soup.find_all("a", href=True)
                     if a["href"].lower().endswith(".pdf") and
                     ("interim" in a.get_text(strip=True).lower() or "interim" in a["href"].lower())]
        if not pdf_links:
            return None

        pdf_url = pdf_links[0]
        if not pdf_url.startswith("http"):
            pdf_url = urljoin(base_url, pdf_url)

        log.info("  [MN CARDS] Downloading FDD")
        pdf_resp = requests.get(pdf_url, headers=HEADERS, timeout=60)
        pdf_resp.raise_for_status()
        return pdf_resp.content

    except requests.RequestException as e:
        log.warning(f"  [MN CARDS] Error: {e}")
        return None


def _try_website_fallback() -> list[dict]:
    log.info("  FDD portals unavailable — trying Interim HealthCare website")
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        log.warning("  playwright not installed")
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

            for card in soup.find_all(["div", "li", "article"],
                                       class_=re.compile(r"location|office|franchise|office-card", re.I)):
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
            log.error(f"  Interim website error: {e}", exc_info=True)
        finally:
            browser.close()

    log.info(f"  → {len(records)} locations from Interim website")
    return records


def run(config: dict, test: bool = False) -> list[dict]:
    pdf_bytes = _try_ca_dfpi()
    if not pdf_bytes:
        pdf_bytes = _try_mn_cards()

    if pdf_bytes:
        log.info(f"  Parsing FDD Item 20 ({len(pdf_bytes):,} bytes)")
        records = _extract_item_20_from_pdf(pdf_bytes)
        if test:
            records = records[:20]
    else:
        records = _try_website_fallback()
        if test:
            records = records[:20]

    log.info(f"  fdd_franchisees: {len(records)} records")
    return records
