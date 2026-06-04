"""
NPPES NPI Registry scraper (CMS).
Pulls nursing care agencies from the federal provider database — not in any B2B tool.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime

import requests

log = logging.getLogger(__name__)

NPPES_API = "https://npiregistry.cms.hhs.gov/api/"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; research-bot/1.0)", "Accept": "application/json"}
PAGE_SIZE = 200
DELAY = 0.5

FACILITY_KEYWORDS = {
    "hospital", "medical center", "health system", "health systems", "clinic",
    "pharmacy", "laboratory", "hospice", "assisted living", "rehabilitation",
    "rehab center", "nursing home", "skilled nursing", "long term care", "ltc",
    "surgery center", "diagnostic", "imaging center", "dialysis", "therapy center",
    "home health", "home care", "home nursing", "personal care", "private duty",
    "adult day", "group home", "residential", "inpatient", "outpatient",
}

# organization_name uses starts-with matching; wrap in * for contains search.
# Far more precise than taxonomy_description="Nursing Care" which returns all
# nursing care providers (homes, hospices) rather than staffing agencies.
DEFAULT_QUERIES = [
    "*staffing*", "*placement*", "*recruiting*", "*locum*", "*per diem*",
    "*registry*",      # nurse registries = staffing agencies
    "*supplemental*",  # supplemental nursing = agency language
    "*allied*",        # allied health staffing
    "*travel nurse*",  # travel nurse agencies
    "*medical staffing*",
    "*clinical staffing*",
    "*healthcare staffing*",
]

# Must contain at least one hard signal to be a staffing agency
_HARD_SIGNALS = {
    "staffing", "placement", "recruiting", "recruitment", "locum",
    "per diem", "travel nurse", "agency", "temp",
}


def _is_staffing(name: str) -> bool:
    name_lower = name.lower()
    if any(f in name_lower for f in FACILITY_KEYWORDS):
        return False
    return any(s in name_lower for s in _HARD_SIGNALS)


def _extract(result: dict) -> dict | None:
    basic = result.get("basic", {})
    name = basic.get("organization_name", "").strip()
    if not name or not _is_staffing(name):
        return None

    taxonomies = result.get("taxonomies", [])
    taxonomy_desc = next((t.get("description", "") for t in taxonomies if t.get("primary")), "")
    taxonomy_code = next((t.get("code", "") for t in taxonomies if t.get("primary")), "")

    address = city = state = zip_code = phone = ""
    for addr in result.get("addresses", []):
        if addr.get("address_purpose") == "LOCATION":
            address = addr.get("address_1", "")
            city = addr.get("city", "").title()
            state = addr.get("state", "")
            zip_code = addr.get("postal_code", "")[:5]
            phone = addr.get("telephone_number", "")
            break

    return {
        "company_name": name.title(),
        "address": address.title(),
        "city": city,
        "state": state,
        "zip": zip_code,
        "phone": phone,
        "npi_number": result.get("number", ""),
        "taxonomy_code": taxonomy_code,
        "taxonomy_description": taxonomy_desc,
        "source": "nppes_npi",
        "date_scraped": datetime.now().strftime("%Y-%m-%d"),
    }


def run(config: dict, test: bool = False) -> list[dict]:
    queries = config.get("nppsQueries", DEFAULT_QUERIES)
    max_records = 200 if test else config.get("nppsMaxRecords", 5000)

    all_records: list[dict] = []
    seen_npis: set[str] = set()

    for query in queries:
        log.info(f"  NPPES: '{query}'")
        skip = 0

        while len(all_records) < max_records:
            try:
                # Search by organization_name — targets companies whose legal name
                # contains the term (e.g. "staffing", "locum"). This is far more
                # precise than taxonomy_description which returns all providers in a
                # care category (e.g. "Nursing Care" returns nursing homes).
                resp = requests.get(
                    NPPES_API,
                    params={"version": "2.1", "enumeration_type": "NPI-2",
                            "organization_name": query, "limit": PAGE_SIZE, "skip": skip},
                    headers=HEADERS, timeout=30,
                )
                resp.raise_for_status()
                data = resp.json()
            except Exception as e:
                log.warning(f"    NPPES error at skip={skip}: {e}")
                break

            results = data.get("results", [])
            if not results:
                break

            for result in results:
                npi = result.get("number", "")
                if npi in seen_npis:
                    continue
                seen_npis.add(npi)
                record = _extract(result)
                if record:
                    all_records.append(record)

            skip += PAGE_SIZE
            if skip >= data.get("result_count", 0):
                break
            time.sleep(DELAY)

    log.info(f"  NPPES: {len(all_records)} agencies")
    return all_records
