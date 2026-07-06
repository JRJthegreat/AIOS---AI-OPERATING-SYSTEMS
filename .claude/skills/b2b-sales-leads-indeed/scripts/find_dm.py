"""
Phase 3: Find each company's decision-maker (DM) via AI Ark people_search, then
resolve the DM's email via AnyMailFinder → write cols T-Y.

For every company row (already deduped, one row per company):
  1. AI Ark `people_search` by company DOMAIN (col L), falling back to company NAME
     (col K) where the domain is blank (~89 rows). Returns people with name/title/
     LinkedIn — NO email.
  2. Pick the best DM: sales leadership first (CRO / VP Sales / Head of Sales /
     Sales Director), falling back to Founder/CEO/President/Owner. One call/company.
  3. AnyMailFinder (`/v5.1/find-email/person`) resolves the DM's email from
     full_name + domain. ONLY `valid` emails are accepted — never `risky`/`invalid`.
  4. Write: T DM Name, U DM Title, V LinkedIn, W Email, X First, Y Last.

Rows that already have a DM Name (col T) are skipped unless --force.
AI Ark = MCP server, but called here over its HTTP JSON-RPC endpoint (stateless,
token in URL) so the whole pipeline is one deterministic script. Endpoint + token
are read from the gitignored .mcp.json at project root.

Dry-run by default (plan + cost estimate, NO API calls). --apply spends + writes.

Usage:
  python3 find_dm.py --sheet_url "URL"                    # dry run: counts + cost
  python3 find_dm.py --sheet_url "URL" --limit 10 --apply # 10-company sample (spends)
  python3 find_dm.py --sheet_url "URL" --apply            # full run (after go-ahead)
  python3 find_dm.py --sheet_url "URL" --apply --force    # redo rows that already have a DM
"""

import os
import re
import json
import time
import random
import argparse
import subprocess
import requests
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "..", "..", ".."))
ENV_PATH = os.path.join(PROJECT_ROOT, ".env")
TOKEN_PATH = os.path.join(PROJECT_ROOT, "token.json")
MCP_PATH = os.path.join(PROJECT_ROOT, ".mcp.json")
load_dotenv(ENV_PATH)

ANYMAIL_KEY = os.getenv("ANYMAILFINDER_API_KEY")

# Default campaign sheet (b2b-sales-leads-indeed)
DEFAULT_SHEET = "https://docs.google.com/spreadsheets/d/1g2X-qSv-Y3A5A8Z83cftAD-9Af5PO0XQJTVjH6yq5PQ/edit"

TAB_NAME = "Leads"
COL_COMPANY = 10   # K
COL_WEBSITE = 11   # L
COL_DM_NAME = 19   # T
COL_DM_TITLE = 20  # U
COL_LINKEDIN = 21  # V
COL_EMAIL = 22     # W
COL_FIRST = 23     # X
COL_LAST = 24      # Y

WRITE_BATCH = 25   # flush sheet writes every N processed rows
WORKERS = 4        # concurrent companies — keep modest; AI Ark's edge rate-limits bursts
SIZE = 3           # profiles fetched per AI Ark call — each returned profile costs 0.5 credit

# AI Ark bills 0.5 credit PER PROFILE RETURNED (data delivery), so we filter hard to
# return only the few right people, then keep size small.
#   Tier 1 — the person running sales for the whole company. Leadership seniorities
#   ONLY: dropping manager/senior/entry is what excludes IC reps (account managers,
#   SDRs) that otherwise dominate department=sales and waste credits.
LEADERSHIP_SENIORITY = "c_suite,vp,head,director,partner,owner"
#   Tier 2 — founder/owner/CEO fallback, fired only when tier 1 finds no sales leader.
FOUNDER_SENIORITY = "founder,owner,c_suite"


# ---- AI Ark endpoint (read from gitignored .mcp.json) ------------------------

def ark_endpoint():
    with open(MCP_PATH) as f:
        return json.load(f)["mcpServers"]["ai-ark"]["url"]


ARK_URL = None  # lazily set in main()


