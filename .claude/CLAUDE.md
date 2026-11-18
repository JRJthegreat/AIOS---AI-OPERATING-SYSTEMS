# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Common Commands

```bash
# Run any skill script from the REPO ROOT (each skill bundles its own scripts/)
python3 .claude/skills/<skill-name>/scripts/<script>.py [args]

# upwork-proposal keeps its two builders at the skill root; its scripts/ holds the linter
python3 .claude/skills/upwork-proposal/proposal_doc.py create --title "T" --html .tmp/body.html  # also: update --id, export --id, sheet --id
python3 .claude/skills/upwork-proposal/proposal_from_jd.py --jd-file .tmp/jd.txt --client "Name"  # --body-html F renders a hand-authored body instead

# The repo's only lint gate. Run on the proposal body HTML BEFORE rendering/upload.
# Fails on: em dashes, [bracketed placeholders], a missing <p>&nbsp;</p> gap between blocks,
# zero or >1 <h1>, any <table>, and a body over 1,800 words (warns over 1,200). The audit-section
# requirement was retired Nov 3 2026 (docs went back to the winning letter format).
python3 .claude/skills/upwork-proposal/scripts/check_proposal_html.py .tmp/body.html [--allow-long]

# Cover-letter hook vs Upwork's ~230-char preview cutoff (arg, or stdin via pbpaste)
python3 .claude/skills/upwork-cover-letter/scripts/check_hook_length.py "Hi Name. ... https://loom.com/..."

# scrape-leads: 25-item test scrape BEFORE any full run (Apify bills per result)
python3 .claude/skills/scrape-leads/scripts/scrape_apify.py \
  --query "INDUSTRY" --location "LOCATION" --max_items 25 --no-email-filter --output .tmp/test_leads.json

# Push results to a Google Sheet
python3 .claude/skills/scrape-leads/scripts/update_sheet.py .tmp/leads.json --sheet_name "Leads - INDUSTRY"

# upwork-followups: read | plan | digest | upsert [--notified] are steps of SKILL.md's Run section
# (plan needs the classified.json the agent writes from the MCP scan), not standalone commands
launchctl kickstart gui/$(id -u)/com.nexam.upwork-followups   # fire the unattended run now; log in ~/Library/Logs/upwork-followups/
launchctl kickstart gui/$(id -u)/com.nexam.upwork-job-alerts  # fresh-job sweep now (:07/:37, 15:00-05:37 Taipei); JOB_ALERTS_NOTIFY=<test inbox> scripts/run.sh for a test

# Google OAuth: one-time, needs credentials.json, writes token.json. The script requests Sheets + Drive +
# Docs; the current token.json predates the Docs scope and still works because Drive covers Docs API calls
python3 setup_google_auth.py

# Regenerate the Codex port after editing any skill, agent, or this file (dry run without --apply)
python3 sync_codex_mirror.py --apply

# Apify actors: deploy from inside the actor dir
cd <actor-dir> && pip install -r requirements.txt && apify push
cd productionhub-directory-actor && python3 -m src   # local run off storage/key_value_stores/default/INPUT.json; set testMode:true first
```

**Run skill scripts from the repo root, never after `cd`-ing into a skill dir.** Google auth is
resolved CWD-relative (`os.path.exists('token.json')`); from anywhere else it falls through to the
service-account branch and dies with a misleading `Credentials file 'service_account.json' not found`.
Only `gmaps-leads`'s `heal_enrichment.py` and `verify_email_persona.py` anchor to a `PROJECT_ROOT`.

There is no build step, test suite, or root `requirements.txt`. Skill scripts run on the system
`python3`, **which is 3.9** (no `match`, no runtime `X | Y` types, no `tomllib`), against
already-installed deps (`gspread`, `python-dotenv`, `openai`, `google-auth*`, `requests`); only the
Apify actors pin their own. Validate a change by running the script on a small sample and checking the
`.tmp/` output. When logic warrants real tests, write them throwaway in `.tmp/` and run
`python3 -m pytest .tmp/test_x.py` (example: `.tmp/test_find_company_domains.py`).

## LLM provider (IMPORTANT)

Use **Azure OpenAI**, not Anthropic: `ANTHROPIC_API_KEY` in `.env` is expired (401, rechecked
Oct 6 2026). Env vars:

- `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_API_VERSION`
- `AZURE_OPENAI_DEPLOYMENT` = `gpt-5.1`, for quality/one-shot work (`proposal_from_jd.py`)
- `AZURE_OPENAI_DEPLOYMENT_FAST` = `gpt-4.1`, for bulk per-row work

