# Lesson 2: Your First Scraper — HTML Tables (HIPAA Breaches)

## What you'll learn
- How to scrape an HTML table from a government website
- How to handle PrimeFaces/JSF pagination (the kind that breaks naive scrapers)
- How to parse dates, numbers, and messy government data
- How to add severity scoring — turning raw rows into actionable signals
- How to debug with `page.screenshot()`

## What you'll build
A scraper that pulls healthcare data breaches from the HHS HIPAA Breach Portal, scores them by severity, and outputs intelligence you can act on.

---

## Why HIPAA Breaches?

The Department of Health and Human Services publishes every reported data breach affecting 500+ individuals. It's public, it's updated constantly, and it's a goldmine for anyone selling cybersecurity, compliance consulting, legal services, or insurance.

But nobody scrapes it because the site is built on PrimeFaces (a Java framework) and the table pagination doesn't work with simple HTTP requests. You need a real browser.

That's where Playwright comes in.

## The Prompt

Open Claude Code in your project folder and paste this:

> "Build me an Apify actor in TypeScript called 'security-breaches' that scrapes the HIPAA breach report at https://ocrportal.hhs.gov/ocr/breach/breach_report.jsf. It should extract: company name, state, entity type, individuals affected, breach date, breach type, and breach location from the table. Use PlaywrightCrawler from Crawlee. Handle pagination — the site uses PrimeFaces with a .ui-paginator-next button. Include input parameters for minIndividuals (filter small breaches), stateFilter (comma-separated state codes), and maxPages. Convert breach dates from MM/DD/YYYY to ISO format. Calculate days since breach."

Claude Code will generate the full project. Let's walk through what it creates and why.

## The Project Structure

```
security-breaches/
  .actor/
    actor.json
    input_schema.json
  src/
    main.ts              # Entry point + pagination loop
    parser.ts            # Table row parsing
    scoring.ts           # Breach severity calculation
    enrichment.ts        # Apollo company size (optional)
  package.json
  tsconfig.json
  Dockerfile
```

## Understanding the Code

### The Entry Point (main.ts)

The main file sets up a Playwright browser and navigates to the breach portal:

```typescript
import { Actor } from 'apify';
import { PlaywrightCrawler } from 'crawlee';
import { parseRow } from './parser.js';
import { scoreSeverity } from './scoring.js';

await Actor.init();

const input = await Actor.getInput<{
    minIndividuals?: number;
    stateFilter?: string;
    maxPages?: number;
}>();

const minIndividuals = input?.minIndividuals ?? 500;
const stateFilter = input?.stateFilter
    ? input.stateFilter.split(',').map(s => s.trim().toUpperCase())
    : [];
const maxPages = input?.maxPages ?? 10;
```

Notice the pattern: read inputs, set defaults, normalize. Every scraper starts this way.

### Parsing Table Rows (parser.ts)

Government tables are messy. Here's how we handle it:

```typescript
export function parseRow(cells: string[], reportType: string): BreachRecord | null {
    if (cells.length < 7) return null;

    // The table has an expand arrow in the first column on some views
    // Detect and adjust offset
    const offset = cells.length >= 8 ? 1 : 0;

    const name = cells[offset + 0].trim();
    const state = cells[offset + 1].trim();
    const entityType = cells[offset + 2].trim();
    const individualsRaw = cells[offset + 3].trim().replace(/,/g, '');
    const dateRaw = cells[offset + 4].trim();
    const breachType = cells[offset + 5].trim();
    const location = cells[offset + 6].trim();

    // Parse number — remove commas, handle garbage
    const individuals = parseInt(individualsRaw, 10) || 0;

    // MM/DD/YYYY → ISO
    const dateParts = dateRaw.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/);
    let isoDate = '';
    let daysSince = 0;

    if (dateParts) {
        const month = dateParts[1].padStart(2, '0');
        const day = dateParts[2].padStart(2, '0');
        const year = dateParts[3];
        isoDate = `${year}-${month}-${day}`;

        const breachDate = new Date(`${year}-${month}-${day}T00:00:00Z`);
        daysSince = Math.floor(
            (Date.now() - breachDate.getTime()) / (1000 * 60 * 60 * 24)
        );
    }

    return {
        company_name: name,
        state,
        entity_type: entityType,
        individuals_affected: individuals,
        breach_date: isoDate,
        breach_date_raw: dateRaw,
        days_since_breach: daysSince,
        breach_type: breachType,
        breach_location: location,
        report_type: reportType,
        source_url: 'https://ocrportal.hhs.gov/ocr/breach/breach_report.jsf',
    };
}
```