def ark_people_search(domain=None, company_name=None, seniority=None, department=None, size=SIZE):
    """Call AI Ark people_search over HTTP JSON-RPC. Returns list of person dicts.

    Shelled out to `curl` on purpose: macOS system Python 3.9.6 is linked against
    LibreSSL 2.8.3, whose TLS handshake the Cloudflare/Kong edge in front of
    api.ai-ark.com rejects (TLSV1_ALERT_PROTOCOL_VERSION). curl uses a modern TLS
    stack and connects fine. AnyMailFinder/Google requests still go via `requests`.
    """
    args = {"size": size}
    if seniority:
        args["seniority"] = seniority
    if department:
        args["department"] = department
    if domain:
        args["companyDomain"] = domain
    elif company_name:
        args["companyName"] = company_name
    else:
        return []

    payload = json.dumps({
        "jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {"name": "people_search", "arguments": args},
    })
    # Retry hard failures (network/HTTP 429-5xx/JSON-RPC error) so a rate-limited or
    # transient blip doesn't masquerade as "no DM". A genuine empty result (HTTP 200,
    # totalElements 0) does NOT retry. HTTP status is captured via curl -w because a
    # 429 body otherwise parses as an empty 200 and silently looks like "no results".
    for attempt in range(5):
        try:
            proc = subprocess.run(
                ["curl", "-s", "--max-time", "60", "-X", "POST", ARK_URL,
                 "-H", "Content-Type: application/json",
                 "-H", "Accept: application/json, text/event-stream",
                 "-d", "@-", "-w", "\nHTTPSTATUS:%{http_code}"],
                input=payload, capture_output=True, text=True, timeout=75,
            )
            if proc.returncode != 0 or not proc.stdout:
                raise RuntimeError(f"curl rc={proc.returncode}: {proc.stderr[:160]}")
            body, _, status = proc.stdout.rpartition("\nHTTPSTATUS:")
            status = int(status.strip()) if status.strip().isdigit() else 0
            if status != 200:
                raise RuntimeError(f"HTTP {status}: {body[:160]}")
            outer = json.loads(body)
            if "error" in outer:
                raise RuntimeError(f"JSON-RPC error: {outer['error'].get('message')}")
            content = outer.get("result", {}).get("content", [])
            if not content:
                return []  # genuine empty match
            inner = json.loads(content[0]["text"])  # double-encoded payload
            return inner.get("content", []) or []
        except Exception as e:
            if attempt < 4:
                time.sleep(min(8, 2 ** attempt) + random.uniform(0, 1.5))  # backoff + jitter
                continue
            print(f"    [!] AI Ark request failed after retries: {e}")
            return []


def ark_export_email(person_id):
    """AI Ark export_single by person id → verified email. Returns email or ''.
    Bills 0.5 credit only when a VALID email is found (404/none = no charge)."""
    if not person_id:
        return ""
    payload = json.dumps({
        "jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {"name": "export_single", "arguments": {"id": person_id}},
    })
    for attempt in range(4):
        try:
            proc = subprocess.run(
                ["curl", "-s", "--max-time", "90", "-X", "POST", ARK_URL,
                 "-H", "Content-Type: application/json",
                 "-H", "Accept: application/json, text/event-stream",
                 "-d", "@-", "-w", "\nHTTPSTATUS:%{http_code}"],
                input=payload, capture_output=True, text=True, timeout=105,
            )
            if proc.returncode != 0 or not proc.stdout:
                raise RuntimeError(f"curl rc={proc.returncode}")
            body, _, status = proc.stdout.rpartition("\nHTTPSTATUS:")
            status = int(status.strip()) if status.strip().isdigit() else 0
            if status in (429, 500, 502, 503, 504):
                raise RuntimeError(f"HTTP {status}")
            if status != 200:
                return ""  # 404 = no email found for this person → not an error
            outer = json.loads(body)
            if "error" in outer:
                return ""
            content = outer.get("result", {}).get("content", [])
            if not content:
                return ""
            person = json.loads(content[0]["text"])
            out = (person.get("email") or {}).get("output") or []
            for rec in out:
                if rec.get("status") == "VALID" and rec.get("address"):
                    return rec["address"].strip().lower()
            return ""
        except Exception:
            if attempt < 3:
                time.sleep(min(8, 2 ** attempt) + random.uniform(0, 1.5))
                continue
            return ""


# ---- DM selection ------------------------------------------------------------

