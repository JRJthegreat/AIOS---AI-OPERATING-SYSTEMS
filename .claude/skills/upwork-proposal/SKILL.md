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

- **Keep it SHORT. Target under 1,200 words (Jude, Aug 2026, said twice).** His words:
  "nobody is gonna sit down and read eight pages of documents." A 3,129-word draft on the
  Microsoft 365 email assistant job was sent back for this reason alone; the content was
  right and the length killed it. **Calibrate against the docs that actually won work**
  (export them with `proposal_doc.py export --id <ID>` before authoring if you need the feel):
  - `1voalYmJcXn_E35zA2LeFq6NZAL0o9zQYhAV_xubnrN4` **538 words**, the Paris boat operator,
    won a paid two-developer bake-off. The shortest doc on file is also the biggest win.
  - `1Q6JxthIXIHGB3RNLXiMzzZdBGQQBd0GPacqtHCpMIF8` **1,140 words**, quotation follow-up system.
  - `15OCpAmq1PH7LK38b07WeJPUHg1LqEZMaZax31sAeRJc` **2,436 words**, HubSpot build. The outlier,
    not the model to copy.
  `scripts/check_proposal_html.py` now **enforces** this: it prints the visible word count on
  every run, warns over 1,200, and **fails over 1,800** unless you pass `--allow-long`. Do not
  reach for the override to avoid editing. A JD with a mandated question list (answer all ten
  of these) is the one honest reason to sit in the 1,200 to 1,800 band.
