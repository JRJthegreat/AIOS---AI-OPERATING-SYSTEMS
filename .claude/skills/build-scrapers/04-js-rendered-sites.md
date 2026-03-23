# Lesson 4: JS-Rendered Sites — Conference Speakers (Playwright)

## What you'll learn
- How to detect when a site requires a real browser (the `curl` test)
- How to auto-detect content cards without hardcoding selectors
- The selector cascade: class patterns → grid heuristics → structural fallbacks
- How to handle cookie banners, pagination variants, and infinite scroll
- How to split names properly ("Dr. Jean-Pierre Dubois III" → first/last)

## What you'll build
A universal conference speaker scraper that works on almost any event website — without you having to customize selectors for each one.

---

## When Do You Need Playwright?

Here's the quick test:

```bash
curl -s https://some-conference.com/speakers | head -50
```

If the HTML contains the data you want → use `fetch` (Lesson 03 approach).
If the HTML is mostly empty `<div id="root"></div>` → the site uses React/Angular/Vue and renders everything with JavaScript. You need Playwright.

Conference websites are almost always JavaScript-rendered. They're built with modern frameworks, load data dynamically, and show nothing without JavaScript. That's why this lesson uses Playwright.

## The Prompt

> "Build me an Apify actor in TypeScript called 'conference-speakers' that scrapes speaker information from any conference website. Inputs: speakersUrl (the URL), eventName (string), maxSpeakers (number, default 200). It should auto-detect speaker cards using CSS class patterns and structural heuristics. Extract: first name, last name, full name, job title, company name, photo URL, bio, session topic, speaker URL, LinkedIn URL. Handle pagination (Load More buttons, numbered pages, infinite scroll). Use PlaywrightCrawler from Crawlee. Split names properly handling prefixes (Dr., Prof.) and suffixes (Jr., PhD, MBA)."

## Auto-Detection: The Selector Cascade

The killer feature of this scraper is that it works on most conference sites without customization. Here's how.

Instead of hardcoding `div.speaker-card` (which only works on one site), we try multiple detection strategies in order:

### Tier 1: Class Name Patterns

```typescript
const CARD_SELECTORS = [
    '[class*="speaker" i]',
    '[class*="person" i]',
    '[class*="presenter" i]',
    '[class*="panelist" i]',
    '[class*="attendee" i]',
    '[class*="ListItem" i]',
    '[class*="list-item" i]',
    '[class*="team-member" i]',
    '[class*="profile" i]',
    '[itemtype*="Person"]',
];
```

The `[class*="speaker" i]` selector matches any element whose class contains the word "speaker" (case-insensitive). Most conference sites use predictable class names like `speaker-card`, `speakerItem`, `speaker-list-item`.

We try each selector and pick the first one that finds 3+ elements.

### Tier 2: Grid/Flex Heuristic

If no class names match, we look for layout patterns:

```typescript
// Find containers with 5+ children that have images
// (a grid of people cards almost always contains images)
const containers = await page.$$('div, section, ul');
for (const container of containers) {
    const children = await container.$$(':scope > *');
    if (children.length < 5) continue;

    // Check if children have images
    let withImages = 0;
    for (const child of children.slice(0, 5)) {
        const img = await child.$('img');
        if (img) withImages++;
    }
    if (withImages >= 3) {
        // This container is likely a speaker grid
        return ':scope > *';  // Use its direct children as cards
    }
}
```

The logic: a grid of people cards will be a container with many children, most of which contain images (headshots). This catches sites that use custom or minified class names.

### Tier 3: Structural Heuristic

Last resort — look for the HTML pattern of a person card:

```typescript
const STRUCTURAL_SELECTORS = [
    'article:has(img):has(:is(h2,h3,h4))',
    'div:has(img):has(:is(h2,h3,h4))',
    'li:has(img):has(:is(h2,h3,h4))',
];
```

A person card almost always has:
- An image (headshot)
- A heading (name)

