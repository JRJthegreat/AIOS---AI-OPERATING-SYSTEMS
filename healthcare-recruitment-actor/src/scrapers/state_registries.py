"""
State government licensing registries for healthcare staffing agencies.

Sources:
  NY  — DOH HTML table
  IN  — DOH PDF (monthly list)
  TN  — HFC Excel
  MD  — OHCQ Excel
  MN  — DOH web form
  NJ  — MyLicense bulk (Health Care Service Firm)
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
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

DEFAULT_STATES = ["NY", "IN", "TN", "MD", "MN", "NJ", "PA", "MI"]

_BUSINESS_SIGNALS = re.compile(
    r"\b(llc|inc|corp|ltd|co\.|company|group|health|care|staffing|services|"
    r"medical|nursing|agency|associates|partners|solutions|resources|temp|"
    r"professionals|workforce|talent|registry|supplemental|clinical)\b",
    re.I,
)


def _looks_like_business(name: str) -> bool:
    n = name.strip()
    if not n or re.match(r"^\d+$", n):  # reject pure numbers (license IDs)
        return False
    if _BUSINESS_SIGNALS.search(n):
        return True
    if re.match(r"^[A-Z][a-z]+ [A-Z][a-z]+$", n):
        return False
    return len(n) > 5


def _best_name_col(columns: list[str]) -> str | None:
    """Prefer explicit business-name columns over generic 'name' columns."""
    priority = ["agency name", "business name", "company name", "facility name",
                "organization name", "licensee", "agency", "facility", "business", "company"]
    for p in priority:
        for col in columns:
            if p in col:
                return col
    _contact_words = {"owner", "contact", "primary", "individual", "person", "director", "administrator"}
    for col in columns:
        if "name" in col and not any(w in col for w in _contact_words):
            return col
    log.warning(f"  No clean business-name column found among: {columns}")
    return None


def _record(company_name: str, state: str, address: str = "", city: str = "",
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


def _scrape_ny(test: bool = False) -> list[dict]:
    log.info("  [NY] Scraping DOH Registered Staffing Agencies")
    url = "https://www.health.ny.gov/facilities/staffing_agency/agency_list.htm"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as e:
        log.warning(f"  [NY] Error: {e}")
        return []

    soup = BeautifulSoup(resp.text, "lxml")
    records = []
    for table in soup.find_all("table"):
        for row in table.find_all("tr")[1:]:
            cells = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
            if len(cells) < 2:
                continue
            name = cells[0]
            if not name or name.lower() in ("agency name", "name"):
                continue
            # Skip registration numbers (TAnnnn) and bare row-counter cells (1, 2, 3…)
            data_cells = [c for c in cells[1:] if c and not re.match(r'^TA\d+$', c, re.I) and not re.match(r'^\d{1,3}$', c)]
            address = data_cells[0] if len(data_cells) > 0 else ""
            city = data_cells[1] if len(data_cells) > 1 else ""
            phone = data_cells[2] if len(data_cells) > 2 else ""
            records.append(_record(name, "NY", address=address, city=city, phone=phone, license_type="Registered Staffing Agency"))
            if test and len(records) >= 10:
                break
        if records:
            break

    log.info(f"  [NY] → {len(records)} agencies")
    return records


def _scrape_in(test: bool = False) -> list[dict]:
    log.info("  [IN] Scraping DOH Temporary Health Care Services Agency Registry")
    try:
        import pdfplumber
    except ImportError:
        log.warning("  [IN] pdfplumber not installed, skipping")
        return []

    registry_url = "https://www.in.gov/health/cshcr/temporary-health-care-services-agency-registry/"
    records = []

    try:
        resp = requests.get(registry_url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")
        pdf_links = [a["href"] for a in soup.find_all("a", href=True)
                     if a["href"].lower().endswith(".pdf")]
    except requests.RequestException as e:
        log.warning(f"  [IN] Page error: {e}")
        return []

    if not pdf_links:
        log.warning("  [IN] No PDF found on registry page")
        return []

    pdf_url = pdf_links[0]
    if not pdf_url.startswith("http"):
        pdf_url = urljoin(registry_url, pdf_url)

    try:
        pdf_resp = requests.get(pdf_url, headers=HEADERS, timeout=30)
        pdf_resp.raise_for_status()
    except requests.RequestException as e:
        log.warning(f"  [IN] PDF download error: {e}")
        return []

    with pdfplumber.open(io.BytesIO(pdf_resp.content)) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            for line in [l.strip() for l in text.split("\n") if l.strip()]:
                if len(line) < 5 or line.lower().startswith(("agency", "registered", "page", "indiana")):
                    continue
                phone_match = re.search(r"\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}", line)
                phone = phone_match.group(0) if phone_match else ""
                name = re.sub(r"\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}", "", line).strip()
                name = re.sub(r"\s{2,}", " ", name)
                if len(name) > 3:
                    records.append(_record(name, "IN", phone=phone, license_type="Registered Staffing Agency"))
                if test and len(records) >= 10:
                    break
            if test and records:
                break

    log.info(f"  [IN] → {len(records)} agencies")
    return records


def _scrape_tn(test: bool = False) -> list[dict]:
    log.info("  [TN] Scraping HFC Temporary Healthcare Staffing Registry")
    try:
        import pandas as pd
    except ImportError:
        log.warning("  [TN] pandas not installed, skipping")
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
        log.warning(f"  [TN] Page error: {e}")
        return []

    if not excel_links:
        log.warning("  [TN] No Excel/CSV found on page")
        return []

    file_url = excel_links[0]
    if not file_url.startswith("http"):
        file_url = urljoin(registry_url, file_url)

    try:
        file_resp = requests.get(file_url, headers=HEADERS, timeout=30)
        file_resp.raise_for_status()
        df = pd.read_csv(io.BytesIO(file_resp.content)) if file_url.endswith(".csv") \
            else pd.read_excel(io.BytesIO(file_resp.content))
    except Exception as e:
        log.warning(f"  [TN] Parse error: {e}")
        return []

    df.columns = [str(c).strip().lower() for c in df.columns]
    all_name_cols = [c for c in df.columns if any(k in c for k in ["name", "agency", "facility", "company"])]
    name_col = _best_name_col(all_name_cols)
    phone_cols = [c for c in df.columns if "phone" in c or "tel" in c]
    addr_cols = [c for c in df.columns if "address" in c or "addr" in c]
    city_cols = [c for c in df.columns if "city" in c]
    zip_cols = [c for c in df.columns if "zip" in c or "postal" in c]

    if not name_col:
        log.warning(f"  [TN] Could not find name column. Columns: {list(df.columns)}")
        return []

    log.info(f"  [TN] Using name column: '{name_col}'")
    for _, row in df.iterrows():
        name = str(row[name_col]).strip()
        if not name or name.lower() in ("nan", "name", "agency name"):
            continue
        if not _looks_like_business(name):
            continue
        records.append(_record(
            name, "TN",
            address=str(row[addr_cols[0]]).strip() if addr_cols else "",
            city=str(row[city_cols[0]]).strip() if city_cols else "",
            zip_code=str(row[zip_cols[0]]).strip() if zip_cols else "",
            phone=str(row[phone_cols[0]]).strip() if phone_cols else "",
            license_type="Registered Healthcare Staffing",
        ))
        if test and len(records) >= 10:
            break

    log.info(f"  [TN] → {len(records)} agencies")
    return records


def _scrape_md(test: bool = False) -> list[dict]:
    log.info("  [MD] Scraping OHCQ Health Care Staffing Agency list")
    try:
        import pandas as pd
    except ImportError:
        log.warning("  [MD] pandas not installed, skipping")
        return []

    excel_url = "https://health.maryland.gov/ohcq/docs/Provider-Listings/Excel/Health%20Care%20Staffing%20Agencies-EXCEL.xlsx"
    records = []

    try:
        resp = requests.get(excel_url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as e:
        log.warning(f"  [MD] Direct URL failed ({e}), trying directory page")
        try:
            dir_resp = requests.get(
                "https://health.maryland.gov/ohcq/Pages/OHCQ-Licensee-Directories.aspx",
                headers=HEADERS, timeout=30,
            )
            dir_resp.raise_for_status()
            soup = BeautifulSoup(dir_resp.text, "lxml")
            excel_links = [a["href"] for a in soup.find_all("a", href=True)
                           if "staffing" in a["href"].lower() and
                           any(ext in a["href"].lower() for ext in [".xlsx", ".xls"])]
            if not excel_links:
                log.warning("  [MD] No Excel link found")
                return []
            excel_url = urljoin("https://health.maryland.gov", excel_links[0])
            resp = requests.get(excel_url, headers=HEADERS, timeout=30)
            resp.raise_for_status()
        except requests.RequestException as e2:
            log.warning(f"  [MD] Fallback also failed: {e2}")
            return []

    try:
        df = pd.read_excel(io.BytesIO(resp.content))
    except Exception as e:
        log.warning(f"  [MD] Parse error: {e}")
        return []

    df.columns = [str(c).strip().lower() for c in df.columns]
    log.info(f"  [MD] Excel columns: {list(df.columns)}")
    all_name_cols = [c for c in df.columns if any(k in c for k in ["name", "agency", "facility", "company", "licensee", "provider", "organization"])]
    name_col = _best_name_col(all_name_cols)
    phone_cols = [c for c in df.columns if "phone" in c or "tel" in c]
    addr_cols = [c for c in df.columns if "address" in c]
    city_cols = [c for c in df.columns if "city" in c]
    zip_cols = [c for c in df.columns if "zip" in c]

    if not name_col:
        log.warning(f"  [MD] Could not find name column. Columns: {list(df.columns)}")
        return []

    log.info(f"  [MD] Using name column: '{name_col}'")
    for _, row in df.iterrows():
        name = str(row[name_col]).strip()
        if not name or name.lower() in ("nan", "name"):
            continue
        if not _looks_like_business(name):
            continue
        records.append(_record(
            name, "MD",
            address=str(row[addr_cols[0]]).strip() if addr_cols else "",
            city=str(row[city_cols[0]]).strip() if city_cols else "",
            zip_code=str(row[zip_cols[0]]).strip() if zip_cols else "",
            phone=str(row[phone_cols[0]]).strip() if phone_cols else "",
            license_type="Licensed Healthcare Staffing Agency",
        ))
        if test and len(records) >= 10:
            break

    log.info(f"  [MD] → {len(records)} agencies")
    return records


def _scrape_mn(test: bool = False) -> list[dict]:
    log.info("  [MN] Scraping DOH Supplemental Nursing Services Agency directory")
    url = "https://www.health.state.mn.us/facilities/regulation/directory/providerlist.cfm"
    records = []

    try:
        resp = requests.post(url, headers=HEADERS, timeout=30, data={"providertypecd": "SNSA", "B1": "Search"})
        resp.raise_for_status()
    except requests.RequestException as e:
        log.warning(f"  [MN] Error: {e}")
        return []

    soup = BeautifulSoup(resp.text, "lxml")
    for table in soup.find_all("table"):
        for row in table.find_all("tr")[1:]:
            cells = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
            if len(cells) < 2 or not cells[0] or len(cells[0]) < 3:
                continue
            records.append(_record(cells[0], "MN",
                                   city=cells[1] if len(cells) > 1 else "",
                                   phone=cells[2] if len(cells) > 2 else "",
                                   license_type="Supplemental Nursing Services Agency"))
            if test and len(records) >= 10:
                break
        if records:
            break

    log.info(f"  [MN] → {len(records)} agencies")
    return records


def _scrape_nj(test: bool = False) -> list[dict]:
    log.info("  [NJ] Scraping MyLicense Health Care Service Firm directory")
    search_url = "https://newjersey.mylicense.com/verification/Search.aspx"
    records = []

    try:
        resp = requests.get(search_url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")

        viewstate = soup.find("input", {"id": "__VIEWSTATE"})
        viewstate_gen = soup.find("input", {"id": "__VIEWSTATEGENERATOR"})
        event_validation = soup.find("input", {"id": "__EVENTVALIDATION"})

        post_resp = requests.post(
            search_url,
            headers={**HEADERS, "Content-Type": "application/x-www-form-urlencoded"},
            data={
                "__VIEWSTATE": viewstate["value"] if viewstate else "",
                "__VIEWSTATEGENERATOR": viewstate_gen["value"] if viewstate_gen else "",
                "__EVENTVALIDATION": event_validation["value"] if event_validation else "",
                "t_web_lookup__license_type_name": "Health Care Service Firm",
                "t_web_lookup__first_name": "",
                "t_web_lookup__last_name": "",
                "t_web_lookup__license_no": "",
                "sch_button": "Search",
            },
            timeout=30,
        )
        post_resp.raise_for_status()
        result_soup = BeautifulSoup(post_resp.text, "lxml")

        table = result_soup.find("table", {"id": "datagrid_results"})
        if not table:
            tables = result_soup.find_all("table", class_=re.compile(r"result|data|grid", re.I))
            table = tables[0] if tables else None

        if table:
            for row in table.find_all("tr")[1:]:
                cells = [c.get_text(strip=True) for c in row.find_all("td")]
                if not cells or len(cells[0]) < 3:
                    continue
                records.append(_record(cells[0], "NJ",
                                       city=cells[2] if len(cells) > 2 else "",
                                       license_type="Health Care Service Firm"))
                if test and len(records) >= 10:
                    break

    except requests.RequestException as e:
        log.warning(f"  [NJ] Error: {e}")
        return []

    log.info(f"  [NJ] → {len(records)} agencies")
    return records


def _scrape_tx(test: bool = False) -> list[dict]:
    log.info("  [TX] Scraping HCSSA Provider Directory")
    try:
        import pandas as pd
    except ImportError:
        log.warning("  [TX] pandas not installed, skipping")
        return []

    url = "https://apps.hhs.texas.gov/providers/directories/HHA.xlsx"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=60)
        resp.raise_for_status()
        # Row 0 is a merged title cell; row 1 contains actual column headers
        df = pd.read_excel(io.BytesIO(resp.content), header=1)
    except Exception as e:
        log.warning(f"  [TX] Error: {e}")
        return []

    df.columns = [str(c).strip().lower() for c in df.columns]
    log.info(f"  [TX] Columns: {list(df.columns)}")
    all_name_cols = [c for c in df.columns if any(k in c for k in ["name", "agency", "provider", "facility"])]
    name_col = _best_name_col(all_name_cols)
    phone_cols = [c for c in df.columns if "phone" in c or "tel" in c]
    addr_cols = [c for c in df.columns if "address" in c or "street" in c]
    city_cols = [c for c in df.columns if "city" in c]
    zip_cols = [c for c in df.columns if "zip" in c]

    if not name_col:
        log.warning(f"  [TX] No name column. Columns: {list(df.columns)}")
        return []

    # Validate the selected column actually contains business names, not IDs
    sample_vals = df[name_col].dropna().astype(str).head(20).tolist()
    alpha_ratio = sum(1 for v in sample_vals if re.search(r"[A-Za-z]{3,}", v)) / max(len(sample_vals), 1)
    if alpha_ratio < 0.5:
        log.warning(f"  [TX] Column '{name_col}' looks like IDs (alpha ratio {alpha_ratio:.0%}), not business names. Trying fallback.")
        # Try any column with mostly alphabetic values
        for col in df.columns:
            if col == name_col:
                continue
            s = df[col].dropna().astype(str).head(20).tolist()
            ratio = sum(1 for v in s if re.search(r"[A-Za-z]{3,}", v)) / max(len(s), 1)
            if ratio >= 0.8 and any(k in col for k in ["name", "program", "provider"]):
                name_col = col
                log.info(f"  [TX] Using fallback column '{col}' (alpha ratio {ratio:.0%})")
                break
        else:
            log.warning(f"  [TX] No valid name column found — skipping TX")
            return []

    records = []
    for _, row in df.iterrows():
        name = str(row[name_col]).strip()
        if not name or name.lower() in ("nan",) or not _looks_like_business(name):
            continue
        records.append(_record(
            name, "TX",
            address=str(row[addr_cols[0]]).strip() if addr_cols else "",
            city=str(row[city_cols[0]]).strip() if city_cols else "",
            zip_code=str(row[zip_cols[0]]).strip() if zip_cols else "",
            phone=str(row[phone_cols[0]]).strip() if phone_cols else "",
            license_type="HCSSA",
        ))
        if test and len(records) >= 10:
            break

    log.info(f"  [TX] → {len(records)} agencies")
    return records


def _scrape_pa(test: bool = False) -> list[dict]:
    log.info("  [PA] Scraping THCSA Registered Agencies PDF")
    try:
        import pdfplumber
    except ImportError:
        log.warning("  [PA] pdfplumber not installed, skipping")
        return []

    pdf_url = ("https://www.pa.gov/content/dam/copapwp-pagov/en/health/documents/topics/"
               "documents/facilities-and-licensing/THCSA%20Registered%20Agencies.pdf")
    try:
        resp = requests.get(pdf_url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as e:
        log.warning(f"  [PA] Error: {e}")
        return []

    records = []
    try:
        with pdfplumber.open(io.BytesIO(resp.content)) as pdf:
            for page in pdf.pages:
                for table in page.extract_tables():
                    for row in table:
                        cells = [str(c or "").strip() for c in row if c]
                        name = cells[0] if cells else ""
                        if not name or not _looks_like_business(name):
                            continue
                        records.append(_record(
                            name, "PA",
                            address=cells[1] if len(cells) > 1 else "",
                            city=cells[2] if len(cells) > 2 else "",
                            zip_code=cells[3] if len(cells) > 3 else "",
                            phone=cells[4] if len(cells) > 4 else "",
                            license_type="Temporary Health Care Services Agency",
                        ))
                        if test and len(records) >= 10:
                            break

                if not records:
                    for line in (page.extract_text() or "").split("\n"):
                        line = line.strip()
                        if len(line) < 5 or not _looks_like_business(line):
                            continue
                        phone_m = re.search(r"\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}", line)
                        name = re.sub(r"\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}", "", line).strip()
                        if len(name) > 3:
                            records.append(_record(name, "PA",
                                                   phone=phone_m.group(0) if phone_m else "",
                                                   license_type="Temporary Health Care Services Agency"))
                        if test and len(records) >= 10:
                            break
    except Exception as e:
        log.warning(f"  [PA] Parse error: {e}")

    log.info(f"  [PA] → {len(records)} agencies")
    return records


def _scrape_nc(test: bool = False) -> list[dict]:
    log.info("  [NC] Scraping DHSR Home Care Agency listings")
    listings_url = "https://info.ncdhhs.gov/dhsr/ahc/listings.html"

    # Try direct PDF first (confirmed by research)
    direct_pdf = "https://info.ncdhhs.gov/dhsr/data/hclist.pdf"
    txt_links: list[str] = []
    pdf_links: list[str] = [direct_pdf]

    try:
        resp = requests.get(listings_url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")
        found_txt = [a["href"] for a in soup.find_all("a", href=True)
                     if any(ext in a["href"].lower() for ext in [".txt", ".csv"])]
        found_pdf = [a["href"] for a in soup.find_all("a", href=True)
                     if a["href"].lower().endswith(".pdf")]
        if found_txt:
            txt_links = found_txt
        if found_pdf:
            # Keep direct_pdf first so it's always tried before page-scraped links
            pdf_links = [direct_pdf] + [p for p in found_pdf if p != direct_pdf]
    except requests.RequestException as e:
        log.warning(f"  [NC] Listings page error ({e}), trying direct PDF")

    records = []

    if txt_links:
        file_url = txt_links[0]
        if not file_url.startswith("http"):
            file_url = urljoin(listings_url, file_url)
        try:
            import csv
            file_resp = requests.get(file_url, headers=HEADERS, timeout=30)
            file_resp.raise_for_status()
            reader = csv.DictReader(io.StringIO(file_resp.text))
            for row in reader:
                name = next((str(row[k]).strip() for k in row
                             if any(x in k.lower() for x in ["name", "agency", "provider"])), "")
                if not name or not _looks_like_business(name):
                    continue
                records.append(_record(
                    name, "NC",
                    address=next((str(row[k]) for k in row if "address" in k.lower()), ""),
                    city=next((str(row[k]) for k in row if "city" in k.lower()), ""),
                    zip_code=next((str(row[k]) for k in row if "zip" in k.lower()), ""),
                    phone=next((str(row[k]) for k in row if "phone" in k.lower()), ""),
                    license_type="Home Care Agency",
                ))
                if test and len(records) >= 10:
                    break
        except Exception as e:
            log.warning(f"  [NC] Text parse error: {e}")

    elif pdf_links:
        try:
            import pdfplumber
            pdf_url = pdf_links[0]
            if not pdf_url.startswith("http"):
                pdf_url = urljoin(listings_url, pdf_url)
            pdf_resp = requests.get(pdf_url, headers=HEADERS, timeout=30)
            pdf_resp.raise_for_status()
            with pdfplumber.open(io.BytesIO(pdf_resp.content)) as pdf:
                for page in pdf.pages:
                    for table in page.extract_tables():
                        for row in table:
                            cells = [str(c or "").strip() for c in row]
                            name = cells[0] if cells else ""
                            if not name or not _looks_like_business(name):
                                continue
                            records.append(_record(name, "NC",
                                                   city=cells[2] if len(cells) > 2 else "",
                                                   license_type="Home Care Agency"))
                            if test and len(records) >= 10:
                                break
        except Exception as e:
            log.warning(f"  [NC] PDF parse error: {e}")

    log.info(f"  [NC] → {len(records)} agencies")
    return records


def _scrape_wa(test: bool = False) -> list[dict]:
    log.info("  [WA] Scraping Socrata Health Care Provider Credential Data (Nursing Pool)")
    url = "https://data.wa.gov/resource/qxh8-f4bd.json"
    records = []
    offset = 0
    limit = 1000

    while True:
        try:
            resp = requests.get(url, headers=HEADERS, timeout=30, params={
                "$limit": limit,
                "$offset": offset,
            })
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            log.warning(f"  [WA] Error at offset={offset}: {e}")
            break

        if not data:
            break

        for row in data:
            cred_type = str(row.get("credential_type", "") or row.get("credentialtype", "")).lower()
            if "nursing" not in cred_type and "pool" not in cred_type:
                continue
            status = str(row.get("credential_status", "") or row.get("credentialstatus", "")).upper()
            if status and status not in ("ACTIVE", ""):
                continue
            name = (row.get("credential_holder") or row.get("business_name") or
                    row.get("name") or "").strip()
            if not name or not _looks_like_business(name):
                continue
            records.append(_record(
                name, "WA",
                city=row.get("city", ""),
                zip_code=str(row.get("zip", row.get("postal_code", "")))[:5],
                phone=row.get("phone", ""),
                license_type="Nursing Pool",
            ))
            if test and len(records) >= 10:
                break

        if len(data) < limit or (test and records):
            break
        offset += limit

    log.info(f"  [WA] → {len(records)} agencies")
    return records


def _scrape_mi(test: bool = False) -> list[dict]:
    log.info("  [MI] Scraping LARA Personnel Agency license list")
    try:
        import pandas as pd
    except ImportError:
        log.warning("  [MI] pandas not installed, skipping")
        return []

    reports_url = "https://www.michigan.gov/lara/bureau-list/bpl/license-lists-and-reports"
    try:
        resp = requests.get(reports_url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")
        excel_links = [a["href"] for a in soup.find_all("a", href=True)
                       if any(ext in a["href"].lower() for ext in [".xlsx", ".xls"])
                       and any(kw in (a.get_text(strip=True) + a["href"]).lower()
                               for kw in ["personnel", "m-o", "m–o", "foia", "license"])]
        if not excel_links:
            excel_links = [a["href"] for a in soup.find_all("a", href=True)
                           if any(ext in a["href"].lower() for ext in [".xlsx", ".xls"])]
        log.info(f"  [MI] Found {len(excel_links)} Excel link(s)")
        if not excel_links:
            log.warning("  [MI] No Excel link found")
            return []
        file_url = excel_links[0]
        if not file_url.startswith("http"):
            file_url = urljoin(reports_url, file_url)
        file_resp = requests.get(file_url, headers=HEADERS, timeout=60)
        file_resp.raise_for_status()
        df = pd.read_excel(io.BytesIO(file_resp.content))
    except Exception as e:
        log.warning(f"  [MI] Error: {e}")
        return []

    df.columns = [str(c).strip().lower() for c in df.columns]
    license_col = next((c for c in df.columns if "license" in c or "type" in c or "profession" in c), None)
    if license_col:
        df = df[df[license_col].astype(str).str.contains("personnel", case=False, na=False)]

    all_name_cols = [c for c in df.columns if any(k in c for k in ["name", "business", "company", "agency"])]
    name_col = _best_name_col(all_name_cols)
    city_cols = [c for c in df.columns if "city" in c]
    zip_cols = [c for c in df.columns if "zip" in c]
    phone_cols = [c for c in df.columns if "phone" in c]

    if not name_col:
        log.warning(f"  [MI] No name column. Columns: {list(df.columns)}")
        return []

    records = []
    for _, row in df.iterrows():
        name = str(row[name_col]).strip()
        if not name or name.lower() == "nan" or not _looks_like_business(name):
            continue
        records.append(_record(
            name, "MI",
            city=str(row[city_cols[0]]).strip() if city_cols else "",
            zip_code=str(row[zip_cols[0]]).strip() if zip_cols else "",
            phone=str(row[phone_cols[0]]).strip() if phone_cols else "",
            license_type="Personnel Agency",
        ))
        if test and len(records) >= 10:
            break

    log.info(f"  [MI] → {len(records)} agencies")
    return records


def _scrape_fl(test: bool = False) -> list[dict]:
    log.info("  [FL] Scraping FloridaHealthFinder Nurse Registry")
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        log.warning("  [FL] playwright not installed, skipping")
        return []

    fl_counties = [
        "Broward", "Miami-Dade", "Duval", "Hillsborough", "Orange", "Palm Beach",
        "Pinellas", "Polk", "Brevard", "Volusia", "Sarasota", "Lee", "Collier",
        "Alachua", "Leon", "Escambia", "Osceola", "Seminole", "Pasco", "Manatee",
    ]
    records = []
    seen: set[str] = set()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_context().new_page()

        for county in fl_counties:
            try:
                page.goto("https://quality.healthfinder.fl.gov/Facility-Provider/Nurse-Registry?type=1",
                          wait_until="networkidle", timeout=30000)
                time.sleep(1)

                county_sel = page.query_selector(
                    "select[name*='ounty'], select[id*='ounty']")
                if county_sel:
                    county_sel.select_option(label=county)
                    page.click("input[type='submit'], button[type='submit']")
                    page.wait_for_load_state("networkidle", timeout=15000)

                soup = BeautifulSoup(page.content(), "lxml")
                for row in soup.find_all("tr"):
                    cells = [c.get_text(strip=True) for c in row.find_all("td")]
                    if len(cells) < 2:
                        continue
                    name = cells[0]
                    if not name or name in seen or not _looks_like_business(name):
                        continue
                    seen.add(name)
                    phone_m = re.search(r"\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}", " ".join(cells))
                    records.append(_record(name, "FL",
                                           city=county,
                                           phone=phone_m.group(0) if phone_m else "",
                                           license_type="Nurse Registry"))
                    if test and len(records) >= 10:
                        break
            except Exception as e:
                log.warning(f"  [FL] {county}: {e}")
                continue
            if test and records:
                break

        browser.close()

    log.info(f"  [FL] → {len(records)} agencies")
    return records


_SCRAPERS = {
    "NY": _scrape_ny,
    "IN": _scrape_in,
    "TN": _scrape_tn,
    "MD": _scrape_md,
    "MN": _scrape_mn,
    "NJ": _scrape_nj,
    "TX": _scrape_tx,
    "PA": _scrape_pa,
    "NC": _scrape_nc,
    "WA": _scrape_wa,
    "MI": _scrape_mi,
    "FL": _scrape_fl,
}


def run(config: dict, test: bool = False) -> list[dict]:
    states = config.get("states", DEFAULT_STATES)
    all_records: list[dict] = []

    for state in states:
        fn = _SCRAPERS.get(state)
        if fn is None:
            log.warning(f"  Unknown state '{state}' — skipping")
            continue
        try:
            records = fn(test=test)
            all_records.extend(records)
        except Exception as e:
            log.error(f"  [state_registries/{state}] failed: {e}", exc_info=True)
        time.sleep(1)

    log.info(f"  state_registries: {len(all_records)} total agencies")
    return all_records
