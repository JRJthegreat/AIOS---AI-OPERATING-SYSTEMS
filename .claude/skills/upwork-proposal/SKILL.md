---
name: upwork-proposal
description: Create, build, generate, or write a client-facing Upwork proposal as a styled Google Doc from a discovery-call transcript and a case-study sheet. Use when asked to write an Upwork proposal, draft a client proposal doc, or turn a sales call into a proposal. Output is a native Google Doc (Bricolage Grotesque font, no em dashes, Upwork-consultant byline).
---

# Upwork Proposal

Turns a discovery-call transcript (plus a case-study Google Sheet) into a
polished, client-facing **Upwork proposal as a native Google Doc**. The doc is
built and edited through the driver `proposal_doc.py`, which talks to the Google
**Drive** API (HTML upload + convert) and **Sheets** API. Styling starts in the
uploaded HTML. **Environment verified Oct 2, 2026 (rechecked Oct 6):** the current token also
permits Google Docs API reads and `batchUpdate` (the Drive scope covers it), useful for final
paragraph/page layout. Check access with a read-only call rather than assuming the old
no-Docs-API limitation.

All paths below are relative to the repo root. Run everything from the repo root.

## THE WINNING FORMAT (Nov 3 2026 reset, read this first)

**This section overrides everything below that conflicts with it.** Jude, Nov 3 2026: "when did
we come up with this formula for the Google Doc? Because the formula that we're using that actually
got us job, before is not this one." He was right. Every doc that won work predates late August:

- Axel (Paris boat-tour scheduling, Jul 23 2026), `1voalYmJcXn_E35zA2LeFq6NZAL0o9zQYhAV_xubnrN4`,
  538 words, no diagram. Won a paid two-developer bake-off.
- Larry Hotaling (quotation follow-up, Jul 30 2026), `1Q6JxthIXIHGB3RNLXiMzzZdBGQQBd0GPacqtHCpMIF8`,
  1,140 words, no diagram. **This is the model doc. Export it and read it before authoring.**
- Kimberly Works / Pediatric Works (post-call, Aug 17 2026), `1I-Is5B0Pt8m0Qxhz-uH5pdYSxKzNXmR-uSkvDOMdxSo`,
  976 words, one simple "whole system on one page" diagram.

Then, one complaint at a time, the doc turned from a letter into an audit report: the "free audit"
framing (Aug 15), "Signed off when" acceptance tests (Aug 21), the mandatory linter-enforced
"N things I checked before writing this" audit of vendor research and a mandatory technical
architecture diagram (Aug 27), bigger diagrams (Aug 28), a scoping-call close (Sep 2). No
proposal turned into a new contract after Aug 19 (job targeting changed too, so not proven
causal, but the timing lines up). The Qualcon Spaces doc (`1O8WzEAdvnmx3rsyfKwekUmSTAY57RLMdVZo23bOoT2w`)
was first built in the audit format and redone in this one the same day.

