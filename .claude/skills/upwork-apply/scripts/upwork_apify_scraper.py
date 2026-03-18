#!/usr/bin/env python3
"""
Upwork Job Scraper using Apify — Two-Tier Strategy

Tier 1: Direct AI jobs (AI categories + tool-based keywords)
Tier 2: Hidden gems (non-AI categories + problem-based keywords + Haiku classifier)

Usage:
    python scripts/upwork_apify_scraper.py --target 50 -o .tmp/upwork_jobs_filtered.json
    python scripts/upwork_apify_scraper.py --target 50 --no-tier2 -o .tmp/upwork_jobs_filtered.json
"""

import os
import json
import time
import argparse
import requests
import anthropic
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv

load_dotenv()

# Taiwan timezone (UTC+8)
TW_TZ = timezone(timedelta(hours=8))

# Countries to exclude (low-paying markets)
EXCLUDED_COUNTRIES = {
    'NG', 'ZA', 'IN', 'PK', 'BD', 'KE', 'GH', 'EG', 'UG', 'TZ',
    'ET', 'ZM', 'ZW', 'CM', 'SN', 'RW', 'CI', 'ML', 'BF', 'NE',
}

# Tier 1: Direct AI jobs — tool-based keywords + AI categories
TIER1_CONFIG = {
    "keywords": [
        "AI agent", "n8n", "Make.com", "Zapier", "Retell ai", "Vapi",
        "voice agent", "LLM prompt", "chatGPT", "Claude", "ai automation",
        "workflow automation", "sales automation", "cold email", "Instantly",
        "lead generation", "ClickUp", "monday.com", "Retool", "chatbot",
        "OpenAI API", "GPT-4", "AI assistant", "AI integration",
        "automation developer", "Python automation", "API integration",
        "CRM automation", "no-code automation", "AI app", "LangChain",
        "AI workflow", "airtable automation", "HubSpot automation",
        "email automation", "scraping", "data pipeline", "AI chatbot",
        "conversational AI", "RAG", "vector database", "AI tool"
    ],
    "categories": [
        "AI & Machine Learning",
        "AI Apps & Integration",
        "All - Web, Mobile & Software Dev",
        "DevOps & Solution Architecture"
    ],
    "limit": 500,
}

# Tier 2: Hidden gems — problem-based keywords + non-AI categories
TIER2_CONFIG = {
    "keywords": [
        # Problem-based (what the client needs, not the tool name)
        "automate my", "automate our", "automation specialist", "automation expert",
        "set up workflow", "build workflow", "integrate API", "connect systems",
        "sync data", "scrape data", "extract data", "data extraction",
        "auto-reply", "autoresponder", "dashboard builder", "reporting automation",
        "lead capture", "lead nurture", "lead scoring", "follow-up sequence",
        "email sequence", "CRM setup", "CRM integration", "process automation",
        "business automation", "spreadsheet automation", "Google Sheets automation",
        # Tool names that bleed into non-tech categories
        "n8n", "Make.com", "Zapier", "chatbot", "AI chatbot", "ChatGPT",
        "OpenAI", "Claude API", "GoHighLevel", "HubSpot automation",
        "Salesforce automation", "Twilio", "WhatsApp bot", "voice bot",
        "IVR automation",
    ],
    "categories": [
        "All - Sales & Marketing",
        "All - Data Science & Analytics",
        "All - IT & Networking",
        "All - Admin Support",
        "All - Customer Service",
        "All - Writing",
        "All - Accounting & Consulting"
    ],
    "limit": 1000,
}


def run_apify_scrape(input_data: dict, label: str = "") -> list[dict]:
    """Run a single Apify actor scrape and return results."""
    api_token = os.environ.get("APIFY_API_TOKEN")
    if not api_token:
        raise ValueError("APIFY_API_TOKEN not found in environment")

    actor_id = "upwork-vibe~upwork-job-scraper"
    run_url = f"https://api.apify.com/v2/acts/{actor_id}/runs?token={api_token}"

    print(f"[{label}] Starting Apify run (limit: {input_data.get('limit', '?')})...")
    response = requests.post(run_url, json=input_data)
    if not response.ok:
        raise Exception(f"[{label}] Failed to start actor: {response.text}")

    run_info = response.json()
    run_id = run_info['data']['id']
    dataset_id = run_info['data']['defaultDatasetId']

    status_url = f"https://api.apify.com/v2/actor-runs/{run_id}?token={api_token}"
    for i in range(90):
        time.sleep(5)
        status_resp = requests.get(status_url)
        if status_resp.ok:
            status = status_resp.json().get('data', {}).get('status')
            if status == 'SUCCEEDED':
                print(f"[{label}] Scrape completed!")
                break
            elif status in ('FAILED', 'ABORTED', 'TIMED-OUT'):
                raise Exception(f"[{label}] Actor run failed: {status}")
            if i % 4 == 0:
                print(f"[{label}] {status}...")

    dataset_url = f"https://api.apify.com/v2/datasets/{dataset_id}/items?token={api_token}"
    results_resp = requests.get(dataset_url)
    if not results_resp.ok:
        raise Exception(f"[{label}] Failed to fetch results: {results_resp.text}")

    jobs = results_resp.json()
    print(f"[{label}] Fetched {len(jobs)} raw jobs")
    return jobs


