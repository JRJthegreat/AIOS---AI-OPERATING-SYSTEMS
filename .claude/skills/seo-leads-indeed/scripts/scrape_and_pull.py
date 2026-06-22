"""
Phase 1: Orchestrate Apify Indeed scrapes → Google Sheet (SEO/AEO hiring).

Iterates keyword × location grid, calling the `valig/indeed-jobs-scraper` actor
once per combo. The keyword is the Indeed job-title search; the goal is to find
US companies ACTIVELY HIRING an in-house SEO / organic / AEO role — the
high-intent signal for PN Digital's displacement outbound.

Filters at ingestion:
  - drop postings with no company name
  - drop postings whose TITLE isn't SEO/organic/AEO-relevant (title-strict gate;
    Indeed's title search broad-matches the whole posting, so this removes the
    bulk of the noise — Customer Success, Account Exec, Copywriter, etc.)
  - drop duplicate Job_Ids
  - drop postings older than --max_age_days (stale = role may be filled; fresh =
    live req → live intent). Default 30.
Each kept row is tagged Tier A (AI-search/AEO-aware) or B (traditional SEO) from
its title+description. Agency removal + ICP tagging and company dedup happen
downstream (classify_companies.py, then dedupe_by_company.py).

Usage:
  # Validation run (small): a few keywords × 1-2 metros, low limit
  python3 -W ignore scrape_and_pull.py --keywords "SEO Manager,Head of SEO,AEO Specialist" \
      --cities "San Francisco, CA;Remote" --limit 25 --yes

  # Default cost-shaped full run (Tier-B × full grid; Tier-A × hubs only)
  python3 -W ignore scrape_and_pull.py --yes

  --sheet_url "URL"      append to existing sheet (skips creation)
  --limit 1000           per-combo item cap (actor max is 1000; use 25 for a test)
  --cities "A;B;..."     semicolon-separated override (names contain commas)
  --keywords "A,B,..."   comma-separated override (else default tiered set)
  --max_age_days 30      drop postings older than N days (0 = keep all)
  --workers 6            concurrent Apify runs
  --dry_run              print plan only, no Apify calls
  --yes                  skip confirmation prompt

Resume safety: existing Job_Ids in the sheet are loaded first; matching items
returned by the actor are skipped (no duplicate rows).
"""

import sys
import time
import argparse
import requests
from datetime import date, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from googleapiclient.errors import HttpError

from pull_dataset import (
    HEADERS, TAB_NAME, BATCH_SIZE, SHEET_TITLE,
    APIFY_API_TOKEN,
    get_sheet_id_from_url, get_google_service,
    map_to_row, create_sheet, setup_tab,
    title_is_relevant, parse_iso_date_safe,
)

ACTOR_ID = "valig~indeed-jobs-scraper"
SYNC_URL = f"https://api.apify.com/v2/acts/{ACTOR_ID}/run-sync-get-dataset-items"

# BROAD anchor terms, chosen by an empirical yield probe (one Apify call per
# candidate, measuring count + title relevance). Key finding: narrow titles
# (e.g. "SEO Specialist" = 126 results) starve the funnel vs the broad anchor
# ("SEO" = 580, 4.6x). Precision is enforced downstream by the title gate
# (title must contain seo/organic/aeo/geo) + the LLM (drops managers/agencies/
# off-target) — so the keyword's job is purely to MAXIMIZE the raw pool.
#
# Dropped as proven noise/redundant by the probe: "AI search" (937 results, 0%
# relevant — ML engineers), "link building" (4%), "organic growth" (4%),
# "AI SEO" (16%), "technical SEO"/"SEO content" (subsets of "SEO").
KEYWORDS_TIER_B = [
    "SEO",                          # 580 — broad anchor; supersets narrow SEO variants
    "organic search",              # 184 — distinct organic-intent postings
    "search engine optimization",  # 144 — spelled-out form some postings only use
]
KEYWORDS_TIER_A = [
    "AEO",                            # 14 but 36% relevant — AEO/GEO-native titles nothing else surfaces
    "answer engine optimization",    # 59 — distinct in-body AEO matches
    "generative engine optimization",# 62 — GEO/generative postings; thin AEO pool, take all
]

