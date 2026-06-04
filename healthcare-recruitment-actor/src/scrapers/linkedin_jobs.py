"""
LinkedIn Jobs Guest API scraper.
Finds companies actively posting healthcare jobs in the last N days.
No authentication required.
"""
from __future__ import annotations

import logging
import re
import time
from datetime import datetime
from urllib.parse import urlencode

import requests

log = logging.getLogger(__name__)

LINKEDIN_URL = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.5",
}
TIME_FILTERS = {"day": "r86400", "3days": "r259200", "week": "r604800", "month": "r2592000", "2months": "r5184000"}
# Jobs that staffing AGENCIES post for nurses/doctors to apply to.
# "Travel [Role] - $X/week" and "Locum Tenens [Specialty]" are the
# canonical formats used exclusively by agencies — hospitals never post those.
# "registry" is agency-speak for per diem nurse pools; hospitals never use it.
DEFAULT_QUERIES = [
    # Travel nursing
    "travel nurse assignment",
    "travel radiology technologist",
    "travel respiratory therapist",
    "travel surgical technologist",
    "travel PT physical therapist",
    "travel allied health assignment",
    # Per diem / contract nursing (agency-specific language)
    "per diem RN registry",
    "supplemental nurse staffing",
    "contract nurse agency",
    # Locum tenens — physicians & advanced practice
    "locum tenens physician",
    "locum tenens nurse practitioner",
    "locum tenens hospitalist",
    "locum tenens emergency medicine",
    "locum tenens psychiatry",
    "locum tenens anesthesiology",
    "locum tenens radiology",
    "locum tenens surgeon",
    "locum tenens internal medicine",
    "locum tenens family medicine",
    "locum tenens pediatrics",
    "locum tenens cardiology",
]


def _build_url(query: str, location: str, start: int, time_filter: str) -> str:
    params = {"keywords": query, "start": start}
    if location:
        params["location"] = location
    if time_filter:
        params["f_TPR"] = time_filter
    return f"{LINKEDIN_URL}?{urlencode(params)}"


def _decode(text: str) -> str:
    return (text or "").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">") \
        .replace("&quot;", '"').replace("&#39;", "'").replace("&nbsp;", " ").strip()


def _extract_company(html: str) -> str:
    idx = html.find("base-search-card__subtitle")
    if idx == -1:
        return ""
    region = html[idx:idx + 500]
    m = re.search(r"<a[^>]*>([^<]+)</a>", region)
    if m:
        return m.group(1).strip()
    tag_close = region.find(">")
    if tag_close != -1:
        end = region.find("<", tag_close + 1)
        return region[tag_close + 1:end].strip() if end != -1 else ""
    return ""


def _extract_title(html: str) -> str:
    idx = html.find("base-search-card__title")
    if idx == -1:
        return ""
    tag_close = html.find(">", idx)
    if tag_close == -1:
        return ""
    end = html.find("<", tag_close + 1)
    return html[tag_close + 1:end].strip() if end != -1 else ""


_FACILITY_TERMS = {
    "hospital", "health system", "health systems", "medical center", "clinic",
    "memorial", "presbyterian", "baptist", "methodist", "catholic health",
    "university hospital", "children's hospital", "kaiser", "mayo clinic",
    "va ", " va ", "veterans affairs", "nursing home", "skilled nursing",
    "rehabilitation center", "hospice", "home health", "home care",
    "health network", "health partners", "health services", "lifepoint",
    "dignity health", "commonspirit", "ascension", "intermountain",
    "adventist", "sutter health", "geisinger", "wellspan", "beaumont",
    "piedmont", "sentara", "banner health", "tenet", "hca ", "rwjbarnabas",
    "hackensack", "northwell", "mount sinai", "montefiore", "nyu langone",
    "dana-farber", "dana farber", "cancer institute", "cancer center",
    "surgery center", "surgical center", "surgery partners",
    "recovery center", "behavioral health center", "senior life",
    "senior living", "assisted living", "long term care",
    "university of ", "school of ", " academy", " college", " university",
    "vivian.com", "travelnursesource", "health ecareer",
}

# "registry" = nurse staffing agency language; hospitals never use it for their own jobs.
_AGENCY_TITLE_SIGNALS = (
    "travel ", "locum tenens", "locum ", "travel rn", "travel lpn",
    "registry", "supplemental nurse", "contract nurse",
)

