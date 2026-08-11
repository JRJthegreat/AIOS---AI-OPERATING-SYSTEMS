"""
ProductionHUB Directory Scraper.

Scrapes productionhub.com directory listings by (category × location) into
one deduplicated record per company profile.

Listing pages (/directory/profiles/{category}[/{country}/{region}/{city}])
carry: profile id/URL, company name, city + region links, a truncated
description, and "Member Since YYYY | Views: N". Numbered pagination via
?radius={r}&page={n}.

Profile pages (/profiles/details/{id}) carry the full description — the only
place a company website ever appears (there is no dedicated website field;
companies write their URL into their own blurb, or don't).

Cloudflare fronts the whole site: the first page load answers a JS challenge
(~5s), after which the cf_clearance cookie carries the session. One headed
Chromium context is reused for every page so the challenge is paid once.
Plain headless Chromium fails the challenge — locally this scraper opens a
real browser window; on Apify it runs under xvfb (see Dockerfile CMD).

Fields per record:
  profile_id, name, profile_url, category (first seen), categories (all seen),
  metro, country, region, city, member_since, views, description, website,
  emails, phone, source, date_scraped
"""
from __future__ import annotations

import logging
import os
import re
import time
from datetime import datetime, timezone
from urllib.parse import urlparse

from bs4 import BeautifulSoup
from patchright.sync_api import sync_playwright

log = logging.getLogger(__name__)

BASE = "https://www.productionhub.com"
CHALLENGE_TITLE = "Just a moment"
PAGE_DELAY_S = 1.5
PROFILE_DELAY_S = 0.8
CHALLENGE_TIMEOUT_S = 60

_PROFILE_HREF_RE = re.compile(r"/profiles/details/(\d+)")
_MEMBER_RE = re.compile(r"Member Since\s+(\d{4})(?:\s*\|\s*Views:\s*([\d,]+))?")

# Website extraction from free-text descriptions, most explicit form first.
_URL_RE = re.compile(r"https?://[^\s\"'<>)]+", re.I)
_WWW_RE = re.compile(r"\bwww\.[a-z0-9][a-z0-9.-]*\.[a-z]{2,}\b", re.I)
_BARE_DOMAIN_RE = re.compile(
    r"\b[a-z0-9][a-z0-9-]{1,62}\."
    r"(?:com|net|org|tv|co|io|us|ca|studio|film|media|productions|video|agency|works)\b",
    re.I,
)
_EMAIL_RE = re.compile(r"\b[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}\b", re.I)
_PHONE_RE = re.compile(r"(?:\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}\b")

# Bare-domain matches that are never the company's website.
_DOMAIN_STOPLIST = {
    "productionhub.com", "vimeo.com", "youtube.com", "facebook.com",
    "instagram.com", "linkedin.com", "twitter.com", "x.com", "imdb.com",
    "gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "aol.com",
}


def _clean_domainish(raw: str) -> str | None:
    raw = raw.rstrip(".,;:!?)('\"").strip()
    if not raw:
        return None
    host = re.sub(r"^https?://", "", raw, flags=re.I).split("/")[0].split(":")[0].lower()
    root = host[4:] if host.startswith("www.") else host
    if root in _DOMAIN_STOPLIST or "." not in root:
        return None
    return raw


def extract_website(text: str) -> str | None:
    """Most-explicit-first URL extraction from a profile description."""
    for rx in (_URL_RE, _WWW_RE, _BARE_DOMAIN_RE):
        for m in rx.finditer(text or ""):
            cleaned = _clean_domainish(m.group(0))
            if cleaned:
                return cleaned
    return None


