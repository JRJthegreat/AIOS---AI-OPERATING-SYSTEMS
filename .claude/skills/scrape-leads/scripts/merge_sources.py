#!/usr/bin/env python3
from __future__ import annotations
"""
Merge and deduplicate lead records from all healthcare staffing sources.

Sources:
  source_a: Apify code_crafter/leads-finder (from scrape_apify_parallel.py)
  source_b: Google Maps gmaps-leads (exported from Google Sheet via read_sheet.py)
  source_c: LinkedIn Jobs Guest API (scrape_linkedin_jobs.py)
  source_d: NPPES NPI Registry (scrape_nppes_npi.py)
  source_e: State Licensing Registries (scrape_state_registries.py)
  source_f: Niche Directories (scrape_niche_directories.py)
  source_g: ASA Member Directory (scrape_asa_members.py)
  source_h: FDD Franchisees (scrape_fdd_franchisees.py)

Dedup priority:
  1. company_domain (exact match, strongest signal)
  2. normalized company name (lowercase + strip legal suffixes)

Output: unified JSON with normalized schema, ready for classify_leads_llm.py
"""

import json
import re
import argparse
import sys
from datetime import datetime
from urllib.parse import urlparse
from collections import Counter

# Legal suffix words to strip when normalizing company names for dedup
STRIP_SUFFIXES = re.compile(
    r"\b(inc|llc|ltd|corp|co|company|group|inc\.|llc\.|ltd\.|corporation|"
    r"staffing|recruitment|recruiting|agency|services|solutions|associates|"
    r"partners|international|national|healthcare|health care|medical|"
    r"nursing|nurses|nurse|clinical|allied|health|care|travel)\b",
    re.I,
)


def normalize_name(name: str) -> str:
    """Normalize company name for dedup comparison."""
    if not name:
        return ""
    n = name.lower().strip()
    n = re.sub(r"[^\w\s]", " ", n)  # remove punctuation
    n = STRIP_SUFFIXES.sub(" ", n)
    n = re.sub(r"\s+", " ", n).strip()
    return n


def extract_domain(website: str) -> str:
    """Extract bare domain from a website URL."""
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


def make_unified_record(raw: dict, source_name: str) -> dict:
    """Normalize a raw record from any source into the unified schema."""
    # company_name — try multiple field names
    name = (raw.get("company_name") or raw.get("business_name") or
            raw.get("name") or raw.get("organization") or "").strip()

    # website — multiple field names
    website = (raw.get("website") or raw.get("company_website") or
               raw.get("url") or "").strip()

    # domain
    domain = (raw.get("company_domain") or extract_domain(website) or
              raw.get("domain") or "").strip().lower().lstrip("www.")

    # LinkedIn URL
    linkedin_url = (raw.get("linkedin_url") or raw.get("company_linkedin") or
                    raw.get("linkedin") or "").strip()

    # founder/owner name — FDD source has it directly
    founder_name = (raw.get("owner_name") or raw.get("founder_name") or
                    raw.get("founder") or raw.get("contact_name") or "").strip()

    # Location
    address = (raw.get("address") or raw.get("company_address") or "").strip()
    city = (raw.get("city") or raw.get("company_city") or "").strip()
    state = (raw.get("state") or raw.get("company_state") or "").strip()
    zip_code = (raw.get("zip") or raw.get("zip_code") or raw.get("postal_code") or "").strip()
    phone = (raw.get("phone") or raw.get("company_phone") or "").strip()

    # Source-specific extra fields
    extra: dict = {}
    if "job_count" in raw:
        extra["hiring_signal"] = f"{raw['job_count']} active healthcare job postings"
    if "latest_job_title" in raw:
        extra["hiring_signal"] = (extra.get("hiring_signal", "") +
                                   f" — latest: {raw['latest_job_title']}").strip(" —")
    if "npi_number" in raw:
        extra["npi_number"] = raw["npi_number"]
    if "franchise" in raw:
        extra["franchise"] = raw["franchise"]
    if "taxonomy_description" in raw:
        extra["taxonomy"] = raw["taxonomy_description"]

    # Determine source tag
    source_tag = raw.get("source") or source_name

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
        "source": source_tag,
        **extra,
        "date_scraped": raw.get("date_scraped") or datetime.now().strftime("%Y-%m-%d"),
    }


def load_json(path: str, source_name: str) -> list[dict]:
    try:
        with open(path) as f:
            data = json.load(f)
        if not isinstance(data, list):
            print(f"  WARNING: {path} is not a JSON array, skipping", file=sys.stderr)
            return []
        records = [make_unified_record(r, source_name) for r in data]
        records = [r for r in records if r["company_name"]]
        print(f"  Loaded {len(records)} records from {path}")
        return records
    except FileNotFoundError:
        print(f"  Skipping {path} (not found)")
        return []
    except json.JSONDecodeError as e:
        print(f"  ERROR: Could not parse {path}: {e}", file=sys.stderr)
        return []


