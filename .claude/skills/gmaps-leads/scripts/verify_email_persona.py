#!/usr/bin/env python3
"""
Verify which scraped emails belong to the target persona (e.g. golf course
superintendent) by Google-searching each named email and having the LLM read
the top results (LinkedIn titles usually appear right in the snippets).

Order of evidence per row:
1. team_contacts / owner_* from the website scrape whose title matches the
   persona regex  -> verified_website (free)
2. Named emails (non-generic local part) -> Google SERP via Apify
   apify/google-search-scraper -> Azure gpt-4.1 judges persona match
   -> verified_serp / wrong_persona
3. Anything left -> unverified (feed to AI Ark / AnyMailFinder next)

Writes dm_name, dm_title, dm_email, dm_source, dm_status columns to the tab.
Dry-run by default; --apply writes to the sheet.

Usage:
  python3 verify_email_persona.py --sheet_url URL --tab "Golf Courses" \
    --persona "Golf Course Superintendent / Director of Agronomy / Director of Grounds / Head Greenkeeper" \
    --persona_regex "superintendent|agronom|grounds|greenkeeper|turf" \
    [--limit 25] [--apply]
"""

import os
import re
import sys
import json
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv

import requests
import gspread
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from apify_client import ApifyClient
from openai import AzureOpenAI
from urllib.parse import urlparse

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "..", "..", ".."))
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))
TOKEN_PATH = os.path.join(PROJECT_ROOT, "token.json")

SCOPES = ["https://www.googleapis.com/auth/spreadsheets",
          "https://www.googleapis.com/auth/drive"]

AZURE_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_API_KEY = os.getenv("AZURE_OPENAI_API_KEY")
AZURE_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION", "2024-10-21")
AZURE_DEPLOYMENT = os.getenv("AZURE_OPENAI_DEPLOYMENT_FAST", "gpt-4.1")
_azure = AzureOpenAI(azure_endpoint=AZURE_ENDPOINT, api_key=AZURE_API_KEY,
                     api_version=AZURE_API_VERSION) if AZURE_ENDPOINT else None

SEARCH_ACTOR = "apify/google-search-scraper"
LLM_WORKERS = 4
AMF_KEY = os.getenv("ANYMAILFINDER_API_KEY")

# Domains where AMF company search is pointless (site builders, socials, freemail)
SKIP_AMF_DOMAINS = {"gmail.com", "yahoo.com", "aol.com", "hotmail.com", "outlook.com",
                    "facebook.com", "instagram.com", "wixsite.com", "squarespace.com",
                    "godaddysites.com", "weebly.com", "business.site"}


def site_domain(url: str) -> str:
    if not url:
        return ""
    host = urlparse(url if url.startswith("http") else f"https://{url}").netloc.lower()
    host = host[4:] if host.startswith("www.") else host
    if not host or any(host == d or host.endswith("." + d) for d in SKIP_AMF_DOMAINS):
        return ""
    return host


def amf_company_emails(domain: str) -> list:
    """AnyMailFinder company endpoint -> list of VALID emails for the domain (1 credit)."""
    if not AMF_KEY or not domain:
        return []
    try:
        r = requests.post("https://api.anymailfinder.com/v5.1/find-email/company",
                          headers={"Authorization": AMF_KEY, "Content-Type": "application/json"},
                          json={"domain": domain}, timeout=120)
        if r.status_code != 200:
            return []
        return r.json().get("valid_emails") or []
    except Exception as e:
        print(f"  AMF error for {domain}: {e}")
        return []

DM_COLUMNS = ["dm_first_name", "dm_last_name", "dm_name", "dm_title",
              "dm_email", "dm_source", "dm_status"]

NAME_SUFFIXES = {"jr", "jr.", "sr", "sr.", "ii", "iii", "iv", "cgcs", "csfm", "pga"}


def split_name(full: str) -> tuple:
    """'Dennis Krause' -> ('Dennis', 'Krause'); handles suffixes/middle initials."""
    tokens = [t for t in (full or "").replace(",", " ").split()
              if t.lower() not in NAME_SUFFIXES]
    if not tokens:
        return "", ""
    if len(tokens) == 1:
        return tokens[0], ""
    return tokens[0], tokens[-1]

