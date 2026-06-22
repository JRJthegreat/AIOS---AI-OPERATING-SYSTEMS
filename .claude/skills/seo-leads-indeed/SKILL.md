---
name: seo-leads-indeed
description: Scrape Indeed for US companies actively hiring an in-house SEO/AEO role, drop SEO/marketing agencies with a two-layer name+LLM filter, ICP-tag and dedupe by company, and output a clean company list to Google Sheets. Use when building a signal-based outbound list off an SEO/AEO hiring signal (e.g. for an SEO/AI-search agency like PN Digital).
allowed-tools: Bash, Read, Write, Edit, Glob, Grep
---

# SEO/AEO-Hiring Leads (Indeed)

## Goal
Find **US companies actively hiring an in-house SEO / organic / AEO (answer-engine / generative-engine optimisation) person** on Indeed and turn them into a clean, deduped company list in Google Sheets. An open in-house SEO/AEO req is a high-intent buying signal: the company has diagnosed the pain and allocated budget.

**Built for PN Digital** (pndigital.co.uk — sells AI-search visibility / GEO+AEO + SEO programmes). **Outreach angle:** displacement — *"The SEO Manager you're hiring (~$80k → ~$105–120k/yr loaded) chases Google rankings. They won't get you cited in ChatGPT — a separate discipline, and where your category is moving. We do both, for less than that one hire."* Contact the **economic buyer (CMO → VP/Head of Marketing → CEO/founder)**, never the hiring manager named in the posting (conflicted — they fought for that headcount).

**Deliverable:** the Google Sheet URL. `.tmp/` files are intermediates only.

## Why this actor (not `scrape-leads`)
`scrape-leads` uses `code_crafter/leads-finder` (finds people/contacts — wrong tool). This skill scrapes Indeed **job postings** via `valig~indeed-jobs-scraper` (`title` = job-title search + `location`), which is how you detect *active hiring*. Mirrors the sibling `b2b-sales-leads-indeed` skill.

## Keywords (Indeed `title` search) — BROAD anchors, empirically chosen
Use **broad anchor terms**, not narrow titles. A yield probe (one Apify call per candidate, measuring count + title relevance) found narrow titles starve the funnel: `SEO Specialist` returns 126 vs the broad `SEO` anchor's **580 (4.6×)**. Precision is enforced downstream (title gate + LLM), so the keyword's only job is to maximise the raw pool.

- **Tier B (traditional):** `SEO` (580), `organic search` (184), `search engine optimization` (144)
- **Tier A (AEO/AI-search — thin pool, take all):** `AEO` (14, but 36% relevant — AEO/GEO-native titles), `answer engine optimization` (59), `generative engine optimization` (62)

**Dropped as proven noise** (probe %IC-relevant): `AI search` 937 results @ **0%** (ML engineers), `link building` @ 4%, `organic growth` @ 4%, `AI SEO` @ 16%, `technical SEO`/`SEO content` (subsets of `SEO`). More keywords ≠ more leads — wrong keyword = more noise.

Tier assignment is decided on the **job description** (`Tier` column), not the keyword — a row is **Tier A** if title/description names the AI-search channel (`AEO`, `answer engine`, `generative engine`, `AI search`, `ChatGPT`, `Perplexity`, `Gemini`, `LLM`…); else **Tier B**.

> **Execution-level only (key design choice).** The displacement pitch ("use our programme instead of this hire") only fits when the role is the *executor* doing day-to-day SEO ops — that's the work PN replaces. Two-stage seniority filter: (1) **at ingest**, a regex drops unambiguous leadership (`Head/Director/VP/Chief/Team Lead`) so those never land in the sheet — including AEO/GEO leadership (`Head of AEO/GEO`); (2) **at classify**, the **LLM reads each description** for the nuanced cases — bare `Manager`/`Lead`/`Principal` aren't dropped by regex (a *solo* one can be a hands-on IC), so the LLM decides, and also catches a "Specialist" whose JD shows direct reports (`manager_role` bucket).
>
> `GEO` / `GEO Specialist` is excluded — Indeed matches it to geography/GIS jobs.

## Locations — broad US metro grid (+ Remote)
32 of the largest US business metros (SF, NYC, Austin, Seattle, Boston, LA, Chicago, Denver, Atlanta, Miami, Dallas, Houston, DC, Philadelphia, Phoenix, San Diego, San Jose, Minneapolis, Tampa, Charlotte, Nashville, Portland, Orlando, Raleigh, Las Vegas, Salt Lake City, San Antonio, Columbus, Pittsburgh, Indianapolis, Detroit, Baltimore) + `Remote`. Volume comes from location breadth; **freshness stays tight (`--max_age_days 30`)** — no stale postings.

**Cost-shaped default run:** Tier-B keywords × full grid (33 locations); Tier-A keywords × Remote + top 8 hubs. ≈ **276 actor runs** at `--limit 1000` (~$2 — actor bills $0.0001/result).

> **Cost flag:** `valig~indeed-jobs-scraper` bills per result. ALWAYS run the small test first, eyeball quality, then fire the full grid. Surface the projected cost to Jude before the full run.

## The noise problem (why the filters matter)
Indeed's `title` search **broad-matches the whole posting**, so a raw scrape is ~80% noise: wrong roles (Customer Success, Account Exec, Copywriter, Paid-Media) and **SEO/marketing agencies** (SEER, Hennessey, etc.) — who are PN's *competitors*, not prospects. Two layers remove it:
1. **Title-strict gate (free, at ingest):** keeps only postings whose TITLE signals SEO/organic/AEO ownership (`title_is_relevant`). In testing this alone cut 80 raw → ~18% relevant.
2. **LLM employer filter (`classify_companies.py`):** drops agencies + off-target roles, keeps real end-companies, and ICP-tags the survivors.

