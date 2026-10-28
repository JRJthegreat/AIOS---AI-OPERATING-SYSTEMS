---
name: upwork-cover-letter
description: Write the actual text Jude submits in Upwork's cover letter field when applying to a job. Use when asked to write an Upwork cover letter, draft a proposal message, or create the copy that goes in the Upwork application box. Distinct from upwork-proposal, which builds an optional Google Doc attachment. Output is clean copy-pasteable text, no Google Doc, no commentary.
---

# Upwork Cover Letter

Generates the cover letter text Jude pastes straight into Upwork's application box. This is
what actually gets submitted (per Jude, Aug 2026: he never used the ad hoc cover letters this
repo used to hand-author under `upwork-proposal`; this skill replaces that). Pure copywriting:
Claude authors the text directly. No API call, no Google Doc.

**One lane: the short form** (`templates/short_letter.txt`), which is what Jude actually sends.
**The long form is retired, even when a proposal doc ships with the letter (Jude, Oct 12 2026,
after four long-form letters for a batch that each carried an audit doc: "way too long... they
don't care really, trust me").** A doc link now rides in the short form as one line (part 3c
below); build the doc first with `upwork-proposal` and pass its link in as an input here.

## About Jude (baked-in context, do not re-derive each time)

- Top-rated AI automation engineer on Upwork, runs NEXAM AI.
- Based in Taiwan, works US hours.
- Builds: AI automation systems, outbound lead generation, CRM workflows, voice agents,
  scraping pipelines, SaaS platforms.
- Differentiator: records a **custom Loom** for every single application. For bigger projects
  he also writes a custom proposal doc.

## Inputs

Required every time:
- **The job post text.** Read the ENTIRE post, not just the top. Required phrases or magic
  keywords ("start your proposal with FORIS", "include the word pineapple") are usually
  buried near the bottom, easy to miss on a skim.
- **Jude's Loom link.** If missing, stop and ask for it before writing anything. Never invent
  or omit it silently.
- **Jude's Loom transcript or notes on what the Loom actually covers (Aug 2026, hard gate).**
  Do NOT write the letter until this has been provided, even though the Loom link itself may
  already be in hand. The credibility and technical-insight paragraphs have to match what the
  video actually says; writing them from the job post alone risks the letter promising or
  referencing something the Loom never covers. If Jude gives a Loom link without the
  transcript or notes, ask for it and wait rather than drafting around the gap.

Optional:
- A Google Doc proposal link (from `upwork-proposal`).
- The client's first name.

## Short form (the DEFAULT, Jude, Sep 8 2026)

**OUTPUT THE LETTER AND NOTHING ELSE (Jude, Sep 8 2026, after having to ask five times in one
session: "I always tell you that").** No job-post summary, no client-quality read, no budget or
connects analysis, no "three things worth noting", no explanation of why a proof phrase was
chosen, before or after the letter. He asks when he wants that. Deliver the letter text alone.
This overrides the instinct to be helpful with context: the context IS the noise.


Jude's actual sending habit. On the Hani trading/agentic-AI job he took the full long-form
letter below, cut roughly 80% of it, and sent this shape instead, then asked for it as a
template. **Use this by default.** The long form is now the exception, not the rule.

Template lives at `templates/short_letter.txt`. These parts, nothing else (1b only when a doc ships):

1. **Hook**, same rules as the long form (the word `custom`, the Loom link inside Upwork's
   ~230 character preview, checked with `scripts/check_hook_length.py`). Two phrasings:
   - `Hi {Name}. I created a custom Loom video for you about how I would approach your {specific project descriptor} project: {LOOM}`
   - `Hi {Name}. I created a custom Loom video for you, showing an example of {what it shows}: {LOOM}`
   **Default to the first, with the client's own project descriptor in it (Jude, Sep 9 2026).**
   He picked it on the Hani job even though that Loom was mostly a portfolio walkthrough, and on
   the freight quoting job he corrected an example-phrasing hook twice: first to the approach
   phrasing, then again to add the descriptor ("your freight quoting workflow project", not the
   bare "your project" the template shows). Jude's Looms almost always open by naming the
   client's project before showing proof, so the approach phrasing is accurate. Only use the
   example phrasing when the video genuinely never addresses their project, and raise it once
   rather than swapping silently.
   **Third phrasing, the exact-match hook (Jude, Sep 11 2026, jewelry/Loupe Factory Shopify agent
   job). When Jude has built the client's exact system before and the Loom walks through that
   build, lead the hook with the proof, not with the video:**
   `Hi {Name}. I've built this exact system before for another {client type}, so here's a custom Loom with a free walkthrough of it: {LOOM}`
   He rewrote the approach-phrasing hook into this himself on that job, after saying up front
   "we can lead with the fact that I have built this exact system before". Two things carry over:
   the word `custom` still appears, and `free walkthrough` is his framing (same reciprocity play as
   the free-audit doc line). When this hook is used, the experience line below must NOT repeat
   "I've built this exact system before", open it on what the system actually does instead.
