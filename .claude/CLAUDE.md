# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Common Commands

```bash
# Run any skill script directly (each skill bundles its own scripts/)
python3 .claude/skills/<skill-name>/scripts/<script>.py [args]
# Exception: upwork-proposal keeps its scripts at the skill root, not under scripts/
python3 .claude/skills/upwork-proposal/proposal_doc.py [args]      # from a call transcript
python3 .claude/skills/upwork-proposal/proposal_from_jd.py [args]  # from a job description

# scrape-leads: test a scrape (25-item sample) BEFORE a full run — Apify bills per result
python3 .claude/skills/scrape-leads/scripts/scrape_apify.py \
  --query "INDUSTRY" --location "LOCATION" --max_items 25 --no-email-filter --output .tmp/test_leads.json

# Push results to a Google Sheet (note: update_sheet.py is copied into several skills)
python3 .claude/skills/scrape-leads/scripts/update_sheet.py .tmp/leads.json --title "Leads - INDUSTRY"

# Google OAuth setup (Sheets/Drive/Docs) — run once, generates token.json
python3 setup_google_auth.py

# Apify actors (standalone, deployed separately via Apify CLI)
cd healthcare-recruitment-actor  && pip install -r requirements.txt && apify push
cd nchcr-job-board-actor         && pip install -r requirements.txt && apify push
cd productionhub-directory-actor && pip install -r requirements.txt && apify push

# Run an actor locally (reads .actor/../storage/key_value_stores/default/INPUT.json)
cd productionhub-directory-actor && python3 -m src   # set testMode:true in INPUT.json first
```

**Always invoke skill scripts from the repo root** (as written above), never after `cd`-ing into the
skill dir. Google credentials are resolved CWD-relative (`os.path.exists('token.json')`), so from any
other directory auth falls through to the service-account branch and dies with a misleading
`Credentials file 'service_account.json' not found`. Only `gmaps-leads`'s `heal_enrichment.py` and
`verify_email_persona.py` anchor to a `PROJECT_ROOT` constant; the other ~69 scripts do not.

There is no repo-wide test/lint/build step and no root `requirements.txt` — skill scripts run on system
`python3` against already-installed deps (`gspread`, `python-dotenv`, `openai`, `google-auth*`,
`requests`); only the three Apify actors pin their own. Validate by running the specific script against
a small sample and eyeballing the `.tmp/` output.

## LLM provider (IMPORTANT)

The working LLM is **Azure OpenAI**, NOT Anthropic. The `ANTHROPIC_API_KEY` in `.env` is
expired (returns 401). Scripts read these env vars:

- `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_API_VERSION`
- `AZURE_OPENAI_DEPLOYMENT` (quality/one-shot work, currently `gpt-5.1` — used by `proposal_from_jd.py`)
- `AZURE_OPENAI_DEPLOYMENT_FAST` (bulk per-row work, currently `gpt-4.1`)

When adding LLM calls to a script, follow this pattern (Azure client, `*_FAST` deployment for per-row
batches, a small thread pool e.g. `LLM_WORKERS = 8`). Do not reintroduce Anthropic calls without asking.

**The Azure migration is only partial.** Migrated so far: `gmaps-leads`'s LLM scripts
(`extract_website_contacts.py`, `verify_email_persona.py`), `scrape-leads`'s
`classify_decision_makers.py` / `classify_staffing_leads.py` / `find_company_contacts.py`, and
`upwork-proposal/proposal_from_jd.py`. Still hard-coded to the dead Anthropic key (will 401 until ported):
**`casualize-names`** (all scripts), **`classify-leads`**, **`upwork-apply`**,
**`instantly-autoreply`**, **`cross-niche-outliers`**, and `scrape-leads`'s `classify_leads_llm.py` +
`generate_email_variables.py`. Before running any of these, port the LLM call to the Azure pattern
above (see `gmaps-leads/scripts/extract_website_contacts.py` as a reference implementation).

## Architecture

This repo is a **Claude Code Skills** system — bundled capabilities pairing natural-language instructions
(`SKILL.md`) with deterministic Python scripts. Claude orchestrates: reads the `SKILL.md`, runs the right
scripts in order, and self-heals on errors.

