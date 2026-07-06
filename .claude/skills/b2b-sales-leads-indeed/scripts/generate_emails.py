"""
Phase 4: Generate the cold-email body (col Z) for each lead that has a DM + valid email.

One Azure GPT-4.1 call per lead returns three personalization fields:
  - company_casual : casual company name for the greeting (casualize-names rules: drop
                     'The'/legal suffixes/generic filler, keep core brand, no ALL CAPS).
                     [The standalone casualize-names skill uses the expired ANTHROPIC_API_KEY,
                      so its rules are applied here via the working Azure LLM.]
  - role           : a clean, natural SALES role title from the (messy) Indeed job title,
                     always sales-context; falls back to the col-AB role type or 'sales rep'.
  - icp            : the buyer persona the new rep sells to, from the JOB DESCRIPTION (col J).
                     Low-confidence/filler → safe fallback 'your ideal buyers'.

Then renders the locked template. Test mode (default, no --apply) prints a sample; --apply
writes body→Z, ICP→AD, subject→AE. --limit caps leads (works with --apply for an in-sheet sample).

Usage:
  python3 generate_emails.py --limit 12               # console sample, no writes
  python3 generate_emails.py --apply --limit 20       # write a 20-lead sample to the sheet
  python3 generate_emails.py --apply                  # write all valid-email leads
"""

import os
import re
import json
import time
import random
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse
from dotenv import load_dotenv
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from openai import AzureOpenAI

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "..", "..", ".."))
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))
TOKEN_PATH = os.path.join(PROJECT_ROOT, "token.json")

AZURE_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_API_KEY = os.getenv("AZURE_OPENAI_API_KEY")
AZURE_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION", "2024-10-21")
AZURE_DEPLOYMENT = os.getenv("AZURE_OPENAI_DEPLOYMENT_FAST", "gpt-4.1")
_azure = AzureOpenAI(azure_endpoint=AZURE_ENDPOINT, api_key=AZURE_API_KEY,
                     api_version=AZURE_API_VERSION) if AZURE_ENDPOINT else None

DEFAULT_SHEET = "https://docs.google.com/spreadsheets/d/1g2X-qSv-Y3A5A8Z83cftAD-9Af5PO0XQJTVjH6yq5PQ/edit"
TAB_NAME = "Leads"
COL_JOBTITLE = 1    # B
COL_JOBDESC = 9     # J  (sales posting — names who the rep sells to)
COL_COMPANY = 10    # K
COL_DESC = 15       # P  (company description — usually empty)
COL_DM_NAME = 19    # T
COL_EMAIL = 22      # W
COL_FIRST = 23      # X
COL_BODY = 25       # Z
COL_ROLETYPE = 27   # AB (role-type bucket from classify step: Outside Sales / SDR / Sales)
COL_ICP = 29        # AD (QA column for derived ICP)
COL_SUBJECT = 30    # AE (subject line, for the Instantly import)
LLM_WORKERS = 4     # Azure rate-limits bursts; keep modest + retry on 429
ICP_FALLBACK = "your ideal buyers"

# Reliable role fallback from the already-classified role-type bucket (col AB).
ROLE_MAP = {
    "outside sales": "outside sales rep", "inside sales": "inside sales rep",
    "sdr": "sales development rep", "bdr": "business development rep",
    "account executive": "account executive", "sales": "sales rep",
}

# Backstop: an ICP built ENTIRELY from generic words (no concrete industry/role) → fallback.
GENERIC_WORDS = {
    "customers", "customer", "clients", "client", "accounts", "account", "businesses",
    "business", "organizations", "organization", "buyers", "buyer", "companies", "company",
    "prospects", "prospect", "users", "user", "industries", "industry", "partners", "partner",
    "end", "commercial", "various", "multiple", "key", "b2b", "b2c", "new", "potential", "and",
    "other", "markets", "market", "sectors", "sector", "decision", "makers", "maker", "people",
    "professionals", "professional", "leads", "verticals",
}


def is_filler(phrase):
    words = re.findall(r"[a-z]+", (phrase or "").lower())
    return bool(words) and all(w in GENERIC_WORDS for w in words)


SEP_RE = re.compile(r",| - | – | — | \| | / ")
LEGAL_RE = re.compile(
    r"\b(inc|incorporated|llc|l\.l\.c|corp|corporation|co|ltd|limited|plc|lp|llp|pllc|gmbh|company)\b\.?$",
    re.I)
GENERIC_TAIL = {
    "group", "solutions", "services", "service", "realty", "holdings", "industries",
    "distributing", "distribution", "associates", "enterprises", "international", "worldwide",
    "global", "systems", "technologies", "corporation", "products", "brands", "company",
}


