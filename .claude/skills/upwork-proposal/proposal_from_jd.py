#!/usr/bin/env python3
"""
Upwork proposal Google Doc from a job description.

Pipeline: JD in (file / stdin / --jd) -> Azure gpt-5.1 writes the proposal ->
rendered to a native Google Doc via the upwork-proposal renderer
(proposal_doc._prep: Bricolage Grotesque font + em-dash guard) -> link-shared.

Proposal only (no cover letter). No Google Sheet. Proof lines use bracketed
placeholders (e.g. "[500+ calls/day]") so the model never invents a metric.

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
  "greeting": "Hey [first name only if it is clearly in the JD, otherwise just 'Hey'],",
  "opening": "1-2 sentences mirroring their SPECIFIC pain or goal. Reference something concrete from the JD, not generic filler.",
  "proof": "Start: 'I've built similar [specific thing relevant to THIS job].' Then one proof sentence. For EVERY number, result, timeframe, or client name use a bracketed placeholder, e.g. '[500+ calls/day]' or '[a SaaS client]'. NEVER invent a real metric or client name.",
  "approach": ["4 to 6 steps. Each: what you would do, WHY, and the specific tools where relevant. Plain sentence, do NOT number it yourself."],
  "deliverables": ["2 to 3 concrete, specific deliverables"],
  "timeline": "realistic estimate in a conversational tone",
  "close": "A REPLY-ONLY close: offer to send something (a short walkthrough, a quick plan) and ask them to reply. NEVER ask for a call or meeting."
}}

RULES:
- Do NOT mention budget or pricing anywhere.
- NEVER use em dashes or en dashes. Use periods, commas, or the word 'and'.
- No markdown symbols (no **, #, etc.).
- Whole proposal ~300 words.
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


def build_html(p: dict) -> str:
    def cell(s):
        return html.escape(_sanitize(s))

    def items(key, tag):
        rows = "".join(f"<li>{cell(x)}</li>" for x in p.get(key, []) if str(x).strip())
        return f"<{tag}>{rows}</{tag}>"

    # house style: blank-line spacing between blocks via <p>&nbsp;</p>
    gap = "<p>&nbsp;</p>"
    parts = [
        f"<p>{cell(p.get('greeting', 'Hey,'))}</p>",
        gap,
        f"<p>{cell(p.get('opening', ''))}</p>",
        gap,
        f"<p>{cell(p.get('proof', ''))}</p>",
        gap,
        "<h2>My proposed approach</h2>",
        items("approach", "ol"),
        gap,
        "<h2>What you'll get</h2>",
        items("deliverables", "ul"),
        gap,
        "<h2>Timeline</h2>",
        f"<p>{cell(p.get('timeline', ''))}</p>",
        gap,
        f"<p>{cell(p.get('close', ''))}</p>",
        gap,
        "<p>Jude</p>",
    ]
    return "\n".join(parts)


def create_doc(title: str, body_html: str) -> tuple[str, str]:
    html_out = proposal_doc._prep(body_html)  # font injection + em-dash guard
    drive = proposal_doc._drive()
    media = MediaInMemoryUpload(html_out.encode("utf-8"), mimetype="text/html", resumable=False)
    meta = {"name": title, "mimeType": "application/vnd.google-apps.document"}
    f = drive.files().create(body=meta, media_body=media, fields="id,webViewLink").execute()
    doc_id, url = f["id"], f["webViewLink"]
    # share anyone-with-link (reader) so the Upwork client can open it
    drive.permissions().create(
        fileId=doc_id, body={"type": "anyone", "role": "reader"}, fields="id"
    ).execute()
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
            f"Upwork Proposal - {args.client}" if args.client else "Upwork Proposal"
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

    title = args.title or (f"Upwork Proposal - {args.client}" if args.client else "Upwork Proposal")

    print("Generating proposal with gpt-5.1...", flush=True)
    proposal = generate(jd)
    body = build_html(proposal)
    if args.dump_html:
        Path(args.dump_html).write_text(body, encoding="utf-8")

    doc_id, url = create_doc(title, body)
    print("URL:", url)
    print("ID:", doc_id)


if __name__ == "__main__":
    main()