# Positive signals that the company is a staffing/placement agency.
# Used as a tiebreaker when the company name is ambiguous (no facility terms,
# but also no obvious staffing identity). Hospitals with generic names like
# "Riverside Health" would fail this check.
_AGENCY_COMPANY_SIGNALS = {
    "staffing", "locum", "placement", "recruiting", "recruitment",
    "agency", "solutions", "search", "partners", "group", "healthcare",
    "health care", "clinical", "allied", "travel", "per diem", "registry",
    "resource", "professionals", "services", "workforce", "talent",
    "supplement", "flex", "medstaff", "medstaff", "nursefinders",
}


def _is_agency_posting(company: str, title: str) -> bool:
    c = company.lower()
    t = title.lower()

    # Layer 1: reject known facility names
    if any(term in c for term in _FACILITY_TERMS):
        return False

    # Layer 2: job title must contain an agency-placement signal
    if not any(sig in t for sig in _AGENCY_TITLE_SIGNALS):
        return False

    # Layer 3: company name must contain at least one positive agency signal.
    # Catches hospitals with generic names ("Riverside Health", "St. Mary's")
    # that don't appear in _FACILITY_TERMS but clearly aren't staffing agencies.
    if not any(sig in c for sig in _AGENCY_COMPANY_SIGNALS):
        return False

    return True


def _parse_cards(html: str, query: str) -> list[dict]:
    jobs = []
    chunks = re.split(r'(?=<(?:li|div)[^>]*class="[^"]*base-card[^"]*")', html)
    for chunk in chunks:
        if "base-card" not in chunk:
            continue
        company = _decode(_extract_company(chunk))
        title = _decode(_extract_title(chunk))
        if company and _is_agency_posting(company, title):
            jobs.append({"company_name": company, "latest_job_title": title, "search_query": query})
    return jobs


DEFAULT_LOCATIONS = [
    "New York, NY", "Los Angeles, CA", "Chicago, IL", "Houston, TX",
    "Phoenix, AZ", "Philadelphia, PA", "Dallas, TX", "San Francisco, CA",
    "Seattle, WA", "Denver, CO", "Atlanta, GA", "Miami, FL",
    "Boston, MA", "Nashville, TN", "Minneapolis, MN", "Charlotte, NC",
    "San Diego, CA", "Portland, OR", "Las Vegas, NV", "Austin, TX",
]


def run(config: dict, test: bool = False) -> list[dict]:
    queries = config.get("linkedinQueries", DEFAULT_QUERIES)
    locations = config.get("linkedinLocations", DEFAULT_LOCATIONS)
    if not locations:
        locations = ["United States"]
    time_key = config.get("linkedinTimeFilter", "week")
    max_per_query = 50 if test else config.get("linkedinMaxPerQuery", 300)
    delay = 1.5

    time_filter = TIME_FILTERS.get(time_key, TIME_FILTERS["week"])
    all_companies: dict[str, dict] = {}

    max_pages_per_query = 2 if test else 999

    for location in locations:
      for query in queries:
        log.info(f"  LinkedIn [{location}]: '{query}'")
        start = 0
        consecutive_empty = 0
        query_count = 0
        pages_fetched = 0

        while query_count < max_per_query and consecutive_empty < 3 and pages_fetched < max_pages_per_query:
            url = _build_url(query, location, start, time_filter)
            try:
                resp = requests.get(url, headers=HEADERS, timeout=15)
            except requests.RequestException as e:
                log.warning(f"    Request error: {e}")
                break

            if resp.status_code == 429:
                log.warning("    Rate limited — waiting 30s")
                time.sleep(30)
                continue
            if not resp.ok:
                break

            html = resp.text
            if len(html.strip()) < 100:
                consecutive_empty += 1
                start += 25
                time.sleep(delay)
                continue

            cards = _parse_cards(html, query)
            new_this_page = 0
            for card in cards:
                key = card["company_name"].lower().strip()
                if key in all_companies:
                    all_companies[key]["job_count"] += 1
                else:
                    all_companies[key] = {**card, "job_count": 1, "found_in": location}
                    query_count += 1
                    new_this_page += 1

            if not cards or new_this_page == 0:
                consecutive_empty += 1
            else:
                consecutive_empty = 0

            pages_fetched += 1
            start += 25
            time.sleep(delay)

    today = datetime.now().strftime("%Y-%m-%d")
    return [
        {
            "company_name": d["company_name"],
            "latest_job_title": d["latest_job_title"],
            "job_count": d["job_count"],
            "found_in": d.get("found_in", ""),
            "hiring_signal": f"{d['job_count']} active healthcare job postings — {d['latest_job_title']}",
            "source": "linkedin_jobs",
            "date_scraped": today,
        }
        for d in sorted(all_companies.values(), key=lambda x: -x["job_count"])
    ]
