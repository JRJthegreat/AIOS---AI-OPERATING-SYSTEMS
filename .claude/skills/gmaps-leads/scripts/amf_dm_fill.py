#!/usr/bin/env python3
"""
Fill dm_* columns straight from AnyMailFinder's decision-maker endpoint.
Right for owner-led verticals (landscaping, sports complexes) where the persona
maps to an AMF category ("ceo", "operations"). Accepts VALID emails only.

Usage:
  python3 amf_dm_fill.py --sheet_url URL --tab "Landscaping Contractors" \
    [--category ceo] [--fallback_category operations] [--workers 6] [--apply]
"""

import os
import sys
import json
import argparse
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from verify_email_persona import get_ws, col_letter, split_name, DM_COLUMNS, site_domain

AMF_KEY = os.getenv("ANYMAILFINDER_API_KEY")


def amf_decision_maker(domain: str, company: str, category: str) -> dict:
    body = {"decision_maker_category": [category]}
    if domain:
        body["domain"] = domain
    elif company:
        body["company_name"] = company
    else:
        return None
    try:
        r = requests.post("https://api.anymailfinder.com/v5.1/find-email/decision-maker",
                          headers={"Authorization": AMF_KEY, "Content-Type": "application/json"},
                          json=body, timeout=180)
        if r.status_code != 200:
            return None
        data = r.json()
        if data.get("email") and data.get("email_status") == "valid":
            return data
    except Exception as e:
        print(f"  AMF DM error for {domain or company}: {e}")
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sheet_url", required=True)
    ap.add_argument("--tab", required=True)
    ap.add_argument("--category", default="ceo")
    ap.add_argument("--fallback_category", default="")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    ws = get_ws(args.sheet_url, args.tab)
    values = ws.get_all_values()
    header, data = values[0], values[1:]

    header_full = list(header)
    for c in DM_COLUMNS:
        if c not in header_full:
            header_full.append(c)
    dm_idx = {c: header_full.index(c) for c in DM_COLUMNS}
    n_cols = len(header_full)

    todo = []
    for i, r in enumerate(data):
        r = r + [""] * (n_cols - len(r))
        row = {header_full[j]: r[j] for j in range(n_cols)}
        st = row.get("dm_status") or ""
        if st.startswith("verified"):
            continue
        todo.append((i + 2, row.get("business_name", ""), row.get("website", "")))
    if args.limit:
        todo = todo[:args.limit]
    print(f"{args.tab}: {len(data)} rows, {len(todo)} to fill via AMF decision-maker ({args.category})")
    if not todo:
        return
    if not args.apply:
        print("DRY RUN - re-run with --apply")
        return

    if ws.col_count < n_cols:
        ws.add_cols(n_cols - ws.col_count)
    start_col = col_letter(dm_idx["dm_first_name"] + 1)
    end_col = col_letter(dm_idx["dm_status"] + 1)
    if header != header_full:
        ws.batch_update([{"range": f"{start_col}1:{end_col}1", "values": [DM_COLUMNS]}],
                        value_input_option="RAW")

    def work(item):
        rn, company, website = item
        domain = site_domain(website)
        res = amf_decision_maker(domain, company, args.category)
        cat = args.category
        if not res and args.fallback_category:
            res = amf_decision_maker(domain, company, args.fallback_category)
            cat = args.fallback_category
        return rn, company, res, cat

    found, updates, done = 0, [], 0
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = [ex.submit(work, t) for t in todo]
        for f in as_completed(futs):
            rn, company, res, cat = f.result()
            done += 1
            if res:
                full = (res.get("person_full_name") or "").strip()
                first = (res.get("person_first_name") or "").strip()
                last = (res.get("person_last_name") or "").strip()
                if full and not (first or last):
                    first, last = split_name(full)
                cells = [first, last, full or f"{first} {last}".strip(),
                         (res.get("person_job_title") or "").strip(),
                         res["email"], f"amf-dm:{cat}", "verified_amf_dm"]
                found += 1
                print(f"  [{rn}] {company} -> {full or res['email']} | {res.get('person_job_title')}")
            else:
                cells = ["", "", "", "", "", "", "no_dm_found"]
            updates.append({"range": f"{start_col}{rn}:{end_col}{rn}", "values": [cells]})
            if len(updates) >= 25:
                ws.batch_update(updates, value_input_option="RAW")
                updates = []
                print(f"  {done}/{len(todo)} processed ({found} found)")
    if updates:
        ws.batch_update(updates, value_input_option="RAW")
    print(f"AMF DM fill on '{args.tab}': {found}/{len(todo)} decision-makers with valid email.")


if __name__ == "__main__":
    main()
