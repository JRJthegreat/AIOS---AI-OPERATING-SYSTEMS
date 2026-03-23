# Lesson 3: API Scrapers — No Browser Needed (LinkedIn Jobs)

## What you'll learn
- How to find hidden APIs behind websites (the DevTools trick)
- How to scrape LinkedIn's guest jobs API without authentication
- How to parse HTML with string matching (no libraries needed)
- How to add business logic: repost detection, urgency scoring
- Why API scrapers are 10x faster than browser scrapers

## What you'll build
A scraper that pulls job postings from LinkedIn's public API, calculates hiring urgency, detects reposts, and outputs intelligence about which companies are desperately hiring.

---

## Why Not Use a Browser?

In Lesson 02, we used Playwright to open a real browser. That works, but it's slow and heavy:
- Launches a full Chrome browser (~200MB RAM)
- Waits for JavaScript to render
- Fights with cookie banners and CAPTCHAs
- Can only process 1-2 pages at a time

API scrapers skip all of that. You're making direct HTTP requests — the same thing the website's frontend does when it loads data. No browser, no rendering, no waiting.

**The rule:** If you can get the data from an API, always prefer that over browser scraping. Save Playwright for sites that genuinely require JavaScript rendering (Lesson 04).

## Finding Hidden APIs

Here's the trick that most tutorials don't teach:

1. Open the website in Chrome
2. Open DevTools (F12)
3. Go to the **Network** tab
4. Filter by **Fetch/XHR**
5. Interact with the page (scroll, click, search)
6. Watch what requests appear

Every modern website loads data from an API. The frontend is just a pretty wrapper. When you see a request that returns the data you want, you've found your API.

**For LinkedIn Jobs:**

Go to `linkedin.com/jobs`, search for something, and watch the Network tab. You'll see requests to:

```
https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?keywords=...&start=0
```

That's LinkedIn's guest API. No authentication needed. It returns HTML fragments that contain job cards. Copy that URL pattern — that's your scraper's target.

## The Prompt

> "Build me an Apify actor in TypeScript called 'job-postings' that fetches job listings from LinkedIn's guest API at https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search. Input parameters: searchQuery (required string), location (optional string), maxListings (number, default 100), datePosted (enum: today/3days/week/month/any). Parse the HTML response using string matching to extract: job title, company name, location, date posted (ISO), salary range, and apply URL. Calculate days listed and hiring urgency (fresh/normal/high/critical). Paginate by incrementing the start parameter by 25. No Playwright — use plain fetch."

## How LinkedIn's Guest API Works

The API takes these query parameters:

```typescript
function buildUrl(query: string, location: string, start: number, timeFilter: string): string {
    const params = new URLSearchParams({
        keywords: query,
        start: String(start),
    });
    if (location) params.set('location', location);
    if (timeFilter) params.set('f_TPR', timeFilter);

    return `https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?${params}`;
}
```

The time filter uses LinkedIn's internal codes:

| Input | Code | Meaning |
|-------|------|---------|
| `today` | `r86400` | Last 24 hours |
| `3days` | `r259200` | Last 3 days |
| `week` | `r604800` | Last 7 days |
| `month` | `r2592000` | Last 30 days |
| (empty) | (none) | All time |

Pagination: each page returns ~25 results. Increment `start` by 25 to get the next page. When the response is empty or very short, you've hit the end.

## Parsing HTML Without Libraries

The API returns HTML fragments, not JSON. Most tutorials would tell you to install Cheerio or jsdom. We don't need them.

Here's the insight: HTML is just text. If you know the class names, you can extract data with string operations.

```typescript
function parseJobCards(html: string, searchQuery: string, searchLocation: string): JobRecord[] {
    const jobs: JobRecord[] = [];

    // Split HTML into card chunks
    const cardChunks = html.split(/(?=<div[^>]*class="[^"]*base-card[^"]*")/);

    for (const chunk of cardChunks) {
        if (!chunk.includes('base-card')) continue;

        const title = extractBetween(chunk, 'base-search-card__title', '<');
        const company = extractCompany(chunk);
        const location = extractBetween(chunk, 'job-search-card__location', '<');
        const dateISO = extractAttribute(chunk, 'datetime');
        const jobUrl = extractHref(chunk, 'base-card__full-link');
        const salary = extractBetween(chunk, 'job-search-card__salary-info', '<');

        if (!title) continue;

        // Calculate days since posting
        let daysListed = -1;
        if (dateISO) {
            const posted = new Date(dateISO);
            const now = new Date();
            daysListed = Math.floor(
                (now.getTime() - posted.getTime()) / (1000 * 60 * 60 * 24)
            );
        }

        jobs.push({
            job_title: decodeEntities(title),
            company_name: decodeEntities(company),
            location: decodeEntities(location),
            date_posted: dateISO || '',
            days_listed: daysListed,
            salary_range: decodeEntities(salary),
            apply_url: jobUrl,
            search_query: searchQuery,
            search_location: searchLocation,
        });
    }

    return jobs;
}
```

