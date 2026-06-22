"""
Phase 1.5: Keep only companies at/below an employee-count cap (default 500).

Runs BEFORE the LLM classifier so it also shrinks that job (fewer rows → fewer
LLM calls → lower cost). Reads Company Size (col M), parses the lower bound of
Indeed's ranges ("201 to 500" -> 201, "1,001 to 5,000" -> 1001, "10,000+" ->
10000) and drops rows whose lower bound exceeds the cap.

Blank / "Decline to state" sizes are KEPT by default (usually small companies
that didn't publish headcount) — use --drop_blanks to remove them too.

Dry-run by default; --apply deletes (bottom-up so indices stay stable).

Usage:
  python3 filter_by_size.py --sheet_url "URL"                       # dry run
  python3 filter_by_size.py --sheet_url "URL" --apply               # cap at 500
  python3 filter_by_size.py --sheet_url "URL" --max_employees 200 --apply
"""

import argparse

from pull_dataset import (
    TAB_NAME, get_google_service, get_sheet_id_from_url, parse_size_lower_bound,
)

COL_COMPANY_NAME = 10  # K
COL_COMPANY_SIZE = 12  # M


def get_tab_sheet_id(service, spreadsheet_id, tab_name):
    meta = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    for s in meta["sheets"]:
        if s["properties"]["title"] == tab_name:
            return s["properties"]["sheetId"]
    raise RuntimeError(f"Tab {tab_name!r} not found")


def main():
    parser = argparse.ArgumentParser(description="Drop rows whose company exceeds an employee-count cap")
    parser.add_argument("--sheet_url", required=True)
    parser.add_argument("--max_employees", type=int, default=500, help="Keep companies with lower-bound size <= this (default 500)")
    parser.add_argument("--drop_blanks", action="store_true", help="Also drop rows with blank/unparseable size (default: keep them)")
    parser.add_argument("--apply", action="store_true", help="Actually delete. Default: dry run.")
    args = parser.parse_args()

    spreadsheet_id = get_sheet_id_from_url(args.sheet_url)
    service = get_google_service()
    tab_sheet_id = get_tab_sheet_id(service, spreadsheet_id, TAB_NAME)

    mode = "APPLY" if args.apply else "DRY RUN"
    print(f"=== Filter by Company Size (<= {args.max_employees} employees) [{mode}] ===")
    print(f"Sheet: {spreadsheet_id}\n")

    rows = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id, range=f"{TAB_NAME}!A2:AC50000"
    ).execute().get("values", [])
    print(f"Total rows: {len(rows)}")

    def g(r, i):
        return (r[i] if len(r) > i and r[i] else "").strip()

    to_delete = []
    kept = kept_blank = dropped_blank = 0
    for i, r in enumerate(rows):
        sheet_row = i + 2
        lower = parse_size_lower_bound(g(r, COL_COMPANY_SIZE))
        if lower is None:
            if args.drop_blanks:
                to_delete.append(sheet_row)
                dropped_blank += 1
            else:
                kept += 1
                kept_blank += 1
        elif lower > args.max_employees:
            to_delete.append(sheet_row)
        else:
            kept += 1

    print(f"Keep:  {kept}  (incl. {kept_blank} with blank/unknown size)")
    print(f"Drop:  {len(to_delete)}  (> {args.max_employees} employees{', incl. ' + str(dropped_blank) + ' blank' if args.drop_blanks else ''})")

    if not args.apply:
        print("\n[DRY RUN] No changes made. Re-run with --apply to delete oversized rows.")
        return
    if not to_delete:
        print("\nNothing to delete.")
        print("=== Done ===")
        return

    print(f"\nDeleting {len(to_delete)} rows (bottom-up)...")
    requests_body = [
        {"deleteDimension": {"range": {
            "sheetId": tab_sheet_id, "dimension": "ROWS",
            "startIndex": r - 1, "endIndex": r,
        }}}
        for r in sorted(to_delete, reverse=True)
    ]
    BATCH = 100
    for i in range(0, len(requests_body), BATCH):
        service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id, body={"requests": requests_body[i:i + BATCH]}
        ).execute()
        print(f"  Deleted chunk {i // BATCH + 1}/{(len(requests_body) + BATCH - 1) // BATCH}")

    remaining = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id, range=f"{TAB_NAME}!A2:A50000"
    ).execute()
    print(f"\nRows remaining: {len(remaining.get('values', []))}")
    print("=== Done ===")


if __name__ == "__main__":
    main()