New LLM calls follow that pattern: Azure client, the `*_FAST` deployment for per-row batches, a small
thread pool (the reference takes `--workers`, default 5; the scrape-leads Azure classifiers hardcode
`MAX_WORKERS = 10`). Reference implementation: `gmaps-leads/scripts/extract_website_contacts.py`.
Don't reintroduce Anthropic calls without asking.

**Still on the dead key** (port to Azure before running): `casualize-names`, `classify-leads`,
`instantly-autoreply`, and `scrape-leads`'s `classify_leads_llm.py` + `generate_email_variables.py`.

## Architecture

A Claude Code Skills system: each skill pairs instructions (`SKILL.md`) with deterministic Python
scripts. Claude reads the `SKILL.md`, runs the scripts in order, and fixes them when they break.

```
.claude/
  skills/              # one dir per skill (build-scrapers is docs-only, no SKILL.md)
  agents/              # subagents: code-reviewer, research, qa
  settings.local.json  # git push / reset --hard / clean are DENIED
.mcp.json              # MCP servers ai-ark, make, upwork (gitignored, holds keys)
.env                   # all API keys (gitignored)
setup_google_auth.py   # one-time Google OAuth -> token.json (gitignored)
sync_codex_mirror.py   # regenerates the Codex port (see Repo hygiene)
healthcare-recruitment-actor/  nchcr-job-board-actor/  productionhub-directory-actor/   # Apify actors
reddit-lead-intelligence.workflow.json   # n8n workflow: Reddit -> Apify -> lead enrichment
.tmp/                  # intermediates (gitignored)
```

**Local files are only for processing.** Deliverables live in Google Sheets/Docs/Slides; hand Jude
the URL, not a local path.

### Repo hygiene

- `.gitignore` covers secrets, `.tmp/`, actor `.venv/` / `storage/` / `__pycache__/`,
  `.playwright-mcp/`, root `flowchart_*.png` renders, the `campaign_archive` symlink, and the Codex
  port. Even so, **never `git add -A`**: stage explicit paths.
