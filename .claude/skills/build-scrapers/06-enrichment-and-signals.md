# Lesson 6: Enrichment & Signals

## What you'll learn
- How to use Apollo's free People Search API to enrich company data (0 credits!)
- The research discipline: never accept the first API answer — read every endpoint
- How to add company size, domain, and employee count to any scraper
- How to build scoring systems that turn data into intelligence
- How to generate "why call today" opportunity signals

## What you'll build
An enrichment layer you can bolt onto any scraper from Lessons 02-05. We'll use the HIPAA breach scraper as the example, but the pattern works everywhere.

---

## The Research Discipline

Before we write any code, here's the most important lesson in this entire course:

**Never accept the first API endpoint you find. Read EVERY endpoint in the documentation.**

Here's what happened when we built our enrichment layer:

1. We needed company size data (employee count, domain)
2. We found Apollo's `mixed_companies/search` endpoint — it costs credits per lookup
3. We almost built against it — "$0.01 per lookup, that's fine"
4. Then we read ONE MORE PAGE in Apollo's docs
5. We found `mixed_people/search` — a People Search endpoint that's **completely free** (0 credits)
6. It returns the same `organization` data: `estimated_num_employees`, `primary_domain`

The expensive endpoint was a trap. The free one was one page away in the docs. We saved hundreds of dollars per month by reading one more page.

**The rule:** Before declaring something "costs money" or "has rate limits," exhaust the documentation. There is always a cheaper or free path — the only constraint is whether you invest 20 minutes to find it.

## Apollo's Free People Search

The endpoint:
```
POST https://api.apollo.io/api/v1/mixed_people/search
```

The key: this is a **People Search** endpoint, but it returns **organization data** for each person's company. We don't care about the person — we care about the `organization` object in the response.

```typescript
export interface CompanyEnrichment {
    company_size: string;     // "51-200", "201-500", etc.
    company_domain: string;   // "acme.com"
    employee_count: number;   // 150
}

export async function enrichCompanySize(
    companyName: string,
    apolloApiKey: string | undefined,
): Promise<CompanyEnrichment | null> {
    if (!apolloApiKey || !companyName) return null;

    // Check cache first
    const cacheKey = companyName.toLowerCase().trim();
    if (companyCache.has(cacheKey)) return companyCache.get(cacheKey) ?? null;

    try {
        const res = await fetch('https://api.apollo.io/api/v1/mixed_people/search', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-Api-Key': apolloApiKey,
            },
            body: JSON.stringify({
                organization_name: companyName,
                page: 1,
                per_page: 1,  // We only need one person to get the org data
            }),
        });

        if (!res.ok) {
            companyCache.set(cacheKey, null);
            return null;
        }

        const data = await res.json() as {
            people?: Array<{
                organization?: {
                    estimated_num_employees?: number;
                    primary_domain?: string;
                };
            }>;
        };

        const org = data.people?.[0]?.organization;
        if (!org) {
            companyCache.set(cacheKey, null);
            return null;
        }

        const count = org.estimated_num_employees ?? 0;
        const result: CompanyEnrichment = {
            company_size: countToRange(count),
            company_domain: org.primary_domain ?? '',
            employee_count: count,
        };

        companyCache.set(cacheKey, result);
        return result;
    } catch {
        companyCache.set(cacheKey, null);
        return null;
    }
}
```

### The Cache Pattern

Notice the `companyCache`:

```typescript
const companyCache = new Map<string, CompanyEnrichment | null>();
```

This is critical. Without caching:
- 100 job postings × 60 unique companies = 60 API calls
- With caching = 60 API calls
- Without caching, if companies repeat across pages = 100+ API calls

And we store `null` for failed lookups — this prevents the scraper from retrying the same failed company over and over. If Apollo doesn't have data on "Joe's Local Plumbing," asking again won't help.

### Employee Count to Range