```
.claude/
  skills/          # 18 skills, each = SKILL.md + scripts/
  agents/          # Subagents: code-reviewer, research, qa, email-classifier
  settings.local.json

.mcp.json          # MCP servers: ai-ark (lead enrichment) + make — gitignored, holds API keys
.env               # All API keys (Apify, Azure OpenAI, Instantly, Monday, etc.) — gitignored

healthcare-recruitment-actor/   # Standalone Apify actor (Python, async) — 8 sources
  src/__main__.py               #   entrypoint → SCRAPER_MAP → async per-source → merge/dedup
  src/scrapers/                 #   one module per source (linkedin_jobs, nppes_npi, …)
  src/utils/merge.py            #   dedup: domain match → normalized name match

nchcr-job-board-actor/          # Standalone Apify actor — scrapes nchcr.com job board
  src/scraper.py                #   healthcare recruiting firms (name, recruiter, phone, email)

productionhub-directory-actor/  # Standalone Apify actor — productionhub.com (Cloudflare-fronted)
  src/scraper.py                #   patchright + headed Chrome; listing crawl + profile visit

reddit-lead-intelligence.workflow.json  # n8n workflow: Reddit → Apify → lead enrichment
setup_google_auth.py                    # one-time OAuth flow for Google APIs
token.json                              # Google OAuth token (gitignored)
.tmp/                                   # intermediate files (gitignored) — never commit
```

**Repo hygiene:** `.gitignore` covers secrets and `.tmp/` but *not* actor-local `.venv/`,
`storage/`, or `__pycache__/`, nor the `flowchart_*.png` files that land in the repo root when
rendering proposal diagrams (see below). Never `git add -A` blind — stage explicit paths.

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

### Enrichment/outreach conventions (learned on past campaigns)
Removed skills (`b2b-sales-leads-indeed`, `seo-leads-indeed`, deleted Jul 2026 — recover via git
history if needed) established conventions that still apply to any new enrichment/outreach script:
**dry-run by default with `--apply` to spend/write**; AnyMailFinder emails are **accepted only when
`valid`**, never `risky`/`invalid`; fetch homepages with **`curl`, not `requests`** (macOS LibreSSL
fails TLS on some hosts); ground LLM-derived ICPs in the company website, not job descriptions;
Instantly campaigns are always **created PAUSED** for Jude to review and launch.

## MCP servers

`.mcp.json` (gitignored) defines two: **`ai-ark`** (lead enrichment, below) and **`make`**
(Make.com scenarios). Note `settings.local.json` also lists `context7`, `gmail`, and `pandadoc` under
`enabledMcpjsonServers`, but none of them are defined in this repo's `.mcp.json` — those entries are
inert here unless the server comes from a global config.

### AI Ark (lead enrichment)

The `ai-ark` HTTP MCP server (`api.ai-ark.com`). Tools: `company_search`,
`people_search`, `email_finder`, `mobile_phone_finder`, `industry/location/technology_search`,
`reverse_people_lookup`, `personality_analysis`, export tools. Used to enrich scraped companies with
**decision-maker name + title + LinkedIn + email**.
MCP tools become callable after a Claude Code restart + approving the `ai-ark` trust prompt; raw `curl`
against the endpoint is a working fallback. For batch enrichment, prefer a deterministic script that
calls AI Ark over its **HTTP JSON-RPC endpoint directly** (stateless, token read from the gitignored
`.mcp.json`) so the whole run is one reproducible script with no interactive MCP prompt. A reference
implementation (`find_dm.py` + `AI_ARK_HANDOFF.md` in the removed `b2b-sales-leads-indeed` skill) is
recoverable from git history.

## Skills (19)

