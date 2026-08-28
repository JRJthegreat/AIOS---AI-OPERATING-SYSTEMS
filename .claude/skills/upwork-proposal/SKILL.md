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
- **NO TABLES, EVER (Jude, Aug 28 2026, on the ICT Fair Value Gap doc: "no tables in the Google
  doc, tables make this look AI generated").** Not for a mandated question list, not for a
  comparison, not for a spec summary, not for anything. A grid of short cells is the most
  recognisable LLM tell in a client document, right alongside stacked citation URLs and
  horizontal separator bars, and it is now banned for the same reason those are.
  `scripts/check_proposal_html.py` **fails** on any `<table>` in the body.
  **What replaces one:** answer the JD's list as ONE prose paragraph that runs their items
  together in their own words, or as bold lead-in paragraphs (`<b>Milestone 2, the risk
  layer.</b> ...`), which is the shape the audit and milestone sections already use. In
  practice most of a question table duplicates the milestones and the audit anyway, so the
  honest fix is usually to delete it and let those two sections carry the answers: on the ICT
  doc, cutting the table and folding its one unique clause into Milestone 1 took the body from
  1,311 words to 1,170 and lost nothing.
- **What to cut first, in order:** the case-study list down to ONE proof story (a second only
  if it proves something different); multi-sentence answers down to one sentence; any standalone
  section the milestones already cover (an "ownership" or "what you'll get" section usually is
  one); the formal `Prepared for / Prepared by / Date` block down to a two-line byline.
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
- **The doc must be genuinely USEFUL, not just correct (Jude, Aug 27 2026).** Gaps in their plan,
  the traps ahead of them, and the stack call with its reasoning are mandatory, not decoration.
  See **The audit section** below; this is the single rule most likely to have quietly rotted, so
  check it before anything else when a draft feels flat.
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
- **But NEVER link a documentation or vendor reference URL (Jude, Aug 28 2026: "remove the links
  makes it look AI generated").** On the TEC Specialty Products RAG doc the audit section carried
  three raw `learn.microsoft.com` URLs, one per finding, to source the constraints; he had all
  three removed and kept only the HiveIQ testimonial link. Stacked citation URLs inside body copy
  are the most recognisable LLM tell in a client document. Research the constraint, state it in
  prose with the specific number, version or parameter that proves you read the source, and stop.
  The rule above governs only the links that DO belong: Jude's own proof assets (testimonial
  videos, live portfolio sites, GitHub repos).
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

- **Copy agent**: drafts the body in the letter structure below, including **the research the
  audit section depends on** (WebSearch/WebFetch into the client's actual stack and its API
  docs), done inside its own run rather than as a separate step beforehand. Paste the three
  audit requirements into its prompt verbatim; a copy agent that is not told to hunt for gaps,
  traps and the stack call returns a competent brochure.
- **Flowchart agent**: builds and screenshots the diagram (recipe below), doing its own
  eyeball-and-fix pass internally before returning; this is real, protected time, not
  something to rush.
- **Cover letter agent** (JD path only): drafts the Upwork cover letter off the same JD and
  the claims bank, in parallel, since it does not depend on the copy agent's exact wording.

Then in the main thread: run `check_proposal_html.py` on the copy agent's HTML and fix
anything it flags, embed the flowchart's base64, run the doc script **once** (`create` /
`update` / `proposal_from_jd.py --body-html`), do one quick structural check (`export --html |
grep '<img'`), and hand off doc URL + cover letter + job URL together.

## The audit section: the reason the doc is worth opening (Jude, Aug 27 2026)

**The complaint that created this rule:** "I see the proposal now, it's just a Google doc, there's
no value brought to it." A proposal that only restates the JD, lists milestones and shows a diagram
is a brochure. The client can get that from anyone. What they cannot get from anyone is **a
consultant telling them what is wrong with their own plan before being paid**, which is also the
whole mechanism behind the free-audit framing (reciprocity: "that guy gave me something free").

So every proposal carries a section, usually titled **"N things I checked before writing this"**,
and it must do all three of these. Not one of them, all three:

1. **Name the gaps in what they asked for.** Something their spec assumes that is not true, or a
   requirement they have not thought of yet. Prerequisites on THEIR side are the highest-value
   find of all, because they set the calendar and nobody else will have mentioned them (a Lark
   admin has to approve the app before a single record can be read; CleanCloud gates API access
   behind its Grow plan; Meta System User tokens do not expire).
