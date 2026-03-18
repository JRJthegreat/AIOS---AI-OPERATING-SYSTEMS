#!/usr/bin/env python3
"""
AI-Solvable Job Classifier using Haiku.

Classifies Upwork jobs from non-AI categories to determine if they're genuinely
AI/automation work. Used as a post-filter for Tier 2 (hidden gems) scraping.

Cost: ~$0.0002 per job → ~$0.03 for 150 jobs.
"""

import os
import json
import anthropic
from dotenv import load_dotenv

load_dotenv()


def classify_single(job: dict, client: anthropic.Anthropic) -> bool:
    """Classify whether a job is genuinely AI/automation solvable. Returns True to keep."""
    prompt = f"""Classify this Upwork job. Is AI, automation, or workflow tooling the PRIMARY deliverable?

Title: {job.get('title', '')}
Category: {job.get('category', '')}
Skills: {', '.join(job.get('skills', [])[:10])}
Description: {job.get('description', '')[:600]}

Answer YES if the main work is: building automations, integrating AI/LLM APIs, creating chatbots,
workflow design (n8n/Make/Zapier), data pipeline automation, AI-powered tools, scraping systems,
CRM automation, voice agents, or similar.

Answer NO if: pure design, content writing, manual data entry, traditional dev with no AI/automation,
SEO-only, social media management, or AI is mentioned but is <20% of scope.

Reply with ONLY "YES" or "NO"."""

    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=10,
            messages=[{"role": "user", "content": prompt}]
        )
        answer = response.content[0].text.strip().upper()
        return answer.startswith("YES")
    except Exception as e:
        print(f"    Classifier error: {str(e)[:50]} — keeping job")
        return True  # On error, keep the job


def classify_batch(jobs: list[dict], min_confidence: float = 0.7) -> list[dict]:
    """Classify a batch of jobs. Returns only AI-solvable ones."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("    ANTHROPIC_API_KEY not found — skipping classification, keeping all")
        return jobs

    client = anthropic.Anthropic()
    kept = []

    for i, job in enumerate(jobs):
        is_ai = classify_single(job, client)
        status = "KEEP" if is_ai else "SKIP"
        if i < 5 or not is_ai:  # Log first 5 + all skips
            print(f"    [{status}] {job.get('title', '')[:50]} | {job.get('category', '')}")
        if is_ai:
            kept.append(job)

    return kept


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python classify_ai_job.py <jobs.json>")
        sys.exit(1)

    with open(sys.argv[1]) as f:
        jobs = json.load(f)

    result = classify_batch(jobs)
    print(f"\nKept {len(result)}/{len(jobs)} AI-solvable jobs")
