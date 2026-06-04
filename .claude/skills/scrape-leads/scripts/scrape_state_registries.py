#!/usr/bin/env python3
"""
Scrape state government licensing registries for healthcare staffing agencies.

Sources:
  NY  — DOH HTML table: https://www.health.ny.gov/facilities/staffing_agency/agency_list.htm
  IN  — DOH PDF (monthly list): https://www.in.gov/health/cshcr/temporary-health-care-services-agency-registry/
  TN  — HFC Excel: https://www.tn.gov/hfc/temporary-healthcare-staffing-registry.html
  MD  — OHCQ Excel: https://health.maryland.gov/ohcq/Pages/OHCQ-Licensee-Directories.aspx
  MN  — DOH web scrape (filterable directory): https://www.health.state.mn.us/facilities/regulation/directory/
  NJ  — MyLicense bulk (Health Care Service Firm): https://newjersey.mylicense.com/verification/

Pattern: build-scrapers/02-first-scraper.md (HTML table) + 05-government-data.md (Excel/CSV/PDF)
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

try:
    import pandas as pd
    HAS_PANDAS = True
except ImportError:
    HAS_PANDAS = False

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def make_record(company_name: str, state: str, address: str = "", city: str = "",
                zip_code: str = "", phone: str = "", license_type: str = "") -> dict:
    return {
        "company_name": company_name.strip(),
        "address": address.strip(),
        "city": city.strip(),
        "state": state,
        "zip": zip_code.strip(),
        "phone": phone.strip(),
        "license_type": license_type,
        "source": "state_registry",
        "date_scraped": datetime.now().strftime("%Y-%m-%d"),
    }


# ─── NEW YORK ─────────────────────────────────────────────────────────────────

def scrape_ny(test: bool = False) -> list[dict]:
    print("  [NY] Scraping DOH Registered Staffing Agencies...")
    url = "https://www.health.ny.gov/facilities/staffing_agency/agency_list.htm"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"  [NY] Error: {e}", file=sys.stderr)
        return []

    soup = BeautifulSoup(resp.text, "lxml")
    records = []

    # NY page has a table with columns: Agency Name, City, County, Phone
    tables = soup.find_all("table")
    for table in tables:
        rows = table.find_all("tr")
        for row in rows[1:]:  # skip header
            cells = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
            if len(cells) < 2:
                continue
            name = cells[0]
            if not name or name.lower() in ("agency name", "name"):
                continue
            city = cells[1] if len(cells) > 1 else ""
            phone = cells[3] if len(cells) > 3 else ""
            records.append(make_record(name, "NY", city=city, phone=phone, license_type="Registered Staffing Agency"))
            if test and len(records) >= 10:
                break
        if records:
            break

    print(f"  [NY] → {len(records)} agencies")
    return records


# ─── INDIANA ──────────────────────────────────────────────────────────────────

def scrape_in(test: bool = False) -> list[dict]:
    print("  [IN] Scraping DOH Temporary Health Care Services Agency Registry...")
    # IN publishes a PDF list. Try to find the latest PDF link on the registry page.
    registry_url = "https://www.in.gov/health/cshcr/temporary-health-care-services-agency-registry/"
    records = []

    try:
        resp = requests.get(registry_url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")
        # Find PDF links
        pdf_links = [a["href"] for a in soup.find_all("a", href=True)
                     if a["href"].lower().endswith(".pdf") and "staffing" in a["href"].lower()]
        if not pdf_links:
            # Broader search for any PDF on the page
            pdf_links = [a["href"] for a in soup.find_all("a", href=True)
                         if a["href"].lower().endswith(".pdf")]
    except requests.RequestException as e:
        print(f"  [IN] Page error: {e}", file=sys.stderr)
        return []

    if not pdf_links:
        print("  [IN] No PDF found on registry page", file=sys.stderr)
        return []

    pdf_url = pdf_links[0]
    if not pdf_url.startswith("http"):
        pdf_url = urljoin(registry_url, pdf_url)

    if not HAS_PDFPLUMBER:
        print("  [IN] pdfplumber not installed, skipping", file=sys.stderr)
        return []

    try:
        pdf_resp = requests.get(pdf_url, headers=HEADERS, timeout=30)
        pdf_resp.raise_for_status()
    except requests.RequestException as e:
        print(f"  [IN] PDF download error: {e}", file=sys.stderr)
        return []

    with pdfplumber.open(io.BytesIO(pdf_resp.content)) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            lines = [l.strip() for l in text.split("\n") if l.strip()]
            for line in lines:
                # Lines typically: "Agency Name    City, IN 12345    Phone"
                if len(line) < 5 or line.lower().startswith(("agency", "registered", "page", "indiana")):
                    continue
                # Try to extract phone (XXX-XXX-XXXX or (XXX) XXX-XXXX)
                phone_match = re.search(r"\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}", line)
                phone = phone_match.group(0) if phone_match else ""
                name = re.sub(r"\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}", "", line).strip()
                name = re.sub(r"\s{2,}", " ", name)
                if len(name) > 3:
                    records.append(make_record(name, "IN", phone=phone, license_type="Registered Staffing Agency"))
                if test and len(records) >= 10:
                    break
            if test and records:
                break

    print(f"  [IN] → {len(records)} agencies")
    return records


# ─── TENNESSEE ────────────────────────────────────────────────────────────────

def scrape_tn(test: bool = False) -> list[dict]:
    print("  [TN] Scraping HFC Temporary Healthcare Staffing Registry...")
    if not HAS_PANDAS:
        print("  [TN] pandas not installed, skipping", file=sys.stderr)
        return []

    registry_url = "https://www.tn.gov/hfc/temporary-healthcare-staffing-registry.html"
    records = []

    try:
        resp = requests.get(registry_url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")
        excel_links = [a["href"] for a in soup.find_all("a", href=True)
                       if any(ext in a["href"].lower() for ext in [".xlsx", ".xls", ".csv"])]
    except requests.RequestException as e:
        print(f"  [TN] Page error: {e}", file=sys.stderr)
        return []

    if not excel_links:
        print("  [TN] No Excel/CSV found on page", file=sys.stderr)
        return []

    file_url = excel_links[0]
    if not file_url.startswith("http"):
        file_url = urljoin(registry_url, file_url)

    try:
        file_resp = requests.get(file_url, headers=HEADERS, timeout=30)
        file_resp.raise_for_status()
    except requests.RequestException as e:
        print(f"  [TN] File download error: {e}", file=sys.stderr)
        return []

    try:
        if file_url.endswith(".csv"):
            df = pd.read_csv(io.BytesIO(file_resp.content))
        else:
            df = pd.read_excel(io.BytesIO(file_resp.content))
    except Exception as e:
        print(f"  [TN] Parse error: {e}", file=sys.stderr)
        return []

    df.columns = [str(c).strip().lower() for c in df.columns]
    name_cols = [c for c in df.columns if any(k in c for k in ["name", "agency", "facility", "company"])]
    phone_cols = [c for c in df.columns if "phone" in c or "tel" in c]
    addr_cols = [c for c in df.columns if "address" in c or "addr" in c]
    city_cols = [c for c in df.columns if "city" in c]
    zip_cols = [c for c in df.columns if "zip" in c or "postal" in c]

    if not name_cols:
        print(f"  [TN] Could not find name column. Columns: {list(df.columns)}", file=sys.stderr)
        return []

    for _, row in df.iterrows():
        name = str(row[name_cols[0]]).strip()
        if not name or name.lower() in ("nan", "name", "agency name"):
            continue
        phone = str(row[phone_cols[0]]).strip() if phone_cols else ""
        address = str(row[addr_cols[0]]).strip() if addr_cols else ""
        city = str(row[city_cols[0]]).strip() if city_cols else ""
        zip_code = str(row[zip_cols[0]]).strip() if zip_cols else ""
        records.append(make_record(name, "TN", address=address, city=city,
                                   zip_code=zip_code, phone=phone,
                                   license_type="Registered Healthcare Staffing"))
        if test and len(records) >= 10:
            break

    print(f"  [TN] → {len(records)} agencies")
    return records


# ─── MARYLAND ─────────────────────────────────────────────────────────────────

def scrape_md(test: bool = False) -> list[dict]:
    print("  [MD] Scraping OHCQ Health Care Staffing Agency list...")
    if not HAS_PANDAS:
        print("  [MD] pandas not installed, skipping", file=sys.stderr)
        return []

    # Direct Excel URL (confirmed in research)
    excel_url = "https://health.maryland.gov/ohcq/docs/Provider-Listings/Excel/Health%20Care%20Staffing%20Agencies-EXCEL.xlsx"
    records = []

    try:
        resp = requests.get(excel_url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as e:
        # Fallback: scrape the directory page for the current URL
        print(f"  [MD] Direct Excel URL failed ({e}), trying directory page...", file=sys.stderr)
        try:
            dir_resp = requests.get(
                "https://health.maryland.gov/ohcq/Pages/OHCQ-Licensee-Directories.aspx",
                headers=HEADERS, timeout=30
            )
            dir_resp.raise_for_status()
            soup = BeautifulSoup(dir_resp.text, "lxml")
            excel_links = [a["href"] for a in soup.find_all("a", href=True)
                           if "staffing" in a["href"].lower() and
                           any(ext in a["href"].lower() for ext in [".xlsx", ".xls"])]
            if not excel_links:
                print("  [MD] No Excel link found", file=sys.stderr)
                return []
            excel_url = urljoin("https://health.maryland.gov", excel_links[0])
            resp = requests.get(excel_url, headers=HEADERS, timeout=30)
            resp.raise_for_status()
        except requests.RequestException as e2:
            print(f"  [MD] Fallback also failed: {e2}", file=sys.stderr)
            return []

    try:
        df = pd.read_excel(io.BytesIO(resp.content))
    except Exception as e:
        print(f"  [MD] Parse error: {e}", file=sys.stderr)
        return []

    df.columns = [str(c).strip().lower() for c in df.columns]
    name_cols = [c for c in df.columns if any(k in c for k in ["name", "agency", "facility"])]
    phone_cols = [c for c in df.columns if "phone" in c or "tel" in c]
    addr_cols = [c for c in df.columns if "address" in c]
    city_cols = [c for c in df.columns if "city" in c]
    zip_cols = [c for c in df.columns if "zip" in c]

    if not name_cols:
        print(f"  [MD] Could not find name column. Columns: {list(df.columns)}", file=sys.stderr)
        return []

    for _, row in df.iterrows():
        name = str(row[name_cols[0]]).strip()
        if not name or name.lower() in ("nan", "name"):
            continue
        phone = str(row[phone_cols[0]]).strip() if phone_cols else ""
        address = str(row[addr_cols[0]]).strip() if addr_cols else ""
        city = str(row[city_cols[0]]).strip() if city_cols else ""
        zip_code = str(row[zip_cols[0]]).strip() if zip_cols else ""
        records.append(make_record(name, "MD", address=address, city=city,
                                   zip_code=zip_code, phone=phone,
                                   license_type="Licensed Healthcare Staffing Agency"))
        if test and len(records) >= 10:
            break

    print(f"  [MD] → {len(records)} agencies")
    return records


# ─── MINNESOTA ────────────────────────────────────────────────────────────────

def scrape_mn(test: bool = False) -> list[dict]:
    print("  [MN] Scraping DOH Supplemental Nursing Services Agency directory...")
    # MN has a web form at health.state.mn.us/facilities/regulation/directory/
    # Provider type code for SNSA: use the search endpoint
    url = "https://www.health.state.mn.us/facilities/regulation/directory/providerlist.cfm"
    records = []

    try:
        # POST form to filter by SNSA provider type
        resp = requests.post(url, headers=HEADERS, timeout=30, data={
            "providertypecd": "SNSA",
            "B1": "Search",
        })
        resp.raise_for_status()
    except requests.RequestException as e:
        # Try GET with query params
        try:
            resp = requests.get(
                "https://www.health.state.mn.us/facilities/regulation/directory/providerselect.html",
                headers=HEADERS, timeout=30
            )
            resp.raise_for_status()
        except requests.RequestException as e2:
            print(f"  [MN] Error: {e2}", file=sys.stderr)
            return []

    soup = BeautifulSoup(resp.text, "lxml")
    tables = soup.find_all("table")

    for table in tables:
        rows = table.find_all("tr")
        for row in rows[1:]:
            cells = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
            if len(cells) < 2:
                continue
            name = cells[0]
            if not name or len(name) < 3:
                continue
            city = cells[1] if len(cells) > 1 else ""
            phone = cells[2] if len(cells) > 2 else ""
            records.append(make_record(name, "MN", city=city, phone=phone,
                                       license_type="Supplemental Nursing Services Agency"))
            if test and len(records) >= 10:
                break
        if records:
            break

    print(f"  [MN] → {len(records)} agencies")
    return records


# ─── NEW JERSEY ───────────────────────────────────────────────────────────────

def scrape_nj(test: bool = False) -> list[dict]:
    print("  [NJ] Scraping MyLicense Health Care Service Firm directory...")
    # NJ MyLicense has a searchable directory; try direct search
    search_url = "https://newjersey.mylicense.com/verification/Search.aspx"
    records = []

    try:
        # Get the form first to get hidden fields
        resp = requests.get(search_url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")

        # Extract ASP.NET form fields
        viewstate = soup.find("input", {"id": "__VIEWSTATE"})
        viewstate_gen = soup.find("input", {"id": "__VIEWSTATEGENERATOR"})
        event_validation = soup.find("input", {"id": "__EVENTVALIDATION"})

        form_data = {
            "__VIEWSTATE": viewstate["value"] if viewstate else "",
            "__VIEWSTATEGENERATOR": viewstate_gen["value"] if viewstate_gen else "",
            "__EVENTVALIDATION": event_validation["value"] if event_validation else "",
            "t_web_lookup__license_type_name": "Health Care Service Firm",
            "t_web_lookup__first_name": "",
            "t_web_lookup__last_name": "",
            "t_web_lookup__license_no": "",
            "sch_button": "Search",
        }

        post_resp = requests.post(search_url, headers={**HEADERS, "Content-Type": "application/x-www-form-urlencoded"},
                                  data=form_data, timeout=30)
        post_resp.raise_for_status()
        result_soup = BeautifulSoup(post_resp.text, "lxml")

        table = result_soup.find("table", {"id": "datagrid_results"})
        if not table:
            tables = result_soup.find_all("table", class_=re.compile(r"result|data|grid", re.I))
            table = tables[0] if tables else None

        if table:
            rows = table.find_all("tr")
            for row in rows[1:]:
                cells = [c.get_text(strip=True) for c in row.find_all(["td"])]
                if not cells:
                    continue
                name = cells[0] if cells else ""
                if not name or len(name) < 3:
                    continue
                city = cells[2] if len(cells) > 2 else ""
                records.append(make_record(name, "NJ", city=city, license_type="Health Care Service Firm"))
                if test and len(records) >= 10:
                    break

    except requests.RequestException as e:
        print(f"  [NJ] Error: {e}", file=sys.stderr)
        return []

    print(f"  [NJ] → {len(records)} agencies")
    return records


# ─── MAIN ─────────────────────────────────────────────────────────────────────

SCRAPERS = {
    "NY": scrape_ny,
    "IN": scrape_in,
    "TN": scrape_tn,
    "MD": scrape_md,
    "MN": scrape_mn,
    "NJ": scrape_nj,
}


def main():
    parser = argparse.ArgumentParser(description="Scrape state government healthcare staffing registries")
    parser.add_argument("--states", nargs="+", default=list(SCRAPERS.keys()),
                        choices=list(SCRAPERS.keys()), help="States to scrape")
    parser.add_argument("--output", default=".tmp/source_e_state_registries.json", help="Output JSON file")
    parser.add_argument("--test", action="store_true", help="Test mode: max 10 records per state")
    args = parser.parse_args()

    import os
    os.makedirs(".tmp", exist_ok=True)

    all_records = []
    for state in args.states:
        print(f"\nScraping {state}...")
        records = SCRAPERS[state](test=args.test)
        all_records.extend(records)
        time.sleep(1)

    with open(args.output, "w") as f:
        json.dump(all_records, f, indent=2)

    from collections import Counter
    by_state = Counter(r["state"] for r in all_records)
    print(f"\nDone. {len(all_records)} total agencies → {args.output}")
    for state, count in sorted(by_state.items()):
        print(f"  {state}: {count}")


if __name__ == "__main__":
    main()
