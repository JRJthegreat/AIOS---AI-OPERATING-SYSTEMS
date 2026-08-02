---
name: upwork-proposal
description: Create, build, generate, or write a client-facing Upwork proposal as a styled Google Doc from a discovery-call transcript and a case-study sheet. Use when asked to write an Upwork proposal, draft a client proposal doc, or turn a sales call into a proposal. Output is a native Google Doc (Bricolage Grotesque font, no em dashes, Upwork-consultant byline).
---

# Upwork Proposal

Turns a discovery-call transcript (plus a case-study Google Sheet) into a
polished, client-facing **Upwork proposal as a native Google Doc**. The doc is
built and edited through the driver `proposal_doc.py`, which talks to the Google
**Drive** API (HTML upload + convert) and **Sheets** API. There is no Docs-API
access on the token, so styling is done in the uploaded HTML.

All paths below are relative to the repo root. Run everything from the repo root.

## House style (hard rules, do not deviate)

These were learned the hard way; the client cares about all of them:

- **No em dashes, ever.** Use commas, colons, periods, or parentheses. The
  driver refuses to upload any body that contains an em dash.
- **Font is Bricolage Grotesque.** The driver injects it; do not change it.
- **Byline is `Rood Judeley Joseph (Jude), Upwork consultant`.** Never mention
  NEXAM in a client deliverable.
- **Plain language, no jargon.** Explain like a smart non-specialist is reading.
- **CTAs are reply-only.** Never ask for a call or meeting up front; offer to
  send something and ask for a reply. **Exception:** if the prospect asked for a
  call themselves, accept it plainly and say what to bring. The rule bans pushing
  a call, not agreeing to one; deflecting their own ask reads as evasive.
- **Lead with proof.** The "Why me?" section opens on hard-number case studies.
- **Problem Overview is natural prose grounded only in what the prospect said
  on the call.** No invented pain. No sub-headings stacked on top of each other.
- **No horizontal separator bars** between sections (they read as AI-generated);
  sections divide by their headings. Blank line spacing via `<p>&nbsp;</p>`.
- **List items get breathing room (Aug 2026, Jude: cramped lists are "starting to
  be a little annoying").** The driver auto-injects `margin-bottom:10px` on every
  bare `<li>`; Drive's HTML->Doc conversion turns it into a 7.5pt space-after per
  item. Nothing to do when authoring bare-tag HTML; when safe-editing an exported
  doc, preserve the `padding-bottom:7.5pt` on `<li>` styles.

## Proposal structure

Five sections (this order; "Why me?" sits after Payment per client preference):

1. **Problem Overview**: what is not working, from the call.
2. **Solution**: numbered approach. Step 1 is usually the email-infra audit.
   Includes the ICP (title, company size, region, industry) and the buying
   signals as an `a) b) c)` list, then the cold door-opener play.
3. **Payment Structure**: rate, weekly hours, weekly total, billing.
4. **Why me?**: case-study bullets with hard numbers, then a one-line tie-back.
5. **Subscriptions and Platforms**: a Platform/Price `<table>`.

Start from `templates/proposal_body.html` and fill it in.

## Prerequisites

Google libs are already installed in this repo. Auth is a one-time OAuth token:

```bash
# generates token.json (Drive + Sheets scope); needs credentials.json present
python3 setup_google_auth.py
```

## Run (agent path): the driver

```bash
# 1. Pull case studies for the "Why me?" section
python3 -W ignore .claude/skills/upwork-proposal/proposal_doc.py sheet --id <SHEET_ID>

# 2. Author the body from the template, then create the doc
cp .claude/skills/upwork-proposal/templates/proposal_body.html .tmp/body.html
#    ...edit .tmp/body.html ...
python3 -W ignore .claude/skills/upwork-proposal/proposal_doc.py create \
  --title "Outbound GTM Proposal for <Client>" --html .tmp/body.html
#    -> prints URL: and ID:  (keep the ID)

# 3. Re-generate / replace content in place (same URL, good for an already-shared link)
python3 -W ignore .claude/skills/upwork-proposal/proposal_doc.py update \
  --id <DOC_ID> --html .tmp/body.html
```

The driver auto-injects Bricolage Grotesque and blocks em dashes on `create`
and `update`. Live example doc (current Kualitatem proposal):
`16wc5sSCttuQU-9ySslPeyPfVj7G1FjdiVXLW1SIvVlo`.

## Which skill: this one vs `upwork-apply`

Both make Upwork proposals; they are not interchangeable.

- **`upwork-apply` is batch-only.** It needs an array of *scraped* jobs (Apify output with
  `title`/`url`/`skills`/`budget`) and fans out ~30 at a time to a Sheet. It also
  **truncates the JD to 500 chars** before prompting, and calls **Anthropic**, whose key in
  `.env` is expired. Do not reach for it for one hand-picked job.
- **This skill handles a single job**, including a JD pasted straight into chat, via
  `proposal_from_jd.py` below.

**A single-job application is two deliverables, not one.** The Google Doc is the
attachment; the **cover letter is what actually gets submitted**, and nothing here
generates it. Author it by hand against the `reference_upwork_cover_letter_preview`
memory (no greeting, hook + link inside ~220 chars since that is all the client previews,
then goodwill beat, 1 infra + 1 diagnosis question, then the CTA). Note the CTA rule
inverts here: on Upwork the client is actively hiring, so a value-framed call ask is
expected, unlike cold outreach. Save it next to the body as
`.tmp/cover_letter_<slug>.txt`. Shipping the doc alone is half the job.

## Quick path: proposal straight from a job description

For a one-off Upwork proposal where the only input is a pasted job description
(no discovery call, no case-study sheet), use `proposal_from_jd.py`. It runs the
copy through **Azure `gpt-5.1`** (`AZURE_OPENAI_DEPLOYMENT`), then renders the
Google Doc by reusing this skill's `proposal_doc._prep`/`_drive` (same Bricolage
+ em-dash guard), and link-shares it so the client can open it.

