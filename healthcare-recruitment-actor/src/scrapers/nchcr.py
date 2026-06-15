"""
NCHCR Job Board Scraper.

Scrapes the National Coalition of Healthcare Recruiters job board to build a
lead list of healthcare recruitment firms. For each job posting, the detail
page exposes the posting firm's company name, recruiter name, contact phone,
and recruiter email — and the firm website is derived from the email domain.

Flow:
  1. Load the job search results (direct URL, no session needed)
  2. Raise results-per-page, page through listings, collect one representative
     JobID per unique firm (the "Recruiter" column is the firm name)
  3. Visit one detail page per unique firm → company / recruiter / phone / email
  4. Derive website from the recruiter email domain

A few prolific firms own thousands of listings, so ~10,500 jobs collapse to a
few hundred unique firms. Detail visits scale with unique firms, not jobs.

Fields per record:
  company_name, recruiter_name, recruiter_email, website, company_domain,
  phone, state, city, specialty, sample_job_id, source, date_scraped
"""
from __future__ import annotations

import logging
import os
import re
import time
from datetime import datetime

from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

RESULTS_URL = (
    "https://nchcr.com/healthcare-job-opportunities"
    "?Keywords=&SearchType=And&JobType={job_type}"
)
DETAIL_URL = "https://nchcr.com/healthcare-job-opportunity-details?JobID={job_id}"

_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# Email domains that are personal/generic — keep the email, but don't treat as a website
_GENERIC_DOMAINS = {
    "gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "aol.com",
    "icloud.com", "protonmail.com", "msn.com", "live.com", "comcast.net",
    "att.net", "verizon.net", "me.com", "ymail.com", "nchcr.com",
}

# Listing rows that are placeholders / test entries, not real firms
_SKIP_FIRMS = {"recruiterbalm", "1a-organization test subject"}

_EMAIL_RE = re.compile(r"[\w.+\-]+@[\w\-]+\.[\w.\-]+", re.IGNORECASE)