```typescript
function countToRange(count: number): string {
    if (count <= 0)     return '';
    if (count <= 10)    return '1-10';
    if (count <= 50)    return '11-50';
    if (count <= 200)   return '51-200';
    if (count <= 500)   return '201-500';
    if (count <= 1000)  return '501-1000';
    if (count <= 5000)  return '1001-5000';
    if (count <= 10000) return '5001-10000';
    return '10000+';
}
```

These ranges match LinkedIn's company size tiers, which most people recognize. Saying "51-200 employees" instantly tells someone "this is a mid-stage startup."

## Bolting Enrichment Onto Any Scraper

Here's the pattern. It's the same for every scraper:

```typescript
// After scraping, before pushing data
const apolloApiKey = input?.apolloApiKey;

if (apolloApiKey && records.length > 0) {
    console.log(`Enriching ${records.length} records with Apollo...`);

    for (const record of records) {
        if (!record.company_name) continue;

        const enrichment = await enrichCompanySize(
            record.company_name,
            apolloApiKey,
        );

        if (enrichment) {
            record.company_size = enrichment.company_size;
            record.company_domain = enrichment.company_domain;
            record.employee_count = enrichment.employee_count;
        }
    }

    console.log(`Enrichment complete. Cache size: ${companyCache.size}`);
}

// Now push to dataset
for (const record of records) {
    await Actor.pushData(record);
}
```

Add `apolloApiKey` to your input schema:

```json
{
    "apolloApiKey": {
        "title": "Apollo API Key",
        "type": "string",
        "description": "Optional. Adds company size and domain data.",
        "isSecret": true
    }
}
```

The `"isSecret": true` flag tells Apify to mask this field in the UI. Never log API keys.

## Scoring Systems

Enrichment gives you more data. Scoring turns that data into priorities. Here are the scoring patterns from our four scrapers:

### Pattern 1: Multi-Dimensional Score (HIPAA Breaches)

Combine multiple factors into a single severity label:

```typescript
function scoreSeverity(record: BreachRecord): string {
    let score = 0;

    // Dimension 1: Scale (0-40 points)
    if (record.individuals_affected >= 500000) score += 40;
    else if (record.individuals_affected >= 100000) score += 30;
    else if (record.individuals_affected >= 10000) score += 20;
    else if (record.individuals_affected >= 1000) score += 10;
    else score += 5;

    // Dimension 2: Recency (0-40 points)
    if (record.days_since_breach <= 30) score += 40;
    else if (record.days_since_breach <= 90) score += 30;
    else if (record.days_since_breach <= 180) score += 20;
    else if (record.days_since_breach <= 365) score += 10;
    else score += 5;

    // Dimension 3: Type (0-20 points)
    const type = record.breach_type.toLowerCase();
    if (type.includes('hacking')) score += 20;
    else if (type.includes('unauthorized')) score += 15;
    else if (type.includes('theft')) score += 12;
    else if (type.includes('loss')) score += 8;
    else score += 5;

    if (score >= 70) return 'critical';
    if (score >= 50) return 'high';
    if (score >= 30) return 'medium';
    return 'low';
}
```

**When to use this pattern:** When you have 2-4 independent dimensions that all matter. Each dimension gets a weight (scale gets 40 points because a 500K breach is always serious, regardless of type).

### Pattern 2: Threshold Urgency (Job Postings)

Simple thresholds with escalation:

```typescript
function calcUrgency(daysListed: number, sourceCount: number): string {
    if (daysListed >= 30 || sourceCount >= 4) return 'critical';
    if (daysListed >= 14 || sourceCount >= 3) return 'high';
    if (daysListed < 3 && daysListed >= 0)    return 'fresh';
    return 'normal';
}
```

**When to use this pattern:** When you have 1-2 clear indicators with natural breakpoints. Job urgency has two signals (days open, number of sources), and each has obvious thresholds.

### Pattern 3: Categorical Classification (Wealth Management)

Classify into segments based on quantitative data:

```typescript
function categorizeFirm(aum: number): string {
    if (aum >= 50_000_000_000) return 'mega';
    if (aum >= 5_000_000_000)  return 'institutional';
    if (aum >= 500_000_000)    return 'mid_market';
    return 'boutique';
}
```