# Roles that are NOT buyers for an "we book meetings for your new SDR" offer:
# IC sales reps (the people being hired, not the buyer) + support/admin functions.
DISQUALIFY = re.compile(
    r"\b(account executive|account manager|sdr|bdr|"
    r"sales (rep|representative|associate|consultant|agent|specialist|engineer|coordinator|intern)|"
    r"inside sales (rep|representative|associate)|business development (rep|representative)|"
    r"human resources|recruit|talent acquisition|"
    r"\bit\b|information technology|software|developer|web|"
    r"accountant|controller|bookkeep|payroll|"
    r"customer (success|service|support)|"
    r"office manager|administrative assistant|executive assistant|receptionist|"
    r"warehouse|driver|technician|installer|estimator|foreman)\b",
    re.I,
)

# Only write a DM whose title scores at/above this. The floor == the founder/CEO
# fallback tier (80): qualifies ONLY the head of sales (85-100) or, failing that,
# the founder/CEO/owner (80). Everything else scores 0 → row left blank
# (precision over recall: a wrong/irrelevant contact is worse than none).
MIN_DM_SCORE = 80


def title_score(title):
    """Encodes the rule: the person in charge of sales for the WHOLE company first,
    founder/CEO only as a fallback, nothing else.
      85-100  = sales leadership (CRO / VP Sales / Head of Sales / Sales Director /
                Sales Manager / sales-owning Partner) — all rank ABOVE the founder
      80      = founder / CEO / President / Owner — FALLBACK when no sales leader
      0       = everyone else: IC reps (AE/SDR/BDR), HR, IT, marketing, ops, support
    pick_dm takes the max, so a real sales leader always beats the founder fallback."""
    t = (title or "").lower()
    # --- the person in charge of sales for the whole company (all > founder) ---
    if re.search(r"\b(cro|chief revenue officer)\b", t):
        return 100
    if re.search(r"\b(svp|evp|vp|vice president).{0,18}(sales|revenue|commercial|business development|bd)\b", t) or \
       re.search(r"\b(sales|revenue|commercial).{0,18}\b(svp|evp|vp|vice president)\b", t):
        return 98
    if re.search(r"head of (sales|revenue|commercial|business development|bd)", t):
        return 96
    if re.search(r"(sales|revenue|commercial|business development) director|"
                 r"director of (sales|revenue|commercial|business development)", t):
        return 94
    if re.search(r"(chief|vp|head|director).{0,18}business development", t):
        return 92
    if re.search(r"(national|regional|area|territory )?sales manager\b|sales lead\b|sales & marketing", t):
        return 90
    if re.search(r"\bsales\b|business development", t) and not DISQUALIFY.search(t):
        return 85   # generic sales role (e.g. "Sales/Partner", "Sales & Marketing")
    # --- fallback: founder / owner / chief exec only when no sales leader exists.
    #     Excludes "vice president" (a non-sales VP) and role-ownership artifacts like
    #     "Product/Application Owner", "Partner Manager", "Channel Partner" — those are
    #     job functions, not company ownership. ---
    fake_owner_partner = re.search(
        r"\b(product|application|app|process|program|service|technical|account|data|portfolio|scrum|story|risk|capability)\s+owner\b"
        r"|\bpartner\s+(manager|success|account|enablement|development)\b|\bchannel\s+partner\b|\bpartnership", t)
    real_owner_partner = (not fake_owner_partner) and re.search(r"\b(owner|partner)\b", t)
    if re.search(r"\b(founder|co-?founder|ceo|chief executive|managing director|managing partner)\b", t) \
       or re.search(r"(?<!vice )(?<!vice-)\bpresident\b", t) \
       or real_owner_partner:
        return 80
    return 0        # IC reps, bare VPs, HR, IT, marketing, support, fake "owners" → not a target


def pick_dm(people):
    """Choose the best-fit person above the buyer floor. Returns dict or None."""
    best, best_score = None, -1
    for p in people:
        prof = p.get("profile", {}) or {}
        title = prof.get("title") or prof.get("headline") or ""
        s = title_score(title)
        if s > best_score:
            best_score, best = s, p
    if not best or best_score < MIN_DM_SCORE:
        return None
    prof = best.get("profile", {}) or {}
    link = best.get("link", {}) or {}
    return {
        "ark_id": (best.get("id") or "").strip(),
        "first": (prof.get("first_name") or "").strip(),
        "last": (prof.get("last_name") or "").strip(),
        "full": (prof.get("full_name") or "").strip(),
        "title": (prof.get("title") or prof.get("headline") or "").strip(),
        "linkedin": (link.get("linkedin") or "").strip(),
        "score": best_score,
    }


