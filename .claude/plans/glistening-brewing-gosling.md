# Plan: Generate Personalized Cold Emails for Middle East Founders

## Context

We have a Google Sheet with 58 recently-funded Middle East tech companies. We've already:
1. Split founder names into Founder 1-5 First/Last Name columns
2. Found missing founders via LinkedIn scraping (23/26 found)
3. Found 69/95 founder emails via AnyMailFinder

Now Jude wants to send personalized cold emails to these founders using this template:

> Hey {{first_name}}, Been keeping an eye on {{startup type}} in the GCC building up their team after a new funding round. Most of them prefer private access to pre-vetted {{Type of talent}}, and I connect them with {{type of recruiters}} who understand the {{type of talent}} landscape and can give them an edge before the roles are live. If this is timely for you, happy to share more details.

The variables `{{startup type}}`, `{{Type of talent}}`, and `{{type of recruiters}}` need to be derived from each company's Industries/Description columns.

## Approach: LLM Enrichment → Write Variables to Google Sheet

### Single script: `generate_email_variables.py`

Write a script that:

1. **Reads the sheet** — pulls all 58 company rows
2. **For each company**, calls Claude Haiku to generate 3 personalization variables from the Industries + Description columns:
   - `Startup Type` — e.g., "FinTech startups", "HealthTech startups", "PropTech startups"
   - `Type of Talent` — e.g., "tech talent", "engineering talent", "financial engineering talent"
   - `Type of Recruiters` — e.g., "tech recruiters", "specialized FinTech recruiters"
3. **Writes 3 new columns** to the sheet: `Startup Type`, `Type of Talent`, `Type of Recruiters`

**Why LLM over rule-based mapping:** Industries column has varied formats (e.g., "Financial Services, FinTech" vs "Artificial Intelligence, Machine Learning"). An LLM interprets nuance and generates natural-sounding phrases that fit the email template. Cost: ~$0.01 for 58 companies with Haiku.

**Prompt for Claude:**
```
Given this company's industry and description, generate personalization variables for a recruitment cold email targeting GCC tech startups.

Company: {name}
Industries: {industries}
Description: {description}

Return JSON only:
{
  "startup_type": "<concise industry> startups (e.g., 'FinTech startups', 'AI startups')",
  "talent_type": "<domain-specific> talent (e.g., 'tech talent', 'engineering talent')",
  "recruiter_type": "<specialized> recruiters (e.g., 'tech recruiters', 'FinTech recruiters')"
}
```

**Script features:**
- `--test` flag: run on first 3 companies only
- `--dry_run` flag: generate variables but don't write to sheet
- `--resume` flag: skip companies already enriched (check if Startup Type column is filled)
- Sequential Haiku calls (58 calls takes ~15 seconds, no need for batching)
- Checkpoint to `.tmp/email_variables_checkpoint.json`

## Files

- **New:** `.claude/skills/scrape-leads/scripts/generate_email_variables.py`

## Existing code to reuse

- **Google Sheets auth:** `find_founder_emails.py:45-67` — `get_credentials()` + `read_sheet()`
- **Sheet column creation:** `find_founder_emails.py:225-239` — ensure column exists, resize if needed
- **Checkpoint pattern:** `find_founder_emails.py:147-157`

## Verification

1. Run `generate_email_variables.py --test` on 3 companies to validate LLM output quality
2. Check the sheet — new columns should have natural-sounding values that read well in the template
3. Run full enrichment for all 58 companies
4. Spot-check 5 rows: values make sense for the company's industry, read naturally in the email template
