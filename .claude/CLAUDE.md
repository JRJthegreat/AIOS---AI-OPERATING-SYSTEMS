# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Common Commands

```bash
# Run any skill script directly (each skill bundles its own scripts/)
python3 .claude/skills/<skill-name>/scripts/<script>.py [args]

# scrape-leads: test a scrape (25-item sample) BEFORE a full run — Apify bills per result
python3 .claude/skills/scrape-leads/scripts/scrape_apify.py \
  --query "INDUSTRY" --location "LOCATION" --max_items 25 --no-email-filter --output .tmp/test_leads.json

# Indeed hiring-signal skills (b2b-sales-leads-indeed / seo-leads-indeed): scrape_and_pull.py is the
# orchestrator (keyword × city grid). It writes straight to a Google Sheet — no .json output file.
# Test with --limit 25 (per-combo cap) before the default --limit 1000 full run.
python3 -W ignore .claude/skills/seo-leads-indeed/scripts/scrape_and_pull.py --limit 25
#   useful flags: --keywords "a,b"  --cities "Austin, TX;Remote"  --sheet_url URL  --dry_run  --yes

# Push results to a Google Sheet (note: update_sheet.py is copied into several skills)
python3 .claude/skills/scrape-leads/scripts/update_sheet.py .tmp/leads.json --title "Leads - INDUSTRY"

# Google OAuth setup (Sheets/Drive/Docs) — run once, generates token.json
python3 setup_google_auth.py

# Apify actors (standalone, deployed separately via Apify CLI)
cd healthcare-recruitment-actor && pip install -r requirements.txt && apify push
cd nchcr-job-board-actor       && pip install -r requirements.txt && apify push
```

There is no repo-wide test/lint/build step — this is a scripts + skills repo. Validate by running the
specific script against a small sample and eyeballing the `.tmp/` output.

## LLM provider (IMPORTANT)

Classification/extraction scripts call **Azure OpenAI `gpt-4.1`**, NOT Anthropic. The `ANTHROPIC_API_KEY`
in `.env` is expired (returns 401). Scripts read these env vars:

- `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_API_VERSION`
- `AZURE_OPENAI_DEPLOYMENT` (default model) / `AZURE_OPENAI_DEPLOYMENT_FAST` (bulk per-row work, default `gpt-4.1`)

When adding LLM calls to a script, follow this pattern (Azure client, `*_FAST` deployment for per-row
batches, a small thread pool e.g. `LLM_WORKERS = 8`). Do not reintroduce Anthropic calls without asking.

## Architecture

This repo is a **Claude Code Skills** system — bundled capabilities pairing natural-language instructions
(`SKILL.md`) with deterministic Python scripts. Claude orchestrates: reads the `SKILL.md`, runs the right
scripts in order, and self-heals on errors.

```
.claude/
  skills/          # 20 skills, each = SKILL.md + scripts/
  agents/          # Subagents: code-reviewer, research, qa, email-classifier
  settings.local.json

.mcp.json          # ai-ark MCP server (lead enrichment) — gitignored, holds API key
.env               # All API keys (Apify, Azure OpenAI, Instantly, Monday, etc.) — gitignored

healthcare-recruitment-actor/   # Standalone Apify actor (Python, async) — 7 sources
  src/__main__.py               #   entrypoint → SCRAPER_MAP → async per-source → merge/dedup
  src/scrapers/                 #   one module per source (linkedin_jobs, nppes_npi, …)
  src/utils/merge.py            #   dedup: domain match → normalized name match

nchcr-job-board-actor/          # Standalone Apify actor — scrapes nchcr.com job board
  src/scraper.py                #   healthcare recruiting firms (name, recruiter, phone, email)

reddit-lead-intelligence.workflow.json  # n8n workflow: Reddit → Apify → lead enrichment
setup_google_auth.py                    # one-time OAuth flow for Google APIs
token.json                              # Google OAuth token (gitignored)
.tmp/                                   # intermediate files (gitignored) — never commit
```

**Key principle:** Local files are only for processing. Deliverables live in Google Sheets, Slides, or
other cloud services — the Sheet URL (not a local file) is what you hand to Jude.