def _get(page, url: str, marker: str):
    """
    Load a page and wait until `marker` (a real-content selector) is attached.

    Title-based challenge detection is NOT reliable: mid-solve the title is
    briefly empty/"Loading …", which looks like success and hands back the
    Cloudflare interstitial HTML. Waiting for a content selector instead rides
    through the challenge's auto-navigation (retry loop because the wait can
    throw when the solve navigates and destroys the execution context).
    """
    page.goto(url, wait_until="domcontentloaded", timeout=90_000)
    deadline = time.time() + CHALLENGE_TIMEOUT_S
    while True:
        try:
            page.wait_for_selector(marker, state="attached", timeout=3_000)
            break
        except Exception:
            if time.time() > deadline:
                try:
                    body = re.sub(r"\s+", " ", BeautifulSoup(
                        page.content(), "lxml").get_text(" ", strip=True))[:300]
                except Exception:
                    body = "<unreadable>"
                raise RuntimeError(
                    f"marker {marker!r} not found within {CHALLENGE_TIMEOUT_S}s "
                    f"at {url} | title={page.title()!r} | body: {body}"
                )
    return BeautifulSoup(page.content(), "lxml")


def _parse_listing_cards(soup: BeautifulSoup) -> list[dict]:
    """One card per <h5 class="media-title">; container is its <div class="media">."""
    cards = []
    for h5 in soup.select("h5.media-title"):
        a = h5.find("a", href=_PROFILE_HREF_RE)
        if not a:
            continue
        profile_id = _PROFILE_HREF_RE.search(a["href"]).group(1)
        rec = {
            "profile_id": profile_id,
            "name": a.get_text(strip=True),
            "profile_url": f"{BASE}/profiles/details/{profile_id}",
            "country": None, "region": None, "city": None,
            "member_since": None, "views": None,
            "description": None,
        }

        card = h5.find_parent("div", class_="media") or h5.parent

        # Location links: /directory/profiles/{cat}/us/california/los-angeles.
        # Pagination links share the path but carry ?page= — skip anything with
        # a query. Cards render "City, Region" as two links in that order; on
        # geo-scoped pages BOTH carry the full city href, so assignment is
        # first-link-wins-city, next-distinct-text-wins-region.
        for loc_a in card.find_all("a", href=re.compile(r"/directory/profiles/[^/]+/")):
            href = loc_a["href"]
            if "?" in href:
                continue
            geo = href.strip("/").split("/")[3:]   # after directory/profiles/{cat}
            text = loc_a.get_text(strip=True)
            if not geo or not text:
                continue
            rec["country"] = rec["country"] or geo[0]
            if len(geo) == 3 and rec["city"] is None:
                rec["city"] = text
            elif rec["region"] is None and text != rec["city"]:
                rec["region"] = text

        desc_el = card.select_one("div.media-desc a") or card.select_one("div.media-desc")
        if desc_el:
            rec["description"] = desc_el.get_text(" ", strip=True) or None

        for strong in card.find_all("strong"):
            m = _MEMBER_RE.search(strong.get_text(" ", strip=True))
            if m:
                rec["member_since"] = int(m.group(1))
                if m.group(2):
                    rec["views"] = int(m.group(2).replace(",", ""))
                break

        cards.append(rec)
    return cards


# Boilerplate paragraph every profile page carries — never the company blurb.
_PROFILE_BOILERPLATE = "Only contact profiles if you are interested"

_SOCIAL_HOST_MAP = {
    "linkedin.com": "linkedin_url",
    "vimeo.com": "vimeo_url",
    "facebook.com": None, "instagram.com": None, "twitter.com": None,
    "x.com": None, "youtube.com": None, "youtu.be": None, "tiktok.com": None,
    "imdb.com": None, "behance.net": None,
}

# Share-widget URLs (linkedin.com/shareArticle, facebook sharer, …) — never
# the company's own page.
_SHARE_URL_RE = re.compile(r"shareArticle|/sharer|share\.php|/intent/", re.I)