The helper functions are dead simple:

```typescript
function extractBetween(html: string, className: string, endMarker: string): string {
    const classIdx = html.indexOf(className);
    if (classIdx === -1) return '';
    const tagClose = html.indexOf('>', classIdx);
    if (tagClose === -1) return '';
    const start = tagClose + 1;
    const end = html.indexOf(endMarker, start);
    return html.substring(start, end === -1 ? undefined : end).trim();
}

function extractCompany(html: string): string {
    const subtitleIdx = html.indexOf('base-search-card__subtitle');
    if (subtitleIdx === -1) return '';
    const searchRegion = html.substring(subtitleIdx, subtitleIdx + 500);
    const aMatch = searchRegion.match(/<a[^>]*>([^<]+)<\/a>/);
    return aMatch ? aMatch[1].trim() : '';
}

function extractAttribute(html: string, attr: string): string {
    const regex = new RegExp(`${attr}="([^"]*)"`, 'i');
    const match = html.match(regex);
    return match ? match[1] : '';
}

function extractHref(html: string, className: string): string {
    const idx = html.indexOf(className);
    if (idx === -1) return '';
    const region = html.substring(Math.max(0, idx - 500), idx + 200);
    const hrefMatch = region.match(/href="([^"]+)"/);
    return hrefMatch ? hrefMatch[1].split('?')[0] : '';
}
```

**Why not use Cheerio?** Two reasons:
1. One fewer dependency = fewer things that can break
2. For simple extraction, string operations are actually faster and more readable

## Handling HTML Entities

LinkedIn's HTML contains entities like `&amp;`, `&lt;`, `&#39;`. You need to decode them:

```typescript
function decodeEntities(text: string): string {
    if (!text) return '';
    return text
        .replace(/&amp;/g, '&')
        .replace(/&lt;/g, '<')
        .replace(/&gt;/g, '>')
        .replace(/&quot;/g, '"')
        .replace(/&#39;/g, "'")
        .replace(/&nbsp;/g, ' ')
        .trim();
}
```

This is one of those things that bites you if you skip it. Company names like "Ben & Jerry's" will come out as "Ben &amp; Jerry&#39;s" without decoding.

## Business Logic: Urgency Scoring

Here's where your scraper stops being a dumb data puller and becomes a signal generator.

```typescript
type HiringUrgency = 'fresh' | 'normal' | 'high' | 'critical';

function calcUrgency(daysListed: number, sourceCount: number): HiringUrgency {
    if (daysListed >= 30 || sourceCount >= 4) return 'critical';
    if (daysListed >= 14 || sourceCount >= 3) return 'high';
    if (daysListed < 3 && daysListed >= 0)    return 'fresh';
    return 'normal';
}
```

The logic:
- **Fresh** (< 3 days): Just posted. Company is starting their search.
- **Normal** (3-13 days): Active search. Standard timeline.
- **High** (14-29 days or 3+ sources): Getting desperate. Role is hard to fill.
- **Critical** (30+ days or 4+ sources): This job has been open forever. They NEED someone.

If you sell recruiting services, staffing, or HR tech — the "critical" jobs are your warmest leads. Those companies have been trying to fill a role for over a month. They're feeling the pain right now.

## Repost Detection

Companies that can't fill a role will take it down and repost it to reset the "days ago" counter and appear fresh. We detect this:

```typescript
// If a job appears on 4+ sources, it's likely been reposted
const is_likely_repost = sourceCount >= 4;
```

This is a simple heuristic but surprisingly effective. A job that appears on LinkedIn, Indeed, Glassdoor, and ZipRecruiter simultaneously has been around — the company is casting a wide net because they're struggling to hire.

## The Pagination Loop