<!-- codex:skip-start -->
- **The Codex port is generated, never edited.** `.agents/skills/`, `.codex/agents/*.toml` and
  `AGENTS.md` are an OpenAI Codex port Jude still runs, all built from `.claude/` by
  `sync_codex_mirror.py`. Edit `.claude/` only, then rerun the sync. It rewrites paths only, never
  the word "Claude", because skill text holds facts about Jude's own tooling. `.codex/config.toml`
  (Codex's MCP config, holds the Make auth header) is hand-maintained and the sync never touches it.
<!-- codex:skip-end -->
- `.tmp/` is never cleaned automatically. Delete a job's files once Jude confirms the deliverable
  was sent. For a bulk cleanup, move entries older than ~30 days to the macOS Trash with
  `/usr/bin/trash` (recoverable), skipping still-open projects; never `rm`.

### Shared script toolbox

`scrape-leads/scripts/` is the master toolbox: Apify scraping, LLM classifiers, email/company/domain
enrichment, Instantly push, and the per-source scrapers the healthcare actor mirrors.
`update_sheet.py` is **copied** into `scrape-leads`, `gmaps-leads` and `classify-leads`, and the
copies have drifted: only `scrape-leads`'s has the `set_row_height(18)` step. Treat that one as
canonical and port fixes to the others.

### Enrichment/outreach conventions

For any new enrichment or outreach script:

- Dry-run by default, `--apply` to spend or write.
- AnyMailFinder emails are accepted only when `valid`, never `risky`/`invalid`.
- Fetch homepages with `curl`, not `requests` (macOS LibreSSL fails TLS on some hosts).
- Ground LLM-derived ICPs in the company website, not job descriptions.
- Instantly campaigns are always created PAUSED for Jude to review and launch.

## MCP servers

`.mcp.json` defines `ai-ark`, `make` and `upwork`. `settings.local.json` also enables
`chrome-devtools`, `context7`, `gmail` and `pandadoc`, which aren't defined here; they only work if
a global config provides them.

### Upwork

Official server at `https://mcp.upwork.com/mcp`, OAuth 2.1 + PKCE only: authorize with `/mcp` in an
interactive terminal session. A headless session can't, and the server returns 401 until it's done.

- Every call needs `org_uid` from `list_accounts`: Jude TALENT `1318336437461753857`, NEXAM CLIENT
  `2053682225683378013`.
- **Pull a JD:** `find_jobs` action=`get` with the full job URL as `params.id`. It returns the
  description, contract terms, bid stats, client spend/feedback and connects cost.
  `get_job_posting` is client-side only and 403s on the freelancer org.
- **Search:** `find_jobs` action=`search` takes `title` (title-only, ANDed words) or `query`
  (whole posting, semantic), never both. `save_job` / `find_saved_jobs` manage the saved list. No
  keyword- or profile-ranking tool exists.
- **Apply:** `manage_proposals`, `list_freelancer_proposals`, `get_draft` / `confirm_draft`,
  `get_preview` / `confirm_preview`. Attach a doc with `start_attachment_upload` →
  `confirm_attachment_upload` → `store_uploaded_files` (`get_upload_status` to poll).
- **Pipeline:** `get_profile` / `update_profile`, `boost_profile`, `get_rate_insights`,
  `get_freelancer_dashboard` / `get_freelancer_financials`, `list_contracts` / `update_contract` /
  `end_contract`, `list_milestones` / `manage_milestones` / `submit_milestones`, `get_messages` /
  `send_message`, `list_offers` / `respond_to_offer`.
- Call `get_tool_help` before first use of anything beyond `find_jobs`; argument shapes aren't
  recorded here.

**Confirm with Jude before anything that submits, sends, spends Connects, or changes a contract or
profile:** `manage_proposals`, `confirm_draft`, `confirm_preview`, `send_message`,
`respond_to_offer`, `update_contract`, `end_contract`, `update_profile`, `boost_profile`. (The one standing
exception: the unattended `upwork-followups` run sends queued follow-ups through its guard hook.) The MCP is
plumbing; `upwork-proposal` and `upwork-cover-letter` own proposal quality.

### AI Ark

`ai-ark` HTTP MCP (`api.ai-ark.com`): company and people search, email and mobile finders, reverse
lookup, personality analysis, exports. Used to add decision-maker name + title + LinkedIn + email to
scraped companies. For batch runs, prefer a deterministic script that calls its HTTP JSON-RPC
endpoint directly (token from `.mcp.json`) over interactive MCP calls; raw `curl` works as a
fallback. Reference implementation: `b2b-sales-leads-indeed/scripts/find_dm.py` +
`AI_ARK_HANDOFF.md`, deleted in commit `eba1bcb` (recover with `git show eba1bcb^:<path>`).

## Skills

| Skill | What it does |
|-------|-------------|
| `upwork-proposal` | Client-facing Upwork proposal as a native Google Doc via `proposal_doc.py` (Drive HTML upload + convert; the Docs API is only for post-conversion layout), from a call transcript + case-study Sheet, or from one JD via `proposal_from_jd.py`. Written in the winning letter format (Larry's doc is the model, Nov 3 2026 reset); house style is enforced by the linter above; the doc closes on "send me a message" plus one small free offer. Has a safe-edit flow (export → edit → update) once the client hand-edits. The doc is only the attachment. |
| `upwork-cover-letter` | The cover letter text Jude actually submits. Short form by default; long form only when the letter sells a proposal-doc link. Hard gates: needs his Loom link AND its transcript/notes before drafting, and outputs the letter and nothing else. `scripts/check_hook_length.py` checks the hook. |
| `upwork-followups` | Scans Upwork rooms + invites, applies Jude's follow-up cadence (`scripts/followups.py` owns the math and the "Upwork Follow-ups" Sheet), drafts due follow-ups in his voice and **sends them on Upwork automatically** (since Nov 13 2026), emails him a digest of what went out and what needs him. Runs unattended 3x/day (08:00, 15:30, 22:00 UTC+8) via launchd `com.nexam.upwork-followups` → `scripts/run.sh`, an isolated `claude -p` (no user/project settings, tool allowlist, `guard_email.py` hook pins the only digest recipient, `guard_upwork_send.py` lets out only drafts `followups.py queue` approved, verbatim, one per room per 20h). `"auto_send": false` in the private config turns sending off. Private config (client exclusions, Sheet id) in `~/.config/upwork-followups/`, logs in `~/Library/Logs/upwork-followups/`. |
| `upwork-job-alerts` | Every 30 min (:07/:37, 15:00 to 05:37 Taipei) sweeps ~7 title lanes for jobs posted in the last 40 min, `scripts/job_alerts.py` applies the hard rules (window, country allow/blocklist, $20/hr floor, 150-proposal cap, title blocklist, dedupe) from `config.json`, Claude judges fit, saves picks to his Upwork saved list and emails one alert. Isolated `claude -p` via launchd `com.nexam.upwork-job-alerts` → `scripts/run.sh`; `guard_email.py` pins the recipient by sha256 (address lives in `~/.config/upwork-job-alerts/notify_email`, not the repo), `guard_save.py` allows only `save_job action=save` for this run's candidates. Cloud scheduled-task variant pending the Upwork claude.ai connector. Logs in `~/Library/Logs/upwork-job-alerts/`. |
| `gmaps-leads` | Google Maps → website scrape → contact extraction → Sheet, plus a persona-verification stack (staff pages → AMF company emails → SERP + LLM judge → `dm_*` columns) and AMF decision-maker fill for owner-led verticals. |
| `scrape-leads` | Apify `code_crafter/leads-finder` → LLM classify → email enrich → Sheet. Also the shared toolbox above. |
| `classify-leads` | LLM classification for fine distinctions (product SaaS vs agency). Dead Anthropic key. |
| `casualize-names` | Formal → casual first/company/city names for cold email. Dead Anthropic key. |
| `instantly-autoreply` | Drafts replies to Instantly threads from knowledge bases. Dead Anthropic key. |
| `design-website` | Single-page HTML mockup for a prospect (buildinamsterdam.com style). Needs `UNSPLASH_ACCESS_KEY`, which isn't in `.env`. |
| `monday-crm` | Law-firm CRM on Monday.com: cases, leads, hearings, tasks. |
| `build-scrapers` | Docs only, no `SKILL.md`, so not invocable: guides 00 to 07 for custom Apify scrapers plus a UK M&A pipeline guide. Read the `.md` files directly. |

## Subagents

`.claude/agents/`: `code-reviewer` (PASS/FAIL review by severity, zero context), `research` (web +
file research off the main context), `qa` (writes and runs tests, reports results). They only
report; all fixes happen in the parent. Build workflow: write → run `code-reviewer` + `qa` in
parallel → apply fixes → ship.

## Standalone Apify actors

Deployed separately with `apify push`.

- **`healthcare-recruitment-actor/`**: 8 sources (LinkedIn Jobs, NPPES NPI, state registries, niche
  directories, ASA members, FDD franchisees, SAM.gov, NCHCR) to find healthcare staffing agencies
  missing from Apollo/ZoomInfo. `src/__main__.py` → `SCRAPER_MAP` → async per source → dedup in
  `src/utils/merge.py` (domain match, then normalized name).
- **`nchcr-job-board-actor/`**: NCHCR job board → one record per recruiting firm (website derived
  from the email domain). The same source is the `nchcr` module in the healthcare actor, so
  scrape-logic changes likely apply to both.
- **`productionhub-directory-actor/`**: productionhub.com video production companies. Two modes: a
  listing crawl over `{categorySlug, locationPath, metroKey}` targets, or `profileIds` visit-only
  re-enrichment. Records push per finished target, so a killed run still yields data. The website is
  regex-mined from the profile description by `extract_website()` (there is no website field).
  **Do not "simplify" the anti-bot setup**; Cloudflare needs all of it: `patchright` (not
  playwright), `launch_persistent_context(channel="chrome")` with a fallback to patchright's
  Chromium, `headless=False` under `xvfb-run` in the Dockerfile, and a **sticky** residential
  session (`new_url(session_id=...)`) because `cf_clearance` is bound to one IP. Headless Chromium,
  bare `chromium.launch()`, and rotating proxies each hang on "Verification successful. Waiting
  for … to respond".

## Rendering images (proposal flowcharts, mockups)

Author fixed-layout HTML at 2x and screenshot it with the Playwright MCP. `file://` is blocked:
serve the dir with `python3 -m http.server <port>`, open localhost, and kill the server after.
`browser_take_screenshot` writes the PNG to the **repo root**: read it back, check it, then move or
delete it. Start from `upwork-proposal/templates/flowchart_base.html` (1248px wide at 2x, displayed
at 624px, so every px is double its on-page size); the full recipe is in `upwork-proposal/SKILL.md`.

## Operating principles

- **Self-anneal:** when a script errors, fix it, test it, and record the lesson in its `SKILL.md`.
- **Scripts over prose:** push complexity into deterministic scripts; Claude makes the decisions.
- Don't create new skills, or switch tools/approaches (especially cost-affecting ones), without
  asking Jude.
- **Apify bills per result:** run the small test, check quality, show Jude the projected cost,
  then run in full.