# Broad US metro grid (+ Remote captures remote-only SaaS roles). Freshness is
# kept tight (--max_age_days 30) — volume comes from breadth of locations, not
# from stale postings.
CITY_GRID = [
    # Tier-1 tech/SaaS hubs
    "San Francisco, CA", "New York City, NY", "Austin, TX", "Seattle, WA",
    "Boston, MA", "Los Angeles, CA", "Chicago, IL", "Denver, CO",
    "Atlanta, GA", "Miami, FL",
    # Major business metros
    "Dallas, TX", "Houston, TX", "Washington, DC", "Philadelphia, PA",
    "Phoenix, AZ", "San Diego, CA", "San Jose, CA", "Minneapolis, MN",
    "Tampa, FL", "Charlotte, NC", "Nashville, TN", "Portland, OR",
    "Orlando, FL", "Raleigh, NC", "Las Vegas, NV", "Salt Lake City, UT",
    "San Antonio, TX", "Columbus, OH", "Pittsburgh, PA", "Indianapolis, IN",
    "Detroit, MI", "Baltimore, MD",
    # Second-tier metros (geographically distributed for multi-location leads)
    "Kansas City, MO", "St. Louis, MO", "Cincinnati, OH", "Cleveland, OH",
    "Milwaukee, WI", "Sacramento, CA", "Jacksonville, FL", "Fort Worth, TX",
    "Oklahoma City, OK", "Louisville, KY", "Memphis, TN", "Richmond, VA",
    "Hartford, CT", "Buffalo, NY", "Albuquerque, NM", "Boise, ID",
    "Madison, WI", "Omaha, NE", "New Orleans, LA", "Providence, RI",
]
REMOTE = "Remote"
# Tier-A (AEO/AI-search) titles are rarer; run across Remote + the top hubs.
TIER_A_LOCATIONS = [
    REMOTE, "San Francisco, CA", "New York City, NY", "Austin, TX",
    "Seattle, WA", "Boston, MA", "Los Angeles, CA", "Chicago, IL",
    "Denver, CO", "Atlanta, GA", "Miami, FL", "Washington, DC",
    "Dallas, TX", "San Diego, CA",
]


def build_combos(keywords_override, cities_override):
    """Return list of (keyword, location). Override => full cross product.
    Default => cost-shaped: Tier-B × (grid + Remote); Tier-A × hubs only."""
    if keywords_override or cities_override:
        keywords = keywords_override or (KEYWORDS_TIER_B + KEYWORDS_TIER_A)
        cities = cities_override or (CITY_GRID + [REMOTE])
        return [(k, c) for k in keywords for c in cities]

    combos = []
    grid = CITY_GRID + [REMOTE]
    for k in KEYWORDS_TIER_B:
        for c in grid:
            combos.append((k, c))
    for k in KEYWORDS_TIER_A:
        for c in TIER_A_LOCATIONS:
            combos.append((k, c))
    return combos


def run_actor(keyword, location, limit, timeout=180):
    """Fire one actor run (sync). Returns list of items or []. No retry."""
    try:
        resp = requests.post(
            SYNC_URL,
            params={"token": APIFY_API_TOKEN},
            json={
                "title": keyword,
                "location": location,
                "country": "us",
                "limit": limit,
            },
            timeout=timeout,
        )
    except requests.RequestException as e:
        print(f"  [!] {keyword} @ {location}: {type(e).__name__}: {e}")
        return []

    if resp.status_code not in (200, 201):
        print(f"  [!] {keyword} @ {location}: HTTP {resp.status_code} — {resp.text[:120]}")
        return []

    try:
        return resp.json() or []
    except ValueError:
        print(f"  [!] {keyword} @ {location}: invalid JSON response")
        return []


def filter_items(items, existing_job_ids, max_age_days=0, cutoff=None):
    """Dedup + title-relevance + recency filter. Returns (rows, stats_dict).
    Agency removal, ICP tagging, and company dedup are done downstream."""
    rows = []
    stats = {"total": len(items), "no_company": 0, "off_title": 0,
             "too_old": 0, "dupe_existing": 0, "kept": 0}

    for item in items:
        job_id = item.get("key") or ""
        if job_id and job_id in existing_job_ids:
            stats["dupe_existing"] += 1
            continue

        emp = item.get("employer") or {}
        company_name = (emp.get("name") or "").strip()
        if not company_name:
            stats["no_company"] += 1
            continue

        if not title_is_relevant(item.get("title", "")):
            stats["off_title"] += 1
            continue

        if max_age_days and cutoff:
            pub = parse_iso_date_safe(item.get("datePublished") or "")
            if pub is not None and pub < cutoff:
                stats["too_old"] += 1
                continue

        rows.append((job_id, map_to_row(item)))
        stats["kept"] += 1

    return rows, stats