## Workflow

### Step 0 — Test scrape (always, before the full run)
```bash
cd "/Users/air/AIOS - AI OPERATING SYSTEMS"
python3 -W ignore .claude/skills/seo-leads-indeed/scripts/scrape_and_pull.py \
  --keywords "SEO Manager,Head of SEO,AEO Specialist" --cities "San Francisco, CA;Remote" \
  --limit 25 --yes
```
Open the printed sheet URL. **Pass criteria:** the kept rows are real companies hiring a genuine in-house SEO/organic/AEO role (not agencies, not wrong roles). If it fails, adjust keywords before scaling.

### Step 1 — Full scrape → new sheet
```bash
python3 -W ignore .claude/skills/seo-leads-indeed/scripts/scrape_and_pull.py --yes
```
Fires the cost-shaped grid at `--limit 1000`, applies the title-strict + recency (`--max_age_days 30`) filters, dedupes by Job_Id, tags Tier A/B, streams rows into a new Google Sheet. Append to an existing sheet with `--sheet_url "URL"`.

### Step 2 — Drop agencies + off-target, ICP-tag survivors (the key step)
```bash
# Dry run first — read the KEEP/DROP report
python3 .claude/skills/seo-leads-indeed/scripts/classify_companies.py --sheet_url "URL"
# Then apply (writes Employer Type + ICP Fit, deletes agency/off-target/uncertain rows)
python3 .claude/skills/seo-leads-indeed/scripts/classify_companies.py --sheet_url "URL" --apply
```
Runs **per row** (a company can post both an IC and a manager role). Three layers: (1) leadership-title regex → `manager_role`; (2) staffing/recruiting name regex → `recruiting_agency`; (3) LLM for the rest. Buckets: `TARGET` → KEEP (end company hiring a hands-on IC SEO/AEO executor) · `AGENCY` → DROP (SEO/digital/marketing agency or staffing) · `MANAGER` → DROP (people-management / strategic-leadership role) · `OFF_TARGET` → DROP (wrong role) · `UNCERTAIN` → DROP. Survivors get an `ICP Fit` tag (`b2b_saas` / `multi_location_services` / `other`) — **all ICP types kept**, tag is for send prioritisation.

### Step 3 — Dedupe by company
```bash
python3 .claude/skills/seo-leads-indeed/scripts/dedupe_by_company.py --sheet_url "URL"          # dry run
python3 .claude/skills/seo-leads-indeed/scripts/dedupe_by_company.py --sheet_url "URL" --apply  # apply
```
One row per company. Winner = **Tier A over Tier B**, then most recent posting (still-live signal).

### Step 4 — Review
The sheet is now a clean, deduped, ICP-tagged company list. **Stop here** and let Jude review before spending on enrichment. Useful manual cuts: sort by `Tier` (A first), filter `ICP Fit` to `b2b_saas` / `multi_location_services`.

## Phase 2 — Enrichment (later, after review)
Not built yet. When Jude approves the list, add downstream scripts (port from `b2b-sales-leads-indeed` / the `healthcare-leads-indeed` reference in the *RECRUITMENT PLAYBOOK* project):
- `find_company_domains.py` — resolve each company's real website (Indeed's `corporateWebsite` is unreliable).
- `compute_loaded_cost.py` — from Salary Min/Max (or US market rate by title) compute the fully-loaded annual cost figure (`≈ base × 1.3 + ~$8k tools`) for the displacement email.
- `find_dm.py` — find the economic buyer. **Target titles:** CMO → VP/Head of Marketing → CEO/founder. **Never** the hiring manager.
- `enrich_emails.py` — AnyMailFinder (`ANYMAILFINDER_API_KEY` is set) → fill Email column W.
- `generate_hooks.py` — per-lead opener referencing the role + loaded cost + AI-search wedge.

The sheet schema reserves columns T–AA (DM Name, DM Title, LinkedIn URL, Email, First/Last Name, Email Body, Added to Instantly) for this.

## Sheet schema (32 cols)
A–J Job info · K–Q Company (K Name, L Website, M Size, N Revenue, O CEO, P Description, Q Benefits) · R–S City/State · T–AA Outreach (blank until phase 2) · AB Role Type · AC Indeed URL · **AD Tier (A/B)** · **AE Employer Type** · **AF ICP Fit**.

## Files
- `scripts/scrape_and_pull.py` — orchestrator (keyword × city grid → sheet). Cost-shaped `build_combos`; title-strict + recency filter at ingest. Imports helpers from `pull_dataset.py`.
- `scripts/pull_dataset.py` — schema, sheet helpers, `map_to_row`, title/tier classifiers, + standalone dataset puller (`--dataset_id`).
- `scripts/classify_companies.py` — two-layer agency/off-target filter (name regex + Claude batch) + ICP tag write-back.
- `scripts/dedupe_by_company.py` — one row per company (Tier A, then freshest).

## Notes / constraints
- Auth: scripts read `token.json` + `.env` from the project root (resolved from `__file__`, CWD-independent). Needs `APIFY_API_TOKEN` + Azure OpenAI (`AZURE_OPENAI_API_KEY` / `_ENDPOINT` / `_API_VERSION` / `_DEPLOYMENT_FAST`). The classify step uses Azure (the repo's live LLM, same as `find_company_contacts.py`) — the `ANTHROPIC_API_KEY` in `.env` is stale/invalid.
- Actor limit is 1000 items/run; `--limit` is clamped to that.
- `--max_age_days 0` keeps all postings (disable the recency filter).
- Indeed accepts `Remote` as a location string. If a metro returns 0 results, check the `City, ST` format.
- All deletes are dry-run by default; `--apply` is required to mutate the sheet.
