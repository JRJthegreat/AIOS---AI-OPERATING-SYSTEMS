# Healthcare Recruitment Agency Finder

Scrapes **6 independent sources** to build a list of healthcare staffing and recruitment agencies that are **not in standard B2B databases** like Apollo or ZoomInfo. These are the firms that get overlooked by sales teams relying on over-contacted lead lists.

---

## Why This Exists

Apollo and LinkedIn SalesNav recycle the same 10,000 companies. The real opportunity is in:

- **Boutique agencies** operating in 1–2 states, invisible to national scrapers
- **Dues-paying associations** (ASA) — these firms have marketing budgets
- **Federal regulatory databases** (NPPES) — Apollo doesn't index CMS registries
- **Niche travel nurse platforms** — agencies self-register on Vivian, BluePipes, NATHO but not Apollo
- **Franchise owners** — FDD public filings contain actual owner names, no other source has this

---

## Sources

| Source | What It Is | Why It's Valuable |
|--------|-----------|-------------------|
| **LinkedIn Jobs API** | Companies actively posting travel nurse / locum tenens jobs in the last 7 days | Live revenue signal — they're hiring right now |
| **NPPES NPI Registry** | Federal CMS database searched by organization name (e.g. `*staffing*`, `*locum*`) | Regulatory DB, not scraped by B2B tools |
| **State Licensing Registries** | NY, IN, TN, MD, MN, NJ government staffing agency license lists | Boutique local firms that don't show up nationally |
| **Niche Directories** | NATHO, Vivian Health, BluePipes, TravelNurseSource | Travel healthcare-specific, near-zero Apollo overlap |
| **ASA Member Directory** | Dues-paying American Staffing Association healthcare members | Pre-vetted — they pay dues, they have budgets |
| **FDD Franchisees** | Interim HealthCare franchise owner data from public FDD filings | Contains **owner names** — no other public source has this |

---

## Input

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `sources` | Array | All 6 sources | Which scrapers to run. Options: `linkedin_jobs`, `nppes`, `state_registries`, `niche_directories`, `asa_members`, `fdd_franchisees` |
| `testMode` | Boolean | `false` | Caps each scraper at a small sample (~10–50 records). Use this to verify the actor works before a full run. |
| `linkedinQueries` | Array | 8 travel/locum queries | Job search keywords. These should be jobs that **agencies post for workers**, not jobs hospitals post for internal staff. |
| `linkedinTimeFilter` | String | `week` | Recency filter. Options: `day`, `3days`, `week`, `month` |
| `nppsQueries` | Array | `["*staffing*", "*locum*", "*placement*", "*recruiting*", "*per diem*"]` | NPPES organization name wildcard search terms |
| `states` | Array | All 6 states | State registries to include. Options: `NY`, `IN`, `TN`, `MD`, `MN`, `NJ` |
| `nicheDirectorySources` | Array | All 4 directories | Options: `natho`, `vivian`, `bluepipes`, `travelnursesource` |

### Example Input (Test Run)

```json
{
  "sources": ["linkedin_jobs", "nppes"],
  "testMode": true
}
```

### Example Input (Full Run)

```json
{
  "sources": ["linkedin_jobs", "nppes", "state_registries", "niche_directories", "asa_members", "fdd_franchisees"],
  "testMode": false,
  "linkedinTimeFilter": "week"
}
```

---

## Output

Each record in the dataset represents one unique healthcare staffing agency. Duplicates across sources are merged — if a company appears in both NPPES and a state registry, you get one record with fields filled from both.

| Field | Description |
|-------|-------------|
| `company_name` | Agency name |
| `website` | Company website (populated directly where available) |
| `company_domain` | Bare domain extracted from website |
| `linkedin_url` | Company LinkedIn page URL |
| `founder_name` | Owner/founder name (populated directly from FDD franchisee source) |
| `phone` | Business phone |
| `address` | Street address |
| `city` | City |
| `state` | State (2-letter) |
| `zip` | ZIP code |
| `source` | Which scraper(s) found this company (comma-separated if multiple) |
| `hiring_signal` | LinkedIn-only: job count and latest title (e.g. `"12 active healthcare job postings — Travel RN"`) |
| `npi_number` | NPPES-only: federal NPI registration number |
| `taxonomy` | NPPES-only: provider taxonomy description |
| `franchise` | FDD-only: franchise brand name |
| `date_scraped` | Date the record was collected |

### Sample Output Record

```json
{
  "company_name": "Supplemental Health Care",
  "website": "",
  "company_domain": "",
  "linkedin_url": "",
  "founder_name": "",
  "phone": "",
  "address": "",
  "city": "",
  "state": "",
  "source": "linkedin_jobs",
  "hiring_signal": "8 active healthcare job postings — Travel RN - ICU",
  "date_scraped": "2026-05-14"
}
```

---

## Expected Volume

| Source | Expected Records (full run) |
|--------|----------------------------|
| LinkedIn Jobs | 300–600 unique agencies |
| NPPES NPI | 400–800 agencies |
| State Registries (6 states) | 200–500 agencies |
| Niche Directories | 600–900 agencies |
| ASA Members | 200–400 agencies |
| FDD Franchisees | 200–300 agencies (with owner names) |
| **Total after dedup** | **1,500–2,500 unique agencies** |

---

## Deduplication

Records are merged across sources using this priority:

1. **Exact domain match** — strongest signal
2. **Normalized company name** — strips legal suffixes (`inc`, `llc`, `staffing`, `agency`, etc.) and compares

When a duplicate is found, fields are merged: the first record keeps its data, empty fields are filled from the duplicate. The `source` field becomes comma-separated (e.g. `nppes_npi,asa_members`).

---

## Important Notes

**LinkedIn Jobs filter:** Queries are written to target jobs that *staffing agencies* post for nurses/doctors to apply to (e.g. `travel nurse assignment`). Avoid queries like `travel nurse recruiter` — those match hospitals posting internal HR jobs, which would return health systems instead of agencies.

**NPPES filter:** Searches by `organization_name` with wildcards (e.g. `*staffing*`) rather than by taxonomy description. Taxonomy-based queries (e.g. `Nursing Care`) return all nursing care providers including homes and hospices — not what you want.

**Run time:** A full run across all 6 sources takes approximately 20–45 minutes depending on Playwright scraping speed for JS-rendered sources (Vivian, ASA).

**Cost:** Estimated 0.1–0.3 compute units per full run on Apify's standard infrastructure.

---

## Next Steps After Export

1. **Classify** — Filter to healthcare-specialist-only firms using an LLM classifier
2. **Find websites** — For records missing a website, run a Google search enrichment pass
3. **Find founders** — Scrape LinkedIn employee pages for owner/founder names
4. **Outreach** — Push to your cold email tool (Instantly, Apollo sequences, etc.)
