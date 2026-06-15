#!/usr/bin/env python3
"""
Tag each lead by buying authority for a client-acquisition / demand-gen vendor:
  DM    = can decide to hire such a vendor (owner, founder, C-suite, senior revenue/BD/client leader)
  NOT   = individual contributor / delivery role (recruiter, coordinator, sourcer, product/ops IC)
  COMPANY_PAGE = the "lead" is a company page, not a person (no individual to email)

Writes:
  --output (DM only) and, with --split, also <output>.not_dm.json / <output>.company_pages.json

Usage:
  python3 classify_decision_makers.py --input .tmp/list_a_final.json \
    --output .tmp/list_a_decision_makers.json --split
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

PROMPT = """A B2B demand-generation vendor sells client-acquisition services to healthcare staffing/recruitment firms (it books new client meetings for them). Decide if THIS person has the authority to decide to hire such a vendor.

Reply with ONLY one word: DM or NOT.

DM = owner, founder, co-founder, CEO, president, partner, managing director, principal, or C-suite
     (COO, CRO, CCO, CMO); OR a senior leader who owns revenue / new business / sales / business
     development / client partnerships / growth (e.g. VP or SVP or Director of Sales/BD/Growth/Revenue/
     Client Partnerships, Chief Revenue Officer, Head of Growth).
NOT = recruiter, sourcer, account manager/coordinator, talent acquisition specialist, delivery/
      operations manager, product manager, marketing coordinator, analyst, or any individual-
      contributor / delivery role without authority over buying new-client-acquisition services.

When the title is a vague LinkedIn headline, infer the actual role. If genuinely ambiguous, answer NOT.

Name: {name}
Title/headline: {title}
Company: {company}
Company bio: {bio}

Reply with ONLY: DM or NOT"""


def make_client():
    return AzureOpenAI(
        api_key=os.getenv("AZURE_OPENAI_API_KEY"),
        azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
        api_version=os.getenv("AZURE_OPENAI_API_VERSION"),
    )


def classify_one(client, deployment, idx, lead):
    prompt = PROMPT.format(
        name=(lead.get("first_name", "") + " " + lead.get("last_name", "")).strip()[:80] or "Unknown",
        title=(lead.get("job_title") or "Unknown")[:300],
        company=(lead.get("company_name") or "Unknown")[:200],
        bio=(lead.get("company_bio") or "No bio")[:400],
    )
    try:
        r = client.chat.completions.create(
            model=deployment, max_tokens=5,
            messages=[{"role": "user", "content": prompt}],
        )
        text = (r.choices[0].message.content or "").strip().upper()
        return idx, "DM" if "DM" in text else "NOT"
    except Exception as e:
        print(f"  Error on lead {idx}: {str(e)[:100]}")
        return idx, "NOT"


def is_company_page(lead):
    """Company-page rows have no person name (company name lives in company_name)."""
    return not lead.get("first_name") and not lead.get("last_name")


def main():
    parser = argparse.ArgumentParser(description="Filter leads to decision-makers via Azure OpenAI")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", default=".tmp/list_a_decision_makers.json")
    parser.add_argument("--split", action="store_true", help="Also write NOT and COMPANY_PAGE buckets")
    args = parser.parse_args()

    if not os.getenv("AZURE_OPENAI_API_KEY"):
        print("Error: AZURE_OPENAI_API_KEY not set", file=sys.stderr)
        sys.exit(1)

    deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT_FAST") or os.getenv("AZURE_OPENAI_DEPLOYMENT")

    with open(args.input) as f:
        leads = json.load(f)

    people = [l for l in leads if not is_company_page(l)]
    company_pages = [l for l in leads if is_company_page(l)]
    print(f"Loaded {len(leads)} | people: {len(people)} | company pages: {len(company_pages)}")
    print(f"Classifying {len(people)} people via {deployment}...")

    client = make_client()
    decisions = {}
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = [ex.submit(classify_one, client, deployment, i, lead)
                   for i, lead in enumerate(people)]
        done = 0
        for fut in as_completed(futures):
            idx, decision = fut.result()
            decisions[idx] = decision
            done += 1
            if done % 20 == 0:
                print(f"  {done}/{len(people)} classified")

    dm, not_dm = [], []
    for i, lead in enumerate(people):
        (dm if decisions.get(i) == "DM" else not_dm).append(lead)

    print(f"\n{'='*40}")
    print(f"Decision-makers: {len(dm)}")
    print(f"Not decision-makers: {len(not_dm)}")
    print(f"Company pages (no individual): {len(company_pages)}")

    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    with open(args.output, "w") as f:
        json.dump(dm, f, indent=2)
    print(f"Saved {len(dm)} decision-makers → {args.output}")

    if args.split:
        base = args.output.rsplit(".json", 1)[0]
        with open(f"{base}.not_dm.json", "w") as f:
            json.dump(not_dm, f, indent=2)
        with open(f"{base}.company_pages.json", "w") as f:
            json.dump(company_pages, f, indent=2)
        print(f"Saved {base}.not_dm.json and {base}.company_pages.json")


if __name__ == "__main__":
    main()