An element with both an `<img>` and an `<h2/h3/h4>` is very likely a person card, regardless of class names.

## Extracting Speaker Data

Once we've found the cards, we extract fields:

```typescript
async function extractSpeakerData(card: ElementHandle, eventName: string) {
    // Name — usually in a heading
    const nameEl = await card.$('h2, h3, h4, [class*="name" i]');
    const fullName = nameEl
        ? (await nameEl.textContent())?.trim() ?? ''
        : '';

    if (!fullName) return null;

    // Job title — look for common patterns
    const titleEl = await card.$(
        '[class*="title" i], [class*="position" i], [class*="role" i], ' +
        '[class*="designation" i], [class*="subtitle" i]'
    );
    const jobTitle = titleEl
        ? (await titleEl.textContent())?.trim() ?? ''
        : '';

    // Company — sometimes separate, sometimes in the title
    const companyEl = await card.$(
        '[class*="company" i], [class*="organization" i], [class*="org" i], ' +
        '[class*="affiliation" i]'
    );
    const companyName = companyEl
        ? (await companyEl.textContent())?.trim() ?? ''
        : '';

    // Photo
    const imgEl = await card.$('img');
    const photoUrl = imgEl
        ? (await imgEl.getAttribute('src')) ?? ''
        : '';

    // Bio
    const bioEl = await card.$(
        '[class*="bio" i], [class*="description" i], [class*="about" i], p'
    );
    const bio = bioEl
        ? (await bioEl.textContent())?.trim() ?? ''
        : '';

    // Speaker detail page link
    const linkEl = await card.$('a[href]');
    const speakerUrl = linkEl
        ? (await linkEl.getAttribute('href')) ?? ''
        : '';

    // Split name
    const { firstName, lastName } = splitName(fullName);

    return {
        first_name: firstName,
        last_name: lastName,
        full_name: fullName,
        job_title: jobTitle,
        company_name: companyName,
        event_name: eventName,
        photo_url: photoUrl,
        bio: bio,
        speaker_url: speakerUrl,
    };
}
```

**Key pattern:** For every field, we try multiple CSS selectors with `[class*="keyword" i]`. This catches most naming conventions (`speaker-title`, `speakerTitle`, `SpeakerTitleComponent`, etc.).

## Name Splitting

This sounds simple until you encounter real names:

- "Dr. Jean-Pierre Dubois III"
- "Prof. María García de López"
- "Sarah O'Connor, PhD"
- "Rev. Dr. Martin Luther King Jr."

Here's the utility:

```typescript
const PREFIXES = new Set([
    'dr', 'prof', 'professor', 'mr', 'mrs', 'ms', 'miss',
    'sir', 'dame', 'hon', 'rev', 'reverend', 'fr', 'father',
]);

const SUFFIXES = new Set([
    'jr', 'sr', 'ii', 'iii', 'iv', 'v',
    'phd', 'md', 'esq', 'cpa', 'mba', 'dds', 'rn',
]);

export function splitName(full: string): { firstName: string; lastName: string } {
    if (!full) return { firstName: '', lastName: '' };

    // Remove commas and periods for processing
    let cleaned = full.replace(/,/g, ' ').trim();
    const parts = cleaned.split(/\s+/);

    // Strip prefixes from front
    while (parts.length > 1) {
        const candidate = parts[0].replace(/\./g, '').toLowerCase();
        if (PREFIXES.has(candidate)) {
            parts.shift();
        } else {
            break;
        }
    }

    // Strip suffixes from back
    while (parts.length > 1) {
        const candidate = parts[parts.length - 1].replace(/\./g, '').toLowerCase();
        if (SUFFIXES.has(candidate)) {
            parts.pop();
        } else {
            break;
        }
    }

    if (parts.length === 1) {
        return { firstName: parts[0], lastName: '' };
    }

    const firstName = parts[0];
    const lastName = parts.slice(1).join(' ');
    return { firstName, lastName };
}
```

