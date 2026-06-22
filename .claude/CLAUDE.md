# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Common Commands

```bash
# Run a skill script directly
python3 .claude/skills/<skill-name>/scripts/<script>.py [args]

# Test a lead scrape (25-item sample before full run)
python3 .claude/skills/scrape-leads/scripts/scrape_apify.py \
  --query "INDUSTRY" --location "LOCATION" --max_items 25 --no-email-filter --output .tmp/test_leads.json

# Push to Google Sheet
python3 .claude/skills/scrape-leads/scripts/update_sheet.py .tmp/leads.json --title "Leads - INDUSTRY"

# Google OAuth setup (Sheets/Drive/Docs)
python3 setup_google_auth.py

# Deploy webhooks to Modal
modal deploy execution/modal_webhook.py

# Healthcare Recruitment Actor (Apify)
cd healthcare-recruitment-actor && pip install -r requirements.txt
# Deploy via Apify CLI: apify push
```

## Architecture

This repo is a **Claude Code Skills** system — bundled capabilities that combine natural-language instructions (`SKILL.md`) with deterministic Python scripts. Claude orchestrates by reading `SKILL.md`, running the right scripts in order, and self-healing on errors.

```
.claude/
  skills/          # 20 skills, each = SKILL.md + scripts/
  agents/          # Subagent definitions (code-reviewer, research, qa, email-classifier)
  settings.local.json

healthcare-recruitment-actor/   # Standalone Apify actor (Python, async)
  src/
    __main__.py                 # Actor entrypoint — orchestrates 7 scrapers
    scrapers/                   # One module per source (linkedin_jobs, nppes_npi, etc.)
    utils/merge.py              # Dedup logic: domain match → normalized name match
  Dockerfile, requirements.txt

reddit-lead-intelligence.workflow.json  # n8n workflow: Reddit → Apify → lead enrichment
setup_google_auth.py                    # One-time OAuth flow for Google APIs
token.json                              # Google OAuth token (gitignored)
.tmp/                                   # Intermediate files during processing (never commit)
```

**Key principle:** Local files are only for processing. Deliverables live in Google Sheets, Slides, or other cloud services.

## Skills (20 active)

### Lead Generation
| Skill | What it does |
|-------|-------------|
| `scrape-leads` | Apify `code_crafter/leads-finder` → LLM classify → email enrich → Google Sheet |
| `b2b-sales-leads-indeed` | Indeed job postings (`valig~indeed-jobs-scraper`) for companies hiring B2B sales reps → size cap (≤500) → per-row filter (regex + Azure LLM) keeping only IC B2B sales-rep roles; drops agencies/managers/AEs/B2C-selling/commission-only/non-sales → dedupe → Sheet |
| `gmaps-leads` | Google Maps → website scrape → Claude contact extraction → Sheet |
| `classify-leads` | LLM classification for complex distinctions (e.g. product SaaS vs agencies) |
| `casualize-names` | Formal → casual names for cold email personalization |
| `build-scrapers` | Documentation-only skill: guides for building custom Apify scrapers |

### Email & Outreach
| Skill | What it does |
|-------|-------------|
| `gmail-inbox` | Read/manage email across multiple Gmail accounts |
| `gmail-label` | Parallel subagent classification → bulk apply labels (Action/Waiting/Reference) |
| `instantly-autoreply` | Auto-generate replies to Instantly threads using knowledge bases |

### Sales & Proposals
| Skill | What it does |
|-------|-------------|
| `create-proposal` | PandaDoc proposal from sheet data or call transcript |
| `upwork-apply` | Scrape Upwork jobs → generate personalized proposals |
| `design-website` | Single-page HTML mockup for a prospect (buildinamsterdam.com aesthetic) |
| `monday-crm` | Law firm CRM on Monday.com — cases, leads, hearings, tasks |

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

### Client Onboarding
| Skill | What it does |
|-------|-------------|
| `onboarding-kickoff` | Post-kickoff automation: leads + campaigns + auto-reply setup |

### Infrastructure
| Skill | What it does |
|-------|-------------|
| `add-webhook` | Add Modal webhook: create directive → update webhooks.json → deploy |
| `modal-deploy` | `modal deploy execution/modal_webhook.py` |
| `local-server` | Run orchestrator locally with Cloudflare tunnel |

## Subagents

Defined in `.claude/agents/`. Lighter-weight, unbiased (no parent context). All code fixes happen in the parent — subagents are read-only reporters.

| Agent | Use case |
|-------|---------|
| `code-reviewer` | PASS/FAIL review by severity — zero context, no bias |
| `research` | Web + file research without polluting main context |
| `qa` | Generate + run tests, report results |
| `email-classifier` | Classify email chunks in parallel (used by `gmail-label`) |

**Build workflow:** Write → spawn `code-reviewer` + `qa` in parallel → parent applies all fixes → ship.

## Healthcare Recruitment Actor

Standalone Apify actor in `healthcare-recruitment-actor/`. Scrapes 7 sources (LinkedIn Jobs, NPPES NPI, 6 state registries, niche directories, ASA members, FDD franchisees, SAM.gov) to find healthcare staffing agencies not indexed in Apollo/ZoomInfo. Outputs 1,500–2,500 unique agencies per full run. Entry: `src/__main__.py` → `SCRAPER_MAP` → async per-source runs → merge/dedup in `utils/merge.py`.

## Google OAuth

Scopes: Sheets + Drive + Docs. Run `python3 setup_google_auth.py` once with `credentials.json` present to generate `token.json`. Skills read `token.json` directly — no per-skill auth setup needed.

## Operating Principles

- **Self-anneal:** When a script errors, fix it, test it, update the SKILL.md with what you learned.
- **Scripts over prose:** Push complexity into deterministic scripts. Claude handles decision-making only.
- **Skills are living docs:** Update SKILL.md when you discover API constraints or better approaches. Don't create new Skills without asking.
- **`.tmp/` for intermediates:** All intermediate files go in `.tmp/` (gitignored). Never commit them.