# Local parts that are role/department inboxes, not people
GENERIC_LOCALS = {
    "info", "contact", "contactus", "hello", "admin", "office", "sales",
    "events", "event", "banquets", "banquet", "catering", "membership",
    "memberships", "member", "golf", "proshop", "pro", "shop", "teetimes",
    "reservations", "frontdesk", "clubhouse", "marketing", "hr", "jobs",
    "careers", "support", "service", "services", "booking", "bookings",
    "weddings", "dining", "restaurant", "accounting", "billing", "mail",
    "email", "enquiries", "inquiries", "general", "team", "staff", "press",
    "media", "webmaster", "noreply", "no-reply", "gm", "manager", "office2",
    "reception", "clubinfo", "tournaments", "leagues", "youth", "camps",
}


def get_ws(sheet_url: str, tab: str):
    with open(TOKEN_PATH) as f:
        creds = Credentials.from_authorized_user_info(json.load(f), SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    client = gspread.authorize(creds)
    sheet_id = sheet_url.split("/d/")[1].split("/")[0] if "/d/" in sheet_url else sheet_url
    ss = client.open_by_key(sheet_id)
    return ss.worksheet(tab)


def col_letter(n: int) -> str:
    s = ""
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def named_emails(emails_str: str) -> list:
    """Return emails whose local part looks like a person, not a role inbox."""
    out = []
    for e in re.split(r"[,;\s]+", emails_str or ""):
        e = e.strip().lower()
        if not e or "@" not in e:
            continue
        local = e.split("@")[0]
        base = re.sub(r"[0-9]+$", "", re.sub(r"[._-]", "", local))
        if local in GENERIC_LOCALS or base in GENERIC_LOCALS:
            continue
        out.append(e)
    return out


def _dm(name, title, email, source, status) -> dict:
    first, last = split_name(name)
    return {"dm_first_name": first, "dm_last_name": last,
            "dm_name": name or "", "dm_title": title or "",
            "dm_email": email or "", "dm_source": source, "dm_status": status}


def mine_site_contacts(row: dict, persona_regex) -> dict:
    """Check owner_* and team_contacts for a title matching the persona."""
    if persona_regex.search(row.get("owner_title") or ""):
        return _dm(row.get("owner_name"), row.get("owner_title"),
                   row.get("owner_email"), "website", "verified_website")
    try:
        team = json.loads(row.get("team_contacts") or "[]")
    except json.JSONDecodeError:
        team = []
    for m in team:
        if persona_regex.search(m.get("title") or ""):
            return _dm(m.get("name"), m.get("title"), m.get("email"),
                       "website", "verified_website")
    return None


def serp_batch(queries: list, cache: dict = None) -> dict:
    """Run queries through google-search-scraper, 3 chunks concurrently.
    `cache` ({query: results}) short-circuits already-searched queries."""
    serps = dict(cache or {})
    todo = [q for q in queries if q not in serps]
    if not todo:
        return serps
    client = ApifyClient(os.getenv("APIFY_API_TOKEN"))
    CHUNK = 100
    chunks = [todo[i:i + CHUNK] for i in range(0, len(todo), CHUNK)]
    print(f"  SERP: {len(todo)} new queries in {len(chunks)} batches "
          f"({len(serps)} cached)...")

    def run_chunk(pair):
        n, chunk = pair
        run = client.actor(SEARCH_ACTOR).call(run_input={
            "queries": "\n".join(chunk),
            "resultsPerPage": 20,
            "maxPagesPerQuery": 1,
            "countryCode": "us",
            "languageCode": "en",
        })
        out = {}
        for item in client.dataset(run["defaultDatasetId"]).iterate_items():
            term = (item.get("searchQuery") or {}).get("term", "")
            out[term] = [
                {"title": r.get("title"), "url": r.get("url"),
                 "snippet": r.get("description")}
                for r in (item.get("organicResults") or [])[:20]
            ]
        print(f"  SERP batch {n}/{len(chunks)} done ({len(out)} results)")
        return out

    with ThreadPoolExecutor(max_workers=3) as ex:
        for f in as_completed([ex.submit(run_chunk, (i + 1, c))
                               for i, c in enumerate(chunks)]):
            serps.update(f.result())
    return serps


def judge_email(email: str, business: str, persona: str, results: list) -> dict:
    """LLM reads SERP results and decides whether the email is the persona."""
    if not results:
        return {"status": "no_results"}
    prompt = f"""You are verifying the owner of a business email address.

Email: {email}
Business it was scraped from: {business}
Target persona: {persona}

Below are Google search results for this email address. Decide:
1. Can you identify the PERSON who uses this email (name)?
2. What is their job title, and at which company?
3. How close are they to the target persona AT THIS business (or its parent club/company)?
   - "exact": title matches the target persona
   - "adjacent": same department or the operational decision-maker who owns that area
     (e.g. assistant superintendent, director of course/field operations, head of maintenance,
     or the GM at a small operation)
   - "unrelated": different function entirely (front desk, events, membership, F&B, pro shop)

Search results (JSON):
{json.dumps(results, ensure_ascii=False)}

Respond with ONLY a JSON object:
{{"person_name": "or null", "person_title": "or null", "employer": "or null",
"is_target_persona": true/false, "closeness": "exact/adjacent/unrelated",
"evidence_url": "most relevant url or null", "confidence": "high/medium/low"}}"""
    import time, random
    for attempt in range(5):
        try:
            resp = _azure.chat.completions.create(
                model=AZURE_DEPLOYMENT, max_tokens=400,
                response_format={"type": "json_object"},
                messages=[{"role": "user", "content": prompt}])
            out = json.loads(resp.choices[0].message.content)
            # LLMs sometimes emit the STRING "null" - normalize to empty
            for k in ("person_name", "person_title", "employer", "evidence_url"):
                if str(out.get(k) or "").strip().lower() in ("null", "none", "n/a"):
                    out[k] = ""
            out["status"] = "ok"
            return out
        except Exception as e:
            if "429" in str(e) or "rate limit" in str(e).lower():
                wait = (2 ** attempt) * 5 + random.uniform(0, 3)
                time.sleep(wait)
                continue
            print(f"  LLM error for {email}: {e}")
            return {"status": "llm_error"}
    print(f"  LLM rate-limited after retries for {email}")
    return {"status": "llm_error"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sheet_url", required=True)
    ap.add_argument("--tab", required=True)
    ap.add_argument("--persona", required=True,
                    help="Persona description for the LLM judge")
    ap.add_argument("--persona_regex", required=True,
                    help="Regex for title matching in scraped site contacts")
    ap.add_argument("--limit", type=int, default=0, help="Max rows to process (0 = all)")
    ap.add_argument("--max_emails_per_row", type=int, default=0,
                    help="Cap on named emails judged per row (0 = judge ALL named emails)")
    ap.add_argument("--amf", action="store_true",
                    help="Use AnyMailFinder company search (1 credit/domain) to pull more named emails for unresolved rows")
    ap.add_argument("--serp_cache", help="JSON file of {query: results} from prior runs; cached queries are not re-searched")
    ap.add_argument("--force", action="store_true", help="Re-process rows that already have dm_status")
    ap.add_argument("--apply", action="store_true", help="Write results to the sheet")
    args = ap.parse_args()

    persona_regex = re.compile(args.persona_regex, re.I)

    ws = get_ws(args.sheet_url, args.tab)
    values = ws.get_all_values()
    header, data = values[0], values[1:]
    if args.limit:
        data = data[:args.limit]

    # Ensure dm_ columns exist in header
    header_full = list(header)
    for c in DM_COLUMNS:
        if c not in header_full:
            header_full.append(c)
    dm_idx = {c: header_full.index(c) for c in DM_COLUMNS}
    n_cols = len(header_full)

    rows = []
    for i, r in enumerate(data):
        r = r + [""] * (n_cols - len(r))
        rows.append({"_rownum": i + 2, **{header_full[j]: r[j] for j in range(n_cols)}})

    # Pass 1: free mining of website-scraped staff titles
    pending_search = []   # (row, email)
    resolved = {}         # rownum -> dm dict
    needs_amf = []        # rows to top up with AMF company emails
    for row in rows:
        st = row.get("dm_status") or ""
        if st.startswith("verified") and not args.force:
            continue
        if st and not args.force and not args.amf:
            continue  # already judged; only an --amf sweep retries non-verified rows
        hit = mine_site_contacts(row, persona_regex)
        if hit:
            resolved[row["_rownum"]] = hit
            continue
        cands = named_emails(row.get("emails", ""))
        if row.get("owner_email"):
            cands = named_emails(row["owner_email"]) + cands
        seen = set()
        cands = [c for c in cands if not (c in seen or seen.add(c))]
        row["_cands"] = cands
        if args.amf and site_domain(row.get("website", "")):
            needs_amf.append(row)
        elif not cands:
            resolved[row["_rownum"]] = _dm("", "", "", "", "no_named_email")
        else:
            cap = args.max_emails_per_row or len(cands)
            for c in cands[:cap]:
                pending_search.append((row, c))

    # Pass 1b: AMF company search for unresolved rows (1 credit per domain)
    if needs_amf:
        print(f"AMF company search on {len(needs_amf)} domains...")
        def amf_work(row):
            return row, amf_company_emails(site_domain(row.get("website", "")))
        with ThreadPoolExecutor(max_workers=4) as ex:
            for f in as_completed([ex.submit(amf_work, r) for r in needs_amf]):
                row, emails = f.result()
                cands = row.get("_cands", []) + named_emails(", ".join(emails))
                seen = set()
                cands = [c for c in cands if not (c in seen or seen.add(c))]
                if not cands:
                    resolved[row["_rownum"]] = _dm("", "", "", "", "no_named_email")
                else:
                    cap = args.max_emails_per_row or len(cands)
                    for c in cands[:cap]:
                        pending_search.append((row, c))

    print(f"Rows: {len(rows)} | site-verified: "
          f"{sum(1 for v in resolved.values() if v['dm_status'] == 'verified_website')} | "
          f"no named email: {sum(1 for v in resolved.values() if v['dm_status'] == 'no_named_email')} | "
          f"emails to SERP-verify: {len(pending_search)}")

    # Pass 2: SERP + LLM
    if pending_search:
        cache = {}
        if args.serp_cache and os.path.exists(args.serp_cache):
            with open(args.serp_cache) as f:
                cache = json.load(f)
        queries = sorted({f'"{email}"' for _, email in pending_search})
        serps = serp_batch(queries, cache=cache)

        def work(item):
            row, email = item
            res = serps.get(f'"{email}"', [])
            verdict = judge_email(email, row.get("business_name", ""), args.persona, res)
            return row, email, verdict

        judged = {}  # rownum -> list of (email, verdict)
        with ThreadPoolExecutor(max_workers=LLM_WORKERS) as ex:
            futs = [ex.submit(work, it) for it in pending_search]
            for f in as_completed(futs):
                row, email, verdict = f.result()
                judged.setdefault(row["_rownum"], []).append((email, verdict))
                nm = verdict.get("person_name") or "?"
                tt = verdict.get("person_title") or "?"
                ok = verdict.get("is_target_persona")
                print(f"  [{row['_rownum']}] {email} -> {nm} | {tt} | persona={ok}")

        for rownum, pairs in judged.items():
            best, adjacent = None, None
            for email, v in pairs:
                if v.get("status") != "ok":
                    continue
                if v.get("is_target_persona") or v.get("closeness") == "exact":
                    best = _dm(v.get("person_name"), v.get("person_title"), email,
                               f"serp:{v.get('evidence_url') or ''}",
                               f"verified_serp_{v.get('confidence', 'low')}")
                    break
                if (v.get("closeness") == "adjacent" and not adjacent
                        and v.get("person_name")):
                    adjacent = _dm(v.get("person_name"), v.get("person_title"), email,
                                   f"serp:{v.get('evidence_url') or ''}",
                                   f"verified_adjacent_{v.get('confidence', 'low')}")
            if not best and adjacent:
                best = adjacent
            if not best:
                statuses = {v.get("status") for _, v in pairs}
                if "ok" in statuses:
                    st = "wrong_persona"
                elif statuses == {"no_results"}:
                    st = "no_serp_results"
                else:
                    st = "unverified"
                best = _dm("", "", "", "", st)
            resolved[rownum] = best

    # Summary
    counts = {}
    for v in resolved.values():
        counts[v["dm_status"]] = counts.get(v["dm_status"], 0) + 1
    print("\nSummary:", json.dumps(counts, indent=2))

    if not args.apply:
        print("\nDRY RUN - nothing written. Re-run with --apply to write to the sheet.")
        return

    # Write: headers (if new) + per-row dm columns in one batch
    if ws.col_count < n_cols:
        ws.add_cols(n_cols - ws.col_count)
    updates = []
    start_col = col_letter(dm_idx["dm_first_name"] + 1)
    end_col = col_letter(dm_idx["dm_status"] + 1)
    if header != header_full:
        updates.append({"range": f"{start_col}1:{end_col}1", "values": [DM_COLUMNS]})
    for rownum, v in sorted(resolved.items()):
        updates.append({"range": f"{start_col}{rownum}:{end_col}{rownum}",
                        "values": [[v[c] for c in DM_COLUMNS]]})
    ws.batch_update(updates, value_input_option="RAW")
    print(f"Wrote {len(resolved)} rows to '{args.tab}'.")


if __name__ == "__main__":
    main()
