"""
Phase 4a: Derive each company's buyer PERSONA (ICP) from its WEBSITE → col AD.

Why website, not job description: sales postings describe duties/comp, not who the
company sells to — that made JD-derived ICPs confidently wrong. The homepage reliably
states what they sell and to which accounts, so we ground the persona in real facts.

Per lead with a domain:
  1. curl the homepage (+ /about,/industries if thin) → cleaned text. (curl, not requests:
     macOS LibreSSL fails TLS on some hosts.)
  2. Azure GPT-4.1 extracts {what_they_sell, accounts_served} from the text, then infers
     buyer_persona (the ROLE/person who buys) + confidence — based ONLY on the page.
  3. Gate: confidence 'high' + a real persona → write it; otherwise write 'buyers'
     (renders as "qualified buyers"). Wrong is worse than generic, so bias to 'buyers'.

Writes the persona to col AD ('ICP'). generate_emails.py reads col AD for {ICP}.

Usage:
  python3 derive_icp_web.py --limit 15            # SPREAD sample across all leads, no writes
  python3 derive_icp_web.py --apply               # derive + write col AD for all leads
  python3 derive_icp_web.py --apply --force       # redo rows that already have an ICP
"""

import os
import re
import json
import time
import random
import argparse
import subprocess
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed
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
COL_COMPANY = 10    # K
COL_WEBSITE = 11    # L
COL_DM_NAME = 19    # T
COL_EMAIL = 22      # W
COL_ICP = 29        # AD
WORKERS = 6
ICP_FALLBACK = "buyers"   # renders as "qualified buyers"

GENERIC_WORDS = {
    "customers", "customer", "clients", "client", "accounts", "account", "businesses",
    "business", "organizations", "organization", "buyers", "buyer", "companies", "company",
    "prospects", "users", "industries", "industry", "partners", "end", "commercial", "various",
    "multiple", "key", "b2b", "b2c", "new", "and", "other", "markets", "market", "sectors",
    "people", "professionals", "leads", "verticals", "consumers", "consumer",
}


def is_filler(phrase):
    words = re.findall(r"[a-z]+", (phrase or "").lower())
    return bool(words) and all(w in GENERIC_WORDS for w in words)


# ---- website fetch (curl) ----
def normalize_url(domain):
    d = (domain or "").strip()
    if not d:
        return ""
    if "://" not in d:
        d = "https://" + d
    host = (urlparse(d).netloc or urlparse(d).path).split("/")[0]
    return "https://" + host if host else ""


def curl_get(url):
    try:
        p = subprocess.run(
            ["curl", "-sL", "--max-time", "15", "-A",
             "Mozilla/5.0 (compatible; NEXAM-ICP/1.0)", url],
            capture_output=True, text=True, timeout=22,
        )
        return p.stdout if p.returncode == 0 else ""
    except Exception:
        return ""


def strip_html(html):
    html = re.sub(r"(?is)<(script|style|noscript|svg|head).*?</\1>", " ", html)
    title = ""
    m = re.search(r"(?is)<title>(.*?)</title>", html)
    if m:
        title = re.sub(r"\s+", " ", m.group(1)).strip()
    desc = ""
    m = re.search(r'(?is)<meta[^>]+name=["\']description["\'][^>]+content=["\'](.*?)["\']', html) or \
        re.search(r'(?is)<meta[^>]+content=["\'](.*?)["\'][^>]+name=["\']description["\']', html)
    if m:
        desc = re.sub(r"\s+", " ", m.group(1)).strip()
    body = re.sub(r"(?is)<[^>]+>", " ", html)
    body = re.sub(r"&[a-z#0-9]+;", " ", body)
    body = re.sub(r"\s+", " ", body).strip()
    return f"TITLE: {title}\nDESC: {desc}\nTEXT: {body}"[:3800]


def get_site_text(domain):
    base = normalize_url(domain)
    if not base:
        return ""
    text = strip_html(curl_get(base) or "")
    meaningful = re.sub(r"TITLE:|DESC:|TEXT:", "", text).strip()
    if len(meaningful) < 200:  # thin homepage → try common sub-pages
        for path in ("/about", "/about-us", "/industries", "/markets", "/solutions"):
            t2 = strip_html(curl_get(base.rstrip("/") + path) or "")
            if len(t2) > len(text):
                text = t2
            if len(re.sub(r"TITLE:|DESC:|TEXT:", "", text)) > 600:
                break
    return text


# ---- persona derivation ----
WEB_SYSTEM = (
    "You are given text scraped from a company's website. Work out who that company's "
    "sales reps SELL TO and return a JSON object:\n"
    '{"what_they_sell": str, "accounts_served": str, "buyer_persona": str, "confidence": "high"|"low"}\n'
    "- what_they_sell / accounts_served: based ONLY on the website text. If the text does not "
    "make the business clear, set confidence to 'low'.\n"
    "- buyer_persona: the ROLE/PERSON at those accounts who would actually buy — a plural noun "
    "phrase (2-5 words) fitting 'put your reps in front of qualified ___ at scale'. Name a "
    "person/role (owner, manager, director, buyer), NOT just the company type and NOT the "
    "employer's own staff. Examples: 'auto body shop owners', 'facility managers', "
    "'multifamily property managers', 'hospital procurement directors', 'restaurant operators', "
    "'plant maintenance managers'.\n"
    "- confidence: 'high' ONLY if the website clearly shows what they sell AND to whom. "
    "Otherwise 'low'. Never guess from the company name alone.\n"
    "Return only the JSON object."
)


