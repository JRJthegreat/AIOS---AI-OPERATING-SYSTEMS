#!/usr/bin/env python3
"""
Scrape LinkedIn posts by keyword and date range → extract unique authors → JSON file.

Single keyword:
  python3 scrape_linkedin_posts.py \
    --keyword "SIA Healthcare Staffing Summit" \
    --date-from 2025-11-01 --date-to 2025-12-15 \
    --max-posts 200 --output .tmp/sia_post_authors.json

Multiple keywords (each with its own date window), merging an existing file:
  python3 scrape_linkedin_posts.py \
    --keywords-file .tmp/sia_keywords.json --max-posts 1000 \
    --merge .tmp/sia_post_authors.json --output .tmp/list_a_raw.json

  keywords-file is a JSON array: [{"keyword": "...", "date_from": "YYYY-MM-DD", "date_to": "YYYY-MM-DD"}, ...]
"""

import os
import sys
import json
import argparse
import hashlib
from datetime import datetime
from dotenv import load_dotenv
from apify_client import ApifyClient

load_dotenv()

DEFAULT_ACTOR = "harvestapi/linkedin-post-search"


def parse_post_date(date_str):
    if not date_str:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d", "%B %d, %Y"):
        try:
            return datetime.strptime(str(date_str), fmt).date()
        except ValueError:
            continue
    return None


def extract_author(item):
    author = item.get("author") or {}

    full = (author.get("name") or "").strip()
    name_parts = full.split(" ", 1)
    first = name_parts[0] if name_parts else ""
    last = name_parts[1] if len(name_parts) > 1 else ""

    # Build clean profile URL from publicIdentifier (strips miniProfileUrn query param)
    slug = (author.get("publicIdentifier") or "").strip()
    if slug:
        author_url = f"https://www.linkedin.com/in/{slug}"
    else:
        raw_url = (author.get("linkedinUrl") or "").strip()
        author_url = raw_url.split("?")[0].rstrip("/") if raw_url else ""

    title = (author.get("info") or "").strip()

    content = (item.get("content") or "").strip()
    snippet = content[:200] if content else ""

    post_url = (item.get("linkedinUrl") or item.get("shareLinkedinUrl") or "").strip()

    # Date is nested: postedAt.date (ISO string)
    posted_at = item.get("postedAt") or {}
    raw_date = posted_at.get("date") or posted_at.get("timestamp") or ""

    return {
        "full_name": full,
        "first_name": first,
        "last_name": last,
        "job_title": title,
        "company_name": "",
        "linkedin_url": author_url,
        "post_snippet": snippet,
        "post_url": post_url,
        "post_date": str(raw_date),
    }


def author_hash(author):
    key = (author.get("linkedin_url") or author.get("full_name") or "").lower().strip()
    return hashlib.md5(key.encode()).hexdigest()


def scrape_posts(keyword, actor_id, max_posts):
    api_token = os.getenv("APIFY_API_TOKEN")
    if not api_token:
        print("Error: APIFY_API_TOKEN not set", file=sys.stderr)
        sys.exit(1)

    client = ApifyClient(api_token)

    run_input = {
        "searchQueries": [keyword],
        "maxPosts": max_posts,
    }

    print(f"Actor: {actor_id}")
    print(f"Keyword: '{keyword}' | Max posts: {max_posts}")
    run = client.actor(actor_id).call(run_input=run_input)
    if not run:
        print("Actor run failed.", file=sys.stderr)
        sys.exit(1)

    items = list(client.dataset(run["defaultDatasetId"]).iterate_items())
    print(f"Fetched {len(items)} raw posts")
    return items


def process_keyword(keyword, date_from_str, date_to_str, actor_id, max_posts, seen):
    """Scrape one keyword, filter by date, add new unique authors into `seen` (dict by hash)."""
    date_from = datetime.strptime(date_from_str, "%Y-%m-%d").date() if date_from_str else None
    date_to = datetime.strptime(date_to_str, "%Y-%m-%d").date() if date_to_str else None

    items = scrape_posts(keyword, actor_id, max_posts)

    added = 0
    skipped_date = 0
    skipped_no_author = 0

    for item in items:
        author = extract_author(item)

        posted_at = item.get("postedAt") or {}
        raw_date = posted_at.get("date") or str(posted_at.get("timestamp", ""))
        post_date = parse_post_date(raw_date)

        if post_date:
            if date_from and post_date < date_from:
                skipped_date += 1
                continue
            if date_to and post_date > date_to:
                skipped_date += 1
                continue

        if not author["linkedin_url"] and not author["full_name"]:
            skipped_no_author += 1
            continue

        author["source_keyword"] = keyword
        h = author_hash(author)
        if h not in seen:
            seen[h] = author
            added += 1

    print(f"  Skipped (outside date range): {skipped_date} | (no author): {skipped_no_author} | NEW unique: {added}")
    return added


def main():
    parser = argparse.ArgumentParser(description="Scrape LinkedIn posts and extract unique authors")
    parser.add_argument("--keyword", help="Single search keyword")
    parser.add_argument("--keywords-file", help="JSON array of {keyword, date_from, date_to}")
    parser.add_argument("--date-from", help="Keep posts on/after YYYY-MM-DD (single-keyword mode)")
    parser.add_argument("--date-to", help="Keep posts on/before YYYY-MM-DD (single-keyword mode)")
    parser.add_argument("--max-posts", type=int, default=200)
    parser.add_argument("--merge", help="Existing authors JSON to seed results (avoids re-scraping)")
    parser.add_argument("--output", default=".tmp/sia_post_authors.json")
    parser.add_argument("--actor", default=DEFAULT_ACTOR, help="Apify actor ID")
    args = parser.parse_args()

    if not args.keyword and not args.keywords_file:
        parser.error("Provide either --keyword or --keywords-file")

    # Build keyword list
    if args.keywords_file:
        with open(args.keywords_file) as f:
            keywords = json.load(f)
    else:
        keywords = [{"keyword": args.keyword, "date_from": args.date_from, "date_to": args.date_to}]

    # Seed with existing results if merging
    seen = {}
    if args.merge and os.path.exists(args.merge):
        with open(args.merge) as f:
            existing = json.load(f)
        for author in existing:
            seen[author_hash(author)] = author
        print(f"Merged {len(seen)} existing authors from {args.merge}\n")

    start_count = len(seen)
    for kw in keywords:
        print(f"\n=== Keyword: '{kw['keyword']}' ===")
        process_keyword(
            kw["keyword"], kw.get("date_from"), kw.get("date_to"),
            args.actor, args.max_posts, seen,
        )

    results = list(seen.values())
    print(f"\n{'='*40}")
    print(f"Started with: {start_count} | Total unique now: {len(results)} (+{len(results) - start_count} new)")

    os.makedirs(".tmp", exist_ok=True)
    with open(args.output, "w") as f:
        json.dump(results, f, indent=2)
    print(f"Saved → {args.output}")


if __name__ == "__main__":
    main()