### Shared script toolbox
`scrape-leads/scripts/` is the master toolbox (~25 scripts): Apify scraping, multiple LLM classifiers,
email/company/domain enrichment, Instantly push, and the per-source scrapers the healthcare actor mirrors
(`scrape_nppes_npi.py`, `scrape_state_registries.py`, `scrape_asa_members.py`, …). `update_sheet.py` is
**copied** into `scrape-leads`, `gmaps-leads`, `classify-leads`, and `upwork-apply` — if you fix a bug in
one, check whether the others need the same fix. These copies have **already drifted**: only
`scrape-leads`'s copy has the `set_row_height(18)` step; the other three lack it. Treat `scrape-leads`'s
as the canonical version when reconciling.

### Indeed hiring-signal pattern (shared by two skills)
`b2b-sales-leads-indeed` and `seo-leads-indeed` mirror each other and follow the same pipeline:
**scrape Indeed job postings** (`valig~indeed-jobs-scraper`, `title` × `location` grid) → **size cap**
(≤500 employees) → **per-row filter** (regex gate + Azure LLM reads each job description) → **dedupe by
company** (newest posting wins) → enrich domains → **Google Sheet**. The premise: an open req is a
high-intent buying signal. The LLM filter exists to strip noise (agencies, managers, wrong role types).
These differ from `scrape-leads`, which uses `code_crafter/leads-finder` (people, not job postings).

### b2b-sales-leads-indeed outreach pipeline (phases 3–5, b2b only)
`b2b-sales-leads-indeed` extends the shared Indeed pipeline past the Sheet into a full
enrichment→outreach run; `seo-leads-indeed` stops at the company list. One row per company, each
phase its own script, **dry-run by default — `--apply` spends/writes**. Sheet cols T–AE are reserved
for this:
- **Phase 3 `find_dm.py`** — AI Ark `people_search` (by domain, fallback to name) picks the best
  decision-maker (sales leadership first, then Founder/CEO) → AnyMailFinder resolves the email
  (**accept `valid` only**, never `risky`/`invalid`) → writes cols T–Y (DM Name/Title/LinkedIn/Email/
  First/Last). Skips rows that already have a DM unless `--force`.
- **Phase 4a `derive_icp_web.py`** — curls each homepage (`curl`, not `requests`: macOS LibreSSL
  fails TLS on some hosts), Azure `gpt-4.1` infers the buyer persona → col AD. Grounded in the
  website, NOT the job description (JD-derived ICPs were confidently wrong); low confidence → generic.
- **Phase 4 `generate_emails.py`** — one Azure `gpt-4.1` call/lead → casual company name + clean
  role + ICP, rendered into a locked template → body col Z, ICP col AD, subject col AE.
- **Phase 5 `push_emails_to_instantly.py`** — creates an Instantly campaign (single step using
  `{{subject}}`/`{{email_body}}`) from rows with a valid email + body. **Created PAUSED — review and
  launch it in Instantly yourself.**

## AI Ark MCP (lead enrichment)

`.mcp.json` configures the `ai-ark` HTTP MCP server (`api.ai-ark.com`). Tools: `company_search`,
`people_search`, `email_finder`, `mobile_phone_finder`, `industry/location/technology_search`,
`reverse_people_lookup`, `personality_analysis`, export tools. Used to enrich scraped companies with
**decision-maker name + title + LinkedIn + email** (e.g. filling Sheet columns T–Y on the b2b campaign).
MCP tools become callable after a Claude Code restart + approving the `ai-ark` trust prompt; raw `curl`
against the endpoint is a working fallback. For batch enrichment, prefer the deterministic-script path:
`b2b-sales-leads-indeed/scripts/find_dm.py` calls AI Ark over its **HTTP JSON-RPC endpoint directly**
(stateless, token read from the gitignored `.mcp.json`) so the whole run is one reproducible script with
no interactive MCP prompt. See `.claude/skills/b2b-sales-leads-indeed/AI_ARK_HANDOFF.md`.

## Skills (20)

### Lead Generation
| Skill | What it does |
|-------|-------------|
| `scrape-leads` | Apify `code_crafter/leads-finder` → LLM classify → email enrich → Google Sheet |
| `b2b-sales-leads-indeed` | Indeed postings → ≤500 size cap → regex+Azure-LLM filter (keep IC B2B sales reps; drop agencies/managers/AEs/B2C/commission-only) → dedupe → Sheet |
| `seo-leads-indeed` | Indeed postings → drop SEO/marketing agencies (name + LLM) → ICP-tag (Tier A AEO/AI-search vs Tier B traditional) → dedupe → Sheet (built for PN Digital) |
| `gmaps-leads` | Google Maps → website scrape → contact extraction → Sheet, plus a persona-verification stack (staff-page mining → AMF company emails → Google SERP + LLM judge → dm_* columns) and AMF decision-maker fill for owner-led verticals |
| `classify-leads` | LLM classification for complex distinctions (e.g. product SaaS vs agencies) |
| `casualize-names` | Formal → casual names for cold-email personalization |
| `build-scrapers` | Documentation-only: guides for building custom Apify scrapers |

