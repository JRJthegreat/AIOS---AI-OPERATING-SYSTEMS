# Lesson 7: Deploy & Monetize

## What you'll learn
- How to push your scraper to Apify so it runs in the cloud
- The Dockerfile pattern that works every time
- How to write a README that sells your scraper
- How to configure scheduling and monitoring
- Pricing strategies: free (distribution) vs paid (product)
- How to connect scraper output to your platform or workflow

## What you'll build
A cloud-deployed, production-ready Apify actor with a professional README, input schema, and deployment config.

---

## Pushing to Apify

You've been running scrapers locally with `apify run`. Now let's deploy them to the cloud.

### Step 1: Verify Locally

Always test one more time before deploying:

```bash
apify run
cat storage/datasets/default/000000001.json
```

Looks good? Move on.

### Step 2: Push

```bash
apify push
```

That's it. Apify uploads your code, builds the Docker image, and deploys it.

**Version format:** Apify uses `MAJOR.MINOR` (not semver). Your `actor.json` specifies this:

```json
{
    "actorSpecification": 1,
    "name": "security-breaches",
    "title": "HIPAA Breach Intelligence Scraper",
    "version": "1.0",
    "buildTag": "latest",
    "input": "./input_schema.json",
    "dockerfile": "../Dockerfile"
}
```

Each `apify push` creates a new build under the version specified in `actor.json`. To release a new major version, change `"version": "1.0"` to `"version": "2.0"`.

## The Dockerfile Pattern

Every scraper we've built uses this same two-stage Dockerfile. It works for all four scraper patterns:

### For Playwright scrapers (Lessons 02, 04):

```dockerfile
# Build stage
FROM apify/actor-node-playwright-chrome:22 AS builder
COPY --chown=myuser:myuser package*.json ./
RUN npm install --include=dev --audit=false
COPY --chown=myuser:myuser tsconfig.json ./
COPY --chown=myuser:myuser src/ ./src/
RUN npm run build

# Production stage
FROM apify/actor-node-playwright-chrome:22
COPY --chown=myuser:myuser package*.json ./
RUN npm install --omit=dev --audit=false && npm cache clean --force
COPY --from=builder /home/myuser/dist ./dist
COPY --chown=myuser:myuser .actor ./.actor
CMD ["node", "dist/main.js"]
```

### For non-browser scrapers (Lessons 03, 05):

```dockerfile
# Build stage
FROM apify/actor-node:22 AS builder
COPY --chown=myuser:myuser package*.json ./
RUN npm install --include=dev --audit=false
COPY --chown=myuser:myuser tsconfig.json ./
COPY --chown=myuser:myuser src/ ./src/
RUN npm run build

# Production stage
FROM apify/actor-node:22
COPY --chown=myuser:myuser package*.json ./
RUN npm install --omit=dev --audit=false && npm cache clean --force
COPY --from=builder /home/myuser/dist ./dist
COPY --chown=myuser:myuser .actor ./.actor
CMD ["node", "dist/main.js"]
```

**The difference:** `apify/actor-node-playwright-chrome:22` includes Chrome browser. `apify/actor-node:22` doesn't — it's smaller and faster to build.

**Key details:**
- `--chown=myuser:myuser` — Apify containers run as `myuser`, not root. Without this, file permissions break.
- Two stages: build stage installs dev dependencies and compiles TypeScript, production stage only has the compiled JavaScript and production dependencies.
- `npm cache clean --force` — Shrinks the Docker image by removing the npm cache.
- `.actor` directory is copied separately — it contains metadata, not code.

## Writing a README That Sells

Your README is the sales page for your scraper. Here's the structure that works:

### 1. One-Sentence Hook

```markdown
# HIPAA Breach Intelligence Scraper

Scrape healthcare data breaches from the HHS portal with severity scoring,
company enrichment, and "why call today" signals.
```

Not "This actor scrapes the HIPAA breach portal." That describes what it does. The hook describes what you GET.

### 2. Use Cases (Not Features)

Don't list technical features. List business outcomes:

```markdown
## Use Cases

- **Cybersecurity sales:** Find companies that just had a breach
  and need security consulting NOW
- **Compliance consulting:** Identify healthcare organizations
  under investigation for data handling failures
- **Insurance brokers:** Spot healthcare providers with recent
  incidents who need updated cyber liability coverage
- **Legal services:** Track breaches that may lead to class action
  lawsuits or regulatory penalties
```

