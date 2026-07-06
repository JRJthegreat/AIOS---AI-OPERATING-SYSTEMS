# Session Handoff — AI Ark Decision-Maker Enrichment

**Date:** 2026-06-22
**Read this first, then wait for Jude's instructions on exactly how to use AI Ark.**

---

## 1. Who / what this is for
- **Jude (Rood Judeley Joseph)** — founder of **NEXAM AI**, a B2B demand-generation company expanding from recruitment into **general B2B demand gen**.
- This is **Jude's own campaign** (not a client's).
- **Signal/thesis:** companies actively hiring B2B sales reps on Indeed = strong buying signal (budget + believe in outbound + pipeline pressure). Outreach angle: *"You just hired an SDR — we book qualified meetings into their calendar from day one"* (additive to the hire, not "replace your sales team").

## 2. Where we are right now (the deliverable)
We already built the `b2b-sales-leads-indeed` skill and ran the full pipeline. The current deliverable:

- **Google Sheet:** https://docs.google.com/spreadsheets/d/1g2X-qSv-Y3A5A8Z83cftAD-9Af5PO0XQJTVjH6yq5PQ/edit
- **Sheet ID:** `1g2X-qSv-Y3A5A8Z83cftAD-9Af5PO0XQJTVjH6yq5PQ`
- **Tab:** `Leads`
- **Contents:** **937 unique B2B companies** hiring individual-contributor (IC) sales reps — agencies, managers, Account Executives, B2C/consumer-facing companies, commission-only, and >500-employee companies already filtered out.
- **Domain coverage:** ~90% (848/937) have a website in **column L**.

### Pipeline already completed (in order)
1. Scrape Indeed job postings (`valig~indeed-jobs-scraper` via Apify) across 4 keywords × 9 US locations.
2. `filter_by_size.py` — drop companies >500 employees (kept blanks).
3. `classify_companies.py` — per-row regex + Azure OpenAI `gpt-4.1`; KEEP only `TARGET` (B2B company + IC frontline sales rep).
4. `dedupe_by_company.py` — one row per company (newest posting wins).
5. `find_company_domains.py` — filled missing websites into col L (Apify Google Search + Azure LLM).

Scripts live in `.claude/skills/b2b-sales-leads-indeed/scripts/`. Full details in that skill's `SKILL.md`.

## 3. Sheet schema (29 columns)
- **A–J** Job info (B = Job Title, J = Job Desc)
- **K–Q** Company: **K Name**, **L Website/Domain**, **M Size**, N Revenue, O CEO, P Description, Q Benefits
- **R–S** City / State
- **T–AA** Outreach — **currently blank, reserved for this enrichment phase:**
  - **T** DM Name · **U** DM Title · **V** LinkedIn URL · **W** Email · **X** First Name · **Y** Last Name · **Z** Email Body · **AA** Added to Instantly
- **AB** Role Type · **AC** Indeed URL

## 4. What we're trying to achieve next (THE GOAL)
**Find the decision maker (DM) at each of the 937 companies and their email, then write into columns T–W (and X/Y for first/last name).**

- **Target DM titles:** Founder / CEO / President **and** sales leadership: VP Sales / Head of Sales / CRO / Sales Director.
  - *(Jude will confirm the exact title/seniority priority before we run — ask if unclear.)*
- Match companies to people primarily by **domain** (col L), falling back to **company name** (col K) where domain is blank (~89 companies).

## 5. AI Ark MCP — setup status
- Config added to **`/Users/air/AIOS - AI OPERATING SYSTEMS/.mcp.json`** (project-scoped, HTTP transport). Jude added his real API key.
- **`.mcp.json` is gitignored** (key must never be committed).
- **Verified working:** raw MCP `initialize` + `tools/list` over curl returned HTTP 200 and the full tool set. Endpoint: `https://api.ai-ark.com/v1/mcp?token=…`.
- The MCP tools become callable **after a full Claude Code restart** + approving the `ai-ark` trust prompt. (If they still don't appear, raw `curl` against the endpoint is a working fallback.)

## 6. AI Ark tool inventory (what's available)
Apollo/ZoomInfo-class dataset: **70M companies / 500M people.**

| Tool | Use |
|------|-----|
| `people_search` | Find people by `companyDomain`/`companyName` + `title`/`seniority`/`department` (no email) |
| `email_finder` | **Search people AND get emails in one step** — same filters as `people_search`. **Async:** returns a `trackId` (+ optional `webhook`) |
| `email_finder_results` | Poll results by `trackId` (paginated; full person data incl. email) |
| `export_single` | One person → real-time email, by AI-Ark `id` or LinkedIn `url` |
| `mobile_phone_finder` | Mobile numbers by LinkedIn URL or name+domain |
| `reverse_people_lookup` | Find a person by email/phone |
| `personality_analysis` | DISC + OCEAN from a LinkedIn profile (cold-email tone) |
| `company_search` | 70M companies by industry/tech/size/funding/revenue/etc. |
| `industry_search` / `technology_search` / `location_search` | **Enum resolvers — call FIRST** |

### Critical gotchas
- **Enum tokens required:** `company_search` / `people_search` / `email_finder` need *exact* enum values for `industry`, `location`, `technology`. Resolve free text → token via `industry_search` / `location_search` / `technology_search` before filtering. (For our case we filter by domain + title, so we mostly avoid industry/location enums.)
- **`email_finder` is asynchronous:** it returns a `trackId` and `state: PENDING`; you must poll `email_finder_results` (or use a `webhook`). Plan the batch loop around that.
- **937 companies = cost + rate limits.** Run a small sample (5–10 companies) first, eyeball quality + match rate, confirm credit cost with Jude, *then* batch. Jude is cost-sensitive — flag spend before full runs.

## 7. Proposed approach (pending Jude's exact instructions)
1. Read companies from the sheet (col K name, col L domain).
2. For each company: `email_finder` (or `people_search` → `export_single`) filtered by `companyDomain` + DM titles/seniority, take the best-ranked match.
3. Poll `email_finder_results` → write **T** name, **U** title, **V** LinkedIn, **W** email, **X/Y** first/last into the sheet.
4. Likely a new script `find_dm.py` in the skill's `scripts/` (mirrors the existing scripts' auth + Sheets-write pattern: `--sheet_url`, dry-run by default, `--apply` to write, batched writes with 429/503 backoff).

**Do NOT run a full batch without Jude's go-ahead** — wait for his instructions on tool choice, title priority, and sample-first sizing.

## 8. Conventions / env (already in place)
- Scripts read `token.json` + `.env` from project root (resolved from `__file__`, CWD-independent).
- **LLM:** Azure OpenAI `gpt-4.1` (`AZURE_OPENAI_ENDPOINT` / `AZURE_OPENAI_API_KEY`). **`ANTHROPIC_API_KEY` in `.env` is expired (401)** — do not use Claude for classification.
- `APIFY_API_TOKEN` (scraping), `ANYMAILFINDER_API_KEY` (set — alternative email source) available.
- Google Sheets: 18px row height convention (baked into helpers); deletes bottom-up via `deleteDimension`.
- All mutating scripts: **dry-run by default, `--apply` to write.**
- `.tmp/` for intermediates (gitignored, never commit).