def build_apify_input(config: dict, from_date: str, to_date: str) -> dict:
    """Build Apify actor input from a tier config."""
    return {
        "includeKeywords.keywords": config["keywords"],
        "includeKeywords.matchTitle": True,
        "includeKeywords.matchDescription": True,
        "includeKeywords.matchSkills": True,
        "jobCategories": config["categories"],
        "fromDate": from_date,
        "toDate": to_date,
        "limit": config["limit"],
        "addons.enableClientDetails": True,
        "vendor.includeWithoutCountryPreference": True,
    }


def filter_jobs(
    jobs: list[dict],
    min_hourly: float = 35,
    min_fixed: float = 100,
    min_client_hires: int = 1,
    min_hire_rate: float = 60,
    exclude_countries: set = None,
    keep_unspecified_budget: bool = True,
) -> list[dict]:
    """Apply post-scrape quality filters. Unspecified-budget jobs are kept by default."""
    if exclude_countries is None:
        exclude_countries = EXCLUDED_COUNTRIES

    filtered = []
    skipped = {'country': 0, 'hourly': 0, 'fixed': 0, 'hires': 0, 'hire_rate': 0}

    for job in jobs:
        client = job.get('client', {})
        stats = client.get('stats', {})
        budget = job.get('budget', {})
        hourly = budget.get('hourlyRate', {})
        fixed = budget.get('fixedBudget')

        # Country exclusion
        country = (client.get('countryCode', '') or '').upper()
        if country in exclude_countries:
            skipped['country'] += 1
            continue

        # Budget logic: keep unspecified, filter low hourly/fixed
        hourly_max = hourly.get('max') or hourly.get('min') or 0
        has_hourly = hourly_max > 0
        has_fixed = fixed and fixed > 0
        has_no_budget = not has_hourly and not has_fixed

        if has_no_budget and keep_unspecified_budget:
            pass  # Always keep unspecified budget jobs
        elif has_hourly and hourly_max < min_hourly:
            skipped['hourly'] += 1
            continue
        elif has_fixed and fixed < min_fixed:
            skipped['fixed'] += 1
            continue

        # Client hires
        hires = stats.get('totalHires', 0)
        if hires < min_client_hires:
            skipped['hires'] += 1
            continue

        # Hire rate
        hire_rate = stats.get('hireRate', 0) or 0
        if hire_rate < min_hire_rate:
            skipped['hire_rate'] += 1
            continue

        filtered.append(job)

    print(f"  Filter stats: {skipped} | Passed: {len(filtered)}")
    return filtered


def format_job(job: dict, tier: int = 1) -> dict:
    """Format raw Apify job data for output."""
    budget = job.get('budget', {})
    hourly = budget.get('hourlyRate', {})
    fixed = budget.get('fixedBudget')

    if fixed:
        budget_str = f"${fixed} fixed"
    elif hourly.get('min') or hourly.get('max'):
        budget_str = f"${hourly.get('min', 0)}-${hourly.get('max', hourly.get('min', 0))}/hr"
    else:
        budget_str = "Not specified"

    client = job.get('client', {})
    stats = client.get('stats', {})

    source = 'hidden_gem' if tier == 2 else 'direct'

    return {
        'id': job.get('uid'),
        'title': job.get('title', ''),
        'description': job.get('description', ''),
        'url': job.get('externalLink', ''),
        'budget': budget_str,
        'budget_raw': budget,
        'category': job.get('category', ''),
        'experience_level': job.get('vendor', {}).get('experienceLevel', ''),
        'skills': job.get('skills', []),
        'posted': job.get('createdAt', ''),
        'connects_cost': job.get('applicationCost', 0),
        'is_featured': job.get('isFeatured', False),
        'rank_score': job.get('_rank_score', 0),
        'tier': tier,
        'source': source,
        'client': {
            'country': client.get('countryCode', ''),
            'timezone': client.get('timezone', ''),
            'payment_verified': client.get('paymentMethodVerified', False),
            'total_spent': stats.get('totalSpent', 0),
            'total_hires': stats.get('totalHires', 0),
            'hire_rate': stats.get('hireRate', 0),
            'feedback_score': stats.get('feedbackRate', 0),
        },
    }


