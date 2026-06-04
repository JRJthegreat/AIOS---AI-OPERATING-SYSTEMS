"""
Normalize and deduplicate records from all sources into a unified schema.

Dedup priority:
  1. company_domain (exact match)
  2. normalized company name (lowercase + strip legal/industry suffixes)

When duplicates are found, non-empty fields are merged (first record wins for conflicts).
"""
from __future__ import annotations

import re
from datetime import datetime
from urllib.parse import urlparse

_STRIP_SUFFIXES = re.compile(
    r"\b(inc|llc|ltd|corp|co|company|group|corporation|"
    r"staffing|recruitment|recruiting|agency|services|solutions|associates|"
    r"partners|international|national|healthcare|health care|medical|"
    r"nursing|nurses|nurse|clinical|allied|health|care|travel)\b",
    re.I,
)


def normalize_name(name: str) -> str:
    if not name:
        return ""
    n = name.lower().strip()
    n = re.sub(r"[^\w\s]", " ", n)
    n = _STRIP_SUFFIXES.sub(" ", n)
    n = re.sub(r"\s+", " ", n).strip()
    return n


def _extract_domain(website: str) -> str:
    if not website:
        return ""
    url = website.strip()
    if not url.startswith("http"):
        url = f"https://{url}"
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lstrip("www.").lower()
        return domain if "." in domain else ""
    except Exception:
        return ""


def normalize_record(raw: dict) -> dict:
    name = (raw.get("company_name") or raw.get("business_name") or
            raw.get("name") or raw.get("organization") or "").strip()

    website = (raw.get("website") or raw.get("company_website") or raw.get("url") or "").strip()

    domain = (raw.get("company_domain") or _extract_domain(website) or
              raw.get("domain") or "").strip().lower().lstrip("www.")

    linkedin_url = (raw.get("linkedin_url") or raw.get("company_linkedin") or
                    raw.get("linkedin") or "").strip()

    founder_name = (raw.get("owner_name") or raw.get("founder_name") or
                    raw.get("founder") or raw.get("contact_name") or "").strip()

    address = (raw.get("address") or raw.get("company_address") or "").strip()
    city = (raw.get("city") or raw.get("company_city") or "").strip()
    state = (raw.get("state") or raw.get("company_state") or "").strip()
    zip_code = (raw.get("zip") or raw.get("zip_code") or raw.get("postal_code") or "").strip()
    phone = (raw.get("phone") or raw.get("company_phone") or "").strip()

    extra: dict = {}
    if "job_count" in raw:
        extra["hiring_signal"] = f"{raw['job_count']} active healthcare job postings"
    if "latest_job_title" in raw:
        extra["hiring_signal"] = (extra.get("hiring_signal", "") +
                                   f" — latest: {raw['latest_job_title']}").lstrip(" —")
    if "npi_number" in raw:
        extra["npi_number"] = raw["npi_number"]
    if "franchise" in raw:
        extra["franchise"] = raw["franchise"]
    if "taxonomy_description" in raw:
        extra["taxonomy"] = raw["taxonomy_description"]
    if "uei" in raw:
        extra["uei"] = raw["uei"]
    if "cage_code" in raw:
        extra["cage_code"] = raw["cage_code"]
    if "found_in" in raw:
        extra["found_in"] = raw["found_in"]

    return {
        "company_name": name,
        "website": website,
        "company_domain": domain,
        "linkedin_url": linkedin_url,
        "founder_name": founder_name,
        "address": address,
        "city": city,
        "state": state,
        "zip": zip_code,
        "phone": phone,
        "source": raw.get("source", ""),
        **extra,
        "date_scraped": raw.get("date_scraped") or datetime.now().strftime("%Y-%m-%d"),
    }


def deduplicate(records: list[dict]) -> list[dict]:
    seen_domains: dict[str, int] = {}
    seen_names: dict[str, int] = {}
    result: list[dict] = []

    for record in records:
        domain = record.get("company_domain", "").strip().lower()
        norm_name = normalize_name(record.get("company_name", ""))

        existing_idx = None

        if domain and len(domain) > 4:
            existing_idx = seen_domains.get(domain)

        if existing_idx is None and norm_name and len(norm_name) > 3:
            existing_idx = seen_names.get(norm_name)

        if existing_idx is not None:
            existing = result[existing_idx]
            for field, value in record.items():
                if value and not existing.get(field):
                    existing[field] = value
            if record["source"] and record["source"] not in existing["source"]:
                existing["source"] = existing["source"] + "," + record["source"]
        else:
            idx = len(result)
            result.append(record)
            if domain and len(domain) > 4:
                seen_domains[domain] = idx
            if norm_name and len(norm_name) > 3:
                seen_names[norm_name] = idx

    return result