"Dr. Jean-Pierre Dubois III" → strip "Dr." prefix → strip "III" suffix → first: "Jean-Pierre", last: "Dubois"

## Handling Cookie Banners

Almost every conference website has a cookie consent popup. If you don't dismiss it, it can block your scraper from interacting with the page.

```typescript
async function dismissCookieBanner(page: Page): Promise<void> {
    const buttonTexts = [
        'Accept', 'Accept All', 'Accept Cookies',
        'I Accept', 'I Agree', 'Agree',
        'Got it', 'OK', 'Allow All',
        'Continue', 'Close',
    ];

    for (const text of buttonTexts) {
        const btn = page.locator(`button:has-text("${text}")`).first();
        try {
            if (await btn.isVisible({ timeout: 500 })) {
                await btn.click();
                await page.waitForTimeout(500);
                return;
            }
        } catch {
            // Button not found, try next
        }
    }
}
```

Call this right after `page.waitForLoadState('networkidle')` and before you start extracting data.

## Three Pagination Strategies

Conference sites use different pagination approaches. Our scraper detects and handles all three:

### Load More Button

```typescript
async function handleLoadMore(page: Page): Promise<boolean> {
    const loadMoreTexts = [
        'Load More', 'Show More', 'View More',
        'See More', 'Load more speakers',
    ];

    for (const text of loadMoreTexts) {
        const btn = page.locator(`button:has-text("${text}")`).first();
        if (await btn.isVisible({ timeout: 1000 })) {
            await btn.click();
            await page.waitForTimeout(2000);
            return true;
        }
    }
    return false;
}
```

### Numbered Pages

```typescript
async function handleNumberedPages(page: Page): Promise<boolean> {
    // Find current page indicator
    const active = page.locator(
        '.pagination .active, [aria-current="page"], .current-page'
    ).first();

    if (await active.count() === 0) return false;

    const currentText = await active.textContent();
    const currentNum = parseInt(currentText ?? '0', 10);

    // Click next number
    const nextLink = page.locator(
        `.pagination a:has-text("${currentNum + 1}")`
    ).first();

    if (await nextLink.count() > 0) {
        await nextLink.click();
        await page.waitForLoadState('networkidle', { timeout: 10000 });
        return true;
    }

    return false;
}
```

### Infinite Scroll

```typescript
async function handleInfiniteScroll(page: Page): Promise<boolean> {
    const heightBefore = await page.evaluate(() => document.body.scrollHeight);

    await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
    await page.waitForTimeout(2000);

    const heightAfter = await page.evaluate(() => document.body.scrollHeight);

    // If page height increased, new content was loaded
    return heightAfter > heightBefore;
}
```

The main loop tries each strategy:

```typescript
let consecutiveEmpty = 0;

while (totalPushed < maxSpeakers && consecutiveEmpty < 3) {
    // Extract cards from current page state
    const cards = await page.$$(cardSelector);
    // ... process cards ...

    // Try pagination
    const loaded = await handleLoadMore(page)
        || await handleNumberedPages(page)
        || await handleInfiniteScroll(page);

    if (!loaded) {
        consecutiveEmpty++;
    } else {
        consecutiveEmpty = 0;
    }
}
```

## URL Resolution

Conference sites often use relative URLs for speaker pages and images:

```typescript
function resolveUrl(relative: string, baseUrl: string): string {
    if (!relative) return '';
    if (relative.startsWith('http')) return relative;
    if (relative.startsWith('//')) return 'https:' + relative;

    try {
        return new URL(relative, baseUrl).href;
    } catch {
        return relative;
    }
}
```

Always resolve URLs before saving them. A relative URL like `/speakers/jane-doe` is useless without the domain.

## Deduplication

Speakers might appear on multiple pages or in multiple sections:

```typescript
const seenNames = new Set<string>();

// Inside the extraction loop:
const key = record.full_name.toLowerCase();
if (seenNames.has(key)) continue;
seenNames.add(key);
```

Simple, effective. Keyed by lowercase full name.

## Proxy Configuration

When running locally, you don't need a proxy. When running on Apify's cloud, you might. Here's the pattern:

```typescript
// Only use proxy on Apify platform, not locally
const proxyConfig = process.env.APIFY_IS_AT_HOME
    ? { useApifyProxy: true }
    : undefined;

const crawler = new PlaywrightCrawler({
    proxyConfiguration: proxyConfig
        ? await Actor.createProxyConfiguration(proxyConfig)
        : undefined,
    // ...
});
```

`APIFY_IS_AT_HOME` is set automatically when your actor runs in Apify's cloud. This prevents proxy errors when developing locally.

## The Crawler Setup

Putting it all together:

```typescript
const crawler = new PlaywrightCrawler({
    launchContext: {
        launchOptions: { headless: true },
    },
    navigationTimeoutSecs: 60,
    requestHandlerTimeoutSecs: 300,  // 5 min for slow pagination
    maxRequestsPerCrawl: 1,          // We handle pagination manually
    async requestHandler({ page, log }) {
        // Wait for content to render
        await page.waitForLoadState('networkidle', { timeout: 15_000 });

        // Handle cookie banners
        await dismissCookieBanner(page);

        // Auto-detect card selector
        const cardSelector = await detectCards(page);
        if (!cardSelector) {
            log.error('Could not detect speaker cards');
            return;
        }

        log.info(`Detected card selector: ${cardSelector}`);

        // Extract and paginate
        // ... main loop from above ...
    },
});

await crawler.run([input.speakersUrl]);
```

**`maxRequestsPerCrawl: 1`** — This is important. We don't want Crawlee to follow links. We handle pagination ourselves because conference sites use client-side pagination (Load More, infinite scroll) that doesn't change the URL.

**`requestHandlerTimeoutSecs: 300`** — Five minutes. Some conference sites have hundreds of speakers and slow Load More buttons. You need patience.

## Real Mistakes We Made

**Mistake 1: Trusting class names**
The first version hardcoded `div.speaker-card`. Worked on one site, broke on every other. The auto-detection cascade was born from frustration — we tested on 8 different conference sites and every one used different class names.

**Mistake 2: Not waiting for `networkidle`**
SPA sites don't render immediately. The first version extracted data as soon as the page loaded, getting zero results. `networkidle` waits until all AJAX calls finish — that's when the data is actually in the DOM.

**Mistake 3: Cookie banners blocking clicks**
On one site, the Load More button was behind a cookie banner. Our click hit the banner instead of the button. Adding `dismissCookieBanner()` as the first step after page load fixed it.

**Mistake 4: Name splitting edge cases**
"María García de López" was splitting into first: "María", last: "García". The "de López" part got lost. We fixed this by making `lastName = parts.slice(1).join(' ')` — everything after the first name is the last name.

---

## Next Up

You've now handled the three hardest scraping patterns: tables, APIs, and JS-rendered SPAs. In [Lesson 05: Government Data](./05-government-data.md), we'll tackle the easiest pattern of all — government agencies that literally hand you the data as downloadable files.

## What you just learned
- Test with `curl` first — if it returns empty HTML, you need Playwright
- Auto-detection beats hardcoded selectors: class patterns → grid heuristics → structural fallbacks
- Dismiss cookie banners before scraping or they'll block your interactions
- Three pagination types: Load More buttons, numbered pages, infinite scroll
- Name splitting: strip prefixes (Dr., Prof.) and suffixes (Jr., PhD) from both ends
- Resolve relative URLs with `new URL(relative, baseUrl).href`
- Only use proxy on Apify platform (`process.env.APIFY_IS_AT_HOME`)
- Set `maxRequestsPerCrawl: 1` when handling pagination manually
