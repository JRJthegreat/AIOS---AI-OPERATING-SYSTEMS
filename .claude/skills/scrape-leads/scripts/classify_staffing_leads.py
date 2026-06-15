#!/usr/bin/env python3
"""
Classify scraped leads as KEEP (healthcare staffing/recruitment firm or person at one)
or DROP (clinicians, hospitals, vendors, etc.) using Azure OpenAI.

Keeps only KEEP records. Runs classifications in parallel (Azure has no simple batch API).

Usage:
  python3 classify_staffing_leads.py \
    --input .tmp/list_a_raw.json --output .tmp/list_a_classified.json
"""

import os
import sys
import json
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv
from openai import AzureOpenAI

load_dotenv()

MAX_WORKERS = 10

PROMPT = """Classify this lead for a healthcare staffing/recruitment outreach list. Reply with ONLY one word: KEEP or DROP.

KEEP = a staffing agency, recruitment firm, travel nursing company, locum tenens firm, temp staffing
       agency, healthcare job board, or healthcare RPO — or a person (owner, exec, recruiter, founder)
       who works at one.
DROP = an individual nurse/doctor/clinician, a hospital or health system, a software/SaaS/tech vendor
       (incl. ATS, VMS, credentialing, background-check, recruiting-AI tools), a pharma company,
       a finance/consulting firm, or anyone clearly not a staffing/recruitment firm.

Weigh the company bio most heavily — it is the strongest signal, especially when the title is just a
follower count (these are company pages).

Name: {name}
Title: {title}
Company: {company}
Company bio: {bio}
Post context: {context}

Reply with ONLY: KEEP or DROP"""


def make_client():
    return AzureOpenAI(
        api_key=os.getenv("AZURE_OPENAI_API_KEY"),
        azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
        api_version=os.getenv("AZURE_OPENAI_API_VERSION"),
    )


def classify_one(client, deployment, idx, lead):
    prompt = PROMPT.format(
        name=(lead.get("full_name") or f"{lead.get('first_name','')} {lead.get('last_name','')}").strip()[:80] or "Unknown",
        title=(lead.get("job_title") or "Unknown")[:300],
        company=(lead.get("company_name") or "Unknown")[:200],
        bio=(lead.get("company_bio") or "No bio")[:600],
        context=(lead.get("post_snippet") or "No context")[:300],
    )
    try:
        r = client.chat.completions.create(
            model=deployment,
            max_tokens=5,
            messages=[{"role": "user", "content": prompt}],
        )
        text = (r.choices[0].message.content or "").strip().upper()
        return idx, "KEEP" if "KEEP" in text else "DROP"
    except Exception as e:
        print(f"  Error on lead {idx}: {str(e)[:100]}")
        return idx, "DROP"  # conservative default


def main():
    parser = argparse.ArgumentParser(description="Classify leads KEEP/DROP via Azure OpenAI")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", default=".tmp/list_a_classified.json")
    args = parser.parse_args()

    if not os.getenv("AZURE_OPENAI_API_KEY"):
        print("Error: AZURE_OPENAI_API_KEY not set", file=sys.stderr)
        sys.exit(1)

    deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT_FAST") or os.getenv("AZURE_OPENAI_DEPLOYMENT")

    with open(args.input) as f:
        leads = json.load(f)
    print(f"Loaded {len(leads)} leads | classifying via {deployment} ({MAX_WORKERS} workers)...")

    client = make_client()
    decisions = {}

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = [ex.submit(classify_one, client, deployment, i, lead)
                   for i, lead in enumerate(leads)]
        done = 0
        for fut in as_completed(futures):
            idx, decision = fut.result()
            decisions[idx] = decision
            done += 1
            if done % 25 == 0:
                print(f"  {done}/{len(leads)} classified")

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
