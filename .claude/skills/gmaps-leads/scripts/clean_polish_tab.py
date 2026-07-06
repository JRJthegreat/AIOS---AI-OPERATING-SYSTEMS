#!/usr/bin/env python3
"""
Final quality pass on a lead tab (run ONLY when no other writers are active,
it rewrites the tab):
1. Drop rows with rating < min_stars or no rating
2. Drop rows matching an exclude regex on name/category (late noise)
3. Sort: verified DMs first (by dm_status), then rating desc
4. Row height 18px, frozen bold header

Usage:
  python3 clean_polish_tab.py --sheet_url URL --tab "Golf Courses" \
    [--min_stars 4.0] [--exclude REGEX] [--apply]
"""

import os
import re
import sys
import json
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from verify_email_persona import get_ws

STATUS_RANK = {  # lower = higher in sheet
    "verified_website": 0, "verified_serp_high": 1, "verified_amf_dm": 2,
    "verified_serp_medium": 3, "verified_adjacent_high": 4, "verified_serp_low": 5,
    "verified_adjacent_medium": 6, "verified_adjacent_low": 7,
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sheet_url", required=True)
    ap.add_argument("--tab", required=True)
    ap.add_argument("--min_stars", type=float, default=4.0)
    ap.add_argument("--exclude", default="")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    ws = get_ws(args.sheet_url, args.tab)
    values = ws.get_all_values()
    header, data = values[0], values[1:]
    idx = {n: i for i, n in enumerate(header)}
    rx = re.compile(args.exclude, re.I) if args.exclude else None

    def cell(row, name):
        i = idx.get(name)
        return row[i] if i is not None and i < len(row) else ""

    kept, dropped_rating, dropped_noise = [], 0, 0
    for row in data:
        if not any(row):
            continue
        try:
            rating = float(cell(row, "rating"))
        except (ValueError, TypeError):
            rating = None
        if rating is None or rating < args.min_stars:
            dropped_rating += 1
            continue
        if rx and rx.search(f"{cell(row, 'business_name')} {cell(row, 'category')}"):
            dropped_noise += 1
            continue
        kept.append(row)

    def sort_key(row):
        st = cell(row, "dm_status")
        try:
            rating = float(cell(row, "rating"))
        except (ValueError, TypeError):
            rating = 0.0
        return (STATUS_RANK.get(st, 99), -rating)

    kept.sort(key=sort_key)
    verified = sum(1 for r in kept if cell(r, "dm_status").startswith("verified"))
    print(f"{args.tab}: keep {len(kept)} | drop {dropped_rating} sub-{args.min_stars}/unrated"
          f" + {dropped_noise} noise | verified DMs: {verified}")
    if not args.apply:
        print("DRY RUN - re-run with --apply")
        return

    n_cols = len(header)
    kept = [r[:n_cols] + [""] * max(0, n_cols - len(r)) for r in kept]
    ws.clear()
    ws.update(values=[header] + kept, range_name="A1")
    ws.format("A1:AZ1", {"textFormat": {"bold": True},
                         "backgroundColor": {"red": 0.9, "green": 0.9, "blue": 0.9}})
    ws.freeze(rows=1)
    sheet_id = ws.id
    ws.spreadsheet.batch_update({"requests": [{
        "updateDimensionProperties": {
            "range": {"sheetId": sheet_id, "dimension": "ROWS",
                      "startIndex": 1, "endIndex": len(kept) + 1},
            "properties": {"pixelSize": 18}, "fields": "pixelSize"}}]})
    print(f"Rewrote '{args.tab}' with {len(kept)} rows, 18px rows, header frozen.")


if __name__ == "__main__":
    main()