1b. **Free-audit line, whenever a proposal doc ships: RIGHT AFTER THE HOOK (Jude, Oct 27 2026,
   LawNeeds job: "the document should be a little bit upward", i.e. straight after the Loom).** Its
   own paragraph. Say what the doc actually covers in plain words, lifted from the doc itself:
   `I also created a free audit document for you, showing {what the doc covers}. Completely free, no strings attached: {DOC LINK}`
   **Never write "It's my thank you for opening my proposal and watching the video"** (the Oct 12
   wording; Jude, Oct 27 2026: "I don't like when you say it's my thank you"). Keep "completely free,
   no strings attached". Do not re-sell the doc's findings beyond the one "showing" clause.
2. **One experience line: the similar project he built (Jude, Oct 12 2026, now the default).**
   His words: "I believe I'm a good fit for this job because I worked on a similar project
   before", plus "a little bit of line about what the project was, what the company was, what
   you did for them." Shape, one or two sentences:
   `I'm the perfect fit for this because I've built a similar {system} before: for {Company}, a {what they are}, I built {what it does}. {One clause tying it to their job.}`
   **Opener is "I'm the perfect fit for this", never "I believe I'm a good fit"** (Jude, Oct 27 2026,
   LawNeeds Pinecone job: "don't say I believe I'm a good fit. Say I am the perfect fit for this").
   Company names follow the claims bank's own rules (Boat in Paris and EMRG Media by name;
   Grenke only for Australian clients; a demo build with no client stays unnamed).
   **Only proof that matches the job's actual work, never an off-topic metric (Jude, Oct 29 2026,
   robot-training video/sensor QC pipeline job).** He rejected leading with the Meta ad-spy agent
   and its "20 hours a week to 10 minutes" number as "irrelevant", even though the Loom showed it.
   On data/vision/video-pipeline jobs, open on the NHRI biotech role (claims bank), then the video
   pipelines he helped companies build, described generically ("a pipeline that analyzes large
   volumes of video"), no ad-agent name and no ad metric. The older
   domain-range line below is the fallback for a job with no single close match:
   `I have direct experience with these types of {DOMAIN} projects, from {PROOF_ONE} to {PROOF_TWO}, so I should be able to handle your project straightforwardly.`
   - `{DOMAIN}` is lifted from the client's own words in the post ("trading and agent AI").
   - `{PROOF_ONE}` and `{PROOF_TWO}` are two real, contrasting claims-bank assets written as
     generic capability phrases, no links and no client names ("custom-coded decentralized
     exchange platforms" to "AI investment analysis workflows"). The plural is deliberate.
   - This single line replaces the long form's credibility, technical insight, "a little bit
     about me" and free next step paragraphs. Do not smuggle any of them back in. (The CTA
     came back as its own line, part 3d, on Oct 27 2026.)
3. **Social proof line**, verbatim, on the line immediately after the experience line with **no
   blank line between them**.
3b. **GitHub line (Jude, Sep 11 2026; default ON since Oct 12 2026, "put my GitHub link too").**
   One line, its own paragraph, after the social proof line and before the PS:
   `You can also see more of my code on my GitHub: https://github.com/JRJthegreat`
3c. **(Moved, see 1b.)** The free-audit line used to sit here, after the GitHub line.
3d. **CTA, always (Jude, Oct 27 2026: "There needs to be a CTA. Message me.").** Its own paragraph,
   after the GitHub line and before the PS, verbatim:
   `If you're still looking for someone with experience in this, feel free to message me back here on Upwork. I'd love to help.`
4. **PS**, verbatim: `PS: I have a 100% success score here on Upwork, so you are in safe hands.`
   It sits ABOVE the sign-off here, unlike the long form where the PS is the last line.
5. **Close**, verbatim and doubled: `Speak soon,` / blank line / `Best,` / `Jude`
   The two-line close is intentional. It was flagged to Jude twice and kept both times.

**"We decide what to send" (Jude, Sep 8 2026).** A job post's own instructions do not drive the
letter. The Hani post demanded an attached brief and carried two screening questions, and the
sent letter answered neither. Surface that kind of requirement once as a note to Jude, then
drop it. Never let it grow the letter or hold up sending.

**Still binding in the short form:** no em or en dashes, contractions throughout, the hook
character budget, claims-bank-only proof, the French-client rule, never promising guaranteed
financial returns, and the `.tmp/` cleanup rule.

## Long form structure (RETIRED Oct 12 2026, kept for history only)

Do not use this, including for letters that carry a proposal doc: Jude rejected four of these
on Oct 12 2026 as "way too long", and the doc link now rides in the short form's part 3c. The
reasoning below (hook budget, free-audit framing, claims rules) still informs the short form.

The order below is exact:

1. **Required keyword/phrase, if the post buries one.** Goes on its own line, above
   everything else, including the hook.
2. **Hook (first line, the whole game). Two variants, pick by what the Loom actually shows
   (Jude, Aug 2026, corrected the single-template version below for being forced when the
   video isn't literally the client's own project):**
   - **The Loom is genuinely about their project/approach:**
     `Hi [Name]. I created a custom Loom video for your [specific project descriptor] project: [LOOM LINK]`
   - **The Loom shows a relevant example or demo (e.g. a system built for a different company,
     a portfolio piece), not literally the client's own project:**
     `Hi [Name]. I created a custom Loom video for you, showing an example of [specific descriptor]: [LOOM LINK]`
     Do not force the first variant's "for your ... project" phrasing onto a video that is
     actually a proof example, it reads as inaccurate the moment the client watches it.
   - Name only if known, otherwise just `Hi.`
   - The descriptor must be specific and lifted from the client's own language in the post
     (e.g. "peptide ordering and fulfillment system," "GoHighLevel customer lifecycle,"
     "Stripe payment reminder") or, for the example variant, name what the Loom concretely
     shows (e.g. "an AI sales feedback automation"). Never generic jargon like "automation
     project."
   - The word **custom** always appears.
   - **Character budget, non-negotiable:** Upwork's preview shows only the first ~230
     characters. Everything before the Loom URL must be under ~170 characters so the full URL
     is visible and clickable in the preview. Check with `scripts/check_hook_length.py` before
     handing the letter back (see below).
   - Never bury the Loom link below other text.
3. **Proposal doc line, only if a doc link was given. Default framing (Jude, Aug 15 2026,
   supersedes the two-variant rule below as the default): the doc is a FREE AUDIT.** The doc
   is now built to carry this framing (see `upwork-proposal`: audit language in the title and
   the researched technical-flags section as the audit's core), and the letter line sells it
   as something free, custom, and worth reading, a reciprocity play in Jude's words ("that
   guy gave me something free"). Shape, close to his own phrasing:
   `I also took the time to create a free audit for you, outlining exactly [what it flags in their specific stack]. I wrote this custom for you and it took real time to put together, so I'd really encourage you to give it a read. Here's the link: [DOC LINK]`
   The framing must stay honest: only call it an audit when the doc actually contains
   researched, client-specific findings (the `upwork-proposal` flow produces these by
   default). If a doc somehow ships without any audit substance, fall back to the older
   two-variant rule below.
   **Older two-variant rule (now the fallback). The dividing line is NOT
   "does the doc contain real research", it is whether the doc explains something the client
   already saw demoed in the Loom, versus something genuinely new beyond it (Jude, Aug 2026,
   corrected a first attempt at this rule that used "research-driven vs portfolio roundup" as
   the split; the sales-coaching doc had real research and tradeoffs in it and he still picked
   the simple variant, because the doc was elaborating on the exact system already shown in the
   video):**
   - **The doc goes deeper on something the Loom already demoed or walked through** (the most
     common case when Jude shows a system in the video and the doc is its detailed written
     companion, even if that doc contains genuine analysis, tradeoffs, or a real technical
     finding): the simpler
     `I also have a Google Doc that outlines in detail [what it covers, tied to what the Loom showed]. Here's the link: [DOC LINK]`
   - **The doc contains something the client has not seen or heard yet**, because it is
     client-specific analysis the Loom did not cover (e.g. a real platform/API constraint about
     the client's own stack that only appears in the doc, like the Halaxy paid-API-add-on
     discovery, where the Loom pointed at the doc without restating the finding):
     `I also took the time to create a custom proposal outlining exactly how I'd [do the thing]. Here's the link: [DOC LINK]`
     followed by
     `I wrote this myself and it took real time and research, so I'd really encourage you to give it a read.`
   - Do not claim "real time and research" for a doc that is really just the written version of
     what the client already watched, that oversells it and reads as templated once they notice.
4. **Credibility paragraph.** Named clients plus concrete results, tight. Do not re-explain
   how the systems work, the Loom already does that; if a system explanation runs three
   sentences, cut it to one. Pull claims **only** from the claims bank below, never invent a
   client, number, or result.
5. **Technical insight paragraph, when applicable.** This is Jude's biggest differentiator on
   complex jobs: name a real constraint or gotcha about the client's specific stack, stated
   directly with the tradeoff. Style reference: "Kajabi's API doesn't expose email analytics,"
   "QuickBooks gives card balances but not credit limits," "Make bills per operation so n8n is
   cheaper at scale," "WhatsApp Business API requires a dedicated number." Skip this paragraph
   entirely if there's no genuine finding for this job; do not force one.
6. **"A little bit about me" paragraph, always this exact shape:**
   `A little bit about me: I'm a top-rated AI automation engineer with hands-on experience building [3-4 relevant things]. I've shipped dozens of high-performing systems for [relevant client type], many of which have scaled to $1M+ in revenue. I'm extremely proficient at [4-6 relevant tools/skills].`
7. **One specific free next step, tied to the job.** A single sentence offering something
   concrete you can send before they commit (a data model, an entity diagram, a permission
   checklist), framed so it is theirs whoever they hire. **Do not open this with "Let me know
   if you're interested in working together"** (Jude, Aug 27 2026: "I don't like this"). The
   interest line moved to step 9, where it doubles as the CTA.
8. **Social proof line.**
   `Below are a few samples of recent reviews from clients and systems I've created. I can provide dozens of additional examples upon request.`
   Keep `dozens`. Jude approved this exact wording, and a bigger number reads as a boast.
9. **Interest plus CTA, in this position.** Jude dictated the order (Aug 27 2026): social proof
   line first, then this.
   `I'd love to help you build your [their thing, in their own words]. Let me know if you're open to a quick chat.`
   **This asks for a chat on purpose, and it does NOT violate the reply-only rule.** That rule
   (`feedback_low_friction_ask`) governs COLD outreach and proposal docs, where a call ask is
   friction against someone who never asked to hear from you. An Upwork client who posted a job
   is already planning to interview candidates, so offering a chat matches what they expect.
   Do not "correct" this back to a reply-only CTA.
10. **Sign-off.** `Best,` / `Jude`
    A bare `Jude` is right here: his Upwork **display name is now Jude** (changed Aug 2026), so
    the letter matches the profile the client is reading it on. Do not expand it to
    `Rood Judeley Joseph (Jude)`; that byline belongs on the proposal DOC, not the letter. This
    is a real exception to `feedback_upwork_byline`, recorded there too.
    Also drop the old `Looking forward to connecting!` line: it is redundant next to the chat
    CTA in step 9.
11. **PS, always the last line.** `PS: I work US hours, feel free to message me anytime.` Swap
    for a timezone-overlap line instead if the client is in Australia, Hong Kong, Japan,
    Singapore, or New Zealand (e.g. "PS: I'm in a similar timezone to you, so overlap won't be
    an issue.").

## Claims bank

Pull every credibility-paragraph and technical-insight claim from the
`reference_upwork_proposal_claims_bank` memory. It holds, among others: Grenke Australia
(outbound pipeline, AUD 800K pipeline value, 25,000+ companies classified), EMRG Media (NYC
events, GoHighLevel stack, Speed to Lead system, 40% revenue increase), HiveIQ (SaaS platform,
lead AI engineer, built on Supabase, founder testimonial), cold email campaign results (61
conversations / 58% positive reply rate in logistics, 18 conversations selling SEO to $1M+
companies, 54 conversations in 2 weeks for hotels), a Meta Ad Library / Facebook Ad Spy scraper
for a California ecommerce brand (cut competitor research from 20 hours/week to 10 minutes), a
Monday.com CRM for a law firm (GraphQL API), invoice automation (QuickBooks for a Florida
plumbing company, PDF.co plus Airtable parser for a New Jersey manufacturer, a Stripe overdue
invoice chase system), an AI resume generator plus job application system, custom scrapers
(Google Maps via Apify, Instagram, LinkedIn Sales Navigator), his personal Claude Code AI
operating system with a multi-agent setup and custom skills (this repo), and name-drop-only
mentions of a blockchain decentralized exchange, an AI hedge fund, and a stock analysis app.
**Never invent a client, number, or result beyond what is in that memory.** If nothing in the
bank fits the job, keep the credibility paragraph general instead of stretching a claim to fit.

The bank also holds proof-asset **links**, not just claims: the HiveIQ founder testimonial
YouTube link (https://youtu.be/gwt_qoaR6d0) and Jude's GitHub (https://github.com/JRJthegreat)
are both on file there. When the Loom promises either link "in my cover letter", include the
actual URL in the letter (Aug 2026 miss: a letter shipped saying "you'll find it in my
portfolio" when the YouTube link was sitting in the bank). And apply the bank's audience and
framing rules, not just its facts: Grenke is named for Australian-market clients only
(anonymous "equipment finance company" otherwise), and HiveIQ is always "lead AI engineer"
with "we", never a solo end-to-end build claim.

## Hard rules

- **No dashes of any kind, em or en.** Commas, parentheses, or restructure the sentence.
- **Contractions always** (I'm, I've, you're). It should read like a person talking, not a
  corporate template.
- **Never over-explain the systems.** The Loom carries the detail.
- **Screening questions Upwork asks in separate fields do NOT go in the letter body.** If the
  post has them, ask Jude whether he wants them folded in anyway before doing so.
- **French-speaking clients (Quebec, France, etc.):** write the whole letter in French, but
  keep the "A little bit about me" paragraph in English.
- **Never promise guaranteed financial returns** on trading or investment jobs.
- **Match technical depth to the client.** Technical posts get technical depth, non-technical
  posts get plain language.

## Output format

Clean, copy-pasteable text. **No commentary before or after, ever, unless Jude explicitly asks
for it.** See the hard rule at the top of the short form section: this is the single most
repeated correction in this skill's history. If something required is missing, above all the
Loom link or the Loom transcript/notes, ask before writing anything.

**No job link under the letter (Jude, Oct 28 2026: "remove the job link when you are giving me
the cover letter to copy").** Use the job URL to pull the post (`find_jobs` action=`get`), but
never echo a trailing `Job: <url>` line after the letter; it gets in the way of copying. The
`upwork-proposal` echo rule covers doc handoffs only.

## Character budget check

```bash
python3 .claude/skills/upwork-cover-letter/scripts/check_hook_length.py \
  "Hi Ronald. I created a custom Loom video for your secure pet ID tag activation flow project: https://www.loom.com/share/abc123def456"
```

Reports the character count before the URL (target under ~170) and the total through the end
of the URL (target under ~230, Upwork's real preview cutoff). Run this on the hook line before
handing the letter back; tighten the descriptor if it fails.

## Cleanup (Aug 2026, Jude)

`.tmp/cover_letter_<slug>.txt` piled up badly before this rule: dozens of old letters sat
there indefinitely. Once Jude confirms in chat that a letter was sent or is otherwise done
with (not before, and don't assume silence means done), delete its `.tmp/` file(s) for that
job right away, in the same turn. Do not proactively bulk-delete older `cover_letter_*.txt`
files from earlier sessions without asking first, since their sent/unsent status is unknown.

## Related

- `upwork-proposal`: the Google Doc attachment for bigger jobs, and the skill's own house
  style (no em dashes, Bricolage Grotesque, reply framing) that this one shares.
- `reference_upwork_proposal_claims_bank` memory: the source of truth for every credibility
  claim.
- `feedback_upwork_cover_letters_unused` memory: why the old hand-authored-per-job cover
  letters got replaced by this skill.
- `templates/short_letter.txt`: the short-form template, the default shape for a letter that
  ships on its own.