def tidy_company(name):
    """Deterministic casualization backstop (runs on every result, LLM or fallback):
    cut at first comma/dash/pipe, drop a leading 'The', strip trailing legal suffixes,
    drop trailing generic words. Casing is left as-is (the LLM/recase handles that)."""
    name = (name or "").strip()
    if not name:
        return name
    name = SEP_RE.split(name)[0].strip()
    name = re.sub(r"^the\s+", "", name, flags=re.I).strip()
    prev = None
    while prev != name:                       # peel repeated legal suffixes ("Co., Inc.")
        prev = name
        name = LEGAL_RE.sub("", name).strip(" .,&-")
    toks = name.split()
    while len(toks) > 1 and toks[-1].lower().strip(".,&") in GENERIC_TAIL:
        toks.pop()
    return " ".join(toks).strip() or name


def recase(name):
    """Title-case fully-shouting names; restore true acronyms."""
    letters = [c for c in name if c.isalpha()]
    if letters and all(c.isupper() for c in letters):
        name = name.title()
    return re.sub(r"\b(Llc|Usa|Hvac|Rv)\b", lambda m: m.group(0).upper(), name)


def clean_company(name):
    """No-LLM fallback: recase shouting names, then deterministic tidy."""
    return tidy_company(recase((name or "").strip()))


def clean_role(job_title):
    """Fallback role cleanup from a raw job title."""
    if not job_title:
        return "sales rep"
    role = re.split(r"[|(/–—:]", job_title)[0]          # NOTE: no '-' split (breaks 'Multi-Family')
    role = re.sub(r"\s+", " ", role).strip().lower()
    return role or "sales rep"


FIELDS_SYSTEM = (
    "You prepare personalization fields for a B2B cold email. You get a company name and a "
    "SALES job posting. Return ONLY a JSON object with exactly these keys:\n"
    '"company_casual": the company\'s casual name for an email greeting. Drop a leading "The", '
    "legal suffixes (LLC, Inc, Corp, Ltd, Co), and generic filler (Group, Solutions, Services, "
    "Realty, Holdings, Industries, Distributing, Associates). Keep the core brand, nicely "
    "capitalized, never ALL CAPS. "
    "Shorten to the 1-2 word core brand; drop trailing descriptor lists and 'and X' clauses. "
    "Examples: 'HORIZON FOREST PRODUCTS'->'Horizon Forest', 'Cothrons Safe & Lock'->'Cothrons', "
    "'New Hampshire Hydraulics, Inc.'->'New Hampshire Hydraulics', 'AAAG LLC'->'AAAG', "
    "'Allied Flooring, Paint, and Design'->'Allied Flooring', "
    "'Crown Uniform and Linen Service'->'Crown Uniform'.\n"
    '"role": a short, natural SALES role title for the rep being hired (2-3 words, lowercase, '
    "singular). ALWAYS sales-oriented; clean up messy or mislabeled postings. "
    "Examples: 'Multi-Family Outside Sales Rep - Cabinet Div'->'outside sales rep', "
    "'Saddle Expert / Sales Representative'->'sales rep', 'Crown Uniform Sales Opportunity'->"
    "'sales rep', 'Mitsubishi Product Specialist'->'sales rep', 'Sales Engineer'->'sales engineer', "
    "'Territory Sales Executive'->'territory sales rep'. If it isn't a clear specific sales title, "
    "use 'sales rep'.\n"
    '"icp": who the new rep will SELL TO (customer/buyer persona), a plural noun phrase fitting '
    "'in front of qualified ___ at scale'. Use the posting's own description of the target "
    "customers/market. Examples: 'flooring contractors', 'auto body repair shops', "
    "'facility managers', 'foodservice operators', 'automotive dealers'. Do NOT output vague "
    "fillers (customers, clients, accounts, businesses, organizations). If the posting does not "
    "indicate who they sell to, use 'UNKNOWN'.\n"
    "Return only the JSON object, no commentary."
)