# Legal/industry suffixes stripped when normalizing a firm name for dedup
_NORM_STRIP = re.compile(
    r"\b(inc|llc|ltd|corp|co|company|group|associates|partners|"
    r"staffing|recruiting|recruitment|search|solutions|services|"
    r"healthcare|health|medical|consulting)\b",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Listing page
# ---------------------------------------------------------------------------

def _results_table(soup: BeautifulSoup):
    """Return the job-results table (the one with the JobID sort link)."""
    for t in soup.find_all("table"):
        if t.find("a", href=re.compile("lbSortByJobID")):
            return t
    return None


def _parse_listing_rows(page) -> list[dict]:
    """Parse the current results page into row dicts."""
    soup = BeautifulSoup(page.content(), "lxml")
    table = _results_table(soup)
    if not table:
        return []

    rows = []
    for tr in table.find_all("tr")[1:]:  # skip header
        cells = [td.get_text(" ", strip=True) for td in tr.find_all("td")]
        if len(cells) < 8:
            continue
        job_id = cells[0].strip()
        firm = cells[7].strip()
        if not job_id or not firm:
            continue
        if firm.lower() in _SKIP_FIRMS:
            continue
        rows.append({
            "job_id":    job_id,
            "city":      cells[4].strip(),
            "state":     cells[5].strip(),
            "specialty": cells[6].strip(),
            "firm":      firm,
        })
    return rows


def _set_results_per_page(page, n: int) -> None:
    """Raise the results-per-page count to reduce pagination."""
    try:
        box = page.locator("#ContentPlaceHolder1_txtResultsPerPage_Top")
        go  = page.locator("#ContentPlaceHolder1_btnResultsPerPage_Top")
        if box.count() > 0:
            box.fill(str(n))
            go.click()
            page.wait_for_load_state("domcontentloaded", timeout=30000)
            time.sleep(3)
            log.info(f"  [NCHCR] Results per page → {n}")
    except Exception as e:
        log.warning(f"  [NCHCR] Could not set results-per-page: {e}")


def _first_job_id(page) -> str:
    rows = _parse_listing_rows(page)
    return rows[0]["job_id"] if rows else ""


def _next_page(page) -> bool:
    """
    Advance to the next results page via PostBack. Return False on last page.

    Note: after raising results-per-page, the *top* pager (`lbNext_Top`) stops
    advancing, but the *bottom* pager (`lbNext`) works reliably — use that.
    """
    before = _first_job_id(page)
    if not before:
        return False
    try:
        page.evaluate(
            "__doPostBack('ctl00$ContentPlaceHolder1$lbNext','')"
        )
    except Exception as e:
        log.warning(f"  [NCHCR] Pagination error: {e}")
        return False

    # A PostBack may not reset the load state, so poll until the first JobID
    # actually changes (the page has refreshed) rather than guessing a sleep.
    for _ in range(20):  # up to ~10s
        time.sleep(0.5)
        after = _first_job_id(page)
        if after and after != before:
            return True
    return False


# ---------------------------------------------------------------------------
# Detail page
# ---------------------------------------------------------------------------

def _labeled(soup: BeautifulSoup, label: str) -> str:
    """Read the value from a <strong>Label:</strong> value block."""
    for strong in soup.find_all("strong"):
        if strong.get_text(strip=True).rstrip(":").lower() == label.lower():
            parent = strong.parent
            if label.lower() == "recruiter email":
                a = parent.find("a")
                if a:
                    txt = a.get_text(strip=True)
                    m = _EMAIL_RE.search(txt) or _EMAIL_RE.search(
                        a.get("href", "")
                    )
                    return m.group(0).lower() if m else txt.strip().lower()
            text = parent.get_text(" ", strip=True)
            return text.split(":", 1)[-1].strip() if ":" in text else ""
    return ""


def _scrape_detail(page, job_id: str) -> dict | None:
    """Open a job detail page and extract firm/recruiter info."""
    try:
        page.goto(DETAIL_URL.format(job_id=job_id),
                  wait_until="domcontentloaded", timeout=30000)
        time.sleep(0.6)
    except Exception as e:
        log.warning(f"  [NCHCR] Detail load failed (JobID={job_id}): {e}")
        return None

    soup = BeautifulSoup(page.content(), "lxml")
    company = _labeled(soup, "Company Name")
    recruiter = _labeled(soup, "Recruiter Name")
    phone = _labeled(soup, "Contact Phone")
    email = _labeled(soup, "Recruiter Email")

    if not company and not email:
        return None
    return {
        "company_name": company,
        "recruiter_name": recruiter,
        "phone": phone,
        "email": email,
    }


# ---------------------------------------------------------------------------
# Record assembly + dedup
# ---------------------------------------------------------------------------

def _domain_from_email(email: str) -> str:
    if "@" not in email:
        return ""
    domain = email.rsplit("@", 1)[-1].strip().lower().lstrip("www.")
    if not domain or domain in _GENERIC_DOMAINS:
        return ""
    return domain


def _normalize_name(name: str) -> str:
    n = re.sub(r"[^a-z0-9 ]", " ", name.lower())
    n = _NORM_STRIP.sub(" ", n)
    return re.sub(r"\s+", " ", n).strip()


def _make_record(firm: str, meta: dict, detail: dict) -> dict:
    email = detail.get("email", "")
    domain = _domain_from_email(email)
    company = detail.get("company_name") or firm
    return {
        "company_name":   company.strip(),
        "recruiter_name": detail.get("recruiter_name", "").strip(),
        "recruiter_email": email,
        "website":        f"https://{domain}" if domain else "",
        "company_domain": domain,
        "phone":          detail.get("phone", "").strip(),
        "state":          meta.get("state", ""),
        "city":           meta.get("city", ""),
        "specialty":      meta.get("specialty", ""),
        "sample_job_id":  meta.get("job_id", ""),
        "source":         "nchcr",
        "date_scraped":   datetime.now().strftime("%Y-%m-%d"),
    }


def _dedupe(records: list[dict]) -> list[dict]:
    seen_domain: set[str] = set()
    seen_name: set[str] = set()
    out = []
    for r in records:
        dom = r.get("company_domain", "")
        key_name = _normalize_name(r.get("company_name", ""))
        if dom and dom in seen_domain:
            continue
        if not dom and key_name and key_name in seen_name:
            continue
        if dom:
            seen_domain.add(dom)
        if key_name:
            seen_name.add(key_name)
        out.append(r)
    return out


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def run(config: dict, test: bool = False) -> list[dict]:
    """
    Scrape the NCHCR job board → unique recruitment firms with emails/websites.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        log.warning("  [NCHCR] playwright not installed — skipping")
        return []

    job_type  = config.get("nchcrJobType", "Both")
    rpp       = int(config.get("nchcrResultsPerPage", 500))
    max_pages = 1 if test else int(config.get("nchcrMaxListPages", 30))
    max_firms = 10 if test else int(config.get("nchcrMaxFirms", 0))  # 0 = no cap

    os.makedirs(".tmp", exist_ok=True)
    firms: dict[str, dict] = {}
    records: list[dict] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(user_agent=_UA)

        try:
            # --- Phase 1: enumerate unique firms from listing pages ---
            listing = ctx.new_page()
            log.info(f"  [NCHCR] Loading job results (JobType={job_type})")
            listing.goto(RESULTS_URL.format(job_type=job_type),
                         wait_until="domcontentloaded", timeout=45000)
            time.sleep(2)

            try:
                listing.screenshot(path=".tmp/nchcr_debug.png", full_page=False)
            except Exception:
                pass

            if not _results_table(BeautifulSoup(listing.content(), "lxml")):
                log.warning("  [NCHCR] No results table — site may be down")
                browser.close()
                return []

            _set_results_per_page(listing, rpp)

            for page_num in range(1, max_pages + 1):
                rows = _parse_listing_rows(listing)
                new = 0
                for row in rows:
                    if row["firm"] not in firms:
                        firms[row["firm"]] = row
                        new += 1
                log.info(
                    f"  [NCHCR] Listing page {page_num}: "
                    f"{len(rows)} rows, {new} new firms ({len(firms)} total)"
                )
                if max_firms and len(firms) >= max_firms:
                    break
                if not _next_page(listing):
                    log.info("  [NCHCR] Reached last results page")
                    break

            # --- Phase 2: one detail visit per unique firm ---
            firm_items = list(firms.items())
            if max_firms:
                firm_items = firm_items[:max_firms]
            log.info(f"  [NCHCR] Visiting {len(firm_items)} firm detail pages")

            detail = ctx.new_page()
            for i, (firm, meta) in enumerate(firm_items, 1):
                d = _scrape_detail(detail, meta["job_id"])
                if d:
                    records.append(_make_record(firm, meta, d))
                if i % 25 == 0:
                    log.info(f"  [NCHCR] …{i}/{len(firm_items)} details done")

        except Exception as e:
            log.error(f"  [NCHCR] Fatal error: {e}", exc_info=True)
        finally:
            browser.close()

    deduped = _dedupe(records)
    with_web = sum(1 for r in deduped if r["website"])
    log.info(
        f"  [NCHCR] → {len(deduped)} unique firms "
        f"({with_web} with website/email domain)"
    )
    return deduped
