"""
NCHCR Job Board — Healthcare Recruiter Finder (Apify Actor entry point).

Reads input, runs the scraper, and pushes one dataset record per unique
recruitment firm.
"""
from __future__ import annotations

import asyncio
import functools
import logging

from apify import Actor

from .scraper import scrape

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


async def main() -> None:
    async with Actor:
        inp = await Actor.get_input() or {}

        job_type    = inp.get("jobType", "Both")
        rpp         = int(inp.get("resultsPerPage", 500))
        max_pages   = int(inp.get("maxListPages", 30))
        max_firms   = int(inp.get("maxFirms", 0))
        test_mode   = bool(inp.get("testMode", False))

        log.info("=== NCHCR Job Board Scraper ===")
        log.info(f"jobType={job_type} resultsPerPage={rpp} "
                 f"maxListPages={max_pages} maxFirms={max_firms} test={test_mode}")
        await Actor.set_status_message("Scraping NCHCR job board…")

        # Playwright sync API must run off the event loop thread
        loop = asyncio.get_event_loop()
        worker = functools.partial(
            scrape,
            job_type=job_type,
            results_per_page=rpp,
            max_list_pages=max_pages,
            max_firms=max_firms,
            test=test_mode,
        )
        records = await loop.run_in_executor(None, worker)

        if records:
            await Actor.push_data(records)

        with_web = sum(1 for r in records if r.get("website"))
        with_email = sum(1 for r in records if r.get("recruiter_email"))
        log.info(f"Done — {len(records)} firms "
                 f"({with_email} with email, {with_web} with website)")
        await Actor.set_status_message(
            f"Done — {len(records)} recruitment firms "
            f"({with_email} with email, {with_web} with website)"
        )


asyncio.run(main())