**Key lessons here:**
1. **The offset trick** — Government tables sometimes have extra columns (expand arrows, checkboxes). Count the cells and adjust.
2. **Date parsing** — Government dates are MM/DD/YYYY. You want ISO (YYYY-MM-DD) for sorting and analysis.
3. **Number cleaning** — `"1,234"` → remove commas → `parseInt`.
4. **Days since** — This is the recency signal. A breach from 7 days ago is way more actionable than one from 2 years ago.

### Scoring Severity (scoring.ts)

This is where data becomes intelligence. Raw breach records are just facts. Scored records are **signals**.

```typescript
export function scoreSeverity(record: BreachRecord): string {
    let score = 0;

    // Scale — how many people were affected? (0-40 points)
    if (record.individuals_affected >= 500000) score += 40;
    else if (record.individuals_affected >= 100000) score += 30;
    else if (record.individuals_affected >= 10000) score += 20;
    else if (record.individuals_affected >= 1000) score += 10;
    else score += 5;

    // Recency — how recent was this? (0-40 points)
    if (record.days_since_breach <= 30) score += 40;
    else if (record.days_since_breach <= 90) score += 30;
    else if (record.days_since_breach <= 180) score += 20;
    else if (record.days_since_breach <= 365) score += 10;
    else score += 5;

    // Breach type — how serious? (0-20 points)
    const type = record.breach_type.toLowerCase();
    if (type.includes('hacking') || type.includes('it incident')) score += 20;
    else if (type.includes('unauthorized')) score += 15;
    else if (type.includes('theft')) score += 12;
    else if (type.includes('loss')) score += 8;
    else score += 5;

    // Map to label
    if (score >= 70) return 'critical';
    if (score >= 50) return 'high';
    if (score >= 30) return 'medium';
    return 'low';
}
```

**Why three dimensions?**
- A breach of 1M records from 2 years ago? Old news. Medium at best.
- A breach of 1,000 records from last week via hacking? Urgent. They're bleeding right now.
- A breach of 500K records from last month via hacking? Critical. That's a company in crisis mode.

The scoring captures this nuance. Every row that comes out of your scraper now has a `breach_severity` field that tells you where to focus.

## The PrimeFaces Pagination Problem

This is where most scrapers fail on government sites. The HIPAA portal uses PrimeFaces (a Java Server Faces framework), which means:

1. The table is rendered server-side
2. Clicking "Next" triggers an AJAX request, not a page navigation
3. The URL doesn't change when you paginate
4. Standard "follow the next link" crawling doesn't work

Here's how we handle it:

```typescript
async function goToNextPage(page: Page, log: Log): Promise<boolean> {
    const nextBtn = page.locator('.ui-paginator-next').first();

    if (await nextBtn.count() === 0) return false;

    const classList = await nextBtn.getAttribute('class') ?? '';
    if (classList.includes('ui-state-disabled')) return false;

    // Capture current state to verify page actually changed
    const firstCell = await page.$('tr td:nth-child(2)');
    const firstRowText = firstCell
        ? (await firstCell.textContent())?.trim() ?? ''
        : '';

    await nextBtn.click();
    await page.waitForLoadState('networkidle', { timeout: 15000 })
        .catch(() => {});
    await page.waitForTimeout(1500);  // PrimeFaces needs a moment

    // Verify the page actually changed
    const newFirstCell = await page.$('tr td:nth-child(2)');
    const newFirstRowText = newFirstCell
        ? (await newFirstCell.textContent())?.trim() ?? ''
        : '';

    return newFirstRowText !== firstRowText && firstRowText !== '';
}
```

**Critical detail:** We don't just click and hope. We:
1. Check if the button is disabled (`ui-state-disabled`)
2. Capture the first row's text BEFORE clicking
3. Click and wait for network to settle
4. Check if the first row changed — if it didn't, we're stuck

This "verify the page changed" pattern will save you hours of debugging. Without it, you'll get stuck in infinite loops on broken pagination.

## Running It

```bash
cd security-breaches
npm install
apify run
```

First run, check what you got:

```bash
ls storage/datasets/default/
cat storage/datasets/default/000000001.json
```

