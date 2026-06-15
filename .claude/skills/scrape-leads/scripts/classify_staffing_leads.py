#!/usr/bin/env python3
"""
Classify scraped leads as KEEP (healthcare staffing/recruitment firm or person at one)
or DROP (clinicians, hospitals, vendors, etc.) using the Anthropic Message Batches API.

Keeps only KEEP records.

Usage:
  python3 classify_staffing_leads.py \
    --input .tmp/list_a_raw.json --output .tmp/list_a_classified.json
"""

import os
import sys
import json
import argparse
import time
import anthropic
from dotenv import load_dotenv

load_dotenv()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
MODEL = "claude-haiku-4-5-20251001"

PROMPT = """Classify this person for a healthcare staffing/recruitment outreach list. Reply with ONLY one word: KEEP or DROP.

KEEP = works at (owner, exec, recruiter, founder, etc.) a staffing agency, recruitment firm,
       travel nursing company, locum tenens firm, temp staffing agency, healthcare job board, or healthcare RPO.
DROP = an individual nurse/doctor/clinician, a hospital or health system, a SaaS/tech vendor,
       a pharma company, a large general management-consulting firm, or anyone clearly not at a staffing/recruitment firm.

Title: {title}
Company: {company}
Context: {context}

Reply with ONLY: KEEP or DROP"""


def make_request(lead, custom_id):
    full_prompt = PROMPT.format(
        title=(lead.get("job_title") or "Unknown")[:300],
        company=(lead.get("company_name") or "Unknown")[:200],
        context=(lead.get("post_snippet") or "No context")[:300],
    )
    return {
        "custom_id": custom_id,
        "params": {
            "model": MODEL,
            "max_tokens": 5,
            "messages": [{"role": "user", "content": full_prompt}],
        },
    }


def main():
    parser = argparse.ArgumentParser(description="Classify leads KEEP/DROP for healthcare staffing outreach")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", default=".tmp/list_a_classified.json")
    args = parser.parse_args()

    if not ANTHROPIC_API_KEY:
        print("Error: ANTHROPIC_API_KEY not set", file=sys.stderr)
        sys.exit(1)

    with open(args.input) as f:
        leads = json.load(f)
    print(f"Loaded {len(leads)} leads")

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    requests = [make_request(lead, f"lead_{i}") for i, lead in enumerate(leads)]
    print(f"Submitting batch of {len(requests)} classification requests...")

    batch = client.messages.batches.create(requests=requests)
    batch_id = batch.id
    print(f"Batch: {batch_id} | Status: {batch.processing_status}")

    last = None
    while True:
        batch = client.messages.batches.retrieve(batch_id)
        counts = (batch.request_counts.processing,
                  batch.request_counts.succeeded,
                  batch.request_counts.errored)
        if counts != last:
            print(f"  {batch.request_counts.succeeded}/{len(leads)} done, "
                  f"{batch.request_counts.processing} processing, {batch.request_counts.errored} errors")
            last = counts
        if batch.processing_status == "ended":
            break
        time.sleep(2)

    # Parse results
    decisions = {}
    for result in client.messages.batches.results(batch_id):
        idx = int(result.custom_id.split("_")[1])
        if result.result.type == "succeeded":
            text = result.result.message.content[0].text.strip().upper()
            decisions[idx] = "KEEP" if "KEEP" in text else "DROP"
        else:
            decisions[idx] = "DROP"  # default to DROP on error (conservative)

    for i, lead in enumerate(leads):
        lead["_classification"] = decisions.get(i, "DROP")

    kept = [l for l in leads if l["_classification"] == "KEEP"]
    dropped = len(leads) - len(kept)

    print(f"\n{'='*40}")
    print(f"KEEP: {len(kept)} | DROP: {dropped}")

    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    with open(args.output, "w") as f:
        json.dump(kept, f, indent=2)
    print(f"Saved {len(kept)} KEEP leads → {args.output}")


if __name__ == "__main__":
    main()