### 3. The "Why This Is a Signal" Table

This is the killer differentiator. Every field explains WHY it matters:

```markdown
## Output Fields

| Field | Example | Why It Matters |
|-------|---------|----------------|
| company_name | "Ascension Health" | Your target |
| individuals_affected | 5,599,924 | Scale = urgency. 5M records = enterprise-level crisis |
| days_since_breach | 12 | Recency = timing. Under 30 days = they're still in response mode |
| breach_type | "Hacking/IT Incident" | Hacking = most severe, most likely to need external help |
| breach_severity | "critical" | Pre-calculated priority. Focus on critical + high first |
| company_size | "5001-10000" | Enriched via Apollo. Larger = bigger contract potential |
| company_domain | "ascension.org" | For email outreach and further research |
| opportunity_signal | "500K+ records breached 12 days ago..." | The one-sentence pitch |
```

Most scrapers dump data. Yours explains the data. That's the difference between a tool and a product.

### 4. Quick Start

```markdown
## Quick Start

1. Click "Start" in the Apify Console
2. Set your filters (state, minimum affected individuals)
3. Optionally add your Apollo API key for company size enrichment
4. Run and download results as CSV, JSON, or Excel

No coding required.
```

### 5. Input Reference

```markdown
## Input Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| minIndividuals | number | 500 | Filter out small breaches |
| stateFilter | string | (all) | Comma-separated: "CA,TX,NY" |
| maxPages | number | 10 | Pages to scrape |
| apolloApiKey | string | (none) | Adds company size and domain |
```

## Running in Apify Console

After `apify push`, go to your actor in the Apify Console:

1. Click **"Start"** to run with default inputs
2. Click **"Input"** to configure parameters
3. Click **"Runs"** to see execution history
4. Click any run → **"Dataset"** → preview or download results

**Always test in the console before publishing.** The cloud environment can behave differently than your laptop — different IP, different timezone, different resource limits.

### Common Cloud Issues

**"Build failed"**
Check the build log. Usually a missing dependency in `package.json` or a Dockerfile issue.

**"Actor timed out"**
Default timeout is 1 hour. For large scrapes, increase it in Settings → Timeout.

**"Empty dataset"**
The site might be blocking Apify's IP range. Add proxy support:

```typescript
const proxyConfiguration = process.env.APIFY_IS_AT_HOME
    ? await Actor.createProxyConfiguration({ useApifyProxy: true })
    : undefined;
```

**"Memory limit exceeded"**
Playwright scrapers need more memory. Go to Settings → Memory and increase to 1024 MB or 2048 MB.

## Scheduling

Set your scraper to run automatically:

1. Go to your actor → **"Schedules"**
2. Click **"Create schedule"**
3. Set frequency: daily, weekly, monthly
4. Set input: the same parameters you use manually

**Recommended schedules:**
- HIPAA breaches: daily (new breaches appear constantly)
- Job postings: daily (jobs change fast)
- Conference speakers: weekly (events update slowly)
- SEC wealth management: monthly (data publishes monthly)

## Pricing Strategies

### Free (Distribution Play)

Publish your scraper as free on the Apify Store. Why give it away?

- **Distribution:** Free scrapers get 10-100x more users than paid ones
- **Lead generation:** Users who need custom features become consulting clients
- **Platform visibility:** High-usage actors rank higher in Apify's marketplace
- **Data network effects:** More users → more feedback → better scraper

This works best when the scraper itself isn't your product — the intelligence layer is. Give away the scraper, sell the analysis.

### Paid (Product Play)

Charge per result or per monthly subscription:

- **Per-result pricing:** $0.001 - $0.01 per record. Works for high-volume scrapers.
- **Monthly subscription:** $10-50/month for access. Works for niche, high-value data.

This works best when the data itself is hard to get and the scraper required significant domain expertise to build.

### The Hybrid

Most effective approach: free scraper with basic fields, paid version with enrichment and signals.

```
Free tier:  company_name, state, breach_date, breach_type
Paid tier:  + breach_severity, company_size, company_domain, opportunity_signal
```