2. **Flag what they should look out for.** The trap that bites after the build is live: the fee
   that eats the margin on small transactions, the record ceiling they will hit, the double-credit
   on a refreshed payment tab, the CRM that is dirty inside a month because neither tool dedupes.
   Say what breaks, when, and what prevents it.
3. **Make the stack call and justify it, including what you would NOT use.** Never present a tool
   list as a given. Name the choice, the reason, and the alternative you rejected with why:
   "Softr and Glide cannot read Lark Base, both publish their supported sources and it is on
   neither, so a Softr build means two versions of the truth. Skip the middleman." Where a tool in
   THEIR spec is the wrong call, that belongs here too, framed as a push-back, not a complaint.

**The test for every item: could a competent competitor have written this sentence without doing
the research?** If yes, it is filler, cut it. A real item names a specific document, limit, price,
API behaviour or version. Do NOT link the source; see the no-reference-URLs rule in House style.
Generic caution ("data quality will be important", "we should scope carefully") is worse than
nothing, since it takes the slot a real finding should have had.

Length: 3 or 4 sentences per item, 3 to 5 items. This is also why the research has to happen
inside the copy agent's own run (WebSearch + WebFetch on the client's actual stack and its API
docs). **A doc that reaches the render step without this section is not shippable**, and
`scripts/check_proposal_html.py` now fails on it rather than letting it drift again.

## Proposal structure

**Both paths use the same letter structure** (listed in full under the JD path below): byline,
opener, **the audit**, "How I would build it" with the flowchart at its
end, similar work, reply-only next step, sign-off. Start from `templates/proposal_body.html`,
which encodes it.

What a call-derived proposal adds, versus one from a pasted JD:

- The opener becomes a **Problem Overview** in natural prose, grounded ONLY in what the prospect
  actually said on the call. No invented pain, no sub-headings stacked on each other.
- For an outbound GTM engagement, the build section carries the **ICP** (title, company size,
  region, industry) and the buying signals as an `a) b) c)` list, then the cold door-opener play.
- **Why me?** can stand as its own section with case-study bullets when the call surfaced a
  specific credibility question, instead of the single "Similar work" proof story.

**Two sections that used to be in this template and must not come back:** a **Payment Structure**
section (rate, weekly hours, weekly total) and a **Subscriptions and Platforms** price table. Money
never appears in a proposal doc; it is a call conversation (standing rule, `feedback_no_pricing_in_proposal_doc`).
The old template carried both, plus no audit section at all, which is a large part of why the docs
drifted into being "just a Google doc" (Jude, Aug 27 2026). Also gone: the formal
`Prepared for / Prepared by / Date` block, now a two-line byline.

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
3. If the JD mandates a question list, answer it in **prose, never a table** (see the no-tables
   rule in House style): one paragraph that runs their items together in their own words, one
   clause each. Check it against the milestones first, since a checklist answer that repeats
   Milestone 1 to 4 should just be deleted.