def _parse_profile(soup: BeautifulSoup) -> dict:
    """Full description + structured contact data from a profile detail page."""
    out = {"description": None, "website": None, "phone": None,
           "linkedin_url": None, "vimeo_url": None}

    paras = [p.get_text(" ", strip=True) for p in soup.find_all("p")]
    paras = [t for t in paras if len(t) > 80 and _PROFILE_BOILERPLATE not in t]
    if paras:
        out["description"] = max(paras, key=len)

    tel = soup.find("a", href=re.compile(r"^tel:"))
    if tel:
        out["phone"] = tel["href"][4:].strip()

    # External links: socials get their own fields; the first non-social,
    # non-productionhub link is the website.
    for a in soup.find_all("a", href=re.compile(r"^https?://", re.I)):
        href = a["href"].strip()
        host = re.sub(r"^www\.", "", href.split("//", 1)[1].split("/")[0].lower())
        root = ".".join(host.split(".")[-2:])
        if "productionhub" in href.lower() or _SHARE_URL_RE.search(href):
            continue
        if root in _SOCIAL_HOST_MAP:
            field = _SOCIAL_HOST_MAP[root]
            if field and not out[field]:
                out[field] = href
        elif not out["website"]:
            out["website"] = href
    return out


def _launch_context(pw, proxy_url: str | None):
    """
    Patchright stealth setup that actually clears Cloudflare (verified):
    persistent context + real Chrome channel + no viewport override.
    Plain playwright, headless mode, and bare chromium.launch() all get stuck
    on the challenge — don't "simplify" back to them.
    Falls back to patchright's patched Chromium where Chrome isn't installed
    (e.g. the Apify Docker image).

    The profile dir is PERSISTENT across runs (override with PH_PROFILE_DIR).
    Cloudflare's cf_clearance cookie lives there — with it, no challenge is
    solved at all; without it, every run burns a fresh challenge and ~8 of
    those from one IP within an hour got us flagged (degraded 27-card pages,
    then outright "Waiting for … to respond" holds). Do not switch back to
    a temp dir per run.
    """
    user_data = os.environ.get("PH_PROFILE_DIR") or os.path.join(
        os.path.expanduser("~"), ".cache", "ph_scraper_profile")
    os.makedirs(user_data, exist_ok=True)
    kwargs = dict(user_data_dir=user_data, headless=False, no_viewport=True)
    if proxy_url:
        # Chromium rejects credentials embedded in the proxy URL
        # (ERR_INVALID_AUTH_CREDENTIALS) — Playwright wants them split out.
        u = urlparse(proxy_url)
        kwargs["proxy"] = {"server": f"{u.scheme}://{u.hostname}:{u.port}"}
        if u.username:
            kwargs["proxy"]["username"] = u.username
            kwargs["proxy"]["password"] = u.password or ""
    try:
        return pw.chromium.launch_persistent_context(channel="chrome", **kwargs)
    except Exception:
        return pw.chromium.launch_persistent_context(**kwargs)


def visit_profiles_only(profile_ids: list[str], test: bool = False,
                        proxy_url: str | None = None, on_batch=None) -> list[dict]:
    """
    Visit-only mode: no listing crawl, just profile detail pages for the given
    ids. Used to enrich rows that already passed classification, so the slow
    per-profile visits are spent on ICP survivors only.
    """
    if test:
        profile_ids = profile_ids[:5]
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    out: list[dict] = []

    with sync_playwright() as pw:
        ctx = _launch_context(pw, proxy_url)
        page = ctx.new_page()
        batch: list[dict] = []
        for i, pid in enumerate(profile_ids, 1):
            url = f"{BASE}/profiles/details/{pid}"
            try:
                psoup = _get(page, url, "h3")
            except Exception as e:
                log.warning(f"  profile {pid} failed: {e}")
                continue
            detail = _parse_profile(psoup)
            text = detail["description"] or ""
            rec = {
                "profile_id": pid,
                "profile_url": url,
                "description": detail["description"],
                "website": detail["website"] or extract_website(text),
                "phone": detail["phone"],
                "linkedin_url": detail["linkedin_url"],
                "vimeo_url": detail["vimeo_url"],
                "emails": sorted(set(_EMAIL_RE.findall(text))),
                "source": "productionhub",
                "date_scraped": now,
            }
            out.append(rec)
            batch.append(rec)
            if len(batch) >= 25:
                log.info(f"  profiles visited: {i}/{len(profile_ids)}")
                if on_batch:
                    on_batch(batch)
                batch = []
            time.sleep(PROFILE_DELAY_S)
        if on_batch and batch:
            on_batch(batch)
        ctx.close()
    return out


