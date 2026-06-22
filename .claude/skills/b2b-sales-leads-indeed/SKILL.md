---
name: b2b-sales-leads-indeed
description: Scrape Indeed for companies actively hiring B2B sales reps (Outside Sales / SDR / BDR), cap by company size (≤500), then keep only B2B companies hiring individual-contributor sales reps — dropping recruiting agencies, managers, Account Executives/account-management, B2C (consumer-facing) companies, commission-only, and non-sales roles — via a per-row regex+LLM filter, dedupe by company, and output a clean company list to Google Sheets. Use when finding companies hiring salespeople, building a demand-gen prospect list off a hiring signal, or running NEXAM's own B2B campaign.
---

# B2B Sales-Hiring Leads (Indeed)

## Goal
Find **companies actively hiring B2B sales reps** on Indeed and turn them into a clean, deduped company list in Google Sheets. A company hiring sales reps is a strong demand-gen buying signal: they have budget, believe in outbound, and have pipeline pressure (you don't hire reps when the calendar's full).

**Outreach angle this list is built for:** "You just hired an SDR — they've got a 90-day ramp and a cold pipeline. We book qualified meetings into their calendar from day one." Additive to the hire, not "replace your sales team."

**Deliverable:** the Google Sheet URL. `.tmp/` files are intermediates only.

## Why this actor (not `scrape-leads`)
`scrape-leads` uses `code_crafter/leads-finder`, which finds **people/contacts** — wrong tool. This skill scrapes Indeed **job postings** via `valig~indeed-jobs-scraper` (query = job title, plus location), which is how you detect *active hiring*.

## Keywords (Indeed `title` search)
Indeed matches the job title, so keywords must be real titles people post.
1. `Outside Sales Representative`
2. `B2B Sales Representative`
3. `B2B Sales Development Representative`
4. `Business Development Representative`  (BDR)

`Account Executive` is intentionally excluded (high volume; AE roles are dropped downstream anyway). **Note:** on the first full run, keyword #3 (`B2B Sales Development Representative`) added **0 unique rows** — fully overlapped by the other three. Consider replacing it with plain `Sales Development Representative` or `Inside Sales Representative` next run.

## Locations (round 1: US top-8 metros + Remote)
New York, NY · Los Angeles, CA · Chicago, IL · Dallas, TX · Atlanta, GA · Boston, MA · San Francisco, CA · Austin, TX · Remote

4 keywords × 9 locations = **36 actor runs**. Concentrated company density = higher quality. Scale the `--cities` grid for round 2.

> **Cost flag:** `valig~indeed-jobs-scraper` bills per result. Always run the 25-item test first, eyeball quality, then fire the full grid.

## Workflow

### Step 0 — Test scrape (always, before the full run)
```bash
cd "/Users/air/AIOS - AI OPERATING SYSTEMS"
python3 -W ignore .claude/skills/b2b-sales-leads-indeed/scripts/scrape_and_pull.py \
  --keywords "Sales Development Representative" --cities "Remote" --limit 25 --yes
```
Open the printed sheet URL. **Pass criteria:** ≥80% are real B2B companies hiring salespeople (not staffing agencies, not B2C field sales like insurance/door-to-door). If it fails, adjust keywords before scaling.

### Step 1 — Full scrape → new sheet
```bash
python3 -W ignore .claude/skills/b2b-sales-leads-indeed/scripts/scrape_and_pull.py --yes
```
Fires the 4 × 9 grid at `--limit 1000`, dedupes by Job_Id, drops postings older than `--max_age_days` (default 45 — fresh = currently hiring), streams rows into a new Google Sheet. Append to an existing sheet with `--sheet_url "URL"`.