def derive_persona(company, job_title, site_text):
    """Returns (persona, confident)."""
    if _azure is None or not site_text:
        return ICP_FALLBACK, False
    prompt = (f"Company: {company}\nThey are hiring: {job_title}\n\n"
              f"Website text:\n{site_text}\n\nReturn the JSON.")
    for attempt in range(5):
        try:
            resp = _azure.chat.completions.create(
                model=AZURE_DEPLOYMENT, max_tokens=160, temperature=0,
                response_format={"type": "json_object"},
                messages=[{"role": "system", "content": WEB_SYSTEM},
                          {"role": "user", "content": prompt}],
            )
            raw = resp.choices[0].message.content or ""
            m = re.search(r"\{.*\}", raw, re.S)
            d = json.loads(m.group(0)) if m else {}
            persona = (d.get("buyer_persona") or "").strip().lower().strip(".\"'`")
            conf = (d.get("confidence") or "").strip().lower()
            if conf != "high" or not persona or "unknown" in persona or len(persona) > 60 or is_filler(persona):
                return ICP_FALLBACK, False
            return persona, True
        except Exception as e:
            msg = str(e)
            if "content_filter" in msg or "ResponsibleAIPolicy" in msg:
                return ICP_FALLBACK, False
            if attempt < 4 and ("429" in msg or "Too Many Requests" in msg or "timeout" in msg.lower()):
                time.sleep(min(20, 3 * (attempt + 1)) + random.uniform(0, 2))
                continue
            if attempt < 4:
                time.sleep(2 ** attempt)
                continue
            return ICP_FALLBACK, False
    return ICP_FALLBACK, False


# ---- sheets ----
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


def sheet_id_from_url(url):
    return url.split("/d/")[1].split("/")[0] if "/d/" in url else url


def col_letter(idx):
    result = ""
    idx += 1
    while idx:
        idx, rem = divmod(idx - 1, 26)
        result = chr(65 + rem) + result
    return result


def ensure_columns(svc, sheet_id, min_cols):
    meta = svc.spreadsheets().get(spreadsheetId=sheet_id, fields="sheets.properties").execute()
    for sh in meta.get("sheets", []):
        props = sh["properties"]
        if props.get("title") == TAB_NAME:
            if props.get("gridProperties", {}).get("columnCount", 0) < min_cols:
                svc.spreadsheets().batchUpdate(
                    spreadsheetId=sheet_id,
                    body={"requests": [{"updateSheetProperties": {
                        "properties": {"sheetId": props["sheetId"],
                                       "gridProperties": {"columnCount": min_cols}},
                        "fields": "gridProperties.columnCount"}}]},
                ).execute()
            return


def main():
    ap = argparse.ArgumentParser(description="Derive buyer persona (ICP) from company websites → col AD")
    ap.add_argument("--sheet_url", default=DEFAULT_SHEET)
    ap.add_argument("--limit", type=int, default=15, help="Sample size for test mode (spread across all leads)")
    ap.add_argument("--apply", action="store_true", help="Write col AD. Default: test print (spread sample).")
    ap.add_argument("--force", action="store_true", help="Redo rows that already have an ICP in col AD")
    args = ap.parse_args()

    svc = get_service()
    sid = sheet_id_from_url(args.sheet_url)
    rows = svc.spreadsheets().values().get(
        spreadsheetId=sid, range=f"{TAB_NAME}!A2:AD50000"
    ).execute().get("values", [])

    leads = []
    for i, row in enumerate(rows):
        def c(j):
            return (row[j] if len(row) > j else "").strip()
        if not c(COL_DM_NAME) or not c(COL_EMAIL):
            continue
        if c(COL_ICP) and not args.force and args.apply:
            continue
        leads.append({"row": i + 2, "company": c(COL_COMPANY), "domain": c(COL_WEBSITE),
                      "job_title": c(COL_JOBTITLE)})

    if not args.apply:  # spread sample across the WHOLE list (not just the head)
        step = max(1, len(leads) // args.limit)
        leads = leads[::step][:args.limit]
    print(f"{'TEST (no writes)' if not args.apply else 'LIVE'} — {len(leads)} leads\n")
    if not leads:
        print("Nothing to do.")
        return

    def work(ld):
        site = get_site_text(ld["domain"])
        persona, ok = derive_persona(ld["company"], ld["job_title"], site)
        return {**ld, "persona": persona, "ok": ok, "had_site": bool(site)}

    results = []
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        for fut in as_completed([ex.submit(work, ld) for ld in leads]):
            results.append(fut.result())
    results.sort(key=lambda r: r["row"])

    if not args.apply:
        for r in results:
            tag = "" if r["ok"] else ("  [no-site→buyers]" if not r["had_site"] else "  [low-conf→buyers]")
            print(f"── {r['company'][:30]:32} {r['domain'][:26]:28} → qualified {r['persona']}{tag}")
        n_ok = sum(1 for r in results if r["ok"])
        print(f"\nPersona derived: {n_ok}/{len(results)} | fallback 'buyers': {len(results)-n_ok}")
        print("[TEST] No writes. Re-run with --apply.")
        return

    ensure_columns(svc, sid, COL_ICP + 1)
    updates = [{"range": f"{TAB_NAME}!{col_letter(COL_ICP)}1", "values": [["ICP"]]}]
    for r in results:
        updates.append({"range": f"{TAB_NAME}!{col_letter(COL_ICP)}{r['row']}", "values": [[r["persona"]]]})
    for j in range(0, len(updates), 2000):
        svc.spreadsheets().values().batchUpdate(
            spreadsheetId=sid, body={"valueInputOption": "RAW", "data": updates[j:j + 2000]}
        ).execute()
    n_ok = sum(1 for r in results if r["ok"])
    print(f"Wrote {len(results)} personas → col AD.")
    print(f"Persona derived: {n_ok}/{len(results)} | fallback 'buyers': {len(results)-n_ok}")


if __name__ == "__main__":
    main()
