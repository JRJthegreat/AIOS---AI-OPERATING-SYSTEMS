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
  send something and ask for a reply.
- **Lead with proof.** The "Why me?" section opens on hard-number case studies.
- **Problem Overview is natural prose grounded only in what the prospect said
  on the call.** No invented pain. No sub-headings stacked on top of each other.
- **No horizontal separator bars** between sections (they read as AI-generated);
  sections divide by their headings. Blank line spacing via `<p>&nbsp;</p>`.

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

How it differs from the transcript path above:
- **Proposal only** (no cover letter), **no Google Sheet**.
- Structure is the apply-style proposal: opening that mirrors the JD, a proof
  line, "My proposed approach" (numbered), "What you'll get", "Timeline", a
  **reply-only** close, signed "Jude". Not the 5-section bespoke structure.
- **Proof uses bracketed placeholders** (e.g. `[500+ calls/day]`, `[a SaaS
  client]`) on purpose, the model never invents a metric. Fill them in before
  sending.

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
