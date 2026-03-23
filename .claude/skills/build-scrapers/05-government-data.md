# Lesson 5: Government Data — No Scraping Needed (SEC Wealth Management)

## What you'll learn
- How to find bulk government data downloads (SEC, HHS, Census, SAM.gov)
- How to download and unzip files in Node.js
- How to parse CSV with quoted fields (the comma-inside-company-names trap)
- How to map cryptic government column codes to useful field names
- Why the best scraper sometimes isn't a scraper at all

## What you'll build
A scraper that downloads SEC Form ADV filings, extracts investment adviser firm data, and adds categorization and opportunity signals — all without opening a browser.

---

## The Insight

Sometimes the government just gives you the data. No HTML tables to parse. No JavaScript to render. No CAPTCHAs to fight. They publish bulk data files — CSV, ZIP, XML — and update them monthly.

This is the fastest scraper you'll build because there's no scraping involved. It's a download-parse-transform pipeline.

**Where to find government data:**
- **SEC** (securities/investment): [adviserinfo.sec.gov](https://adviserinfo.sec.gov/IAPD/IAPDFoia.aspx) — Form ADV filings, investment adviser registrations
- **HHS** (healthcare): [data.cms.gov](https://data.cms.gov/) — hospital data, provider info, breach reports
- **SAM.gov** (federal contracts): [sam.gov/data-services](https://sam.gov/data-services/) — government contract awards
- **Census** (demographics): [data.census.gov](https://data.census.gov/) — population, business, economic data
- **FDIC** (banking): [fdic.gov/resources/data-tools](https://www.fdic.gov/resources/data-tools/) — bank financial data
- **SBA** (small business): [sba.gov/funding-programs/loans](https://data.sba.gov/) — PPP loans, SBA lending

For this lesson, we're using SEC Form ADV — the registration form every investment adviser files with the SEC. It contains firm size, AUM, client types, compensation model, and location. It's free, it's comprehensive, and it updates monthly.

## The Prompt

> "Build me an Apify actor in TypeScript called 'wealth-management' that downloads SEC Form ADV data from https://reports.adviserinfo.sec.gov/reports/foia/advFilingData. It should download the ZIP file for a given month, extract the CSV, and parse each row into a structured record. Fields: firm name, business name, CRD number, SEC number, city, state, zip, employees, AUM total/discretionary/non-discretionary, accounts total, average account size, client focus, compensation model. No Playwright needed — use fetch and unzipper. Include AUM formatting ($4.6B, $450M), firm categorization (boutique/mid-market/institutional/mega), and opportunity signal generation."

## Downloading and Unzipping

The SEC publishes Form ADV data as monthly ZIP files:

```typescript
const BASE_URL = 'https://reports.adviserinfo.sec.gov/reports/foia/advFilingData';

async function downloadAndExtractCSV(url: string, targetFile: string): Promise<string> {
    const response = await fetch(url, {
        headers: {
            'User-Agent': 'Mozilla/5.0 (compatible; ApifyBot)',
        },
    });

    if (!response.ok) throw new Error(`HTTP ${response.status}`);

    const arrayBuffer = await response.arrayBuffer();
    const buffer = Buffer.from(arrayBuffer);

    // Unzip in memory
    const unzipper = await import('unzipper');
    const directory = await unzipper.Open.buffer(buffer);

    for (const file of directory.files) {
        if (file.path.includes('IA_ADV_Base_A')) {
            const content = await file.buffer();
            return content.toString('utf8');
        }
    }

    throw new Error(`${targetFile} not found in ZIP`);
}
```

**Key details:**
- Download into memory (`arrayBuffer`), not disk
- Use `unzipper` to extract — it handles ZIP files cleanly
- Look for the right file inside the ZIP (SEC ZIPs contain multiple files)
- The data file is usually called `IA_ADV_Base_A_*.csv`

### Resolving the Data Month

SEC publishes data monthly. By default, we grab last month's data:

```typescript
function resolveDataMonth(input: string): {
    year: string; month: string;
    startDate: string; endDate: string;
} {
    let y: number, m: number;

    if (input && /^\d{4}-\d{2}$/.test(input)) {
        // User specified "2026-02"
        [y, m] = input.split('-').map(Number);
    } else {
        // Default to previous month
        const now = new Date();
        now.setMonth(now.getMonth() - 1);
        y = now.getFullYear();
        m = now.getMonth() + 1;
    }

    const year = String(y);
    const month = String(m).padStart(2, '0');
    const lastDay = new Date(y, m, 0).getDate();

    return {
        year,
        month,
        startDate: `${year}${month}01`,
        endDate: `${year}${month}${String(lastDay).padStart(2, '0')}`,
    };
}
```

## The CSV Parsing Trap

Government CSVs look simple until you hit this:

```csv
"Smith, Johnson & Associates, LLC",NY,123456
```

That company name has two commas inside it. A naive `.split(',')` would break it into 4 fields instead of 3.

Here's the parser that handles quoted fields correctly:

```typescript
export function parseCSVLine(line: string): string[] {
    const result: string[] = [];
    let current = '';
    let inQuote = false;

    for (let i = 0; i < line.length; i++) {
        const c = line[i];

        if (c === '"') {
            inQuote = !inQuote;
            continue;
        }

        if (c === ',' && !inQuote) {
            result.push(current);
            current = '';
            continue;
        }

        current += c;
    }

    result.push(current);  // Don't forget the last field
    return result;
}
```

**How it works:** Walk through each character. When you hit a quote, toggle `inQuote`. When you hit a comma and you're NOT inside quotes, it's a field separator. When you hit a comma and you ARE inside quotes, it's part of the data.

This is one of those things you could get from a library (like `csv-parse`), but it's 20 lines of code and zero dependencies. For a simple CSV with quoted fields, this is all you need.

## Column Mapping

Government CSVs have 100+ columns with no obvious names. You need the form instructions to understand what each column means.

For SEC Form ADV:

```typescript
export const COL = {
    FILING_ID: 0,
    DATE_SUBMITTED: 2,
    LEGAL_NAME: 3,             // Item 1A
    BUSINESS_NAME: 4,          // Item 1B1
    SEC_NUMBER: 9,             // Item 1D
    CRD_NUMBER: 10,            // Item 1E1
    CITY: 13,
    STATE: 14,
    ZIP: 16,
    EMPLOYEES: 41,             // Item 5A

    // Client types (Y/N flags)
    CLIENTS_INDIVIDUALS: 50,   // Item 5D1a
    CLIENTS_HNW: 51,           // Item 5D1b
    CLIENTS_BANKING: 52,       // Item 5D1c
    CLIENTS_POOLED: 55,        // Item 5D1f
    CLIENTS_PENSION: 56,       // Item 5D1g
    CLIENTS_CORPORATIONS: 62,  // Item 5D1m

    // Compensation model (Y/N flags)
    COMP_PCT_AUM: 91,          // Item 5E1
    COMP_HOURLY: 92,           // Item 5E2
    COMP_FIXED: 94,            // Item 5E4
    COMP_COMMISSIONS: 95,      // Item 5E5
    COMP_PERFORMANCE: 96,      // Item 5E6

    // AUM
    AUM_DISCRETIONARY: 99,
    AUM_NON_DISCRETIONARY: 100,
    AUM_TOTAL: 101,
    ACCOUNTS_DISCRETIONARY: 102,
    ACCOUNTS_NON_DISCRETIONARY: 103,
    ACCOUNTS_TOTAL: 104,
};
```

**How we figured this out:** Download the [Form ADV instructions PDF](https://www.sec.gov/about/forms/formadv-instructions.pdf) and match each item number to the CSV column position. Column 41 = "Item 5A: Employees" and so on.

This is the tedious part of government data. The data itself is gold, but the documentation is scattered across PDFs and instruction pages. Spend the time to map it correctly — it's a one-time cost.

## Building the Record

```typescript
function buildRecord(fields: string[]): FirmRecord | null {
    const aumTotal = parseFloat(fields[COL.AUM_TOTAL]) || 0;
    const employees = parseInt(fields[COL.EMPLOYEES], 10) || 0;
    const accountsTotal = parseInt(fields[COL.ACCOUNTS_TOTAL], 10) || 0;

    // Skip firms with no AUM (they're not active managers)
    if (aumTotal <= 0) return null;

    const aumDisc = parseFloat(fields[COL.AUM_DISCRETIONARY]) || 0;
    const aumNonDisc = parseFloat(fields[COL.AUM_NON_DISCRETIONARY]) || 0;

    return {
        firm_name: fields[COL.LEGAL_NAME]?.trim() || '',
        business_name: fields[COL.BUSINESS_NAME]?.trim() || '',
        crd_number: fields[COL.CRD_NUMBER]?.trim() || '',
        sec_number: fields[COL.SEC_NUMBER]?.trim() || '',
        city: fields[COL.CITY]?.trim() || '',
        state: fields[COL.STATE]?.trim() || '',
        zip: fields[COL.ZIP]?.trim() || '',
        employees,
        aum_total: aumTotal,
        aum_display: formatAUM(aumTotal),
        aum_discretionary: aumDisc,
        aum_non_discretionary: aumNonDisc,
        accounts_total: accountsTotal,
        accounts_discretionary: parseInt(fields[COL.ACCOUNTS_DISCRETIONARY], 10) || 0,
        avg_account_size: accountsTotal > 0 ? Math.round(aumTotal / accountsTotal) : 0,
        aum_per_employee: employees > 0 ? Math.round(aumTotal / employees) : 0,
        client_focus: getClientFocus(fields),
        compensation_model: getCompensationModel(fields),
        firm_category: categorizeFirm(aumTotal),
        opportunity_signal: '',  // Filled in later
        filing_date: fields[COL.DATE_SUBMITTED]?.trim() || '',
        source_url: 'https://adviserinfo.sec.gov',
    };
}
```

### Formatting AUM

Nobody wants to read `4600000000`. They want `$4.6B`:

```typescript
function formatAUM(aum: number): string {
    if (aum >= 1_000_000_000) {
        return `$${(aum / 1_000_000_000).toFixed(1)}B`;
    }
    if (aum >= 1_000_000) {
        return `$${(aum / 1_000_000).toFixed(0)}M`;
    }
    if (aum >= 1_000) {
        return `$${(aum / 1_000).toFixed(0)}K`;
    }
    return `$${aum}`;
}
```

## Categorization and Signals

### Firm Categories

```typescript
function categorizeFirm(aum: number): string {
    if (aum >= 50_000_000_000) return 'mega';            // $50B+
    if (aum >= 5_000_000_000)  return 'institutional';   // $5B-$50B
    if (aum >= 500_000_000)    return 'mid_market';       // $500M-$5B
    return 'boutique';                                     // < $500M
}
```

### Client Focus Detection

```typescript
function getClientFocus(fields: string[]): string {
    const yes = (col: number) => fields[col]?.trim().toUpperCase() === 'Y';

    const individuals = yes(COL.CLIENTS_INDIVIDUALS);
    const hnw = yes(COL.CLIENTS_HNW);
    const pooled = yes(COL.CLIENTS_POOLED);
    const pension = yes(COL.CLIENTS_PENSION);
    const corps = yes(COL.CLIENTS_CORPORATIONS);
    const banking = yes(COL.CLIENTS_BANKING);

    const retail = individuals || hnw;
    const institutional = pooled || pension || corps || banking;

    if (hnw && !institutional)           return 'high-net-worth';
    if (retail && !institutional)         return 'retail';
    if (institutional && !retail)         return 'institutional';
    if (pooled && !retail)               return 'fund-of-funds';
    return 'mixed';
}
```

### Opportunity Signals

This is the crown jewel — the "why should I care?" field:

```typescript
function generateSignal(record: FirmRecord): string {
    const signals: string[] = [];

    // Lean operation — high AUM per employee
    if (record.aum_per_employee > 500_000_000) {
        signals.push(
            'Extremely lean operation — high AUM per employee means heavy tech dependence'
        );
    } else if (record.aum_per_employee > 100_000_000) {
        signals.push(
            'Lean team managing significant AUM — likely needs automation and tooling'
        );
    }

    // Small team + big AUM
    if (record.employees <= 5 && record.aum_total >= 100_000_000) {
        signals.push(
            'Sub-5 person team with $100M+ AUM — prime candidate for outsourced services'
        );
    }

    // Ultra-high-net-worth accounts
    if (record.avg_account_size >= 5_000_000) {
        signals.push(
            `Avg account ${formatAUM(record.avg_account_size)} — ultra-high-net-worth focus`
        );
    }

    // Scaling strain
    if (record.accounts_total > 500 && record.employees <= 10) {
        signals.push(
            `${record.accounts_total} accounts with only ${record.employees} staff — scaling strain`
        );
    }

    // Compensation model clues
    if (record.compensation_model.includes('performance')) {
        signals.push('Performance-based fees — sophisticated fund operation');
    }
    if (record.compensation_model.includes('commissions')) {
        signals.push('Commission-based — heightened compliance scrutiny');
    }

    if (signals.length === 0) {
        signals.push(
            `${record.firm_category} firm, ${record.aum_display} AUM`
        );
    }

    return signals[0];
}
```

Every record that comes out of your scraper now has an `opportunity_signal` explaining WHY this firm is interesting. That's the difference between a data dump and intelligence.

## The Main Loop

```typescript
await Actor.init();

const input = await Actor.getInput<{
    dataMonth?: string;    // "2026-02"
    minAUM?: number;       // Filter small firms
    stateFilter?: string;  // "CA,TX,NY"
    maxRecords?: number;
}>();

const { startDate, endDate } = resolveDataMonth(input?.dataMonth ?? '');

// Build download URL
const url = `${BASE_URL}/IA_ADV_Base_A_${startDate}_${endDate}.zip`;
console.log(`Downloading: ${url}`);

const csvContent = await downloadAndExtractCSV(url, 'IA_ADV_Base_A');
const lines = csvContent.split('\n');

console.log(`Parsing ${lines.length} rows...`);

const seen = new Set<string>();
let pushed = 0;

// Skip header row
for (let i = 1; i < lines.length; i++) {
    const line = lines[i].trim();
    if (!line) continue;

    const fields = parseCSVLine(line);
    const record = buildRecord(fields);
    if (!record) continue;

    // Dedup by CRD number
    if (seen.has(record.crd_number)) continue;
    seen.add(record.crd_number);

    // Apply filters
    if (input?.minAUM && record.aum_total < input.minAUM) continue;
    if (input?.stateFilter) {
        const states = input.stateFilter.split(',').map(s => s.trim().toUpperCase());
        if (!states.includes(record.state)) continue;
    }

    // Generate signal
    record.opportunity_signal = generateSignal(record);

    await Actor.pushData(record);
    pushed++;

    if (input?.maxRecords && pushed >= input.maxRecords) break;
}

console.log(`Pushed ${pushed} records`);
await Actor.exit();
```

## Running It

```bash
cd wealth-management
npm install
apify run --input='{"minAUM":100000000,"stateFilter":"CA,TX","maxRecords":50}'
```

Output:

```json
{
    "firm_name": "FISHER INVESTMENTS",
    "business_name": "Fisher Investments",
    "crd_number": "123456",
    "city": "CAMAS",
    "state": "WA",
    "employees": 4800,
    "aum_total": 236000000000,
    "aum_display": "$236.0B",
    "avg_account_size": 783200,
    "firm_category": "mega",
    "client_focus": "retail",
    "compensation_model": "% of AUM",
    "opportunity_signal": "Extremely lean operation — high AUM per employee means heavy tech dependence",
    "source_url": "https://adviserinfo.sec.gov"
}
```

## Speed Comparison

| Pattern | Lesson | Time for 100 records |
|---------|--------|---------------------|
| HTML table (Playwright) | 02 | ~60 seconds |
| Guest API (fetch) | 03 | ~10 seconds |
| JS-rendered SPA (Playwright) | 04 | ~90 seconds |
| **CSV download (fetch)** | **05** | **~3 seconds** |

Government bulk data is the fastest pattern by far. No browsers, no pagination, no rate limits. Download, parse, done.

## Real Mistakes We Made

**Mistake 1: Using `.split(',')` on the CSV**
Company names with commas broke everything. We got "Smith" in one field and "Johnson & Associates" in the next. The custom `parseCSVLine` with quote tracking fixed it.

**Mistake 2: Wrong column indices**
The SEC documentation is split across multiple PDFs. We mapped "Employees" to the wrong column and got garbage numbers. Had to cross-reference the actual CSV header row with the form instructions.

**Mistake 3: Not skipping the header**
The first row of the CSV is column names. The first version tried to parse "LEGAL_NAME" as a company name and pushed a garbage record. Start from `i = 1`.

---

## Next Up

You've now built scrapers across all four patterns: tables, APIs, SPAs, and bulk downloads. In [Lesson 06: Enrichment & Signals](./06-enrichment-and-signals.md), you'll learn how to add Apollo company enrichment and scoring logic to any scraper — turning raw data into actionable intelligence.

## What you just learned
- Government agencies publish bulk data as CSV/ZIP — no scraping needed
- SEC Form ADV gives you firm size, AUM, client types, compensation model — all for free
- CSV parsing trap: company names contain commas — use quote-aware parsing, not `.split(',')`
- Column mapping requires reading the form instructions — tedious but one-time
- Categorization (boutique/institutional/mega) + signals ("why call today") are what make your data actionable
- Bulk download is the fastest pattern: ~3 seconds for 100 records vs ~60 seconds with Playwright