### Step 1.5 — Filter by company size (≤500 employees)
```bash
python3 .claude/skills/b2b-sales-leads-indeed/scripts/filter_by_size.py --sheet_url "URL"          # dry run (see breakdown)
python3 .claude/skills/b2b-sales-leads-indeed/scripts/filter_by_size.py --sheet_url "URL" --apply  # cap at 500
```
Deterministic, free, and run **before** the LLM step so it also shrinks (and cheapens) the classify. Parses Company Size (col M) lower bound and drops companies above the cap. **Blanks/"Decline to state" are KEPT by default** (usually small companies that didn't publish headcount) — add `--drop_blanks` to remove them, or `--max_employees N` to change the cap. On the first full run this cut 11,558 → 5,310 rows (mostly mega-enterprises that are a poor fit for a small BD connector).

### Step 2 — Keep only B2B sales-rep roles (the key step)
```bash
# Dry run first — read the KEEP/DROP report
python3 .claude/skills/b2b-sales-leads-indeed/scripts/classify_companies.py --sheet_url "URL"
# Then apply
python3 .claude/skills/b2b-sales-leads-indeed/scripts/classify_companies.py --sheet_url "URL" --apply
```
Keeps a posting only when **both** the company is B2B (sells to other businesses) **and** the role is an IC frontline sales rep. Runs **per row (per posting)**, not per company — seniority/role is a property of the posting. Layers:
1. **Title regex (free):** auto-drops unambiguous **leadership** titles (`VP`, `Director`, `Head of`, `Chief`, `President`), **Account Executive / Account Exec** titles, and **commission-only / 1099 / freelance** titles. `Manager` alone is *not* auto-dropped — "Territory/Account/Business-Development Manager" is often an IC, so it goes to the LLM.
2. **Company-name regex (free):** auto-drops unambiguous agency names (`Staffing`, `Recruiting`, `Headhunters`, `RPO`, `Locum`, `Executive Search`…).
3. **LLM (Azure OpenAI `gpt-4.1`, concurrent):** judges the rest into eight buckets. **KEEP only `TARGET`:**
   - `TARGET` → **KEEP** — B2B company **+** IC frontline rep doing new-business sales (SDR, BDR, Outside/Inside/Territory/B2B Sales Rep), salaried base ± commission, no direct reports.
   - `AGENCY` → DROP — staffing/recruiting firm posting on behalf of a client.
   - `MANAGER` → DROP — people-management / sales-leadership (manages a team, has reports).
   - `ACCOUNT_EXEC` → DROP — Account Executive, Account Manager, or closing/existing-account-management roles (we want frontline prospectors, per spec).
   - `B2C` → DROP — **the COMPANY sells primarily to consumers**, regardless of role: retail, residential home services (lawn/pools/roofing/HVAC/windows/solar/pest), consumer insurance, residential real estate/mortgage, auto dealers, gyms, hospitality, home health / consumer healthcare, DTC.
   - `COMMISSION_ONLY` → DROP — no base salary (100% commission, 1099, freelance).
   - `OFF_TARGET` → DROP — not a frontline sales rep (customer/member service, call center, client success/retention, marketing/"marketer"/liaison, sales support/coordinator/admin, ops).
   - `UNCERTAIN` → DROP.

   B2C is judged at the **company** level (per spec: drop all consumer-facing companies). A two-pass run on the first dataset (full pass, then a cheap re-pass over survivors) scrubbed residential/home-services leakers.

   **Why this matters:** Indeed's title search is loose — a query for "Business Development Representative" / "Outside Sales Representative" also returns managers, Account Executives, commission-only gigs, and consumer-facing companies (insurance/roofing/solar/pest/lawn/pools). The regex layers + the LLM's company-and-role judgment strip all of that, leaving only B2B companies hiring frontline sales reps. A rare commercial-only edge case (e.g. a pool co that's actually B2B) may survive — eyeball-deletable.

### Step 3 — Dedupe by company
```bash
python3 .claude/skills/b2b-sales-leads-indeed/scripts/dedupe_by_company.py --sheet_url "URL"          # dry run
python3 .claude/skills/b2b-sales-leads-indeed/scripts/dedupe_by_company.py --sheet_url "URL" --apply  # apply
```
One row per company (companies post the same role across cities). Keeps the most recent posting.

### Step 4 — Review
The sheet is now a clean, deduped company list. **Stop here** and let Jude review quality before spending on enrichment. (Tighter ICP cut available anytime via `filter_by_size.py --max_employees N`, e.g. 200.)

## Phase 2 — Enrichment

### Step 5 — Find missing company domains (built)
```bash
python3 .claude/skills/b2b-sales-leads-indeed/scripts/find_company_domains.py --sheet_url "URL"          # dry run (count + cost)
python3 .claude/skills/b2b-sales-leads-indeed/scripts/find_company_domains.py --sheet_url "URL" --apply  # fill blanks
```
Fills col L for companies missing a website. Per company: Apify Google Search → filter out job boards/directories/social/ATS → Azure `gpt-4.1` picks the official domain (bare, e.g. `bestblock.com`). Skips rows that already have a domain/URL (`--force` to redo). Dedupes by company. Cost ≈ $0.0085/company. First run: 937 cos → 398 already had a site, 539 looked up → **450 found / 89 not** → 90% coverage.

### Still to build (port from `healthcare-leads-indeed` reference in *RECRUITMENT PLAYBOOK*):
- `find_dm.py` — find decision makers. **Target titles for B2B demand-gen:** Founder / CEO / President + VP Sales / Head of Sales / CRO / Sales Director.
- `enrich_emails.py` — AnyMailFinder (`ANYMAILFINDER_API_KEY` is set) → fill Email column W.

The sheet schema already reserves columns T–AA (DM Name, DM Title, LinkedIn URL, Email, First/Last Name, Email Body, Added to Instantly) for this.

## Sheet schema (29 cols)
A–J Job info · K–Q Company (K Name, L Website, M Size, N Revenue, O CEO, P Description, Q Benefits) · R–S City/State · T–AA Outreach (blank until phase 2) · AB Role Type · AC Indeed URL.

## Files
- `scripts/scrape_and_pull.py` — orchestrator (keyword × city grid → sheet). Imports helpers from `pull_dataset.py`.
- `scripts/pull_dataset.py` — schema, sheet helpers, `map_to_row`, + standalone dataset puller (`--dataset_id`).
- `scripts/filter_by_size.py` — drop companies above an employee-count cap (default ≤500), before classify.
- `scripts/classify_companies.py` — per-row filter (regex + Azure LLM) keeping only B2B sales-rep roles.
- `scripts/dedupe_by_company.py` — one row per company.
- `scripts/find_company_domains.py` — fill missing website domains (Apify Google Search + Azure LLM) → col L.

## Notes / constraints
- Auth: scripts read `token.json` + `.env` from the project root (resolved from `__file__`, CWD-independent). Needs `APIFY_API_TOKEN` (scrape) + `AZURE_OPENAI_ENDPOINT` / `AZURE_OPENAI_API_KEY` (classify). Note: `ANTHROPIC_API_KEY` in `.env` is currently expired (401) — that's why classify uses Azure.
- Actor limit is 1000 items/run; `--limit` is clamped to that.
- `--max_age_days 0` keeps all postings (disable the recency filter).
- Indeed accepts `Remote` as a location string. If a metro returns 0 results, check the `City, ST` format.
- All deletes are dry-run by default; `--apply` is required to mutate the sheet.
