"""
ProductionHUB Directory Scraper (Apify Actor entry point).

Reads input, runs the scraper, and pushes one dataset record per unique
company profile. Records are pushed per finished (category × location)
target, so a partial run still yields data.
"""
from __future__ import annotations

import asyncio
import functools
import logging
import os

from apify import Actor

from .scraper import scrape, visit_profiles_only

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


async def main() -> None:
    async with Actor:
        inp = await Actor.get_input() or {}

        targets = inp.get("targets") or []
        profile_ids = [str(p) for p in (inp.get("profileIds") or [])]
        max_pages = int(inp.get("maxPagesPerList", 50))
        radius = int(inp.get("radius", 100))
        visit_profiles = bool(inp.get("visitProfiles", True))
        test_mode = bool(inp.get("testMode", False))

        if not targets and not profile_ids:
            raise ValueError("Provide 'targets' (listing crawl) or 'profileIds' (visit-only)")

        proxy_url = None
        proxy_input = inp.get("proxyConfiguration")
        if proxy_input and (proxy_input.get("useApifyProxy") or proxy_input.get("proxyUrls")):
            proxy_cfg = await Actor.create_proxy_configuration(actor_proxy_input=proxy_input)
            if proxy_cfg:
                # Sticky session — Cloudflare issues cf_clearance to ONE IP.
                # Without session pinning Apify residential rotates the exit
                # per request and the solved challenge never lands (verified:
                # "Verification successful. Waiting for … to respond" loop).
                run_id = os.environ.get("APIFY_ACTOR_RUN_ID", "local")
                proxy_url = await proxy_cfg.new_url(session_id=f"phub_{run_id[:12]}")

        log.info("=== ProductionHUB Directory Scraper ===")
        log.info(f"{len(targets)} targets, maxPagesPerList={max_pages}, "
                 f"radius={radius}, visitProfiles={visit_profiles}, test={test_mode}")
        await Actor.set_status_message(f"Scraping {len(targets)} directory targets…")

        loop = asyncio.get_event_loop()

        def push_batch(records: list[dict]) -> None:
            fut = asyncio.run_coroutine_threadsafe(Actor.push_data(records), loop)
            fut.result()

        if profile_ids:
            log.info(f"Visit-only mode: {len(profile_ids)} profiles")
            worker = functools.partial(
                visit_profiles_only,
                profile_ids=profile_ids,
                test=test_mode,
                proxy_url=proxy_url,
                on_batch=push_batch,
            )
        else:
            worker = functools.partial(
                scrape,
                targets=targets,
                max_pages=max_pages,
                radius=radius,
                visit_profiles=visit_profiles,
                test=test_mode,
                proxy_url=proxy_url,
                on_batch=push_batch,
            )
        records = await loop.run_in_executor(None, worker)

        with_site = sum(1 for r in records if r.get("website"))
        log.info(f"Done — {len(records)} profiles ({with_site} with website in description)")
        await Actor.set_status_message(
            f"Done — {len(records)} production company profiles "
            f"({with_site} with website)"
        )


asyncio.run(main())
