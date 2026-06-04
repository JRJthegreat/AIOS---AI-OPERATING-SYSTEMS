"""
SAM.gov (System for Award Management) entity scraper.
Pulls healthcare staffing agencies registered as federal contractors.

NAICS 561320 = Temporary Help Services.
Free API key: register at https://sam.gov → Account Details → Public API Key.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime

import requests

log = logging.getLogger(__name__)

SAM_API = "https://api.sam.gov/entity-information/v3/entities"
PAGE_SIZE = 10  # SAM.gov public key max page size
DELAY = 1.0

NAICS_CODES = [
    "561320",  # Temporary Help Services
    "561110",  # Office Administrative Services (some staffing firms use this)
]

_HEALTHCARE_SIGNALS = {
    "health", "medical", "nurse", "nursing", "clinical", "staffing",
    "locum", "allied", "therapy", "travel", "physician", "dental",
    "rehab", "behavioral", "mental", "per diem", "registry", "supplemental",
    "care", "med", "rx", "surgical", "radiology", "respiratory",
}

_EXCLUDE_SIGNALS = {
    "hospital", "clinic", "center", "institute", "foundation",
    "school", "university", "college", "church",
}


def _is_healthcare_staffing(name: str) -> bool:
    n = name.lower()
    if any(ex in n for ex in _EXCLUDE_SIGNALS):
        return False
    return any(sig in n for sig in _HEALTHCARE_SIGNALS)


def _extract(entity: dict) -> dict | None:
    reg = entity.get("entityRegistration", {})
    name = reg.get("legalBusinessName", "").strip()
    if not name or not _is_healthcare_staffing(name):
        return None

    physical = (entity.get("coreData") or {}).get("physicalAddress") or {}
    address = physical.get("addressLine1", "")
    city = physical.get("city", "")
    state = physical.get("stateOrProvinceCode", "")
    zip_code = (physical.get("zipCode") or "")[:5]

    naics_list = ((entity.get("assertions") or {})
                  .get("goodsAndServices") or {}).get("naicsList") or []
    primary_naics = next(
        (n.get("naicsCode", "") for n in naics_list if n.get("isPrimary")), ""
    )

    def _title(s: str) -> str:
        return s.title() if s and s.isupper() else s

    return {
        "company_name": _title(name),
        "address": _title(address),
        "city": _title(city),
        "state": state,
        "zip": zip_code,
        "phone": "",
        "uei": reg.get("ueiSAM", ""),
        "cage_code": reg.get("cageCode", ""),
        "naics_code": primary_naics,
        "source": "sam_gov",
        "date_scraped": datetime.now().strftime("%Y-%m-%d"),
    }


def run(config: dict, test: bool = False) -> list[dict]:
    api_key = config.get("samGovApiKey", "")
    if not api_key:
        log.warning("  SAM.gov: no API key (samGovApiKey) — skipping this source")
        return []

    max_records = 200 if test else config.get("samGovMaxRecords", 3000)
    max_pages_per_naics = 5 if test else 9999
    all_records: list[dict] = []
    seen_ueis: set[str] = set()

    for naics in NAICS_CODES:
        log.info(f"  SAM.gov: NAICS {naics}")
        page = 0

        while len(all_records) < max_records and page < max_pages_per_naics:
            try:
                resp = requests.get(
                    SAM_API,
                    params={
                        "api_key": api_key,
                        "naicsCode": naics,
                        "size": PAGE_SIZE,
                        "page": page,
                    },
                    timeout=30,
                )
                if resp.status_code == 429:
                    log.warning("    SAM.gov rate limited — skipping NAICS")
                    break
                resp.raise_for_status()
                data = resp.json()
            except Exception as e:
                log.warning(f"    SAM.gov error at page={page}: {e}")
                break

            entities = data.get("entityData") or []
            if not entities:
                break

            for entity in entities:
                uei = (entity.get("entityRegistration") or {}).get("ueiSAM", "")
                if uei in seen_ueis:
                    continue
                seen_ueis.add(uei)
                record = _extract(entity)
                if record:
                    all_records.append(record)

            total = data.get("totalRecords", 0)
            page += 1
            if page * PAGE_SIZE >= total:
                break
            time.sleep(DELAY)

    log.info(f"  SAM.gov: {len(all_records)} healthcare staffing entities")
    return all_records