**The winning skeleton** (`templates/proposal_body.html` encodes it):
1. `<h1>` "<What it is> for <Client>" (no "audit" in the title) and the two-line byline.
2. **What you're after**: `Hey <Name>,` then ONE paragraph mirroring what they asked for in
   THEIR words and THEIR specifics (Larry's: "day 10 to the person you quoted, day 21 to that
   person plus senior management contacts"). If a Loom ships with it: "This is the written
   version of what I showed you in the video." No free-audit line.
3. **The system from the video, and why yours is the same logic** (or "A system I've built that
   runs on the same logic" when the Loom shows something else): ONE proof story with real numbers
   from the claims bank, then the analogy that lands it, "Different object, same machine."
4. **How I would build your system**: an optional one-paragraph stack call in plain language
   (Pediatric: "HubSpot stays, but only as your database... n8n, about $30 a month"), then 5 to 7
   numbered steps in the client's own process terms. Optional diagram right after the stack call,
   introduced with "Here's the whole system on one page:".
5. **Three things to get right early**: 2 or 3 practical risks in plain words, what goes wrong and
   what the build does about it (Larry's: deliverability and tone, missing senior contacts, honest
   AI classification with a review queue). Common sense the client recognises. A real platform rule
   that bites (a carrier registration, an off-platform ban) belongs here in one plain sentence, but
   no vendor quotes, no price comparisons, no citation-style research dump.
6. **What you'll get**: 4 to 7 outcome bullets.
7. **Timeline**: a rough sequence or honest week range (both cold winners gave one), or the
   client's own phases mirrored back, plus what you need from them to start.
8. **One more practical note**, only when it fits (Larry: Hong Kong, Jude lives in Taiwan and
   speaks Chinese, same hours; Axel: French).
9. **Next step**: "If this approach resonates, send me a message." plus ONE small, specific free
   next step tied to their first step (Larry: the system map for their setup plus draft copy for
   the day-10 and day-21 emails, "free, so you can judge both the thinking and the tone before
   committing to anything"). Not a scoping call.
10. `Best,<br/>Rood Judeley Joseph (Jude)`.

**What is OUT:** the "Free audit" title and opener line, the mandatory "N things I checked" audit
section, "Signed off when" acceptance tests on every step, the mandatory technical architecture
diagram, vendor quotes and competitor price comparisons, the scoping-call close. **What stays:**
600 to 1,100 words, Bricolage, no em dashes, no tables, no placeholders, `<p>&nbsp;</p>` gaps,
clickable proof links (Jude's own only), no fee for Jude's own work (client-side tool costs are
fine when the client asks for them, as Pediatric Works did), the claims-bank-only proof rule.

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
  When the doc carries a diagram, keep it rather than cutting it: a good one replaces a lot of
  prose. But a diagram is optional since Nov 3 2026 (see THE WINNING FORMAT).
- **No em dashes, ever.** Use commas, colons, periods, or parentheses. The
  driver refuses to upload any body that contains an em dash.
- **Font is Bricolage Grotesque.** The driver injects it; do not change it.
- **Byline is `Rood Judeley Joseph (Jude), Upwork consultant`.** Never mention
  NEXAM in a client deliverable.
- **Never leave a browser tab open on the doc (Jude, Aug 28 2026: "I can see there are some
  profiles that are looking at the doc right now").** A Playwright tab left on a Google Doc keeps
  showing as a live viewer avatar in the doc's header, so Jude (and the CLIENT, once the link is
  sent) sees phantom people reading it. Close the tab with `browser_close` the moment a visual
  check is done, every time, including the doc itself and any localhost page used to render the
  flowchart. See **Finding a stale viewer** in Gotchas for how to hunt one down after the fact.
- **Plain language, no jargon.** Explain like a smart non-specialist is reading.
- **The close is "send me a message" plus ONE small free next step (Nov 3 2026 reset, SUPERSEDES
  the Sep 2 2026 scoping-call close).** Both cold-proposal winners (Larry, Axel) closed this way.
  On Sep 2 Jude had switched to a scoping call because nobody ever claimed the free offer; the
  offer is not what wins, so keep it small and specific, tied to their first build step, and let
  "send me a message" do the work. Never a meeting ask in the doc.
- **Lead with ONE proof story, tied to the Loom.** "The system from the video, and why yours is
  the same logic": what that client needed, what Jude built, the real result, then the analogy
  ("Different object, same machine"). A second proof only if it proves something different.
- **RETIRED Nov 3 2026: "Frame the doc as a FREE AUDIT" (Aug 15) and "the doc must carry the
  gaps/traps/stack-call audit" (Aug 27).** Both were part of the drift away from the winning
  letter. "Useful" now means the client's own specifics mirrored back, the build in their process
  terms, and the short "Three things to get right early" section. The cover letter's doc line
  (`upwork-cover-letter`) already dropped the free-audit wording on Oct 30 2026.
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

**Nov 3 2026:** this section applies when the doc carries a diagram. The copy agent no longer runs
an audit research step or hunts for "gaps, traps and the stack call"; it writes the winning-format
letter (THE WINNING FORMAT above) and only checks the facts the letter actually states.

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

**The flowchart sets the clock, so it starts first (Jude, Oct 13 2026).** His words: "The
flowchart is the most valuable thing here... the goal is to provide a free audit, quickly explain
how you would get this done with a nice visual representation of it." Said after two jobs went
stale (35 and 46 minutes from JD to doc) in a chain where research ran first, the copy agent wrote
the architecture spec partway through a 1,750-word draft, and only then could the flowchart start;
an Opus review then changed the architecture and forced a relabel. The order that respects his
goal:
1. The architecture spec (named components, the branch, the human step, the foundation line)
   is the FIRST file written, right after the JD is pulled and the research that the components
   depend on is checked. The flowchart agent starts the moment it exists.
2. The copy is SHORT (600 to 1,100 words, the winning-format letter) and is written in
   parallel with the diagram, never ahead of it.
3. Review covers claims, commitments and house rules. It re-fetches a source only when a fact
   looks wrong, and it changes the architecture only for a factual error in the diagram.

Agents to dispatch in one message, in parallel:

- **Copy agent**: drafts the body from `templates/proposal_body.html` in the winning format, with
  the proof story taken verbatim from the claims bank and the Loom transcript. Light research only,
  for the few platform facts the letter states (and the "things to get right early").
- **Flowchart agent**: builds and screenshots the diagram (recipe below), doing its own
  eyeball-and-fix pass internally before returning; this is real, protected time, not
  something to rush.
- **Cover letter agent** (JD path only): drafts the Upwork cover letter off the same JD and
  the claims bank, in parallel, since it does not depend on the copy agent's exact wording.

Then in the main thread: read the "Similar work" section against the claims bank sentence by
sentence (Sep 29 2026: one agent added a made-up "its main issue was Notion's rate limit" to a real
project, another described Grenke as leasing "to healthcare businesses"; neither is on file), and
ask the agent for the saved query/output behind any statistic it produced itself. Then run
`check_proposal_html.py` on the copy agent's HTML and fix anything it flags, embed the flowchart's base64, run the doc script **once** (`create` /
`update` / `proposal_from_jd.py --body-html`), do one quick structural check (`export --html |
grep '<img'`), and hand off doc URL + cover letter + job URL together. **Hand off the share link form,
`https://docs.google.com/document/d/<ID>/edit?usp=sharing`, not the `usp=drivesdk` URL the driver
prints** (Jude, Nov 3 2026).

## RETIRED Nov 3 2026: the mandatory audit section (history only, do not apply)

Superseded by THE WINNING FORMAT at the top: none of the three docs that won work had this section.
The practical part that survives is the short "Three things to get right early". The Aug 27
reasoning below is kept only so nobody reintroduces it without seeing why it was dropped.


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

**Both paths use the winning letter structure** in THE WINNING FORMAT at the top. Start from
`templates/proposal_body.html`, which encodes it.

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
Also gone: the formal
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

## Single-job applications

This is the only Upwork proposal path (the old batch `upwork-apply` skill was deleted Oct 6 2026;
git history has it). It handles one job at a time, from a JD pasted into chat or pulled with the
Upwork MCP's `find_jobs` action=`get`, via `proposal_from_jd.py` below.

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
message alongside the doc URL (format: "Job: <url>"). A cover-letter-only handoff never
carries it (Jude, Oct 28 2026, see `upwork-cover-letter`). Pull the JD from the URL with the
Upwork MCP (`find_jobs` action=`get`); the page itself is login-gated.

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

**Structure: THE WINNING FORMAT at the top of this file (Nov 3 2026 reset).** The Aug 2026
"letter structure" that used to be listed here (free-audit opener, mandatory audit, "Signed off
when" milestones, scoping-call close) is superseded. One rule from it still stands: **the proof
that matches the client's own platform leads the proof section** (Oct 12 2026, Bennett Meta-ads
job: the Facebook Ads Spy Agent repo was cited only inside a question-1 answer, and Jude asked
"why didn't you mention that?"). A platform-matched asset, above all one Jude demos in the Loom,
leads and goes in the cover letter too. A mandated JD question list is answered in prose inside
the build steps or the risks section, never a table. Any real skill gap gets one sentence (see
`feedback_honest_gap_framing`).

**Timeline wording (Nov 3 2026, per the winning docs):** Axel's said "about 2 to 3 weeks",
Larry's split weeks one to two and two to three. A rough, honest range is fine, or mirror the
client's own phases when they gave them. The Aug 2026 reason for avoiding durations still matters
(Jude builds fast with Claude Code, so a very short estimate invites repricing), so never quote
less than the work is worth, and name what you need from their side to start. Money for Jude's own
work still never appears in the doc.

How the LLM path differs from the transcript path above:
- **Proposal only** (no cover letter), **no Google Sheet**.
- Structure is the winning letter shape (Nov 3 2026): What you're after, the same-logic proof
  plus analogy, How I would build your system, Things to get right early, What you'll get,
  Timeline, a "send me a message" close with one small free offer.
- **It cannot see the Loom, the claims bank or the web, and it cannot draw.** Its proof story is
  placeholders. For a job Jude is really sending, author the body and render with `--body-html`.
- **The LLM still emits bracketed placeholders** (e.g. `[500+ calls/day]`) so it
  never invents a metric, but **NO placeholder may survive into the delivered
  doc** (house rule, Jul 2026: a forgotten bracket reads as templated and kills
  trust). Immediately after generation, replace every bracket with a real
  verified number, or rephrase without a number ("hundreds of records per run")
  and `update` the doc before handing Jude the URL. When authoring the body
  yourself, write real numbers directly from the start. The one exception is
  `[LOOM LINK]` in cover letters, which Jude swaps after recording.

## Flowchart (OPTIONAL since Nov 3 2026)

Two of the three winning docs had no diagram; Pediatric Works had one simple "whole system on one
page" view. So use a diagram when the system has several moving parts (multiple channels, a
branch, a human step) and it genuinely saves prose, not by default. When you do use one, it still
has to be good (Jude: "don't give me anything sloppy"). Working recipe, learned on the AI
Maintenance Coordinator proposal:

**Placement (Nov 3 2026, per the Pediatric Works doc):** inside "How I would build your system",
right after the one-paragraph stack call and before the numbered steps, introduced with "Here's
the whole system on one page:" ABOVE the image (a caption under the image gets orphaned when the
image moves). The Aug 27 rule that put it at the end of the build section is superseded.

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

- **SIZE RULE UPDATED (Jude, Aug 28 2026): "the flowcharts can be bigger and larger" and "the very
  detailed flowchart is the value of the google doc proposal."** The 240px cap below is SUPERSEDED.
  The real ceiling is one page: **at most ~620px displayed, ~1240px of canvas at 2x**, because a
  Google Doc page body is ~648px and Docs will not split an image. Fill that budget with COMPONENTS
  and WHITESPACE, never with more words per box. Spend the height.

- **The failure mode to avoid, and it took three rejected drafts to name (Aug 28 2026, TEC job).**
  Asked for "more technical" I added sentences inside the boxes; asked for "bigger" I added more
  rows; I never added air. The result was 24 boxes of small grey prose at 8px padding and
  `line-height:1.2`, and Jude's verdict was "why is the flowchart so concentrated... they are bad."
  **A box gets a component name plus a FRAGMENT of 3 to 8 words** (`410 resyncRequired forces a full
  recrawl`, `No citation, no answer`, `Re-reads superseded_by at send`), never a sentence and never
  two. The explanation belongs in the prose above the image. Concretely, the layout that worked:
  a left **swim-lane label column** (~132px, uppercase 23px) naming each stage (INGEST, PROCESS,
  INDEX, ANSWER, DELIVER, EVALUATE), **3 cards per lane maximum**, card padding 13-17px, `gap:34px`
  between cards, `gap:20px` between lanes, heading **28px**, subtitle **24px**, and one full-width
  tinted panel for the centrepiece (the index schema). Detail comes from having 15 real components
  and one hard technical fragment on each, not from cramming.

- **THE EXEMPLAR: doc `1IJOCoYPBlNK2-fZWz08WCj7KdWez1vAMZ8KZ2qvOQKE` (the quotation-system diagram).**
  Jude pointed at this one as the flowchart that works, after rejecting three of mine. Pull it with
  `proposal_doc.py export --id <ID> --html` and base64-decode the `<img>` before authoring a new
  diagram. Its design language, which is now the house standard:
  - **A title and subtitle inside the image** ("How the quotation system fits together" / one line of
    plain-English framing). Not a tenant chip, an actual headline.
  - **Numbered eyebrows**: `1 · REQUEST`, `2 · AI CLEANUP`, 21px, 700, letter-spacing 2.6px, uppercase,
    `#8a9099`. The sequence is explicit.
  - **Black borders and black arrows.** `border:3px solid #14161a`, arrows `stroke:#14161a` at 4px with
    a solid triangular head. Pale grey borders (`#dde1e7`) and thin grey arrows are why my versions read
    as washed out and mushy.
  - **Varied box widths and a real branch.** Not a grid. The reference fans one wide box into three
    outcome boxes, then funnels two of them onward. On the TEC job the honest branch was
    `cited answer | refused: confidence | refused: category`, all three converging on the escalation box.
    A diagram of N equal rows of equal boxes is a table, and Jude reads it as one.
  - **Colour used sparingly, for meaning only**: blue (`#2563eb` border, `#eff5fe` fill) on the two boxes
    that are the system's core, amber (`#d0932a` / `#fdf6ea`) on the single human step, light grey
    (`#f2f4f6`) on the outcome boxes, dark bar for the system of record. Never flood whole rows.
  - Type: title 34px, subtitle 24px, heading 29px/700, body 24px/`#4b5563`, padding 12-16px.

- **Arrowheads flip direction when the path length goes negative.** `across`/`elbow` start at
  `A.right + GAP` and end at `B.left - GAP`, so if the CSS `gap` between cards is smaller than
  `2 * GAP` the segment inverts and the marker renders pointing backwards, or a stub with no line.
  Hit twice on this job (card `gap:14px` with `GAP=8`, then lane `gap:20px` with `G=11`). **Keep
  `2 * GAP` at least 10px below the CSS gap** and eyeball every arrow in the render before shipping.
  This bit a THIRD time on the same job because I shrank the row gap for height without touching `G`,
  so do not hardcode it: derive it, `const G = Math.max(3, Math.min(9, ROW_GAP/2 - 3));`, and re-check
  the render after any spacing change.

- SUPERSEDED, kept for context: **it must be SMALL: at most ~240px DISPLAYED, so ~480px of canvas at 2x** (Jude, Aug 27 2026:
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

## Final pagination check (verified Oct 2, 2026)

The current OAuth token can call the Google Docs API using the existing `_creds()`.
After Drive conversion, `documents.get` and `documents.batchUpdate` can adjust layout
without reimporting the body or disturbing the embedded image/font. On a batch of ten
proposals, use of `keepWithNext` for the architecture caption and intervening blank
paragraph kept the caption with its image. `keepLinesTogether` and
`avoidWidowAndOrphan` prevented split paragraphs; keeping the signature paragraphs
together removed lone-name pages. Modest 48pt top/bottom margins and 6pt blank spacer
paragraphs preserved readable body text and diagrams. These are optional layout
adjustments, not mandatory page-count shortcuts. If a final signature still spills,
trim repetitive proof prose before shrinking the diagram.

Export PDF after these edits and inspect it. Re-export HTML as the live source for
any subsequent safe edits: uploading an older authored body would undo API formatting.
Do not assume permission from a previous environment; verify access read-only first.

When reimporting a live HTML export to replace a figure, preserve the live content,
replace the image source, and restore numeric width/height attributes. Check actual
PDF font names afterward: exported spacer runs can return as Arial even while the
body retains Bricolage. A whole-document `weightedFontFamily.fontFamily` update can
also normalize bold runs to regular. Preserve or explicitly restore each heading
and bold lead-in's `bold` flag and 700 weight, then verify both Bricolage Regular
and Bold in the exported PDF. Reapply pagination after any HTML reimport.

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

- **Drive HTML import remains the creation path.** Docs API access is verified (Oct 2, 2026) but
  only for post-conversion layout (see Final pagination check). Font is set via inline CSS in the HTML, so
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
- **Finding a stale viewer on a doc (Aug 28 2026).** Jude runs a dozen Claude sessions at once,
  each with its own Playwright MCP browser, so a phantom viewer is usually another session's
  leftover tab, not this one's. `browser_tabs list` only sees THIS session's browser, so it will
  come back clean and prove nothing. The browsers launch with `--remote-debugging-pipe`, so there
  is no port to attach to either. What works is reading each profile's history on disk:

  ```bash
  cd /Users/air/Library/Caches/ms-playwright-mcp && for d in mcp-chrome-*; do
    cp "$d/Default/History" /tmp/h.db 2>/dev/null && echo "$d :: $(sqlite3 /tmp/h.db \
      "select url from urls where url like '%docs.google.com%' order by last_visit_time desc limit 3")"
  done
  ```
  Match the doc id, then `kill` that profile's top-level `Google Chrome` pid (find it with
  `pgrep -f mcp-chrome-<hash>`). Killing it is cheap and safe: the owning MCP server relaunches a
  browser on its next call. Do not kill the `playwright-mcp` node servers or Jude's own Chrome.
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
