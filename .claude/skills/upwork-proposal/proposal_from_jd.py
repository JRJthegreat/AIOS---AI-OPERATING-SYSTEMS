#!/usr/bin/env python3
"""
Upwork proposal Google Doc from a job description.

Pipeline: JD in (file / stdin / --jd) -> Azure gpt-5.1 writes the proposal ->
rendered to a native Google Doc via the upwork-proposal renderer
(proposal_doc._prep: Bricolage Grotesque font + em-dash guard) -> link-shared.

Proposal only (no cover letter). No Google Sheet. Proof lines use bracketed
placeholders (e.g. "[500+ calls/day]") so the model never invents a metric.

IMPORTANT, this path is the fallback, not the default. It has no web access, so the
audit section it writes can only reason from the JD plus training data, and the audit is
the part of the proposal that actually wins work (it needs live research into the client's
stack and its API docs). It also cannot build the flowchart. For any job Jude is really
sending, author the body yourself with research and a diagram and render it with
--body-html. Use the LLM path for a fast first draft or a low-priority job only.

Auth: token.json in the CWD (Drive scope). Run from the repo root.

Usage:
  python3 .claude/skills/upwork-proposal/proposal_from_jd.py \
    --jd-file .tmp/jd.txt --client "Acme"
  pbpaste | python3 .claude/skills/upwork-proposal/proposal_from_jd.py --client "Acme"
"""
import os
import sys
import json
import html
import argparse
from pathlib import Path

# reuse the canonical proposal-doc renderer (em-dash guard + Bricolage font)
sys.path.insert(0, str(Path(__file__).resolve().parent))
import proposal_doc  # noqa: E402  -> _prep, _drive

from openai import AzureOpenAI  # noqa: E402
from googleapiclient.http import MediaInMemoryUpload  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

load_dotenv()

SYSTEM = (
    "You are Jude, an AI automation engineer (n8n, Make, Claude/OpenAI APIs) "
    "writing a first-person Upwork proposal. Voice: conversational, direct, "
    "confident, peer-to-peer, never salesy."
)

USER_TMPL = """Write a personalized Upwork proposal for this job.

JOB DESCRIPTION:
{jd}

Return ONLY a JSON object with these fields:
{{
  "focus": "4 to 8 words naming the scope of the work, for the 'Focus:' byline line.",
  "greeting": "Hey [first name only if it is clearly in the JD, otherwise just 'Hey'],",
  "opening": "1-2 sentences mirroring their SPECIFIC pain or goal. Reference something concrete from the JD, not generic filler. End by telling them this document is a free audit of the approach they have picked.",
  "proof": "Start: 'I've built similar [specific thing relevant to THIS job].' Then one proof sentence. For EVERY number, result, timeframe, or client name use a bracketed placeholder, e.g. '[500+ calls/day]' or '[a SaaS client]'. NEVER invent a real metric or client name.",
  "audit_heading": "e.g. 'Three things I checked before writing this' or 'Two things I would push back on'. Match the count to the number of items you actually return.",
  "audit": ["THE MOST IMPORTANT FIELD. 3 or 4 items, 3 to 4 sentences each. Every item must do ONE of these three jobs, and across the set you must cover at least two of them: (a) name a GAP or a false assumption in their spec, or a prerequisite on THEIR side they have not thought of, (b) flag a TRAP that bites after launch and say what prevents it, (c) make the TOOL or STACK call, with the reason AND the alternative you are rejecting and why. Name the specific product, plan tier, API limit or behaviour. Where a tool in THEIR OWN spec is the wrong call, say so plainly as a push-back. If you are not certain a technical fact is still current, write it as the thing you would verify first and say what it changes about the build, rather than asserting it. NEVER write generic caution: 'data quality is important', 'we should scope carefully' and 'testing is key' are all banned, they are worse than nothing because they take the slot a real finding should have had."],
  "approach": ["4 to 6 milestones. Each: what gets built and WHY, with the specific tools where relevant. End each one with an objective acceptance test in the form 'Signed off when: ...' that the client could run themselves. Plain sentence, do NOT number it yourself."],
  "timeline": "Name the SEQUENCE and the dependencies that actually set the calendar (client-side admin access, credentials, a real data window to tune against), then say you commit to dates at kickoff. NEVER give week counts, day counts or any duration estimate.",
  "close": "A REPLY-ONLY close: offer to send something specific and free (a data model, a permission checklist, a short walkthrough) and ask them to reply. NEVER ask for a call or meeting."
}}

RULES:
- Do NOT mention budget, pricing, rates or hours anywhere.
- NEVER use em dashes or en dashes. Use periods, commas, or the word 'and'.
- No markdown symbols (no **, #, etc.).
- Plain language, no jargon. A smart non-specialist is reading.
- Body ~600 words, and the audit gets the largest share of them.
- Output valid JSON only, nothing before or after."""


def _llm():
    return AzureOpenAI(
        azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
        api_key=os.environ["AZURE_OPENAI_API_KEY"],
        api_version=os.environ["AZURE_OPENAI_API_VERSION"],
    )


