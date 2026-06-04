"""
Healthcare Recruitment Agency Finder — Apify Actor

Orchestrates 6 independent scrapers to find healthcare staffing agencies
that are NOT in standard B2B databases (Apollo, ZoomInfo, etc.).

Sources:
  A. LinkedIn Jobs Guest API    — companies actively posting healthcare jobs (last 7 days)
  B. NPPES NPI Registry (CMS)   — federal nursing care agency registry (~8K orgs)
  C. State Licensing Registries — NY/IN/TN/MD/MN/NJ government lists (boutique local firms)
  D. Niche Directories          — NATHO / Vivian Health / BluePipes / TravelNurseSource
  E. ASA Member Directory       — dues-paying American Staffing Association healthcare members
  F. FDD Franchisees            — Interim HealthCare franchise owner names from public FDD filings
"""

from __future__ import annotations

import asyncio
import functools
import logging

from apify import Actor

from .scrapers import asa_members, fdd_franchisees, linkedin_jobs, niche_directories, nppes_npi, sam_gov, state_registries
from .utils.merge import normalize_record

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

DEFAULT_SOURCES = ["state_registries", "nppes", "asa_members", "fdd_franchisees", "niche_directories", "linkedin_jobs", "sam_gov"]

SCRAPER_MAP = {
    "linkedin_jobs":    linkedin_jobs.run,
    "nppes":            nppes_npi.run,
    "state_registries": state_registries.run,
    "niche_directories":niche_directories.run,
    "asa_members":      asa_members.run,
    "fdd_franchisees":  fdd_franchisees.run,
    "sam_gov":          sam_gov.run,
}


async def main() -> None:
    async with Actor:
        inp = await Actor.get_input() or {}

        sources      = inp.get("sources", DEFAULT_SOURCES)
        test_mode    = inp.get("testMode", False)

        log.info("=== Healthcare Recruitment Agency Finder ===")
        log.info(f"Sources: {sources}")
        log.info(f"Test mode: {test_mode}")

        all_records: list[dict] = []
        seen_norm_names: set[str] = set()

        from .utils.merge import normalize_name

        for source in sources:
            fn = SCRAPER_MAP.get(source)
            if fn is None:
                log.warning(f"Unknown source '{source}' — skipping")
                continue

            await Actor.set_status_message(f"Scraping {source}…")
            log.info(f"--- Running: {source} ---")

            try:
                loop = asyncio.get_event_loop()
                partial = functools.partial(fn, config=inp, test=test_mode)
                records = await loop.run_in_executor(None, partial)
                log.info(f"  {source}: {len(records)} records")
            except Exception as exc:
                log.error(f"  {source} failed: {exc}", exc_info=True)
                await Actor.set_status_message(f"Warning: {source} failed — {exc}")
                continue

            # Normalize, deduplicate against already-pushed records, push immediately
            new_records = []
            for r in records:
                norm = normalize_record(r)
                key = normalize_name(norm["company_name"])
                if key and len(key) > 3 and key not in seen_norm_names:
                    seen_norm_names.add(key)
                    new_records.append(norm)
                    all_records.append(norm)

            if new_records:
                await Actor.push_data(new_records)
                log.info(f"  {source}: pushed {len(new_records)} new records ({len(all_records)} total)")
            await Actor.set_status_message(
                f"{source} done — {len(new_records)} new, {len(all_records)} total so far"
            )

        coverage = {
            "total":        len(all_records),
            "with_website": sum(1 for r in all_records if r.get("website")),
            "with_phone":   sum(1 for r in all_records if r.get("phone")),
            "with_founder": sum(1 for r in all_records if r.get("founder_name")),
        }
        log.info(f"Coverage: {coverage}")
        await Actor.set_status_message(
            f"Done — {len(all_records)} unique healthcare staffing agencies "
            f"({coverage['with_website']} with website, {coverage['with_founder']} with founder name)"
        )


asyncio.run(main())