```bash
python3 -W ignore .claude/skills/upwork-proposal/proposal_from_jd.py \
  --jd-file .tmp/jd.txt --client "<Client>"
#   also accepts --jd "..." or piped stdin; --dump-html .tmp/body.html to inspect
#   -> prints URL: and ID:
```

**Authored-body variant (preferred when the JD asks a technical question).** If the JD
ends with "To apply, please answer...", or buries a single question that is really the
filter ("can QBO ingest this and sort it?"), or the win depends on specific technical
calls, do NOT let the LLM write it: author the HTML yourself and render it with
`--body-html`. Same Bricolage injection, em-dash guard, and anyone-with-link share,
no LLM call.

**Research the client's stack before authoring.** The section that wins these is the one
naming a constraint they do not know about yet, so read the actual API docs (WebSearch +
WebFetch) and lead with what you found. Two examples that landed: CleanCloud gates API
access behind its Grow plan and documents no per-employee attribution on orders; Meta
System User tokens do not expire. A prerequisite gate on the client's side is the single
highest-value thing you can surface, so give it its own section.

```bash
#    ...author .tmp/body.html (apply-style sections; answer their questions FIRST)...
python3 -W ignore .claude/skills/upwork-proposal/proposal_from_jd.py \
  --body-html .tmp/body.html --title "<Doc title>"
```

Structure that works for a screening-question JD: header block (byline + focus), a
2-line opening that mirrors the JD, a proof line with REAL verified numbers, **"Your
two questions, answered first"**, "How I would build it" (numbered, one step per phase
of their spec), **"Two things I would push back on"** (where the real expertise shows,
name the wrong tool choices in their spec and the fix), "What you'll get", "Timeline"
(call out the one blocker on their side), reply-only next step, signed
"Best, / Rood Judeley Joseph (Jude)" (full-name sign-off, never a bare "Jude"; "Cheers," also OK).

How the LLM path differs from the transcript path above:
- **Proposal only** (no cover letter), **no Google Sheet**.
- Structure is the apply-style proposal: opening that mirrors the JD, a proof
  line, "My proposed approach" (numbered), "What you'll get", "Timeline", a
  **reply-only** close, signed "Best, / Rood Judeley Joseph (Jude)" (never a bare
  "Jude"). Not the 5-section bespoke structure.
- **The LLM still emits bracketed placeholders** (e.g. `[500+ calls/day]`) so it
  never invents a metric, but **NO placeholder may survive into the delivered
  doc** (house rule, Jul 2026: a forgotten bracket reads as templated and kills
  trust). Immediately after generation, replace every bracket with a real
  verified number, or rephrase without a number ("hundreds of records per run")
  and `update` the doc before handing Jude the URL. When authoring the body
  yourself, write real numbers directly from the start. The one exception is
  `[LOOM LINK]` in cover letters, which Jude swaps after recording.