def deduplicate(records: list[dict]) -> tuple[list[dict], int]:
    """
    Deduplicate records.
    Priority: exact domain match → normalized name match.
    Merges non-empty fields when duplicates are found.
    """
    seen_domains: dict[str, int] = {}   # domain → index in result
    seen_names: dict[str, int] = {}     # normalized name → index in result
    result: list[dict] = []
    dup_count = 0

    for record in records:
        domain = record.get("company_domain", "").strip().lower()
        norm_name = normalize_name(record.get("company_name", ""))

        existing_idx = None

        # Check domain match first (strongest signal)
        if domain and len(domain) > 4:
            if domain in seen_domains:
                existing_idx = seen_domains[domain]

        # Then check normalized name match
        if existing_idx is None and norm_name and len(norm_name) > 3:
            if norm_name in seen_names:
                existing_idx = seen_names[norm_name]

        if existing_idx is not None:
            # Merge: fill in any empty fields from this duplicate
            existing = result[existing_idx]
            for field, value in record.items():
                if value and not existing.get(field):
                    existing[field] = value
            # Append source tag so we know it came from multiple sources
            if record["source"] not in existing["source"]:
                existing["source"] = existing["source"] + "," + record["source"]
            dup_count += 1
        else:
            idx = len(result)
            result.append(record)
            if domain and len(domain) > 4:
                seen_domains[domain] = idx
            if norm_name and len(norm_name) > 3:
                seen_names[norm_name] = idx

    return result, dup_count


def main():
    parser = argparse.ArgumentParser(description="Merge and deduplicate leads from all healthcare sources")
    parser.add_argument("--sources", nargs="+", help="JSON files to merge (auto-detects from .tmp/ if not specified)")
    parser.add_argument("--output", default=".tmp/healthcare_merged.json", help="Output JSON file")
    parser.add_argument("--stats", action="store_true", help="Print per-source stats")
    args = parser.parse_args()

    import os
    os.makedirs(".tmp", exist_ok=True)

    # Default source file paths (auto-detect)
    default_sources = [
        (".tmp/source_a_raw.json", "apify"),
        (".tmp/source_a_raw_b.json", "apify"),
        (".tmp/source_b_gmaps.json", "gmaps"),
        (".tmp/source_c_linkedin_jobs.json", "linkedin_jobs"),
        (".tmp/source_d_nppes_npi.json", "nppes"),
        (".tmp/source_e_state_registries.json", "state_registry"),
        (".tmp/source_f_niche_directories.json", "niche_directory"),
        (".tmp/source_g_asa_members.json", "asa_members"),
        (".tmp/source_h_fdd_franchisees.json", "fdd_franchisee"),
    ]

    if args.sources:
        sources_to_load = [(path, "custom") for path in args.sources]
    else:
        sources_to_load = default_sources

    print("Loading sources...")
    all_records: list[dict] = []
    for path, source_name in sources_to_load:
        records = load_json(path, source_name)
        all_records.extend(records)

    print(f"\nTotal before dedup: {len(all_records)}")

    if not all_records:
        print("ERROR: No records loaded. Run the individual scrapers first.", file=sys.stderr)
        sys.exit(1)

    # Per-source stats before dedup
    if args.stats:
        source_counts = Counter(r["source"].split(",")[0] for r in all_records)
        print("\nPer-source counts (pre-dedup):")
        for src, count in sorted(source_counts.items()):
            print(f"  {src}: {count}")

    print("\nDeduplicating...")
    deduped, dup_count = deduplicate(all_records)
    print(f"  Removed {dup_count} duplicates")
    print(f"  Unique records: {len(deduped)}")

    # Stats
    has_website = sum(1 for r in deduped if r.get("website"))
    has_linkedin = sum(1 for r in deduped if r.get("linkedin_url"))
    has_founder = sum(1 for r in deduped if r.get("founder_name"))
    has_phone = sum(1 for r in deduped if r.get("phone"))

    print(f"\nData completeness:")
    print(f"  Website:      {has_website}/{len(deduped)} ({has_website*100//len(deduped)}%)")
    print(f"  LinkedIn URL: {has_linkedin}/{len(deduped)} ({has_linkedin*100//len(deduped)}%)")
    print(f"  Founder name: {has_founder}/{len(deduped)} ({has_founder*100//len(deduped)}%)")
    print(f"  Phone:        {has_phone}/{len(deduped)} ({has_phone*100//len(deduped)}%)")

    # Source breakdown
    source_counts = Counter(r["source"].split(",")[0] for r in deduped)
    print(f"\nPer-source (post-dedup):")
    for src, count in sorted(source_counts.items()):
        print(f"  {src}: {count}")

    with open(args.output, "w") as f:
        json.dump(deduped, f, indent=2)

    print(f"\nDone. {len(deduped)} unique records → {args.output}")
    print("\nNext step: run classify_leads_llm.py to filter healthcare-specialist firms only")
    print(f"  python3 .claude/skills/scrape-leads/scripts/classify_leads_llm.py {args.output} --custom-prompt ...")


if __name__ == "__main__":
    main()