You should see something like:

```json
{
    "company_name": "Ascension Health",
    "state": "MO",
    "entity_type": "Healthcare Provider",
    "individuals_affected": 5599924,
    "breach_date": "2025-05-08",
    "days_since_breach": 304,
    "breach_type": "Hacking/IT Incident",
    "breach_location": "Network Server",
    "breach_severity": "high",
    "source_url": "https://ocrportal.hhs.gov/ocr/breach/breach_report.jsf"
}
```

That's a real breach record with severity scoring. You can now sort by severity and call the critical ones first.

## Debugging Tips

### Screenshot Everything

When something doesn't work, add this to your scraper:

```typescript
await page.screenshot({ path: 'debug.png', fullPage: true });
```

Then look at `debug.png`. You'll often discover:
- A cookie consent banner blocking the table
- A CAPTCHA you didn't expect
- The table hasn't loaded yet
- You're on the wrong page

Screenshots are your best debugging tool. Use them liberally.

### `page.evaluate()` vs `page.$$()`

Sometimes `page.evaluate()` (which runs JavaScript inside the browser) fails on government sites with strict Content Security Policy. When that happens, use `page.$$()` instead:

```typescript
// This might fail on strict CSP sites
const data = await page.evaluate(() => {
    return document.querySelectorAll('tr');
});

// This always works — it runs in Node, not the browser
const rows = await page.$$('tbody tr');
for (const row of rows) {
    const cells = await row.$$('td');
    const texts = [];
    for (const cell of cells) {
        texts.push((await cell.textContent())?.trim() ?? '');
    }
    // Now parse texts[]
}
```

### The Table Isn't There

If your selector finds nothing, the table might:
1. Be inside an iframe → `page.frameLocator('iframe').locator('table')`
2. Need time to load → `await page.waitForSelector('table tbody tr')`
3. Be rendered by JavaScript → you're already using Playwright, so wait longer
4. Have a different structure → use `page.content()` to see the raw HTML

## Adding Input Filters

Make your scraper configurable so you don't have to edit code every time:

```json
{
    "title": "HIPAA Breach Scraper",
    "type": "object",
    "schemaVersion": 1,
    "properties": {
        "minIndividuals": {
            "title": "Minimum Individuals Affected",
            "type": "integer",
            "default": 500,
            "description": "Filter out breaches below this threshold"
        },
        "stateFilter": {
            "title": "State Filter",
            "type": "string",
            "description": "Comma-separated state codes (e.g., 'CA,TX,NY')"
        },
        "maxPages": {
            "title": "Max Pages",
            "type": "integer",
            "default": 10,
            "description": "How many pages to scrape"
        }
    }
}
```

Then in your code:

```typescript
// Apply filters during parsing
if (record.individuals_affected < minIndividuals) continue;
if (stateFilter.length > 0 && !stateFilter.includes(record.state)) continue;
```

Filter at parse time, not after. No point storing data you'll throw away.

## Real Mistakes We Made

**Mistake 1: Trusting cell count**
The first version assumed exactly 7 columns. Some rows had an expand arrow column, making it 8. The parser returned garbage until we added the offset detection.

**Mistake 2: Not waiting for PrimeFaces**
We clicked "Next" and immediately tried to read the table. PrimeFaces hadn't finished its AJAX update yet. Adding `waitForLoadState('networkidle')` plus a 1.5s buffer fixed it.

**Mistake 3: Infinite pagination loop**
Without the "verify page changed" check, the scraper would click "Next" forever on the last page (the button existed but was disabled via CSS class, not via the `disabled` attribute). Always verify state change after clicking pagination controls.

---

## Next Up

You just built a browser-based table scraper — the most common pattern for government data. In [Lesson 03: API Scrapers](./03-api-scraper.md), you'll learn a much faster approach: hitting APIs directly without a browser at all.

## What you just learned
- Government websites are goldmines — public data, timestamped, constantly updated
- PrimeFaces/JSF pagination requires a browser (Playwright) and state-change verification
- Date parsing: government uses MM/DD/YYYY, convert to ISO YYYY-MM-DD
- Severity scoring turns raw rows into actionable intelligence (critical/high/medium/low)
- Debug with `page.screenshot()` — it reveals what you can't see in code
- Filter at parse time, not after — don't store data you'll throw away
- Always verify pagination actually changed the page before reading new data