**When to use this pattern:** When the data naturally maps to well-known industry categories. Every financial advisor knows what "boutique" vs "institutional" means.

### Pattern 4: Narrative Signals (All Scrapers)

Generate a human-readable "why this matters" field:

```typescript
function generateSignal(record: FirmRecord): string {
    const signals: string[] = [];

    if (record.employees <= 5 && record.aum_total >= 100_000_000) {
        signals.push(
            'Sub-5 person team with $100M+ AUM — prime candidate for outsourced services'
        );
    }

    if (record.accounts_total > 500 && record.employees <= 10) {
        signals.push(
            `${record.accounts_total} accounts with only ${record.employees} staff — scaling strain`
        );
    }

    // ... more signal rules ...

    return signals[0] || `${record.firm_category} firm, ${record.aum_display} AUM`;
}
```

**When to use this pattern:** Always. Every scraper should have a signal field that answers "why should I care about this record?" This is what separates your scraper from every other data source.

## Building Your Own Scoring System

Here's the framework for any industry:

1. **Identify the question:** "Which companies should I call first?"
2. **List the factors:** What makes a company more or less urgent/valuable?
3. **Assign weights:** Which factors matter most?
4. **Set thresholds:** Where are the natural breakpoints?
5. **Test against real data:** Do the labels match your intuition?

For example, if you were scoring SBA loan data:

```
Question: "Which businesses need financial services right now?"
Factors: Loan size, loan age, industry, number of employees
Weights: Loan age (highest — recent loans mean recent needs)
Thresholds: < 6 months = "active", 6-12 months = "established", 12+ months = "mature"
Signal: "Received $500K SBA loan 3 months ago — actively deploying capital"
```

## The Intelligence Stack

Here's how data flows from raw scrape to actionable signal:

```
1. SCRAPE    → Raw data (company name, numbers, dates)
2. PARSE     → Structured records (typed fields, clean formats)
3. ENRICH    → External data (company size, domain, employee count)
4. SCORE     → Priority labels (critical, high, medium, low)
5. SIGNAL    → Human narrative ("why call today")
```

Lessons 02-05 covered steps 1-2. This lesson covers steps 3-5. When you combine all five, you have something no one else has: **a real-time market intelligence system built from public data.**

Most people stop at step 2. The data exists, but it's just a spreadsheet. Steps 3-5 are where the value lives — and they're almost entirely free to add.

## Real Mistakes We Made

**Mistake 1: Calling Apollo for every record**
The first version called Apollo on every single job posting — including duplicates. 200 records, 200 API calls. With caching, it dropped to ~60 calls (unique companies only).

**Mistake 2: Not storing null in cache**
When Apollo didn't have data on a company, we skipped caching it. Next time that company appeared, we'd call Apollo again and fail again. Storing `null` for misses prevents wasted calls.

**Mistake 3: Using the wrong Apollo endpoint**
We initially used `mixed_companies/search`, which costs credits. The free `mixed_people/search` endpoint returns the same org data. Twenty minutes of reading docs saved hundreds of dollars.

**Mistake 4: Overly complex scoring**
The first severity scoring had 6 dimensions and 4 sub-scores. It was impossible to understand why something scored "high." We simplified to 3 dimensions (scale, recency, type) and it became immediately intuitive.

---

## Next Up

Your scrapers now produce enriched, scored, signal-bearing intelligence. In [Lesson 07: Deploy & Monetize](./07-deploy-and-monetize.md), you'll push everything to Apify's cloud so it runs on autopilot, write a README that sells, and connect it to your business.

## What you just learned
- Apollo's `mixed_people/search` is free (0 credits) and returns company size + domain
- Always read every API endpoint before accepting a cost — there's usually a free alternative
- Cache enrichment results (including failures as `null`) to prevent wasted API calls
- Four scoring patterns: multi-dimensional score, threshold urgency, categorical classification, narrative signals
- Every scraper should have a "why call today" signal field
- The intelligence stack: scrape → parse → enrich → score → signal