# ---- Email resolution: AI Ark → AnyMailFinder person → AnyMailFinder DM --------
# Every tier accepts ONLY valid emails (never risky/invalid). See [[feedback_anymailfinder_valid_only]].

def _amf_post(path, body):
    """POST to AnyMailFinder. Returns parsed JSON dict or None (4xx not-found = None)."""
    if not ANYMAIL_KEY:
        return None
    try:
        resp = requests.post(
            f"https://api.anymailfinder.com/v5.1/{path}",
            headers={"Authorization": ANYMAIL_KEY, "Content-Type": "application/json"},
            json=body, timeout=180,
        )
        if resp.status_code != 200:  # 451/4xx = not found, not an error to raise on
            return None
        return resp.json()
    except Exception as e:
        print(f"    [!] AnyMailFinder {path} failed: {e}")
        return None


def amf_person_email(full_name, first, last, domain, company_name):
    """AnyMailFinder person endpoint → valid email or ''."""
    if not (full_name or (first and last)) or not (domain or company_name):
        return ""
    body = {}
    if full_name:
        body["full_name"] = full_name
    if first:
        body["first_name"] = first
    if last:
        body["last_name"] = last
    if domain:
        body["domain"] = domain
    if company_name:
        body["company_name"] = company_name
    data = _amf_post("find-email/person", body)
    if data and data.get("email") and data.get("email_status") == "valid":
        return data["email"]
    return ""


def amf_decision_maker(domain, company_name, category):
    """AnyMailFinder decision-maker endpoint → dict with the found person + valid email,
    or None. This may surface a DIFFERENT person than AI Ark identified, so we return
    that person's details to keep the row's name↔email consistent."""
    if not (domain or company_name):
        return None
    body = {"decision_maker_category": [category]}
    if domain:
        body["domain"] = domain
    if company_name:
        body["company_name"] = company_name
    data = _amf_post("find-email/decision-maker", body)
    if data and data.get("email") and data.get("email_status") == "valid":
        return {
            "email": data["email"],
            "full": (data.get("person_full_name") or "").strip(),
            "first": (data.get("person_first_name") or "").strip(),
            "last": (data.get("person_last_name") or "").strip(),
            "title": (data.get("person_job_title") or "").strip(),
            "linkedin": (data.get("person_linkedin_url") or "").strip(),
        }
    return None


def resolve_email(dm, domain, company_name, category=None):
    """Per-DM email waterfall: AI Ark → AnyMailFinder person → AnyMailFinder decision-maker.
    Returns (email, source, override_person_or_None); override is set only when the
    decision-maker tier supplies a DIFFERENT named contact (so name↔email stay consistent).
    `category` drives the decision-maker tier ('sales' or 'ceo'); defaults from title score."""
    if category is None:
        category = "sales" if dm["score"] >= 85 else "ceo"
    # Tier 1 — AI Ark verified email for the identified DM (by id)
    e = ark_export_email(dm.get("ark_id"))
    if e:
        return e, "ai-ark", None
    # Tier 2 — AnyMailFinder person (same DM, by name + domain)
    e = amf_person_email(dm["full"], dm["first"], dm["last"], domain, company_name)
    if e:
        return e, "amf-person", None
    # Tier 3 — AnyMailFinder decision-maker by category
    res = amf_decision_maker(domain, company_name, category)
    if res:
        override = res if res["full"] else None  # keep AI Ark name if endpoint returned none
        return res["email"], "amf-dm", override
    return "", "", None


def merge_override(dm, override):
    """Replace dm's identity with a tier-3 decision-maker person, keeping AI Ark's
    title/linkedin when the endpoint didn't supply them."""
    if not override:
        return dm
    return {**dm,
            "full": override["full"], "first": override["first"], "last": override["last"],
            "title": override["title"] or dm["title"],
            "linkedin": override["linkedin"] or dm["linkedin"]}


# ---- Google Sheets -----------------------------------------------------------

def get_sheet_id_from_url(url):
    p = urlparse(url)
    if "docs.google.com" in p.netloc:
        parts = p.path.split("/")
        if "d" in parts:
            return parts[parts.index("d") + 1]
    return url