The free tier proves the data exists. The paid tier adds the intelligence that makes it actionable.

## Connecting to Your Platform

Your scraper produces datasets. Here's how to pipe that data into your business:

### Option 1: Direct Download

Run the scraper → go to the dataset → download as CSV/JSON/Excel. Simple, manual, good for small operations.

### Option 2: Apify API

Fetch results programmatically:

```typescript
const datasetId = 'your-dataset-id';
const response = await fetch(
    `https://api.apify.com/v2/datasets/${datasetId}/items?token=YOUR_TOKEN`
);
const records = await response.json();
```

Use this when you want to pull scraper results into your own application.

### Option 3: Webhooks

Configure Apify to call your webhook when a run finishes:

1. Go to your actor → Integrations → Webhooks
2. Add your webhook URL
3. Apify will POST run metadata when complete

Your server receives the notification, fetches the dataset, and processes it automatically.

### Option 4: Direct Integration

If you use Connector OS or a similar platform, point your pipeline at the Apify dataset ID:

```
Apify dataset → your platform's import → enrichment → scoring → routing
```

The scraper handles acquisition. Your platform handles evaluation and routing. Clean separation.

## The Complete Workflow

Here's the end-to-end workflow for a production scraper:

```
1. Identify a data source (government site, job board, conference)
2. Tell Claude Code what to build (the magic prompt)
3. Test locally (apify run)
4. Add enrichment (Apollo company size)
5. Add scoring (severity, urgency, signals)
6. Test again locally
7. Push to Apify (apify push)
8. Test in Apify Console
9. Set up scheduling (daily/weekly/monthly)
10. Connect to your platform or workflow
```

Steps 1-6 take 1-2 hours for a new scraper. Steps 7-10 take 15 minutes. After that, it runs on autopilot.

## What You Built in This Course

Let's take stock. You built 4 production scrapers across 4 different patterns:

| Scraper | Pattern | Data Source | Intelligence Added |
|---------|---------|-------------|-------------------|
| HIPAA Breaches | HTML table | Government website | Severity scoring, enrichment |
| LinkedIn Jobs | Hidden API | LinkedIn guest API | Urgency scoring, repost detection |
| Conference Speakers | JS-rendered SPA | Conference websites | Auto-detection, name parsing |
| SEC Wealth Mgmt | CSV download | SEC filings | Firm categorization, opportunity signals |

Each one follows the same pipeline:

```
Scrape → Parse → Enrich → Score → Signal
```

The scraping pattern varies (browser, API, download), but the intelligence layer is always the same: take raw data, add external enrichment, score it, and generate a human-readable signal.

That's the formula. Apply it to any data source — federal contracts, court filings, patent databases, funding announcements, real estate records — and you have an automated intelligence pipeline.

## Real Mistakes We Made

**Mistake 1: Deploying before testing in console**
The scraper worked locally but failed on Apify because we were using a file path that didn't exist in the Docker container. Always test in the Apify Console before sharing.

**Mistake 2: Forgetting `--chown=myuser:myuser`**
Without this in the Dockerfile, the container can't write to the filesystem and fails silently. Every COPY in the Dockerfile needs it.

**Mistake 3: Overpricing**
We initially set pricing at $0.05 per record. Usage was zero. Dropped to free and got 50+ users in the first week. The users became consulting leads worth far more than per-record pricing.

---

## What You Just Learned
- `apify push` deploys your scraper to the cloud — one command
- Two-stage Dockerfile: build with dev deps, run with production deps only
- READMEs that sell: hook, use cases, "why it matters" field table, quick start
- Test in Apify Console before publishing — cloud behavior differs from local
- Scheduling: daily for fast-moving data (jobs, breaches), monthly for slow data (filings)
- Pricing: free for distribution, paid for enriched/scored data, hybrid for best of both
- Connect via API, webhook, or direct download

## Course Complete

You started this course with zero scraping experience. You now have:
- 4 production scrapers covering every common pattern
- An enrichment layer (Apollo) you can bolt onto anything
- Scoring systems that turn data into intelligence
- A deployment workflow that takes 15 minutes
- A framework for building new scrapers on any data source

The scrapers are the tap. The intelligence layer is the product. What you do with the water — that's your business.

Go build something.
