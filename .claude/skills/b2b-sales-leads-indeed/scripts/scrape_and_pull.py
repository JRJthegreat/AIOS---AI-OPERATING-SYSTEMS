"""
Phase 1: Orchestrate Apify Indeed scrapes → Google Sheet (B2B sales hiring).

Iterates keyword × location grid, calling the `valig/indeed-jobs-scraper` actor
once per combo. The keyword is the Indeed job-title search; the goal is to find
companies ACTIVELY HIRING B2B sales reps (a buying signal for demand-gen).

Filters at ingestion: drops postings with no company, duplicate Job_Ids, and
(optionally) postings older than --max_age_days (stale = role may be filled;
fresh = company just started hiring → calendar about to be empty). Agency
removal and company dedup happen downstream (classify_companies.py, then
dedupe_by_company.py).

Usage:
  python3 -W ignore scrape_and_pull.py --yes
  python3 -W ignore scrape_and_pull.py --sheet_url "URL" --keywords "Sales Development Representative" --cities "Remote" --limit 25 --yes

  --sheet_url "URL"      append to existing sheet (skips creation)
  --limit 1000           per-combo item cap (actor max is 1000; use 25 for a test)
  --cities "A;B;..."     semicolon-separated override (names contain commas)
  --keywords "A,B,..."   comma-separated override
  --max_age_days 45      drop postings older than N days (0 = keep all)
  --workers 8            concurrent Apify runs
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
)

ACTOR_ID = "valig~indeed-jobs-scraper"
SYNC_URL = f"https://api.apify.com/v2/acts/{ACTOR_ID}/run-sync-get-dataset-items"

# Indeed searches the job TITLE. SDR/BDR titles are inherently B2B, so they
# self-filter; "Outside Sales" / "B2B Sales" cover the field-sales angle.
DEFAULT_KEYWORDS = [
    "Outside Sales Representative",
    "B2B Sales Representative",
    "B2B Sales Development Representative",
    "Business Development Representative",
]

# US top-8 metros + Remote — 9 locations × 4 keywords = 36 actor runs.
# Concentrated company density for quality; scale this grid for round 2.
DEFAULT_CITIES = [
    "New York, NY",
    "Los Angeles, CA",
    "Chicago, IL",
    "Dallas, TX",
    "Atlanta, GA",
    "Boston, MA",
    "San Francisco, CA",
    "Austin, TX",
    "Remote",
]


def parse_iso_date(s):
    if not s:
        return None
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        return None


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
    """Dedup + recency filter. Returns (rows, stats_dict).
    Agency removal and company dedup are done downstream."""
    rows = []
    stats = {"total": len(items), "no_company": 0, "too_old": 0,
             "dupe_existing": 0, "kept": 0}

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

        if max_age_days and cutoff:
            pub = parse_iso_date(item.get("datePublished") or "")
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
    parser = argparse.ArgumentParser(description="Scrape Apify Indeed B2B-sales hiring (keyword × city grid) → Google Sheet")
    parser.add_argument("--sheet_url", default="", help="Existing sheet URL (omit to create new)")
    parser.add_argument("--limit", type=int, default=1000, help="Per-combo actor item cap (max 1000; use 25 for a test)")
    parser.add_argument("--cities", default="", help="Semicolon-separated city override e.g. 'Dallas, TX;Remote'")
    parser.add_argument("--keywords", default="", help="Comma-separated keyword override")
    parser.add_argument("--max_age_days", type=int, default=45, help="Drop postings older than N days (0 = keep all)")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--dry_run", action="store_true")
    parser.add_argument("--yes", action="store_true", help="Skip confirmation prompt")
    args = parser.parse_args()

    if not APIFY_API_TOKEN:
        print("ERROR: APIFY_API_TOKEN not set in .env")
        sys.exit(1)

    keywords = [k.strip() for k in args.keywords.split(",") if k.strip()] if args.keywords else DEFAULT_KEYWORDS
    cities = [c.strip() for c in args.cities.split(";") if c.strip()] if args.cities else DEFAULT_CITIES
    limit = max(1, min(args.limit, 1000))
    cutoff = (date.today() - timedelta(days=args.max_age_days)) if args.max_age_days else None

    combos = [(k, c) for k in keywords for c in cities]

    print("=== Apify Indeed B2B-Sales Hiring Scrape Orchestrator ===")
    print(f"Actor:      {ACTOR_ID}")
    print(f"Keywords:   {len(keywords)}  {keywords}")
    print(f"Locations:  {len(cities)}")
    for c in cities:
        print(f"            {c}")
    print(f"Combos:     {len(combos)}")
    print(f"Limit:      {limit} per combo  (max items = {len(combos) * limit:,})")
    print(f"Max age:    {args.max_age_days} days ({'cutoff ' + cutoff.isoformat() if cutoff else 'no recency filter'})")
    print(f"Workers:    {args.workers}")
    print(f"Filtering:  agency removal + dedup happen downstream")
    if args.sheet_url:
        print(f"Sheet:      {args.sheet_url}\n")
    else:
        print(f"Sheet:      [new sheet will be created]\n")

    if args.dry_run:
        print("[DRY RUN] No Apify calls made.")
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
        "runs_ok": 0, "runs_fail": 0, "raw": 0, "no_company": 0,
        "too_old": 0, "dupe_existing": 0, "dupe_session": 0, "written": 0,
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
            totals["too_old"] += stats["too_old"]
            totals["dupe_existing"] += stats["dupe_existing"]

            session_new = []
            for job_id, row in rows:
                if job_id and job_id in seen:
                    totals["dupe_session"] += 1
                    continue
                seen.add(job_id)
                session_new.append(row)

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
            print(f"  [{done_count}/{len(combos)}] {kw:32s} @ {city:18s}  "
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
    print(f"  Skipped too old:     {totals['too_old']:,}")
    print(f"  Skipped dupe exist:  {totals['dupe_existing']:,}")
    print(f"  Skipped dupe sess:   {totals['dupe_session']:,}")
    print(f"Rows written:          {totals['written']:,}")
    print(f"Elapsed:               {elapsed}s")
    print(f"Sheet: https://docs.google.com/spreadsheets/d/{sheet_id}/edit")


if __name__ == "__main__":
    main()