def derive_fields(company, role_type, job_title, job_desc, company_desc=""):
    """One Azure call → (company_casual, role, icp, icp_ok), with per-field fallbacks."""
    fb_company = clean_company(company)
    fb_role = ROLE_MAP.get((role_type or "").strip().lower()) or clean_role(job_title)
    if _azure is None or not (job_desc or company_desc):
        return fb_company, fb_role, ICP_FALLBACK, False

    prompt = (f"Company name: {company}\nRole-type bucket: {role_type or '(unknown)'}\n"
              f"Job title: {job_title}\n\nJob posting:\n{(job_desc or '')[:2000]}\n")
    if company_desc:
        prompt += f"\nAbout the employer: {company_desc[:300]}\n"
    prompt += "\nReturn the JSON object."

    for attempt in range(5):
        try:
            resp = _azure.chat.completions.create(
                model=AZURE_DEPLOYMENT, max_tokens=120, temperature=0,
                response_format={"type": "json_object"},
                messages=[{"role": "system", "content": FIELDS_SYSTEM},
                          {"role": "user", "content": prompt}],
            )
            raw = resp.choices[0].message.content or ""
            m = re.search(r"\{.*\}", raw, re.S)
            d = json.loads(m.group(0)) if m else {}

            cc = (d.get("company_casual") or "").strip()
            cc = tidy_company(cc) if cc else fb_company   # deterministic backstop on the LLM output
            role = (d.get("role") or "").strip().lower() or fb_role
            # enforce sales context on the role
            if not re.search(r"sales|business development|account exec", role):
                role = fb_role if re.search(r"sales|business development|account exec", fb_role) else "sales rep"

            icp = (d.get("icp") or "").strip().lower().strip(".\"'`")
            if not icp or "unknown" in icp or len(icp) > 60 or is_filler(icp):
                return cc, role, ICP_FALLBACK, False
            return cc, role, icp, True
        except Exception as e:
            msg = str(e)
            if "content_filter" in msg or "ResponsibleAIPolicy" in msg:
                return fb_company, fb_role, ICP_FALLBACK, False
            if attempt < 4 and ("429" in msg or "Too Many Requests" in msg or "timeout" in msg.lower()):
                time.sleep(min(20, 3 * (attempt + 1)) + random.uniform(0, 2))
                continue
            if attempt < 4:
                time.sleep(2 ** attempt)
                continue
            print(f"    [!] fields LLM error for {company}: {msg[:120]}")
            return fb_company, fb_role, ICP_FALLBACK, False
    return fb_company, fb_role, ICP_FALLBACK, False


def article(word):
    return "an" if word[:1].lower() in "aeiou" else "a"


# Spintax baked per-lead (random variant chosen at generation time). We resolve it here
# rather than leaving literal {a|b} for Instantly, because Instantly does NOT reliably
# resolve spintax inside a merged custom field — and the body is pushed as a personalization
# field. Per-lead randomization spreads the 557 sends lexically (deliverability fingerprint).
_SAW = ["Saw", "Noticed", "Spotted"]
_ASSUME = ["so I'm assuming you're", "so I'm guessing you're", "which likely means you're"]
_WHEN = ["for Q3", "this quarter", "heading into Q3"]
_PUT = ["put", "get"]
_FRONT = ["straight in front of", "right in front of"]
_WALK = ["walk into", "start with"]
_CTA = ["Worth a quick chat?", "Worth a quick chat to see if it fits?", "Open to a quick chat?"]
_SUBJ = ["your {r} hire"]   # locked framework (no fake "re:")


def render_email(first, company_casual, role, icp):
    company = company_casual
    poss = company + ("'" if company[-1:].lower() == "s" else "'s")
    subject = random.choice(_SUBJ).format(r=role)
    body = (
        f"Hi {first or 'there'},\n\n"
        f"{random.choice(_SAW)} {poss} hiring for {article(role)} {role}, "
        f"{random.choice(_ASSUME)} pushing hard on pipeline {random.choice(_WHEN)}.\n\n"
        f"I can {random.choice(_PUT)} your new rep {random.choice(_FRONT)} qualified {icp} at scale, "
        f"so they {random.choice(_WALK)} real pipeline instead of cold-dialing their whole first quarter.\n\n"
        f"{random.choice(_CTA)}\n\n"
        f"Jude - NEXAM AI"
    )
    return subject, body


# ---- Google Sheets ----
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
        token=td["token"], refresh_token=td["refresh_token"], token_uri=td["token_uri"],
        client_id=td["client_id"], client_secret=td["client_secret"],
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


def ensure_columns(svc, sheet_id, min_cols):
    """Expand the worksheet grid to >= min_cols columns so writes past the current edge
    (AD/AE) don't fail with 'exceeds grid limits'."""
    meta = svc.spreadsheets().get(spreadsheetId=sheet_id, fields="sheets.properties").execute()
    for sh in meta.get("sheets", []):
        props = sh["properties"]
        if props.get("title") == TAB_NAME:
            cols = props.get("gridProperties", {}).get("columnCount", 0)
            if cols < min_cols:
                svc.spreadsheets().batchUpdate(
                    spreadsheetId=sheet_id,
                    body={"requests": [{"updateSheetProperties": {
                        "properties": {"sheetId": props["sheetId"],
                                       "gridProperties": {"columnCount": min_cols}},
                        "fields": "gridProperties.columnCount"}}]},
                ).execute()
            return