### Email & Outreach
| Skill | What it does |
|-------|-------------|
| `gmail-inbox` | Read/manage email across multiple Gmail accounts |
| `gmail-label` | Parallel subagent classification → bulk-apply labels (Action/Waiting/Reference) |
| `instantly-autoreply` | Auto-generate replies to Instantly threads using knowledge bases |

### Sales & Proposals
| Skill | What it does |
|-------|-------------|
| `create-proposal` | PandaDoc proposal from sheet data or call transcript. **Stub — directory is currently empty (no `SKILL.md`/scripts); needs rebuilding before use.** |
| `upwork-proposal` | Discovery-call transcript + case-study Sheet → client-facing Upwork proposal as a native Google Doc via `proposal_doc.py` (Drive HTML-upload+convert; no Docs API). Bricolage Grotesque, reply-only CTA, Upwork-consultant byline, em dashes blocked at upload. Has a safe-edit (export→edit→update) flow once the client hand-edits. |
| `upwork-apply` | Scrape Upwork jobs → generate personalized proposals |
| `design-website` | Single-page HTML mockup for a prospect (buildinamsterdam.com aesthetic) |
| `monday-crm` | Law-firm CRM on Monday.com — cases, leads, hearings, tasks |

### Content
| Skill | What it does |
|-------|-------------|
| `cross-niche-outliers` | Find viral YouTube videos from adjacent niches for content inspiration |
| `recreate-thumbnails` | Face-swap YouTube thumbnails |
| `generate-report` | Weekly Canada weather reports → PDF |

### Research
| Skill | What it does |
|-------|-------------|
| `literature-research` | PubMed + academic database search |

### Infrastructure
| Skill | What it does |
|-------|-------------|
| `add-webhook` | Add a Modal webhook (directive + `webhooks.json` entry). **Note:** targets a Modal orchestrator (`execution/`, `directives/`) that lives in a separate repo, not this tree. |

## Subagents

Defined in `.claude/agents/`. Lighter-weight, unbiased (no parent context). All code fixes happen in the
parent — subagents are read-only reporters.

| Agent | Use case |
|-------|---------|
| `code-reviewer` | PASS/FAIL review by severity — zero context, no bias |
| `research` | Web + file research without polluting main context |
| `qa` | Generate + run tests, report results |
| `email-classifier` | Classify email chunks in parallel (used by `gmail-label`) |

**Build workflow:** Write → spawn `code-reviewer` + `qa` in parallel → parent applies all fixes → ship.

## Standalone Apify Actors

Deployed to Apify separately from the skills system (`apify push`).

- **`healthcare-recruitment-actor/`** — scrapes 7 sources (LinkedIn Jobs, NPPES NPI, 6 state registries,
  niche directories, ASA members, FDD franchisees, SAM.gov) to find healthcare staffing agencies not in
  Apollo/ZoomInfo. ~1,500–2,500 unique agencies/run. Entry `src/__main__.py` → `SCRAPER_MAP` → async per
  source → merge/dedup in `src/utils/merge.py`.
- **`nchcr-job-board-actor/`** — scrapes the NCHCR (nchcr.com) job board for healthcare recruiting firms
  (company, recruiter, phone, email; website derived from email domain). One deduped record per firm.

## Google OAuth

Scopes: Sheets + Drive + Docs. Run `python3 setup_google_auth.py` once with `credentials.json` present to
generate `token.json`. Skills read `token.json` directly — no per-skill auth setup needed.

## Operating Principles

- **Self-anneal:** when a script errors, fix it, test it, then update its `SKILL.md` with what you learned.
- **Scripts over prose:** push complexity into deterministic scripts; Claude handles decision-making only.
- **Skills are living docs:** update `SKILL.md` when you discover API constraints or better approaches.
  Don't create new skills without asking.
- **Stick to the agreed tool/approach** — don't switch tools (especially cost-affecting ones) without
  asking Jude first.
- **Apify bills per result:** always run the small test, eyeball quality, surface projected cost to Jude,
  then fire the full run.
- **`.tmp/` for intermediates:** all intermediate files go in `.tmp/` (gitignored). Never commit them.