def get_service():
    with open(TOKEN_PATH) as f:
        td = json.load(f)
    creds = Credentials(
        token=td["token"], refresh_token=td["refresh_token"],
        token_uri=td["token_uri"], client_id=td["client_id"],
        client_secret=td["client_secret"],
        scopes=td.get("scopes", ["https://www.googleapis.com/auth/spreadsheets"]),
    )
    if creds.expired:
        creds.refresh(Request())
        td["token"] = creds.token
        with open(TOKEN_PATH, "w") as f:
            json.dump(td, f)
    return build("sheets", "v4", credentials=creds)


def col_letter(idx):
    result = ""
    idx += 1
    while idx:
        idx, rem = divmod(idx - 1, 26)
        result = chr(65 + rem) + result
    return result


def normalize_domain(s):
    """messy col-L value → bare host (e.g. 'http://www.x.com/' → 'x.com'). '' if not domain-like."""
    if not s:
        return ""
    s = s.strip()
    if "://" not in s:
        s = "http://" + s
    host = urlparse(s).netloc.lower().split(":")[0]
    if host.startswith("www."):
        host = host[4:]
    return host if "." in host else ""


def flush(svc, sheet_id, updates):
    """Batch-write staged cell updates with 429/503 backoff."""
    if not updates:
        return
    for attempt in range(5):
        try:
            svc.spreadsheets().values().batchUpdate(
                spreadsheetId=sheet_id,
                body={"valueInputOption": "RAW", "data": updates},
            ).execute()
            return
        except Exception as e:
            code = getattr(getattr(e, "resp", None), "status", None)
            if code in (429, 500, 503) and attempt < 4:
                wait = 2 ** attempt
                print(f"    [!] Sheets {code}, retrying in {wait}s")
                time.sleep(wait)
                continue
            print(f"    [!] Sheets write failed: {e}")
            return