### Lead Generation
| Skill | What it does |
|-------|-------------|
| `scrape-leads` | Apify `code_crafter/leads-finder` → LLM classify → email enrich → Google Sheet |
| `gmaps-leads` | Google Maps → website scrape → contact extraction → Sheet, plus a persona-verification stack (staff-page mining → AMF company emails → Google SERP + LLM judge → dm_* columns) and AMF decision-maker fill for owner-led verticals |
| `classify-leads` | LLM classification for complex distinctions (e.g. product SaaS vs agencies) |
| `casualize-names` | Formal → casual names for cold-email personalization |
| `build-scrapers` | Documentation-only: guides `00`–`07` for building custom Apify scrapers, plus a UK M&A pipeline build guide. **Has no `SKILL.md`**, so it is not auto-invocable via the Skill tool — read the `.md` files directly. |

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
| `upwork-proposal` | Discovery-call transcript + case-study Sheet → client-facing Upwork proposal as a native Google Doc via `proposal_doc.py` (Drive HTML-upload+convert; no Docs API). Bricolage Grotesque, reply-only CTA, Upwork-consultant byline, em dashes blocked at upload. Has a safe-edit (export→edit→update) flow once the client hand-edits. Also handles a single pasted JD via `proposal_from_jd.py` (LLM path, or `--body-html` to render a hand-authored body with the same styling guards) — this, not `upwork-apply`, is the path for one hand-picked job; see its SKILL.md for the skill-choice rules. The doc is only the attachment; pair it with `upwork-cover-letter` for the text that actually gets submitted. |
| `upwork-cover-letter` | Writes the actual Upwork cover letter text Jude submits (job post + his Loom link, optionally a proposal-doc link and client name → copy-pasteable letter). Fixed structure: hook with Loom link inside Upwork's ~230-char preview window, credibility paragraph pulled from the verified claims bank, optional technical-insight paragraph, standard bio/close/PS. Has a `scripts/check_hook_length.py` helper for the hook's character budget. |
| `upwork-apply` | Scrape Upwork jobs → generate personalized proposals. Batch-only (needs Apify-scraped job arrays, truncates JDs to 500 chars) — not for a single hand-picked job |
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
| `add-webhook` | Add a Modal webhook (directive + `webhooks.json` entry). **Note:** targets a Modal orchestrator (`execution/`, `directives/`) that lives in a separate repo, not this tree; its own `scripts/` dir is empty. |

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

- **`healthcare-recruitment-actor/`** — scrapes 8 sources (LinkedIn Jobs, NPPES NPI, 6 state registries,
  niche directories, ASA members, FDD franchisees, SAM.gov, NCHCR) to find healthcare staffing agencies
  not in Apollo/ZoomInfo. ~1,500–2,500 unique agencies/run. Entry `src/__main__.py` → `SCRAPER_MAP` →
  async per source → merge/dedup in `src/utils/merge.py`.
- **`nchcr-job-board-actor/`** — scrapes the NCHCR (nchcr.com) job board for healthcare recruiting firms
  (company, recruiter, phone, email; website derived from email domain). One deduped record per firm.
  The same source also exists as the `nchcr` module inside the healthcare actor — changes to the scrape
  logic likely apply to both.
- **`productionhub-directory-actor/`** — scrapes productionhub.com for video production companies.
  Two modes off one input: a listing crawl over `{categorySlug, locationPath, metroKey}` targets, or
  `profileIds` visit-only (re-enrich rows that already passed classification). Records push per
  finished target, so a killed run still yields data. **Anti-bot is the whole design and is fragile —
  do not "simplify" it:** the site is Cloudflare-fronted, so it uses `patchright` (not plain
  playwright), `launch_persistent_context(channel="chrome")`, `headless=False` under `xvfb-run` in
  the Dockerfile, and a **sticky** Apify residential session (`new_url(session_id=...)`) because
  `cf_clearance` is issued to a single IP. Plain headless Chromium, bare `chromium.launch()`, and
  rotating proxies each hang on "Verification successful. Waiting for … to respond". A company
  website only ever appears free-text inside the profile description, so `extract_website()`
  regex-mines it — there is no website field.

## Rendering images (proposal flowcharts, mockups)

Diagrams are authored as fixed-layout HTML at 2x scale and screenshotted with the **Playwright MCP**
browser. Two constraints that bite every time: `file://` URLs are blocked, so serve the directory with
`python3 -m http.server <port>` and navigate to localhost (kill the server after); and
`browser_take_screenshot` writes the PNG to the **repo root**, not the scratchpad — read it back,
eyeball it, then move or delete it. Full recipe (palette, arrow SVG underlay, base64 embed that
survives the Drive HTML→Doc conversion) lives in `upwork-proposal/SKILL.md`.

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