def load_existing_job_ids(service, sheet_id):
    """Read column A (Job_Id) to build a skip-set for resume safety."""
    try:
        resp = service.spreadsheets().values().get(
            spreadsheetId=sheet_id, range=f"'{TAB_NAME}'!A2:A50000"
        ).execute()
    except Exception as e:
        print(f"  [!] Could not read existing Job_Ids: {e}")
        return set()
    return {r[0] for r in resp.get("values", []) if r and r[0]}


def append_batch(service, sheet_id, batch, max_retries=6):
    """Append with exponential backoff on HTTP 429/503 (Sheets write-quota)."""
    delay = 4
    for attempt in range(max_retries):
        try:
            service.spreadsheets().values().append(
                spreadsheetId=sheet_id,
                range=f"'{TAB_NAME}'!A1",
                valueInputOption="RAW",
                insertDataOption="INSERT_ROWS",
                body={"values": batch},
            ).execute()
            return
        except HttpError as e:
            status = getattr(e.resp, "status", None)
            if status in (429, 503) and attempt < max_retries - 1:
                print(f"  [!] Sheets {status} — backing off {delay}s (attempt {attempt + 1}/{max_retries})")
                time.sleep(delay)
                delay = min(delay * 2, 64)
                continue
            raise


def ensure_headers(service, sheet_id):
    """If A1 is empty, write the header row."""
    resp = service.spreadsheets().values().get(
        spreadsheetId=sheet_id, range=f"'{TAB_NAME}'!A1:A1"
    ).execute()
    vals = resp.get("values", [])
    if not vals or not vals[0]:
        service.spreadsheets().values().update(
            spreadsheetId=sheet_id,
            range=f"'{TAB_NAME}'!A1",
            valueInputOption="RAW",
            body={"values": [HEADERS]},
        ).execute()
        print("  Wrote header row.")