def rank_jobs(jobs: list[dict], target: int = 50) -> list[dict]:
    """Rank jobs by quality using Haiku and return top N.

    Scoring factors: client spend, budget, skill match, competition (connects),
    recency, payment verification, hidden gem bonus.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("  ANTHROPIC_API_KEY not found — skipping ranking, using first N")
        return jobs[:target]

    client = anthropic.Anthropic()
    scored = []

    print(f"\n=== RANKING {len(jobs)} jobs with Haiku ===")

    # Process in batches of 10 for efficiency
    batch_size = 10
    for batch_start in range(0, len(jobs), batch_size):
        batch = jobs[batch_start:batch_start + batch_size]
        batch_idx = batch_start // batch_size + 1
        total_batches = (len(jobs) + batch_size - 1) // batch_size

        # Build batch prompt
        job_summaries = []
        for i, job in enumerate(batch):
            c = job.get('client', {})
            stats = c.get('stats', {})
            budget = job.get('budget', {})
            hourly = budget.get('hourlyRate', {})
            fixed = budget.get('fixedBudget')

            budget_str = ""
            if fixed:
                budget_str = f"${fixed} fixed"
            elif hourly.get('min') or hourly.get('max'):
                budget_str = f"${hourly.get('min', 0)}-${hourly.get('max', 0)}/hr"
            else:
                budget_str = "Not specified"

            job_summaries.append(
                f"JOB {i}:\n"
                f"  Title: {job.get('title', '')}\n"
                f"  Category: {job.get('category', '')}\n"
                f"  Skills: {', '.join(job.get('skills', [])[:8])}\n"
                f"  Budget: {budget_str}\n"
                f"  Client Spent: ${stats.get('totalSpent', 0)}\n"
                f"  Client Hires: {stats.get('totalHires', 0)}\n"
                f"  Hire Rate: {stats.get('hireRate', 0)}%\n"
                f"  Payment Verified: {c.get('paymentMethodVerified', False)}\n"
                f"  Connects: {job.get('applicationCost', 0)}\n"
                f"  Country: {c.get('countryCode', '')}\n"
                f"  Posted: {job.get('createdAt', 'unknown')}\n"
                f"  Description: {job.get('description', '')[:300]}\n"
            )

        now_str = datetime.now(TW_TZ).strftime('%Y-%m-%dT%H:%M:%S')
        prompt = f"""Score each job 1-10 for an AI Automation Engineer who builds:
- AI agents, workflow automation (n8n, Make.com, Zapier)
- Voice agents (Vapi, Retell), chatbots, LLM integrations
- API integrations, CRM automation, data pipelines
- Python automation, scraping systems, RAG

Current time: {now_str} (UTC+8)

Scoring criteria (weighted):
- Client quality (30%): total spent (>$10K great, >$50K excellent), hire rate, payment verified
- Budget value (20%): higher budget = higher score, unspecified is neutral (5)
- Skill match (20%): how well does the job match the engineer's core stack?
- Recency (15%): newer jobs = fewer proposals already submitted = much better odds. Posted <6hrs ago = bonus, >24hrs ago = penalty
- Competition (10%): lower connects cost = less competition = better
- Opportunity (5%): hidden gem potential, clear scope, interesting project

{chr(10).join(job_summaries)}