```typescript
async function fetchLinkedInJobs(
    query: string,
    location: string,
    maxListings: number,
    datePosted: string
): Promise<JobRecord[]> {
    const allJobs: JobRecord[] = [];
    const seen = new Set<string>();
    const timeFilter = getLinkedInTimeFilter(datePosted);

    let start = 0;
    const pageSize = 25;
    let consecutiveEmpty = 0;

    while (allJobs.length < maxListings && consecutiveEmpty < 3) {
        const url = buildUrl(query, location, start, timeFilter);
        const response = await fetch(url, {
            headers: {
                'User-Agent': 'Mozilla/5.0 (compatible; ApifyBot/1.0)',
            },
        });

        if (!response.ok) {
            console.log(`HTTP ${response.status} at start=${start}, stopping`);
            break;
        }

        const html = await response.text();
        if (html.trim().length < 100) {
            consecutiveEmpty++;
            start += pageSize;
            continue;
        }

        const jobs = parseJobCards(html, query, location);
        if (jobs.length === 0) {
            consecutiveEmpty++;
            start += pageSize;
            continue;
        }

        consecutiveEmpty = 0;

        for (const job of jobs) {
            const key = `${job.job_title}|${job.company_name}`.toLowerCase();
            if (seen.has(key)) continue;
            seen.add(key);
            allJobs.push(job);
        }

        start += pageSize;
    }

    return allJobs;
}
```

**Key details:**
- **Deduplication** — `Set<string>` keyed by `title|company`. LinkedIn sometimes returns the same job in multiple pages.
- **`consecutiveEmpty`** — Stop after 3 empty pages in a row. LinkedIn returns empty HTML when you've hit the end.
- **User-Agent** — Some APIs check this. Always include a reasonable one.

## Running It

```bash
cd job-postings
npm install
apify run --input='{"searchQuery":"cybersecurity engineer","location":"United States","maxListings":50,"datePosted":"week"}'
```

Check results:

```bash
cat storage/datasets/default/000000001.json
```

Expected output:

```json
{
    "job_title": "Senior Cybersecurity Engineer",
    "company_name": "Palo Alto Networks",
    "location": "Santa Clara, CA",
    "date_posted": "2026-03-04",
    "days_listed": 3,
    "hiring_urgency": "normal",
    "is_likely_repost": false,
    "salary_range": "$150,000 - $200,000",
    "apply_url": "https://www.linkedin.com/jobs/view/1234567890",
    "search_query": "cybersecurity engineer",
    "search_location": "United States"
}
```

## When APIs Fight Back

Sometimes the API returns a CAPTCHA page instead of data. This happened to us with Google Jobs — Google blocks automated requests aggressively.

**What to do:**
1. Try a different User-Agent string
2. Add delays between requests (1-2 seconds)
3. Use Apify proxy (only on the Apify platform)
4. Pivot to a different source — LinkedIn's guest API is much more permissive than Google's

**The pivot lesson:** We originally built this scraper against Google Jobs. Google started blocking us with CAPTCHAs. Instead of fighting Google's anti-bot system, we pivoted to LinkedIn's guest API, which is more reliable and returns better data. Sometimes the best engineering decision is to find a different door.

## Real Mistakes We Made

**Mistake 1: Using Cheerio**
The first version used Cheerio for HTML parsing. It worked but added a dependency and was actually slower than string operations for this simple extraction. We ripped it out and replaced with `indexOf` + `substring`.

**Mistake 2: Not handling HTML entities**
Company names came out mangled — "AT&amp;T" instead of "AT&T". Added the `decodeEntities` function and everything cleaned up.

**Mistake 3: No deduplication**
LinkedIn returns the same job across page boundaries. Without the `Set<string>` dedup, we were getting 15-20% duplicate records.

**Mistake 4: Hardcoding the User-Agent**
The first version had no User-Agent header. LinkedIn returns a 403 if you look too much like a bot. A simple browser-like User-Agent string fixed it.

---

## Next Up

You've now built scrapers for two patterns: browser-based tables (Lesson 02) and API-based extraction (this lesson). In [Lesson 04: JS-Rendered Sites](./04-js-rendered-sites.md), you'll tackle the hardest pattern: JavaScript-rendered SPAs where even the HTML isn't available until a browser runs.

## What you just learned
- Find hidden APIs using DevTools Network tab → Filter by Fetch/XHR
- API scrapers are 10x faster than browser scrapers — no Chrome, no rendering
- Parse HTML with string operations (`indexOf`, `substring`, `match`) — no Cheerio needed
- Decode HTML entities or your data will be mangled
- Urgency scoring: fresh < 3d, normal 3-13d, high 14-29d, critical 30d+
- Dedup with `Set<string>` keyed by `title|company`
- When an API blocks you, don't fight it — find a different source
