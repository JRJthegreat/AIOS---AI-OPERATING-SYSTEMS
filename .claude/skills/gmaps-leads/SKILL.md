---
name: gmaps-leads
description: Scrape Google Maps for B2B leads with deep website enrichment, contact extraction, and persona verification. Use when user asks to find local businesses, scrape Google Maps, generate contractor lists, or build local service business databases.
allowed-tools: Bash, Read, Write, Edit, Glob, Grep
---

# Google Maps Lead Generation

## Goal
Generate high-quality B2B leads from Google Maps: scrape the universe, enrich each company from its website, then verify the actual decision-maker persona (name, title, direct email) on top.

## Scripts
- `./scripts/gmaps_lead_pipeline.py` - Main pipeline: scrape -> filter -> dedupe -> enrich -> Sheet
- `./scripts/gmaps_parallel_pipeline.py` - Incremental-save variant (row-by-row appends; watch Sheets quota)
- `./scripts/scrape_google_maps.py` - Apify `compass/crawler-google-places` wrapper
- `./scripts/extract_website_contacts.py` - Website contact extractor (Azure OpenAI)
- `./scripts/verify_email_persona.py` - Persona verification: staff-page mining -> SERP+LLM judge -> optional AMF company emails
- `./scripts/amf_dm_fill.py` - AnyMailFinder decision-maker endpoint fill (owner-led verticals)
- `./scripts/heal_enrichment.py` - Re-extract rows whose enrichment died (e.g. Azure 429 storms)
- `./scripts/clean_polish_tab.py` - Final pass: rating floor, noise regex, sort verified DMs first, 18px rows
- `./scripts/update_sheet.py` - Google Sheets sync (legacy)

## LLM provider
Extraction and judging call **Azure OpenAI** (`AZURE_OPENAI_DEPLOYMENT_FAST`, default gpt-4.1). Migrated off Anthropic 2026-07 (repo Anthropic key is dead). Both call sites retry on 429 with backoff; still keep TOTAL concurrent LLM workers across all running processes to ~8-10 or rows silently degrade.

## Pipeline usage
```bash
python3 ./scripts/gmaps_lead_pipeline.py \
  --search "golf course" --location "Florida, United States" --limit 360 \
  --sheet-url "https://docs.google.com/spreadsheets/d/..." --tab "Golf Courses" \
  --include 'golf|country club' \
  --exclude '\bmini\b|miniature|top ?golf|driving range|simulator|indoor' \
  --require-website --min-stars 4 --workers 8
```
Key flags:
- `--location` -> actor `locationQuery`: geocodes and polygon-splits the area. Works for whole states (~10-20 min per state-level scrape). Without it, one map view only.
- `--require-website` / `--min-stars 4` -> actor-NATIVE filters (`website: "withWebsite"`, `placeMinimumStars`). Always prefer native filters: Apify bills ~$3-5 per 1,000 places, so every filtered row is money saved and the cap fills with keepers.
- `--include` / `--exclude` -> case-insensitive regex vs `title + categoryName`, applied BEFORE enrichment (saves LLM cost). Watch substring traps (`mini` matches "Dominion": use `\bmini\b`).
- `--tab` -> worksheet inside one spreadsheet; created with headers if missing. One spreadsheet, one tab per vertical.
- Dedupe vs the sheet happens BEFORE enrichment (lead_id = md5(name|address)), so re-runs and overlapping queries don't re-pay.
- `--from-raw FILE` -> skip scraping, load a paid dataset from JSON; with `--limit N` takes the top-N by rating/reviews AFTER dedupe. Recovery path when a run was killed locally: the Apify run keeps going and its dataset stays retrievable: `client.run(run_id).get()` -> dataset items -> save JSON -> `--from-raw`.
- **Killing a local pipeline does NOT stop the Apify actor run.** Abort via API (`client.run(id).abort()`) or recover the dataset as above.

## Persona verification (the layer that makes the list sellable)
```bash
python3 ./scripts/verify_email_persona.py --sheet_url URL --tab "Golf Courses" \
  --persona "Golf Course Superintendent, Director of Agronomy, ..." \
  --persona_regex "superintendent|agronom|grounds|greenkeeper|turf" \
  --amf --apply
```
Three tiers per unresolved row:
1. **Free**: mine `owner_*` and `team_contacts` (website-scraped staff titles) against `--persona_regex`. Golf clubs list supers on staff pages surprisingly often.
2. **Named emails** (generic locals like info@/proshop@ filtered out) -> Google SERP per email (`apify/google-search-scraper`, ~$3.5/1,000 queries, ~15-30 queries/min) -> Azure judge reads top 20 results and grades closeness: `exact` / `adjacent` (assistant super, dir of course ops, GM at small op) / `unrelated`. LinkedIn titles usually appear in snippets, no page fetch needed.
3. `--amf`: **AnyMailFinder company endpoint** (`v5.1/find-email/company`, 1 credit/domain) returns ALL valid emails for the domain (often 5-12 named people) -> each goes through tier 2. Valid-only rule applies everywhere.

Writes `dm_first_name, dm_last_name, dm_name, dm_title, dm_email, dm_source, dm_status` columns. Re-runs skip `verified*` rows; `--amf` sweeps retry non-verified statuses. `--max_emails_per_row 0` (default) judges every named email. Statuses: `verified_website`, `verified_serp_{conf}`, `verified_adjacent_{conf}`, `wrong_persona`, `no_named_email`, `no_serp_results`.

**Sizing warning:** an uncapped `--amf` sweep over ~1,000 domains produces thousands of SERP queries = several hours. Plan around it.

For owner-led verticals (landscaping, sports complexes) run `amf_dm_fill.py` FIRST (`--category ceo --fallback_category operations`): one call returns name+title+valid email; **misses cost 0 credits**. Hit rate ~20% on tiny companies, ~45% on mid-size. Golf has NO matching AMF category ("operations" returns the clubhouse GM, not the superintendent), so golf skips this and uses the company-emails path.

## Healing and final polish
- `heal_enrichment.py --tab X --apply`: finds rows with a website but ZERO extraction signals (429 storms, transient fetch failures), re-extracts, blanks their dm_ columns so verify reprocesses them. Safe to run alongside appends (writes by rownum in place).
- `clean_polish_tab.py --tab X --min_stars 4 --exclude REGEX --apply`: drops sub-rating/unrated + late noise, sorts verified DMs to top, 18px rows. **Rewrites and reorders the tab: run ONLY when no other process is writing to that tab** (by-rownum writers would corrupt after reorder).
- For a call-ready deliverable while jobs still run: copy verified rows into a curated tab (e.g. "Golf - Verified Superintendents") instead of reordering the source tab.

## Costs (measured 2026-07)
| Component | Cost |
|-----------|------|
| GMaps places (compass actor) | ~$3-5 / 1,000 places |
| Website extraction (Azure gpt-4.1) | ~$0.01-0.02 / lead |
| SERP verification | ~$3.5 / 1,000 emails + ~$0.004 LLM each |
| AMF company search | 1 credit / domain (returns all valid emails) |
| AMF decision-maker | credits only on hit; misses free |

## Ops learnings
- Piping background chains through `grep` buffers stdout: logs look empty while the job works. Log raw and grep afterwards.
- Google Sheets API: batch appends once per run; `batch_update` in chunks of ~25; ~60 writes/min/user quota.
- 3 concurrent state-level scrapes + enrichment is fine; the bottleneck is always enrichment (LLM), never scraping.