def scrape(targets: list[dict], max_pages: int = 50, radius: int = 100,
           visit_profiles: bool = True, test: bool = False,
           proxy_url: str | None = None, on_batch=None) -> list[dict]:
    """
    targets: [{"categorySlug": ..., "locationPath": "us/california/los-angeles" | "",
               "metroKey": "LA"}]
    on_batch: optional callback(list[dict]) fired per finished target so the
              caller can push partial data.
    """
    if test:
        max_pages = 1

    by_id: dict[str, dict] = {}
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")

    with sync_playwright() as pw:
        ctx = _launch_context(pw, proxy_url)
        page = ctx.new_page()

        for tgt in targets:
            slug = tgt["categorySlug"].strip("/")
            loc = (tgt.get("locationPath") or "").strip("/")
            metro = tgt.get("metroKey") or (loc.split("/")[-1] if loc else "ALL")
            list_base = f"{BASE}/directory/profiles/{slug}" + (f"/{loc}" if loc else "")

            new_this_target: list[dict] = []
            for page_no in range(1, max_pages + 1):
                url = f"{list_base}?radius={radius}&page={page_no}"
                try:
                    soup = _get(page, url, "h5.media-title a")
                except Exception as e:
                    log.warning(f"  page {page_no} failed ({e}); stopping this target")
                    break
                cards = _parse_listing_cards(soup)
                if not cards:
                    break
                log.info(f"[{slug} | {metro}] page {page_no}: {len(cards)} profiles")
                for rec in cards:
                    known = by_id.get(rec["profile_id"])
                    if known:
                        if slug not in known["categories"]:
                            known["categories"].append(slug)
                        continue
                    rec.update({
                        "category": slug, "categories": [slug], "metro": metro,
                        "website": None, "emails": [], "phone": None,
                        "linkedin_url": None, "vimeo_url": None,
                        "source": "productionhub", "date_scraped": now,
                    })
                    by_id[rec["profile_id"]] = rec
                    new_this_target.append(rec)

                # Stop when there's no link to the next page.
                if not soup.find("a", href=re.compile(rf"[?&]page={page_no + 1}\b")):
                    break
                time.sleep(PAGE_DELAY_S)

            if visit_profiles:
                to_visit = new_this_target[:5] if test else new_this_target
                for i, rec in enumerate(to_visit, 1):
                    try:
                        psoup = _get(page, rec["profile_url"], "h3")
                    except Exception as e:
                        log.warning(f"  profile {rec['profile_id']} failed: {e}")
                        continue
                    detail = _parse_profile(psoup)
                    if detail["description"] and \
                            len(detail["description"]) > len(rec.get("description") or ""):
                        rec["description"] = detail["description"]
                    text = rec.get("description") or ""
                    # Explicit website link beats a URL fished out of the blurb.
                    rec["website"] = detail["website"] or extract_website(text)
                    rec["phone"] = detail["phone"] or \
                        (m.group(0).strip() if (m := _PHONE_RE.search(text)) else None)
                    rec["linkedin_url"] = detail["linkedin_url"]
                    rec["vimeo_url"] = detail["vimeo_url"]
                    rec["emails"] = sorted(set(_EMAIL_RE.findall(text)))
                    if i % 25 == 0:
                        log.info(f"  profiles visited: {i}/{len(to_visit)}")
                    time.sleep(PROFILE_DELAY_S)

            log.info(f"[{slug} | {metro}] done — {len(new_this_target)} new profiles "
                     f"({len(by_id)} total)")
            if on_batch and new_this_target:
                on_batch(new_this_target)

        ctx.close()

    return list(by_id.values())