## Flowchart (standing rule, Jul 2026)

Every proposal doc gets a **high-quality flowchart of the proposed system** whenever it adds
value (Jude: "don't give me anything sloppy"). Working recipe, learned on the AI Maintenance
Coordinator proposal:

1. Author the diagram as a fixed-layout HTML page at **2x scale** (e.g. 1248px canvas →
   displayed at 624px): absolutely-positioned cards + one SVG underlay for arrows with
   `<marker>` arrowheads. Font is **Bricolage Grotesque via Google Fonts** to match the doc.
   Neutral ink/gray palette; status colors only for true status (red = emergency path,
   amber = review queue), one blue accent for the AI/key step; every node labeled so color
   is never the only carrier. Small uppercase stage labels (1 · Intake, 2 · Normalize, …)
   read well. A dark full-width "foundation" bar (e.g. the system of record) anchors the
   bottom nicely.
2. Render with the Playwright MCP browser. **`file://` is blocked** — serve the scratchpad
   dir with `python3 -m http.server <port>` and navigate to localhost. Resize the browser to
   the canvas size first, then `browser_take_screenshot` with `fullPage: true` and a
   `filename`; **the PNG lands in the repo root**, not the scratchpad. Kill the server after.
3. **Read the PNG and eyeball it** (label collisions, arrow geometry, font actually loaded)
   before embedding. Iterate until it's genuinely clean.
4. Embed as base64: `<img src="data:image/png;base64,..." style="width:624px;">` in the body
   HTML (inject with a small Python script, not a hand edit — the string is ~300KB). This
   survives the Drive HTML→Doc conversion intact (verify with `export --html | grep '<img'`).
   624px = full page width; a 1248-wide PNG displays at 2x sharpness.

## Safe-edit workflow (once the client edits the doc by hand)

Re-running `create`/`update` from a freshly authored body **wipes the client's
hand-edits**. After they start editing, work off the LIVE doc instead:

```bash
# export the current doc (HTML preserves styles/font; text is for quick reading)
python3 -W ignore .claude/skills/upwork-proposal/proposal_doc.py export --id <DOC_ID> --html > .tmp/cur.html
python3 -W ignore .claude/skills/upwork-proposal/proposal_doc.py export --id <DOC_ID>            > .tmp/cur.txt
#   ...edit .tmp/cur.html: insert/move a section, reusing the doc's OWN inline
#      styles so it matches (18pt Bricolage <h2>, 11pt body span, 30pt-indent <li>)...
python3 -W ignore .claude/skills/upwork-proposal/proposal_doc.py update --id <DOC_ID> --html .tmp/cur.html
```

Always re-export and eyeball after an update to confirm nothing was mangled and
section numbering is still correct.

## Gotchas

- **Drive scope only, no Docs API.** Font is set via inline CSS in the HTML, so
  the driver injects `font-family:'Bricolage Grotesque'` on bare block tags. The
  injection **no-ops on already-styled HTML** (e.g. a Google export), so it is
  safe to run `update` on exported-then-edited HTML.
- **Font may need a one-time enable.** If the doc shows a default font, open it,
  Select All, font menu > More fonts > add "Bricolage Grotesque". It then sticks.
- **Mixed editing clobbers.** Either you drive via the script, or the client
  edits the doc; do not do both blindly. Use the safe-edit workflow above.
- **Inserting/moving sections:** the Google HTML export re-imports cleanly enough
  to slice the section block (from its `<h2>` to the next `<h2>`), move it, and
  renumber the heading strings. Reuse the doc's existing inline styles on any new
  markup so it visually matches.
- **`export` (text) shows lists as `* ` and shows no formatting/font.** Use
  `--html` when you need to see or edit styles.
- **`update` keeps the same doc ID and URL**, so a link you already shared stays
  valid.

## Troubleshooting

- `ERROR: em dash found in body...` -> the body contains an em dash. Remove
  them (house rule); the driver will not upload until they are gone.
- `401` / invalid_grant / token errors -> regenerate `token.json` with
  `python3 setup_google_auth.py`.
- Inserted section looks unstyled vs the rest -> you used bare tags on an
  exported doc; copy the surrounding `<h2>`/`<p>`/`<li>` inline `style="..."`
  strings onto your new elements.