def main():
    global ARK_URL
    ap = argparse.ArgumentParser(description="Find decision-makers + emails → cols T-Y")
    ap.add_argument("--sheet_url", default=DEFAULT_SHEET)
    ap.add_argument("--limit", type=int, default=0, help="Max companies to process (0 = all)")
    ap.add_argument("--apply", action="store_true", help="Spend on APIs + write to sheet. Default: dry run.")
    ap.add_argument("--force", action="store_true", help="Redo rows that already have a DM Name (col T)")
    args = ap.parse_args()

    ARK_URL = ark_endpoint()
    if not ANYMAIL_KEY:
        print("ERROR: ANYMAILFINDER_API_KEY not set in .env")
        return

    mode = "LIVE" if args.apply else "DRY RUN"
    print(f"=== Find Decision-Makers ({mode}) ===\n")

    svc = get_service()
    sheet_id = get_sheet_id_from_url(args.sheet_url)

    rows = svc.spreadsheets().values().get(
        spreadsheetId=sheet_id, range=f"{TAB_NAME}!A2:Y50000"
    ).execute().get("values", [])
    print(f"Total rows: {len(rows)}")

    # Build worklist: rows needing a DM
    work = []
    skipped_done = 0
    for i, row in enumerate(rows):
        sheet_row = i + 2
        comp = (row[COL_COMPANY] if len(row) > COL_COMPANY else "").strip()
        if not comp:
            continue
        existing_dm = (row[COL_DM_NAME] if len(row) > COL_DM_NAME else "").strip()
        if existing_dm and not args.force:
            skipped_done += 1
            continue
        domain = normalize_domain(row[COL_WEBSITE] if len(row) > COL_WEBSITE else "")
        work.append({"row": sheet_row, "company": comp, "domain": domain})

    if args.limit:
        work = work[:args.limit]

    by_domain = sum(1 for w in work if w["domain"])
    by_name = len(work) - by_domain
    print(f"Already have a DM (skipped): {skipped_done}")
    print(f"Companies to process: {len(work)}  ({by_domain} by domain, {by_name} by name only)")
    if not work:
        print("Nothing to do.")
        return

    if not args.apply:
        print(f"\nEstimated AI Ark spend (0.5 credit per profile returned):")
        print(f"  ~{0.5*len(work):.0f}-{0.5*SIZE*len(work):.0f} credits for {len(work)} companies "
              f"(tier-1 sales-leader call, size={SIZE}; founder-fallback only when empty).")
        print(f"  Companies with no match return empty = 0 credits. Re-runs on owned profiles = free.")
        print(f"AnyMailFinder: up to {len(work)} lookups; only 'valid' emails accepted → col W.")
        print("Sample of companies we'd process (first 15):")
        for w in work[:15]:
            print(f"  {w['company']:42} | {w['domain'] or '(name-only)'}")
        print("\n[DRY RUN] No API calls made. Re-run with --apply (use --limit 10 first).")
        return

    # ---- live processing ----
    def process(w):
        dom = w["domain"] or None
        name = None if w["domain"] else w["company"]

        def find_founder():  # CEO / owner / president (no department filter)
            return pick_dm(ark_people_search(domain=dom, company_name=name,
                                             seniority=FOUNDER_SENIORITY, size=2))

        # Tier 1: the sales leader for the whole company (cheap — only leaders returned)
        sales_dm = pick_dm(ark_people_search(domain=dom, company_name=name,
                                             department="sales", seniority=LEADERSHIP_SENIORITY))
        if sales_dm:
            email, source, override = resolve_email(sales_dm, w["domain"], w["company"], category="sales")
            if email:
                return {**w, "dm": merge_override(sales_dm, override), "email": email,
                        "source": source, "switched": False}
            # Sales leader found but NO verified email → pivot to CEO/owner/president
            ceo_dm = find_founder()
            if ceo_dm:
                email, source, override = resolve_email(ceo_dm, w["domain"], w["company"], category="ceo")
                if email:
                    return {**w, "dm": merge_override(ceo_dm, override), "email": email,
                            "source": source, "switched": True}
            # Neither yielded an email → keep the (priority) sales leader, email blank
            return {**w, "dm": sales_dm, "email": "", "source": "", "switched": False}

        # No sales leader at all → founder/CEO fallback
        ceo_dm = find_founder()
        if not ceo_dm:
            return {**w, "dm": None, "email": "", "source": "", "switched": False}
        email, source, override = resolve_email(ceo_dm, w["domain"], w["company"], category="ceo")
        return {**w, "dm": merge_override(ceo_dm, override), "email": email,
                "source": source, "switched": False}

    updates = []
    n_dm = n_email = n_none = 0
    src_counts = {"ai-ark": 0, "amf-person": 0, "amf-dm": 0}
    processed = 0

    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futures = {ex.submit(process, w): w for w in work}
        for fut in as_completed(futures):
            res = fut.result()
            processed += 1
            r = res["row"]
            dm = res["dm"]
            # Stage cell writes. Non-empty values always written (append-only, never
            # clobbers good data). Empty values written ONLY on --force, so a re-run
            # reconciles rows whose DM no longer qualifies (clears stale picks).
            fields = [
                (COL_DM_NAME, dm["full"] if dm else ""),
                (COL_DM_TITLE, dm["title"] if dm else ""),
                (COL_LINKEDIN, dm["linkedin"] if dm else ""),
                (COL_EMAIL, res["email"] or ""),
                (COL_FIRST, dm["first"] if dm else ""),
                (COL_LAST, dm["last"] if dm else ""),
            ]
            for col, val in fields:
                if val or args.force:
                    updates.append({"range": f"{TAB_NAME}!{col_letter(col)}{r}", "values": [[val]]})

            if not dm:
                n_none += 1
                print(f"  [{processed}/{len(work)}] {res['company']:38} → no qualified DM")
            else:
                n_dm += 1
                switched = " (→CEO fallback)" if res.get("switched") else ""
                if res["email"]:
                    n_email += 1
                    src_counts[res["source"]] = src_counts.get(res["source"], 0) + 1
                    tag = f" | {res['email']} [{res['source']}]{switched}"
                else:
                    tag = " | (no valid email)"
                print(f"  [{processed}/{len(work)}] {res['company']:38} → {dm['full']} | {dm['title'][:40]}{tag}")

            if len(updates) >= WRITE_BATCH * 4:
                flush(svc, sheet_id, updates)
                updates = []

    flush(svc, sheet_id, updates)

    print("\n=== Summary ===")
    print(f"Processed:        {len(work)}")
    print(f"  DM found:       {n_dm}")
    print(f"  + valid email:  {n_email}")
    print(f"      via AI Ark:        {src_counts['ai-ark']}")
    print(f"      via AMF person:    {src_counts['amf-person']}")
    print(f"      via AMF dec.maker: {src_counts['amf-dm']}")
    print(f"  no DM found:    {n_none}")
    if n_dm:
        print(f"Email match rate (of DMs found): {n_email}/{n_dm} = {100*n_email/n_dm:.0f}%")


if __name__ == "__main__":
    main()