4. **The audit: "N things I checked before writing this"** (or "Two things I would push back
   on"). The gaps in their own plan, the traps ahead of them, and the stack call with its
   reasoning. This is the whole reason the doc is worth opening, so it survives every trim.
   See **The audit section** above for what each item has to contain; a doc without it is the
   failure Jude named on Aug 27 2026.
5. **"How I would build it"**: numbered milestones. Give each an objective
   *Signed off when* acceptance test, which doubles as the "what you'll get" section so you
   do not need a separate one. **The flowchart goes here, at the end of this section**
   (Jude, Aug 27 2026), with its one-line caption ABOVE it, never below (a caption under the
   image gets orphaned onto the next page when the image moves). See the placement rule under
   **Flowchart** below.
6. **Similar work**: ONE proof story told properly, a second only if it proves something the
   first does not. Then any real skill gap in a single sentence (see
   `feedback_honest_gap_framing`), never a paragraph.
7. Reply-only next step offering something specific and free.
8. `Best,` / `Rood Judeley Joseph (Jude)` (full name, never a bare "Jude"; "Cheers," also OK).

**Timeline wording (Jude, Aug 2026): give milestones, not durations.** He builds with Claude
Code, so week-based estimates are inflated and quoting a short timeline invites the client to
reprice the work downward. State the sequence, name the dependencies that actually set the
calendar (client-side admin access, a real data window to tune against), and say you will
commit to dates at kickoff. Fixed-price milestones mean efficiency gains accrue to Jude, which
is the whole reason not to bill hourly. Money still never appears in the doc.

How the LLM path differs from the transcript path above:
- **Proposal only** (no cover letter), **no Google Sheet**.
- Structure is the same letter shape as the authored path (Aug 27 2026: it now emits an
  `<h1>` title, the byline, **the audit section**, "How I would build it" with `Signed off when`
  tests, "Timeline", a **reply-only** close, and signs "Best, / Rood Judeley Joseph (Jude)").
  Before that fix it emitted no audit section, no `<h1>`, a "What you'll get" list, a
  week-count timeline and a bare "Jude", so its output was exactly the valueless doc Jude
  complained about, and it failed the linter on the missing `<h1>`.
- **It cannot research and it cannot draw.** The audit it writes is limited to what the JD and
  the model's training data support, and there is no flowchart. So its audit is a starting point
  to sharpen with real WebSearch/WebFetch findings, never the thing you ship. For a job Jude is
  really sending, author the body and render with `--body-html`.
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

**Placement: at the END of "How I would build it", not high up (Jude, Aug 27 2026).** His words:
"the flowchart that you create should be in the section that explains how I would build this."
The milestones say what gets built in what order, then the diagram shows the architecture those
milestones add up to, so the reader meets every component having just read why it exists. It shows
the SYSTEM, not the milestones (see Content below). Introduce it with a one-line caption ABOVE
the image ("Here is the architecture those milestones add up to, every moving piece named."). Do not put it right after the opener any
more; that placement is retired, not an alternative.

**Content: it is a TECHNICAL ARCHITECTURE diagram, never a picture of the milestones (Jude,
Aug 27 2026).** His words, on a diagram that redrew the build steps: "the flowchart needs to be
super technical. In this case you just outline the four milestones. The flowchart is not about
the four milestones, it's supposed to be about the technical architecture." The milestones are
already written directly above it in prose, so a diagram that repeats them is the same content
twice and adds nothing. What the diagram is for is the thing prose is bad at: which named
components exist and how data moves between them.

So every box is a **real named component**, not a phase: `Telegram Bot API (aiogram webhook)`,
`PumpPortal websocket`, `dedicated Solana RPC`, `Jupiter Swap API`, `Jito block engine`,
`Postgres`, `Redis lock per wallet`, not `1. Trigger`, `2. Safety gate`, `3. Quote`. The subtitle
under each carries the specific technical detail (the actual method names, the actual parameters,
the actual guarantee), which is also where the audit's research gets to show up a second time
visually. **Test before rendering: strip the numbers off the boxes and ask whether a developer
could start building from this picture.** If it only reads as a sequence of things that happen,
it is a process diagram and it needs rewriting.

A layout that works for a service-shaped build: a row of INPUTS (labelled by type with a small
eyebrow, e.g. `COMMAND IN` / `MARKET IN` / `CHAIN IN`), a full-width accent bar for the ENGINE
they all feed into, a row for the ordered EXECUTION path, and the dark `.foundation` bar for
PERSISTENCE and the security guarantee. Wrap the whole thing in the dashed `.tenant` box labelled
with where it runs and whose keys it uses.

Note the size tension this creates: an architecture diagram carries more boxes than a process one.
Buy the extra components out of LAYOUT and COPY (one-line headings, two-line subtitles, four narrow
cards in a row instead of three wide ones), never out of the 23px type floor. The Telegram trading
bot doc landed at 534px canvas / 267px displayed with 8 named components, slightly over the ~240px
target below; that is the honest ceiling for this shape, so treat ~240 as the goal and ~270 as the
point where you cut a band instead of shipping it.

**Three rules that Jude sent a diagram back for (Aug 2026). Read these before authoring:**

- **It must be SMALL: at most ~240px DISPLAYED, so ~480px of canvas at 2x** (Jude, Aug 27 2026:
  "the flowcharts that you're creating right now, they are way too big, they take too much space").
  A Google Doc page body is ~648px tall and Docs will not split an image, so a tall diagram both
  eats the page and shoves whatever follows onto the next one. Measured history: 681px displayed
  left a full blank page, 410px left half a page, 248px flowed clean. `templates/flowchart_base.html`
  was itself the cause of the drift, since it rendered at 535px displayed while this section
  claimed a 300px cap; it is now 240px, so **start from the template and stay near its height
  rather than growing it**.

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
**Hitting the ~480px canvas budget (see the size rule above).** The 23px type floor is fixed, so
   height comes out of LAYOUT, never out of the font size. In order: at most **3 bands** (two card
   rows plus one full-width bar); **one line of subtitle copy per card**, which is worth ~50px of
   canvas per row versus two lines; drop any band the body text already explains; fold a
   `.guard` callout into the dark `.foundation` bar instead of giving it its own band (~85px).
   Six readable boxes beat twelve unreadable ones, and four beat six.
   **Measure it, do not guess:** the template's `draw()` writes the live canvas height into
   `document.title` as `H<px>`, so read it straight off a headless load before you even screenshot:
   ```bash
   "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless --disable-gpu \
     --virtual-time-budget=8000 --window-size=1248,2000 --dump-dom \
     http://localhost:<port>/index.html 2>/dev/null | grep -o "<title>H[0-9]*</title>"
   ```
   Halve that number for the on-page height. If it is over ~480, cut a band before rendering.
   For a final check of real page breaks, export the finished doc to PDF and look at the pages
   (`files().export(mimeType='application/pdf')`, then `pdftoppm -png -r 62` and stitch them side by
   side). That is the only way to see a page-break gap before Jude does.

5. Embed as base64: `<img src="data:image/png;base64,..." width="624" height="752">` in the
   body HTML (inject with a small Python script, not a hand edit, the string is ~300KB), with
   the real half-scale pixel size in the `width`/`height` ATTRIBUTES. **Never
   `style="width:624px;"` on the img (Aug 25 2026, Indeed screening doc): a `width:` inside an
   img `style` triggers the converter bug described in Gotchas below and zeroes Bricolage
   out of the ENTIRE document (isolated by A/B upload: same body with attribute sizing kept the
   font, style sizing came back all Arial).** An img with no size at all keeps the font too but
   renders at the full 1248px, double page width. Verify BOTH after upload:
   `export --html | grep -o 'width: [0-9.]*px; height: [0-9.]*px'` (should be 624px wide) and
   `export --html | grep -o Bricolage | wc -l` (never 0).

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
- **`style` on an `<img>` kills the font document-wide (Aug 25 2026).** `_prep` only injects
  Bricolage into BARE block tags, and Drive's HTML->Doc converter reacts to certain inline CSS
  by dropping the injected font from the ENTIRE document, `<p>` and `<h2>` included, so the doc
  silently comes back as Arial. `style="width:624px;"` on the flowchart img does exactly this;
  size images with `width`/`height` ATTRIBUTES instead (see flowchart step 5). **Always confirm
  after any image change** with `export --html | grep -o Bricolage | wc -l` (never 0; a full doc
  typically shows dozens).
  *Historical note, now moot:* tables triggered the same converter bug (any `style` on the
  `<table>` tag, or `width:` in a `<td>`, zeroed Bricolage globally, Aug 20 2026, property portal
  doc, three round trips). Tables are banned outright as of Aug 28 2026 for a copy reason, not a
  technical one, so the workaround it cost is no longer needed. Do not reintroduce a table
  because you find the styling recipe in git history.

- **A large embedded PNG zeroes the font document-wide, same symptom as the table/img-style bug (Aug 28 2026,
  TEC Specialty Products architecture figure).** A 473 KB PNG (627 KB of base64) came back with **0**
  Bricolage occurrences on two consecutive identical uploads, so it is NOT the converter race below.
  Isolated by A/B: the same body with the `<p>FLOWCHART</p>` placeholder instead of the image gave 64.
  Quantizing the identical image to a 256-colour palette (165 KB) and re-uploading restored 64. Flat-colour
  diagrams lose nothing to quantization, so **keep the embedded PNG under ~200 KB**:
  ```python
  from PIL import Image
  im = Image.open('fc.png').convert('RGB')
  im.quantize(colors=256, method=Image.MEDIANCUT, dither=Image.NONE).save('fc_q.png', optimize=True)
  ```
  Check `export --html | grep -o Bricolage | wc -l` after every image change; if it is 0 and a re-upload does
  not fix it, shrink the PNG before looking anywhere else.
- **The font injection is FLAKY on Drive's side: check it after EVERY create/update** (Aug 27 2026).
  The exact same body HTML uploaded twice gave 0 Bricolage occurrences on one run and 67 on the next,
  with no content change. It is a converter race, not a bug in the body. So always run
  `export --html | grep -o Bricolage | wc -l` after an upload, and if it comes back 0, simply re-run the
  identical `update` and check again. **It can fail several times running** (Aug 28 2026, TEC doc: two
  consecutive re-uploads of a payload that had already succeeded once both came back 0, the third gave 71),
  so retry at least three times before suspecting the body, and rule out the PNG-size cause above first. Do not go hunting for a styling cause first: reproduce it twice
  before assuming the HTML is at fault.
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