Reply with ONLY a JSON array of scores, one per job, in order. Example: [8, 5, 7, 3, 9, 6, 4, 8, 7, 5]
No explanation, just the array."""

        try:
            response = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=100,
                messages=[{"role": "user", "content": prompt}]
            )
            scores_text = response.content[0].text.strip()
            scores = json.loads(scores_text)

            if len(scores) != len(batch):
                print(f"  Batch {batch_idx}: score count mismatch ({len(scores)} vs {len(batch)}), padding")
                scores = (scores + [5] * len(batch))[:len(batch)]

            for job, score in zip(batch, scores):
                scored.append((score, job))

            if batch_idx % 5 == 0 or batch_idx == total_batches:
                print(f"  Scored batch {batch_idx}/{total_batches}")

        except Exception as e:
            print(f"  Batch {batch_idx} error: {str(e)[:60]} — assigning score 5")
            for job in batch:
                scored.append((5, job))

    # Sort by score descending, take top N
    scored.sort(key=lambda x: x[0], reverse=True)
    top = scored[:target]

    # Log score distribution
    all_scores = [s for s, _ in scored]
    top_scores = [s for s, _ in top]
    print(f"  All scores: min={min(all_scores)}, max={max(all_scores)}, avg={sum(all_scores)/len(all_scores):.1f}")
    print(f"  Top {target} cutoff score: {top_scores[-1] if top_scores else 'N/A'}")

    # Attach score to each job
    result = []
    for score, job in top:
        job['_rank_score'] = score
        result.append(job)
    return result


def merge_and_deduplicate(tier1_jobs: list[dict], tier2_jobs: list[dict]) -> list[dict]:
    """Merge both tiers, deduplicate by uid. Tier 1 gets priority."""
    seen_uids = set()
    merged = []

    for job in tier1_jobs:
        uid = job.get('uid') or job.get('id')
        if uid and uid not in seen_uids:
            seen_uids.add(uid)
            merged.append(job)

    dupes = 0
    for job in tier2_jobs:
        uid = job.get('uid') or job.get('id')
        if uid and uid not in seen_uids:
            seen_uids.add(uid)
            merged.append(job)
        else:
            dupes += 1

    if dupes:
        print(f"  Dedup: removed {dupes} duplicates from Tier 2")
    return merged


def main():
    parser = argparse.ArgumentParser(description="Two-tier Upwork job scraper")
    parser.add_argument("--target", "-t", type=int, default=50, help="Target number of jobs (default: 50)")
    parser.add_argument("--days", "-d", type=int, default=1, help="Jobs from last N days (default: 1)")
    parser.add_argument("--no-tier2", action="store_true", help="Skip Tier 2 (hidden gems) scrape")
    parser.add_argument("--no-rank", action="store_true", help="Skip Haiku ranking, take first N")
    parser.add_argument("--output", "-o", help="Output JSON file")
    args = parser.parse_args()

    # Date range in Taiwan time
    from_date = (datetime.now(TW_TZ) - timedelta(days=args.days)).strftime('%Y-%m-%d')
    to_date = (datetime.now(TW_TZ) + timedelta(days=1)).strftime('%Y-%m-%d')
    print(f"Date range (Taiwan UTC+8): {from_date} to {to_date}\n")

    # === Tier 1: Direct AI jobs ===
    print("=== TIER 1: Direct AI Jobs ===")
    tier1_input = build_apify_input(TIER1_CONFIG, from_date, to_date)
    tier1_raw = run_apify_scrape(tier1_input, label="Tier 1")
    tier1_filtered = filter_jobs(tier1_raw)

    all_filtered_raw = list(tier1_filtered)

    # === Tier 2: Hidden gems ===
    tier2_classified = []
    if not args.no_tier2:
        print("\n=== TIER 2: Hidden Gems ===")
        tier2_input = build_apify_input(TIER2_CONFIG, from_date, to_date)
        tier2_raw = run_apify_scrape(tier2_input, label="Tier 2")
        tier2_filtered = filter_jobs(tier2_raw, keep_unspecified_budget=True)

        # AI-solvable classifier
        if tier2_filtered:
            print(f"\n  Classifying {len(tier2_filtered)} Tier 2 jobs with Haiku...")
            from classify_ai_job import classify_batch
            tier2_classified = classify_batch(tier2_filtered)
            print(f"  Kept {len(tier2_classified)} AI-solvable jobs from Tier 2")
    else:
        print("\nTier 2 skipped (--no-tier2)")

    # === Merge + dedup ===
    print("\n=== MERGE ===")
    merged_raw = merge_and_deduplicate(all_filtered_raw, tier2_classified)

    # Rank and pick top N (or blind slice if --no-rank)
    if args.no_rank:
        ranked_raw = merged_raw[:args.target]
        print(f"\n  Ranking skipped (--no-rank), taking first {args.target}")
    else:
        ranked_raw = rank_jobs(merged_raw, target=args.target)

    # Format ranked jobs
    tier2_uids = {j.get('uid') for j in tier2_classified}
    formatted = []
    for job in ranked_raw:
        tier = 2 if job.get('uid') in tier2_uids else 1
        formatted.append(format_job(job, tier=tier))

    # Summary
    t1_count = sum(1 for j in formatted if j['tier'] == 1)
    t2_count = sum(1 for j in formatted if j['tier'] == 2)
    featured = sum(1 for j in formatted if j.get('is_featured'))
    print(f"\nFinal: {len(formatted)} jobs (Tier 1: {t1_count}, Tier 2: {t2_count}, Featured: {featured})")

    for i, j in enumerate(formatted[:10], 1):
        c = j['client']
        tag = "GEM" if j['tier'] == 2 else "   "
        print(f"  {tag} {i}. {j['title'][:50]} | {j['budget']} | {c['country']} | {j['category'][:20]}")

    if len(formatted) > 10:
        print(f"  ... and {len(formatted) - 10} more")

    # Save
    if args.output:
        os.makedirs(os.path.dirname(args.output) or '.', exist_ok=True)
        with open(args.output, 'w') as f:
            json.dump(formatted, f, indent=2)
        print(f"\nSaved {len(formatted)} jobs to {args.output}")

    return formatted


if __name__ == "__main__":
    main()