def main():
    parser = argparse.ArgumentParser(description="Scrape Apify Indeed SEO/AEO hiring (keyword × city grid) → Google Sheet")
    parser.add_argument("--sheet_url", default="", help="Existing sheet URL (omit to create new)")
    parser.add_argument("--limit", type=int, default=1000, help="Per-combo actor item cap (max 1000; use 25 for a test)")
    parser.add_argument("--cities", default="", help="Semicolon-separated city override e.g. 'Austin, TX;Remote'")
    parser.add_argument("--keywords", default="", help="Comma-separated keyword override")
    parser.add_argument("--max_age_days", type=int, default=30, help="Drop postings older than N days (0 = keep all)")
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--dry_run", action="store_true")
    parser.add_argument("--yes", action="store_true", help="Skip confirmation prompt")
    args = parser.parse_args()

    if not APIFY_API_TOKEN:
        print("ERROR: APIFY_API_TOKEN not set in .env")
        sys.exit(1)

    kw_override = [k.strip() for k in args.keywords.split(",") if k.strip()] if args.keywords else None
    city_override = [c.strip() for c in args.cities.split(";") if c.strip()] if args.cities else None
    limit = max(1, min(args.limit, 1000))
    cutoff = (date.today() - timedelta(days=args.max_age_days)) if args.max_age_days else None
    combos = build_combos(kw_override, city_override)

    print("=== Apify Indeed SEO/AEO-Hiring Scrape Orchestrator ===")
    print(f"Actor:      {ACTOR_ID}")
    print(f"Combos:     {len(combos)}  (keyword × location)")
    print(f"Limit:      {limit} per combo  (max items = {len(combos) * limit:,})")
    print(f"Max age:    {args.max_age_days} days ({'cutoff ' + cutoff.isoformat() if cutoff else 'no recency filter'})")
    print(f"Workers:    {args.workers}")
    print(f"Filtering:  title-strict gate at ingest; agency removal + ICP tag + dedup downstream")
    if args.sheet_url:
        print(f"Sheet:      {args.sheet_url}\n")
    else:
        print(f"Sheet:      [new sheet will be created]\n")

    if args.dry_run:
        for k, c in combos:
            print(f"  {k:32s} @ {c}")
        print(f"\n[DRY RUN] {len(combos)} actor runs would fire. No Apify calls made.")
        return

    if not args.yes:
        reply = input(f"Fire {len(combos)} actor runs? [y/N] ").strip().lower()
        if reply not in ("y", "yes"):
            print("Aborted.")
            return

    service = get_google_service()

    if args.sheet_url:
        sheet_id = get_sheet_id_from_url(args.sheet_url)
        ensure_headers(service, sheet_id)
    else:
        print("Creating new Google Sheet...")
        sheet_id = create_sheet(service, SHEET_TITLE)
        setup_tab(service, sheet_id)
        print(f"Sheet URL: https://docs.google.com/spreadsheets/d/{sheet_id}/edit\n")

    print("Loading existing Job_Ids...")
    existing_job_ids = load_existing_job_ids(service, sheet_id)
    print(f"  {len(existing_job_ids):,} already in sheet.\n")

    seen = set(existing_job_ids)
    pending_batch = []
    totals = {
        "runs_ok": 0, "runs_fail": 0, "raw": 0, "no_company": 0, "off_title": 0,
        "too_old": 0, "dupe_existing": 0, "dupe_session": 0, "written": 0, "tier_a": 0,
    }
    t0 = time.time()

    def work(kw, city):
        items = run_actor(kw, city, limit)
        rows, stats = filter_items(items, existing_job_ids, args.max_age_days, cutoff)
        return kw, city, items, rows, stats

    print(f"Launching {len(combos)} runs with {args.workers} workers...\n")

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(work, kw, city): (kw, city) for kw, city in combos}
        done_count = 0
        for fut in as_completed(futures):
            done_count += 1
            kw, city = futures[fut]
            try:
                kw_r, city_r, items, rows, stats = fut.result()
            except Exception as e:
                print(f"  [{done_count}/{len(combos)}] {kw} @ {city}: EXC {e}")
                totals["runs_fail"] += 1
                continue

            if not items and stats["total"] == 0:
                totals["runs_fail"] += 1
            else:
                totals["runs_ok"] += 1

            totals["raw"] += stats["total"]
            totals["no_company"] += stats["no_company"]
            totals["off_title"] += stats["off_title"]
            totals["too_old"] += stats["too_old"]
            totals["dupe_existing"] += stats["dupe_existing"]

            session_new = []
            for job_id, row in rows:
                if job_id and job_id in seen:
                    totals["dupe_session"] += 1
                    continue
                seen.add(job_id)
                session_new.append(row)
                if row[29] == "A":  # AD: Tier
                    totals["tier_a"] += 1

            pending_batch.extend(session_new)

            while len(pending_batch) >= BATCH_SIZE:
                chunk = pending_batch[:BATCH_SIZE]
                pending_batch = pending_batch[BATCH_SIZE:]
                try:
                    append_batch(service, sheet_id, chunk)
                    totals["written"] += len(chunk)
                except Exception as e:
                    print(f"  [!] Sheet write failed: {e}. Re-queueing {len(chunk)} rows.")
                    pending_batch = chunk + pending_batch
                    time.sleep(3)
                    break
                time.sleep(1.2)

            elapsed = int(time.time() - t0)
            print(f"  [{done_count}/{len(combos)}] {kw:30s} @ {city:18s}  "
                  f"raw={stats['total']:3d}  new={len(session_new):3d}  "
                  f"written={totals['written']:5d}  ({elapsed}s)")

    while pending_batch:
        chunk = pending_batch[:BATCH_SIZE]
        pending_batch = pending_batch[BATCH_SIZE:]
        append_batch(service, sheet_id, chunk)
        totals["written"] += len(chunk)
        time.sleep(1.2)

    elapsed = int(time.time() - t0)
    print("\n=== Summary ===")
    print(f"Runs ok / fail:        {totals['runs_ok']} / {totals['runs_fail']}")
    print(f"Raw items:             {totals['raw']:,}")
    print(f"  Skipped no company:  {totals['no_company']:,}")
    print(f"  Skipped off-title:   {totals['off_title']:,}")
    print(f"  Skipped too old:     {totals['too_old']:,}")
    print(f"  Skipped dupe exist:  {totals['dupe_existing']:,}")
    print(f"  Skipped dupe sess:   {totals['dupe_session']:,}")
    print(f"Rows written:          {totals['written']:,}")
    print(f"  Tier A (AI-aware):   {totals['tier_a']:,}")
    print(f"  Tier B (trad SEO):   {totals['written'] - totals['tier_a']:,}")
    print(f"Elapsed:               {elapsed}s")
    print(f"Sheet: https://docs.google.com/spreadsheets/d/{sheet_id}/edit")
    print("\nNext: classify_companies.py (drop agencies + ICP tag) → dedupe_by_company.py")


if __name__ == "__main__":
    main()