def generate(jd: str) -> dict:
    client = _llm()
    deployment = os.environ.get("AZURE_OPENAI_DEPLOYMENT", "gpt-5.1")
    resp = client.chat.completions.create(
        model=deployment,
        messages=[
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": USER_TMPL.format(jd=jd.strip())},
        ],
        response_format={"type": "json_object"},
    )
    raw = resp.choices[0].message.content.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # be forgiving: pull the first {...} block
        s, e = raw.find("{"), raw.rfind("}")
        if s != -1 and e != -1:
            return json.loads(raw[s:e + 1])
        raise


def _sanitize(s: str) -> str:
    """Strip dashes the house style forbids so the renderer never rejects."""
    return (str(s).replace("—", ", ").replace("–", "-").replace("&mdash;", ", "))


def build_html(p: dict, title: str) -> str:
    """Render the JSON into the house-style letter.

    Section order matches the SKILL.md letter structure: byline, opener, proof, THE AUDIT,
    how I would build it, next step, sign-off. The audit sits before the build plan on
    purpose: it is what earns the reader's attention for everything after it.
    """
    def cell(s):
        return html.escape(_sanitize(s))

    def items(key, tag):
        rows = "".join(f"<li>{cell(x)}</li>" for x in p.get(key, []) if str(x).strip())
        return f"<{tag}>{rows}</{tag}>"

    # house style: blank-line spacing between blocks via <p>&nbsp;</p>
    gap = "<p>&nbsp;</p>"
    focus = str(p.get("focus", "")).strip()
    byline = "Rood Judeley Joseph (Jude), Upwork consultant"
    if focus:
        byline += f"<br/>Focus: {cell(focus)}"

    audit_heading = str(p.get("audit_heading", "")).strip() or "Things I checked before writing this"

    parts = [
        f"<h1>{cell(title)}</h1>",
        f"<p>{byline}</p>",
        gap,
        f"<p>{cell(p.get('greeting', 'Hey,'))}</p>",
        gap,
        f"<p>{cell(p.get('opening', ''))}</p>",
        gap,
        f"<p>{cell(p.get('proof', ''))}</p>",
        gap,
        # The audit: gaps, traps and the justified stack call. Never drop this section.
        f"<h2>{cell(audit_heading)}</h2>",
        items("audit", "ol"),
        gap,
        "<h2>How I would build it</h2>",
        items("approach", "ol"),
        gap,
        "<h2>Timeline</h2>",
        f"<p>{cell(p.get('timeline', ''))}</p>",
        gap,
        "<h2>Next step</h2>",
        f"<p>{cell(p.get('close', ''))}</p>",
        gap,
        # House rule: never a bare "Jude" in a client deliverable.
        "<p>Best,</p>",
        "<p>Rood Judeley Joseph (Jude)</p>",
    ]
    return "\n".join(parts)


def create_doc(title: str, body_html: str) -> tuple[str, str]:
    html_out = proposal_doc._prep(body_html)  # font injection + em-dash guard
    drive = proposal_doc._drive()
    media = MediaInMemoryUpload(html_out.encode("utf-8"), mimetype="text/html", resumable=False)
    meta = {"name": title, "mimeType": "application/vnd.google-apps.document"}
    f = drive.files().create(body=meta, media_body=media, fields="id,webViewLink").execute()
    doc_id, url = f["id"], f["webViewLink"]
    proposal_doc._share(drive, doc_id)  # anyone-with-link reader, so the client can always open it
    return doc_id, url


def main():
    ap = argparse.ArgumentParser(description="Upwork proposal Google Doc from a job description")
    ap.add_argument("--jd-file", help="path to a file with the job description")
    ap.add_argument("--jd", help="job description text inline")
    ap.add_argument("--client", help="client/company name (used in the doc title)")
    ap.add_argument("--title", help="explicit doc title (overrides --client)")
    ap.add_argument("--dump-html", help="also write the generated HTML body here (debug)")
    ap.add_argument(
        "--body-html",
        help="render this authored HTML body instead of calling the LLM "
             "(skips the JD entirely; still gets Bricolage + em-dash guard + link share)",
    )
    args = ap.parse_args()

    # authored-body path: agent wrote the proposal itself, just render + share it
    if args.body_html:
        title = args.title or (
            f"Automation Audit and Build Plan for {args.client}"
            if args.client else "Automation Audit and Build Plan"
        )
        body = _sanitize(Path(args.body_html).read_text(encoding="utf-8"))
        doc_id, url = create_doc(title, body)
        print("URL:", url)
        print("ID:", doc_id)
        return

    if args.jd_file:
        jd = Path(args.jd_file).read_text(encoding="utf-8")
    elif args.jd:
        jd = args.jd
    else:
        jd = sys.stdin.read()
    if not jd.strip():
        sys.exit("ERROR: no job description provided (use --jd-file, --jd, or stdin).")

    title = args.title or (
        f"Automation Audit and Build Plan for {args.client}"
        if args.client else "Automation Audit and Build Plan"
    )

    print("Generating proposal with gpt-5.1...", flush=True)
    proposal = generate(jd)
    body = build_html(proposal, title)
    if args.dump_html:
        Path(args.dump_html).write_text(body, encoding="utf-8")

    doc_id, url = create_doc(title, body)
    print("URL:", url)
    print("ID:", doc_id)
    print(
        "NOTE: bracketed placeholders are still in this draft. Replace every one with a real "
        "number, sharpen the audit section against real research, add the flowchart, then "
        "re-render. Lint with scripts/check_proposal_html.py before sending.",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
