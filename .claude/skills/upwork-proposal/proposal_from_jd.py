#!/usr/bin/env python3
"""
Upwork proposal Google Doc from a job description.

Pipeline: JD in (file / stdin / --jd) -> Azure gpt-5.1 writes the proposal ->
rendered to a native Google Doc via the upwork-proposal renderer
(proposal_doc._prep: Bricolage Grotesque font + em-dash guard) -> link-shared.

Proposal only (no cover letter). No Google Sheet. Proof lines use bracketed
placeholders (e.g. "[500+ calls/day]") so the model never invents a metric.

IMPORTANT, this path is the fallback, not the default. It has no web access and cannot
see Jude's Loom or the claims bank, so its proof story is placeholders. For any job Jude
is really sending, author the body yourself from templates/proposal_body.html and render
it with --body-html.

Output follows the WINNING FORMAT (Nov 3 2026 reset, modelled on the Larry, Axel and
Pediatric Works docs that actually won work): a personal letter with "What you're after",
the same-logic proof story, "How I would build your system", "Three things to get right
early", "What you'll get", "Timeline" and a "send me a message" close with one small free
offer. No audit section, no acceptance tests, no "free audit" title.

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
  "focus": "4 to 10 words naming the scope of the work, for the 'Focus:' byline line.",
  "greeting": "Hey [first name only if it is clearly in the JD, otherwise just 'Hey there'],",
  "after": "ONE paragraph mirroring exactly what they asked for, in THEIR words and with THEIR specifics (numbers, steps, tools, deadlines they named). Not generic. This is the 'What you're after' section. Write it the way you would tell a colleague what this client needs, in plain full sentences: their business, the job, and the two or three things that matter most. Include one concrete detail from the post that proves a person read it. Do NOT open with a framing thesis ('You want two connected builds...'), do NOT put a colon before a list of features, do NOT use the post's labels ('Track 1', 'Phase 2') as sentence subjects, and do NOT end on a short punchy fragment.",
  "proof": "The closest system you have built, told as a short story: what that client needed, what you built, the result. For EVERY number, result, timeframe, or client name use a bracketed placeholder, e.g. '[500+ calls/day]' or '[a SaaS client]'. NEVER invent a real metric or client name.",
  "analogy": "One or two sentences on why their problem is the same logic as that proof, in the style 'Different object, same machine.' Name what is the same.",
  "steps": ["5 to 7 build steps in the client's own process terms. Each item: a short bold-worthy lead-in phrase, a period, then 1 to 3 plain sentences on what happens. Do NOT number them yourself."],
  "get_right": ["2 or 3 practical things to get right early: what goes wrong if ignored, and what the build does about it. Common sense the client recognises. No vendor quotes, no price lists, no generic caution like 'testing is key'."],
  "deliverables": ["4 to 6 'What you'll get' outcomes, one line each, in their terms."],
  "timeline": "A rough sequence. Mirror the client's own phases if they gave them, otherwise give an honest week range, and name the two or three things you need from their side to start.",
  "close": "Start 'If this approach resonates, send me a message.' Then offer ONE small, specific free next step tied to their first step (e.g. 'the exact system map for your setup plus draft copy for the first emails, free, so you can judge the thinking and the tone before committing'). NEVER ask for a call."
}}

RULES:
- Do NOT mention Jude's own fee, rates or hours anywhere.
- NEVER use em dashes or en dashes. Use periods, commas, or the word 'and'.
- No markdown symbols (no **, #, etc.).
- Plain language, no jargon. A smart non-specialist is reading. Contractions are fine.
- Body 600 to 1,000 words. It is a personal letter, not a report.
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

    Section order matches templates/proposal_body.html, the winning format (Nov 3 2026):
    What you're after, the same-logic proof, How I would build your system, Three things
    to get right early, What you'll get, Timeline, Next step, sign-off.
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

    parts = [
        f"<h1>{cell(title)}</h1>",
        f"<p>{byline}</p>",
        gap,
        "<h2>What you're after</h2>",
        f"<p>{cell(p.get('greeting', 'Hey there,'))}</p>",
        gap,
        f"<p>{cell(p.get('after', ''))}</p>",
        gap,
        "<h2>A system I've built that runs on the same logic</h2>",
        f"<p>{cell(p.get('proof', ''))}</p>",
        gap,
        f"<p>{cell(p.get('analogy', ''))}</p>",
        gap,
        "<h2>How I would build your system</h2>",
        items("steps", "ol"),
        gap,
        "<h2>Things to get right early</h2>",
        items("get_right", "ol"),
        gap,
        "<h2>What you'll get</h2>",
        items("deliverables", "ul"),
        gap,
        "<h2>Timeline</h2>",
        f"<p>{cell(p.get('timeline', ''))}</p>",
        gap,
        "<h2>Next step</h2>",
        f"<p>{cell(p.get('close', ''))}</p>",
        gap,
        # House rule: never a bare "Jude" in a client deliverable.
        "<p>Best,<br/>Rood Judeley Joseph (Jude)</p>",
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
            f"Proposal for {args.client}"
            if args.client else "Proposal"
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
        f"Proposal for {args.client}"
        if args.client else "Proposal"
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
        "number from the claims bank, tie the proof story to Jude's Loom, then re-render. "
        "Lint with scripts/check_proposal_html.py before sending.",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