def main():
    ap = argparse.ArgumentParser(description="Generate cold-email bodies → col Z")
    ap.add_argument("--sheet_url", default=DEFAULT_SHEET)
    ap.add_argument("--limit", type=int, default=0,
                    help="Cap leads (0=all). Works with --apply, e.g. --apply --limit 20.")
    ap.add_argument("--apply", action="store_true", help="Write to sheet. Default: console test print.")
    ap.add_argument("--force", action="store_true", help="Regenerate rows that already have a body")
    args = ap.parse_args()

    svc = get_service()
    sheet_id = get_sheet_id_from_url(args.sheet_url)
    rows = svc.spreadsheets().values().get(
        spreadsheetId=sheet_id, range=f"{TAB_NAME}!A2:AE50000"
    ).execute().get("values", [])

    leads = []
    for i, row in enumerate(rows):
        def cell(c):
            return (row[c] if len(row) > c else "").strip()
        if not cell(COL_DM_NAME) or not cell(COL_EMAIL):
            continue
        if cell(COL_BODY) and not args.force and args.apply:
            continue
        leads.append({
            "row": i + 2, "company": cell(COL_COMPANY), "job_title": cell(COL_JOBTITLE),
            "jobdesc": cell(COL_JOBDESC), "desc": cell(COL_DESC), "first": cell(COL_FIRST),
            "role_type": cell(COL_ROLETYPE), "icp_web": cell(COL_ICP),  # persona from derive_icp_web
        })

    if args.limit:
        leads = leads[:args.limit]
    elif not args.apply:
        leads = leads[:12]
    print(f"{'TEST (no writes)' if not args.apply else 'LIVE (writing to sheet)'} — {len(leads)} leads\n")
    if not leads:
        print("No leads with DM + valid email to generate.")
        return

    def work(ld):
        # ICP/persona comes from col AD (derive_icp_web); LLM only does company + role.
        cc, role, _icp, _ok = derive_fields(ld["company"], ld["role_type"], ld["job_title"],
                                            ld["jobdesc"], ld["desc"])
        icp = ld["icp_web"].strip() or "buyers"
        ok = icp != "buyers"
        subj, body = render_email(ld["first"], cc, role, icp)
        return {**ld, "company_casual": cc, "role": role, "icp": icp, "ok": ok,
                "subject": subj, "body": body}

    results = []
    with ThreadPoolExecutor(max_workers=LLM_WORKERS) as ex:
        for fut in as_completed([ex.submit(work, ld) for ld in leads]):
            results.append(fut.result())
    results.sort(key=lambda r: r["row"])

    if not args.apply:
        for r in results:
            flag = "" if r["ok"] else "  [icp-fallback]"
            print(f"── {r['company_casual']}  (role: {r['role']})   "
                  f"[raw: {r['company'][:24]} | {r['job_title'][:34]}]")
            print(f"   ICP → qualified {r['icp']}{flag}")
            print()
        print("=== two full samples ===\n")
        for r in results[:2]:
            print(f"Subject: {r['subject']}\n\n{r['body']}\n{'-'*50}")
        n_ok = sum(1 for r in results if r["ok"])
        print(f"\nICP derived: {n_ok}/{len(results)} | fallback: {len(results)-n_ok}")
        print("[TEST] No sheet writes. Re-run with --apply (use --limit for a sample).")
        return

    ensure_columns(svc, sheet_id, COL_SUBJECT + 1)  # grid must reach col AE
    # col AD (ICP) is owned by derive_icp_web — don't overwrite it here; only write body + subject
    updates = [{"range": f"{TAB_NAME}!{col_letter(COL_SUBJECT)}1", "values": [["Subject"]]}]
    for r in results:
        updates.append({"range": f"{TAB_NAME}!{col_letter(COL_BODY)}{r['row']}", "values": [[r["body"]]]})
        updates.append({"range": f"{TAB_NAME}!{col_letter(COL_SUBJECT)}{r['row']}", "values": [[r["subject"]]]})
    for i in range(0, len(updates), 2000):
        svc.spreadsheets().values().batchUpdate(
            spreadsheetId=sheet_id, body={"valueInputOption": "RAW", "data": updates[i:i + 2000]}
        ).execute()
    n_ok = sum(1 for r in results if r["ok"])
    print(f"Wrote {len(results)} emails → col Z (body), AE (subject), AD (ICP).")
    print(f"ICP derived: {n_ok}/{len(results)} | fallback: {len(results)-n_ok}")


if __name__ == "__main__":
    main()
