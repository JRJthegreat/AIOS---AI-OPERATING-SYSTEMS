---
name: upwork-apply
description: Scrape Upwork jobs and generate personalized proposals with cover letters. Use when user asks to find Upwork jobs, create Upwork proposals, or apply to Upwork listings.
allowed-tools: Bash, Read, Write, Edit, Glob, Grep
---

# Upwork Job Scraping & Proposal Generation

## Goal
Scrape Upwork job listings and generate personalized proposals with compelling cover letters.

## Scripts
- `./scripts/upwork_apify_scraper.py` - Two-tier Upwork scraper (direct AI + hidden gems)
- `./scripts/classify_ai_job.py` - Haiku-based AI-solvable classifier for Tier 2
- `./scripts/upwork_proposal_generator.py` - Generate proposals with Claude
- `./scripts/update_sheet.py` - Save to Google Sheets

## Process

### 1. Scrape Jobs (Two-Tier Strategy)

Run the scraper directly:
```bash
python3 ./scripts/upwork_apify_scraper.py --target 50 -o .tmp/upwork_jobs_filtered.json
```

Or skip Tier 2:
```bash
python3 ./scripts/upwork_apify_scraper.py --target 50 --no-tier2 -o .tmp/upwork_jobs_filtered.json
```

**Tier 1 — Direct AI Jobs:** AI categories + 42 tool-based keywords (n8n, Make.com, Claude, etc.)
- Categories: AI & Machine Learning, AI Apps & Integration, All - Web, Mobile & Software Dev, DevOps & Solution Architecture
- Limit: 500 → quality filtered

**Tier 2 — Hidden Gems:** Non-AI categories + problem-based keywords
- Categories: All - Sales & Marketing, All - Data Science & Analytics, All - IT & Networking, All - Admin Support, All - Customer Service, All - Writing, All - Accounting & Consulting
- Keywords: "automate my", "CRM setup", "lead capture", "email sequence", "GoHighLevel", etc.
- Limit: 1000 → filtered → Haiku AI classifier → genuine AI jobs
- Cost: ~$0.03 for Haiku classification

**Why two tiers:** 46% of AI-related jobs on Upwork are miscategorized in non-AI categories. These have less competition because AI specialists don't find them.

Dates calculated in Taiwan time (UTC+8). `toDate` set to tomorrow to catch timezone edge.

Post-scrape quality filters (both tiers):
- Country exclusion: NG, ZA, IN, PK, BD, KE, GH, EG, UG, TZ, ET, ZM, ZW, CM, SN, RW, CI, ML, BF, NE
- Hourly rate: skip if < $35/hr (keep fixed-price and unspecified-budget jobs)
- Fixed price: skip if < $100 (keep hourly and unspecified-budget jobs)
- Unspecified budget: ALWAYS KEEP — often the best opportunities
- Client hires: skip if < 1
- Hire rate: skip if < 60%

Jobs are deduped by uid (Tier 1 priority), tagged with `tier` (1/2) and `source` (direct/hidden_gem).

**Ranking (Haiku):** After merge+dedup, all jobs are scored 1-10 by Haiku in batches of 10. Top N are kept.
- Client quality (30%): total spent, hire rate, payment verified
- Budget value (20%): higher budget = higher score
- Skill match (20%): alignment with AI automation, n8n, Make.com, voice agents, etc.
- Recency (15%): newer jobs = fewer proposals submitted = better odds (<6hrs bonus, >24hrs penalty)
- Competition (10%): lower connects = better
- Opportunity (5%): hidden gem potential, clear scope
- Cost: ~$0.05 for 200 jobs
- Skip with `--no-rank` flag

### 2. Generate Proposals

```bash
python3 ./scripts/upwork_proposal_generator.py \
  --input .tmp/upwork_jobs_filtered.json \
  --output .tmp/proposals.json \
  --workers 5 \
  --new-sheet
```

**IMPORTANT:** Always use `--new-sheet` to create a fresh sheet. Without it, the script reuses the last sheet (cached in `.tmp/current_sheet_id.txt`) and appends to old data.

- Default batch: 30 jobs (slice with `jobs[:30]` before passing in)
- Uses Claude Opus 4.6 for proposals + cover letters
- Creates a Google Doc per proposal, links it in the cover letter
- Writes all results to a new Google Sheet on completion

### 3. Auth Setup (one-time)

Google OAuth token at `token.json` in project root. To regenerate:
```bash
python3 setup_google_auth.py
```
Opens browser OAuth flow → saves `token.json` with Sheets + Drive + Docs scopes.

## Output
Google Sheet with columns:
- Title, URL, Budget, Experience, Skills, Category
- Client Country, Client Spent, Client Hires, Connects, Featured
- Score (1-10 Haiku ranking), Tier, Source (direct/hidden_gem)
- Apply Link, Cover Letter, Proposal Doc (Google Doc link)

## Environment
```
APIFY_API_TOKEN=your_token
ANTHROPIC_API_KEY=your_key
```

## Notes
- Apify-level budget/client filters exist but stacking them is too aggressive — keep quality filters post-scrape
- Tier 2 classifier uses Haiku (~$0.03/run) to filter noise from problem-based keywords
- Unspecified-budget jobs are always kept — often the best opportunities
- Featured jobs included and shown as column in sheet (costs more connects)
- 429 rate limit errors on proposal generation = reduce `--workers` or add `time.sleep` between batches
- `gws auth export` redacts credentials — always regenerate `token.json` via `setup_google_auth.py`