- **What to cut first, in order:** the case-study list down to ONE proof story (a second only
  if it proves something different); multi-sentence answers down to one sentence; any standalone
  section whose content fits inside a table row (an "ownership" or "what you'll get" section
  usually does); the formal `Prepared for / Prepared by / Date` block down to a two-line byline.
  **Never cut the flowchart to save length.** It is the single biggest word-saver in the doc,
  a good diagram replaces roughly 400 words of architecture prose, and per the standing rule
  below it is the thing that makes the proposal land.
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
- **Frame the doc as a FREE AUDIT (Jude, Aug 15 2026, standing rule).** The doc title and the
  researched technical-flags section carry audit language (e.g. title "... Automation Audit for
  <Client>", flags section "Your free audit: ..."), and the opener tells the client they're
  getting a free audit of their stack. The researched-constraints section IS the audit's
  substance, so never drop it when using this framing; reciprocity is the point ("that guy
  gave me something free"). The matching cover letter line lives in `upwork-cover-letter`
  (its free-audit doc-line default). First applied: LGNDRY Marketing GHL doc.
- **Every link is BOTH visible literal text AND an actual clickable hyperlink (Aug 2026,
  Jude, in two parts same day: first "sometimes people can't see it, the thing is just text,"
  then "make them hyperlinks so people can click").** Always write
  `<a href="URL">URL</a>`, the URL as both the href and the visible text. Never
  `<a href="URL">the testimonial</a>` (URL hidden behind other words), and never bare `URL`
  with no `<a>` tag either, that renders as plain unclickable text once Drive converts the
  HTML (confirmed by export: a bare URL with no `<a>` stays plain text, it does not
  auto-linkify). Applies to every link in a proposal doc: testimonial videos, live portfolio
  sites, GitHub, all of it. After render, spot-check with
  `export --html | grep 'href="https://www.google.com/url'` (Drive wraps real hyperlinks in
  its own redirect URL on export, a bare `<span>` with the literal text means it did not
  become a link).
- **Problem Overview is natural prose grounded only in what the prospect said
  on the call.** No invented pain. No sub-headings stacked on top of each other.
- **No horizontal separator bars** between sections (they read as AI-generated);
  sections divide by their headings. Blank line spacing via `<p>&nbsp;</p>`.
- **Every `<p>...</p>` to `<p>...</p>` transition gets a `<p>&nbsp;</p>` gap between them,
  with no exceptions (Aug 2026, real regression: a subagent drafted a doc where the header
  metadata block and the first two body paragraphs ran together with zero spacing, "the
  spacing of the document is terrible," because it copied the numbered-step gap pattern from
  the template but missed that the rule is general, not specific to numbered lists). `<h1>`/
  `<h2>` headings carry their own space-before/space-after from Google Docs' Heading style, so
  a plain paragraph immediately after a heading does not need one, but two consecutive plain
  `<p>` tags always do. The only exception is a signature block or the `<br/>`-joined lines
  inside one metadata `<p>` (those stay tight on purpose). When delegating body-copy drafting
  to a subagent, paste this exact rule into its prompt rather than assuming it will infer it
  from one example; verify the returned HTML against it before rendering.
- **List items get breathing room (Aug 2026, Jude: cramped lists are "starting to
  be a little annoying").** The driver auto-injects `margin-bottom:10px` on every
  bare `<li>`; Drive's HTML->Doc conversion turns it into a 7.5pt space-after per
  item. Nothing to do when authoring bare-tag HTML; when safe-editing an exported
  doc, preserve the `padding-bottom:7.5pt` on `<li>` styles.

## Speed: parallelize, and cut waste everywhere except the flowchart (Aug 2026)

**The flowchart's design quality is never the speed lever.** Jude was explicit (Aug 2026):
the bespoke, agent-designed flowchart is what makes a proposal land, "this is what gets the
client to say, oh wow, this is interesting." Do not template it, do not simplify its ambition,
do not cut the subagent's own eyeball-and-fix cycle when it is building the actual diagram.
"Keep the layout simple" below means clean, non-crowded geometry so arrows do not cross and
labels do not collide, a robustness technique, not a ceiling on creativity, content, color, or
how impressive the result looks. If a proposal is still taking too long, the fix is cutting
process waste elsewhere, never the flowchart's quality bar.

Where real time was actually lost on record, and the fix for each:
- **Sequential steps in the main thread** (research, then copy, then flowchart, one after
  another). Fix: dispatch with the Agent tool, **all in one message with parallel tool
  calls**, so wall-clock is the slowest agent, not the sum of all of them.
- **A subagent told to "read the SKILL.md file"** for the flowchart or copy recipe, which
  costs a full file-read-and-interpret round trip on a long file. Fix: paste the exact
  recipe text (palette, layout rules, Playwright steps, house-style rules) directly into the
  subagent's prompt instead of pointing it at the file.
- **A bug only caught by Jude after render** (Aug 2026: a missing paragraph-spacing gap
  shipped because nobody checked for it before the doc existed). Fix: run
  `scripts/check_proposal_html.py <body.html>` on the copy agent's returned HTML **before**
  creating the doc, catches em dashes, bracketed placeholders, missing spacing gaps and an
  over-long body deterministically, without a Google Docs round trip. Only fall back to a live Playwright
  check of the actual doc for things the linter cannot see (the image genuinely rendered,
  the font genuinely loaded), not for anything text-shaped.

Agents to dispatch in one message, in parallel:

- **Copy agent**: drafts the body (5-section transcript structure, or the apply-style JD
  structure below, whichever applies), including any technical grounding it needs
  (WebSearch/WebFetch) done inside its own run, not as a separate step beforehand.
- **Flowchart agent**: builds and screenshots the diagram (recipe below), doing its own
  eyeball-and-fix pass internally before returning; this is real, protected time, not
  something to rush.
- **Cover letter agent** (JD path only): drafts the Upwork cover letter off the same JD and
  the claims bank, in parallel, since it does not depend on the copy agent's exact wording.

Then in the main thread: run `check_proposal_html.py` on the copy agent's HTML and fix
anything it flags, embed the flowchart's base64, run the doc script **once** (`create` /
`update` / `proposal_from_jd.py --body-html`), do one quick structural check (`export --html |
grep '<img'`), and hand off doc URL + cover letter + job URL together.

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

The driver auto-injects Bricolage Grotesque, blocks em dashes, and shares the doc
anyone-with-link/reader on `create` and `update` (Aug 2026 fix: `create`/`update` never
granted this before, so some doc links Jude sent were only openable by his own Google
account, not the client; `_share()` is idempotent, safe to call every time). Live example
doc (current Kualitatem proposal): `16wc5sSCttuQU-9ySslPeyPfVj7G1FjdiVXLW1SIvVlo`.

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
generates it. Use the **`upwork-cover-letter`** skill for that (Aug 2026: it replaced the
old hand-authored-per-job approach this section used to describe, which Jude never actually
used). Pass it the job post, Jude's Loom link, and this doc's URL as the optional proposal-doc
input. Save its output next to the body as `.tmp/cover_letter_<slug>.txt`. Shipping the doc
alone is half the job.

## Quick path: proposal straight from a job description

**Job URL is a required input (Aug 2026, Jude).** Jude runs several proposal tabs in
parallel and matches deliverables to jobs by URL afterward. If he did not provide the
Upwork job URL with the JD, ask for it before handing off. Save it next to the other
deliverables as `.tmp/job_url_<slug>.txt`, and ALWAYS echo it in the final handoff
message alongside the doc URL and cover letter (format: "Job: <url>"). Upwork job pages
are login-gated, so never try to fetch the URL; it is an identifier, not an input source.

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

**Structure: write a LETTER, not a consulting report (Aug 2026, derived from the three
winning docs above).** Every doc that won work follows the same shape, and none of them
has a standalone ownership section, a five-item case-study list, or an essay per question:

1. Two-line byline header (name + `Focus:` line). Not the formal Prepared-for block.
2. `Hey <Name>,` then ONE paragraph mirroring what they asked for, in their own terms,
   grounded only in the JD. Fold the free-audit line in here.
3. The flowchart, with a one-line caption. Put it high; it answers "recommended
   architecture" in a glance and buys back hundreds of words.
4. If the JD mandates a question list, a **compact table** (`You asked | Answer`), one or
   two sentences per row. A checklist buyer wants to tick items off, and a table does that
   far better than prose. Absorb what would otherwise be standalone sections into rows.
5. **"N things I checked before writing this"** or "Two things I would push back on": the
   researched constraints and the wrong tool choices in their spec. This is the free audit
   and the part no competitor can copy, so it survives every trim. Keep each item to 3 or 4
   sentences.
6. **"How I would build it"**: numbered milestones. Give each an objective
   *Signed off when* acceptance test, which doubles as the "what you'll get" section so you
   do not need a separate one.
7. **Similar work**: ONE proof story told properly, a second only if it proves something the
   first does not. Then any real skill gap in a single sentence (see
   `feedback_honest_gap_framing`), never a paragraph.
8. Reply-only next step offering something specific and free.
9. `Best,` / `Rood Judeley Joseph (Jude)` (full name, never a bare "Jude"; "Cheers," also OK).

**Timeline wording (Jude, Aug 2026): give milestones, not durations.** He builds with Claude
Code, so week-based estimates are inflated and quoting a short timeline invites the client to
reprice the work downward. State the sequence, name the dependencies that actually set the
calendar (client-side admin access, a real data window to tune against), and say you will
commit to dates at kickoff. Fixed-price milestones mean efficiency gains accrue to Jude, which
is the whole reason not to bill hourly. Money still never appears in the doc.

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

**Two rules that Jude sent a diagram back for (Aug 2026). Read these before authoring:**

- **Every font size must be DOUBLE its intended on-page size.** The canvas is 1248px and it
  displays at 624px, so the page halves everything. A 12px label authored at canvas scale
  renders at 6px in the doc: Jude's words, "somebody can see things moving up and down, but
  they cannot actually read what it says." **Floor: 23px authored body text** (11.5px on the
  page), 28px+ for headings. Big type means less text per box, so cut the copy to fit rather
  than shrinking the type. Six readable boxes beat twelve unreadable ones.
- **The background is white (`#ffffff`), never a tinted page colour.** A grey canvas makes the
  image read as a screenshot of a web page sitting awkwardly in the document instead of a
  diagram printed on it (Jude: "there is a background you add, which is a bit grey, why is
  that there?"). Card fills stay white too; drop box-shadows. Colour is only for meaning
  (red = a hard constraint, amber = review queue, one blue accent for the AI step) and a dark
  full-width "foundation" bar still anchors the bottom nicely.

1. Author the diagram as an HTML page at **2x scale** (1248px canvas → displayed at 624px).
   Font is **Bricolage Grotesque via Google Fonts** to match the doc. Every node labelled, so
   colour is never the only carrier of meaning.
2. **Lay out with flexbox and auto heights, and draw the arrows from measured geometry in JS.
   Never hand-place arrow coordinates against fixed card heights.** Hand-placed coordinates
   were the cause of a real regression: type got bigger, fixed-height cards stayed the same,
   and text spilled out of every box while the arrows pointed at nothing. Give cards
   `height:auto` inside `display:flex` rows, then after `document.fonts.ready` measure each
   card with `getBoundingClientRect()` and emit orthogonal `<path>` strings into an absolutely
   positioned SVG underlay. Copy can then change freely without breaking the picture.
   **Start from `templates/flowchart_base.html`**, which is the working implementation of all
   of this (2x type scale, white background, flex rows, measured arrows). Swap the card copy
   and the node ids in the `draw()` call list; leave the sizing and the measuring code alone.
3. Render it. **`file://` is blocked**, so serve the scratchpad dir with
   `python3 -m http.server <port>` and load localhost. Preferred: the Playwright MCP browser
   (resize to canvas width, `browser_take_screenshot` with `fullPage: true` and a `filename`;
   **the PNG lands in the repo root**, not the scratchpad). **Fallback when Playwright errors
   with "Browser is already in use"** (a parallel Claude session holds the profile lock, which
   happens often): do not kill it, shell out to headless Chrome instead, which needs no lock:
   ```bash
   "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless --disable-gpu \
     --hide-scrollbars --force-device-scale-factor=1 --virtual-time-budget=9000 \
     --window-size=1248,1400 --screenshot="$PWD/fc.png" http://localhost:<port>/index.html
   ```
   `--virtual-time-budget` is what lets the webfont load and the arrow JS run before capture.
   With auto heights you cannot know the final height up front, so shoot tall and crop the
   trailing white with PIL: `ImageChops.difference(im, white).getbbox()` then `im.crop(...)`.
   Kill the http server after, and **close the Playwright tab with `browser_close`** if you
   used it (Jude, Aug 2026: don't leave it open). That applies to any tab this skill opens,
   including the live Google Doc you verify against before handing off.
4. **Read the PNG back and eyeball it once** before embedding: text overflowing its box, arrows
   landing on nothing, label collisions, font actually loaded. One build-and-check, not a
   turn-by-turn iterate-until-clean loop. If a subagent is building it, it does that cycle
   itself before returning.
5. Embed as base64: `<img src="data:image/png;base64,..." style="width:624px;">` in the body
   HTML (inject with a small Python script, not a hand edit, the string is ~300KB). This
   survives the Drive HTML→Doc conversion intact. Verify with
   `export --html | grep -o 'width: [0-9.]*px; height: [0-9.]*px'`, which shows the real
   rendered size; 624px wide is full page width.

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
- **Styling a table kills the font document-wide (Aug 20 2026, learned on the property
  portal doc, cost three round trips).** `_prep` only injects Bricolage into BARE block tags,
  so a styled `<td>`/`<th>` loses it. Worse, Drive's HTML->Doc converter reacts to certain
  table CSS by dropping the injected font from the ENTIRE document, `<p>` and `<h2>` included,
  so the doc silently comes back as Arial. Verified by experiment:
  - **Works:** cell styles carrying `font-family` themselves plus `border`, `padding`,
    `vertical-align`, `background-color`, `text-align`, with the `<table>` tag left bare.
  - **Breaks everything:** any `style` on the `<table>` tag itself (`border-collapse`,
    `width:100%`), and `width:` inside a `<td>`/`<th>` style. Both zero out Bricolage globally.
  So: never style `<table>`, never set cell widths, and always repeat
  `font-family:'Bricolage Grotesque',sans-serif;` inside every `<td>`/`<th>` style you add.
  Column widths are simply not available; keep table copy short instead.
  **Always confirm after any table change** with
  `export --html | grep -o Bricolage | wc -l` (should be in the hundreds, never 0).

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

## Cleanup (Aug 2026, Jude)

The doc itself lives in Google Drive; every local `.tmp/` file (`body.html`, exported
`cur.html`/`cur.txt`, flowchart source and PNG, `job_url_<slug>.txt`) is a working
intermediate only, and these piled up badly before this rule. Once Jude confirms in chat that
he's done with a doc for this job (sent, or otherwise finished with it), delete that job's
`.tmp/` files right away, in the same turn. Do not delete before confirmation, and do not
bulk-delete older files from other sessions without asking, since their status is unknown.

## Troubleshooting

- `ERROR: em dash found in body...` -> the body contains an em dash. Remove
  them (house rule); the driver will not upload until they are gone.
- `401` / invalid_grant / token errors -> regenerate `token.json` with
  `python3 setup_google_auth.py`.
- Inserted section looks unstyled vs the rest -> you used bare tags on an
  exported doc; copy the surrounding `<h2>`/`<p>`/`<li>` inline `style="..."`
  strings onto your new elements.
