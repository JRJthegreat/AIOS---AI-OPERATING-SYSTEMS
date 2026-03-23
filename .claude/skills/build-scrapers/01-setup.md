# Lesson 1: Setup

## What you'll learn
- How to install everything you need (Node.js, Apify CLI, Claude Code)
- How to create your first project folder
- The "magic prompt" — how to tell Claude Code exactly what you want
- How to run a scraper locally and see the results

## What you'll build
A working development environment. By the end of this lesson, you'll run `apify run` and see data come out.

---

## Step 1: Install Node.js

Node.js is the engine that runs your scrapers. You need version 22.

**Mac:**
```bash
brew install node@22
```

**Windows:**
Download from [nodejs.org](https://nodejs.org/) — pick the LTS version (22.x).

**Linux:**
```bash
curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
sudo apt-get install -y nodejs
```

Verify it works:
```bash
node --version
# Should show v22.x.x
```

## Step 2: Install Apify CLI

Apify is the platform that runs your scrapers in the cloud. The CLI lets you develop and test locally.

```bash
npm install -g apify-cli
```

Verify:
```bash
apify --version
```

Create an Apify account at [apify.com](https://apify.com) if you don't have one. The free tier gives you enough compute to learn.

Log in:
```bash
apify login
```

It'll ask for your API token — find it at [apify.com/account#/integrations](https://console.apify.com/account#/integrations).

## Step 3: Install Claude Code

Claude Code is the AI that writes your scraper code. It runs in your terminal and can read, write, and edit files.

```bash
npm install -g @anthropic-ai/claude-code
```

You'll need an Anthropic API key. Get one at [console.anthropic.com](https://console.anthropic.com/).

Start Claude Code:
```bash
claude
```

That's it. You're now talking to an AI that can write production code.

## Step 4: Create Your First Project

Let's create a folder for your scrapers:

```bash
mkdir my-scrapers
cd my-scrapers
```

This is where all your scraper projects will live. Each scraper gets its own subfolder.

## Step 5: The Magic Prompt

Here's the most important thing in this course: **how you talk to Claude Code determines what you get.**

Bad prompt:
> "Make me a scraper"

Good prompt:
> "Build me an Apify actor in TypeScript that scrapes https://ocrportal.hhs.gov/ocr/breach/breach_report.jsf and extracts company name, state, individuals affected, breach date, breach type, and location from the table. Use Playwright for browser automation. Include pagination to get all rows."

The good prompt has:
1. **What** — "Build me an Apify actor"
2. **Language** — "in TypeScript"
3. **Where** — the exact URL
4. **Fields** — exactly what data you want
5. **How** — "Use Playwright" (tells it the scraping approach)
6. **Scope** — "Include pagination to get all rows"

That's the formula: **What + Language + URL + Fields + How + Scope.**

Here's another example:

> "Build me an Apify actor in TypeScript that uses LinkedIn's guest jobs API at https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search to extract job title, company name, location, date posted, and salary. Parse the HTML response with string matching (no Cheerio). Include pagination by incrementing the start parameter by 25."

Same formula, different scraper.

## Step 6: Your First Run

Let's test with the simplest possible scraper. In your Claude Code session:

> "Create a new Apify actor project in a folder called 'test-scraper'. It should fetch https://news.ycombinator.com and extract the title and URL of each story on the front page. Use fetch, no browser needed. TypeScript."

Claude Code will create:
```
test-scraper/
  .actor/
    actor.json          # Apify metadata
    input_schema.json   # Input configuration
  src/
    main.ts             # Your scraping logic
  package.json          # Dependencies
  tsconfig.json         # TypeScript config
  Dockerfile            # For cloud deployment
  .dockerignore
```

Now run it:
```bash
cd test-scraper
npm install
apify run
```

Check the results:
```bash
cat storage/datasets/default/*.json
```

You should see a JSON file with Hacker News titles and URLs. That's your first scrape.

## Understanding the Project Structure

Every Apify actor you build will have this same structure. Here's what each file does:

**`src/main.ts`** — This is your scraper. It's the only file you really need to understand. The pattern is always:

```typescript
import { Actor } from 'apify';

await Actor.init();

const input = await Actor.getInput();  // Read configuration

// ... your scraping logic here ...

await Actor.pushData(results);  // Save results to dataset

await Actor.exit();
```

**`.actor/actor.json`** — Tells Apify what your actor is:
```json
{
    "actorSpecification": 1,
    "name": "my-scraper",
    "title": "My Scraper",
    "version": "1.0",
    "buildTag": "latest",
    "input": "./input_schema.json",
    "dockerfile": "../Dockerfile"
}
```

**`.actor/input_schema.json`** — Defines what inputs your scraper accepts (URLs, filters, API keys, etc.)

**`Dockerfile`** — Instructions for building your scraper in the cloud. You rarely need to touch this.

**`package.json`** — Lists your dependencies. The key ones:
- `apify` — The Apify SDK
- `playwright` — Browser automation (only if you need it)
- `crawlee` — Apify's crawling framework (optional but helpful)

## The Local Development Loop

This is your workflow for every scraper:

```
1. Describe what you want to Claude Code
2. Claude Code generates the files
3. npm install
4. apify run
5. Check storage/datasets/default/
6. Not right? Tell Claude Code what's wrong
7. Repeat 4-6 until it works
8. apify push (deploy to cloud)
```

Steps 4-6 are where you'll spend most of your time. The first version rarely works perfectly — that's normal. The skill is knowing what to tell Claude Code to fix.

## Common First-Run Issues

**"Cannot find module"**
```bash
npm install
```
You forgot to install dependencies.

**"APIFY_TOKEN is not set"**
```bash
apify login
```
You need to log in first.

**Empty dataset**
The scraper ran but found nothing. Check the URL — is it correct? Does it require JavaScript to render? (If yes, you need Playwright — we'll cover that in Lesson 04.)

**"page is not defined"**
You're using Playwright code but didn't set up a browser. Either add Playwright to your dependencies or switch to `fetch` (if the site doesn't need JavaScript).

---

## Next Up

You're ready to build real scrapers. In [Lesson 02: Your First Scraper](./02-first-scraper.md), we'll scrape a government website with HTML tables — the simplest pattern and a gold mine of signal data.

## What you just learned
- Node.js 22, Apify CLI, and Claude Code — that's the full stack
- The magic prompt formula: What + Language + URL + Fields + How + Scope
- Every Apify actor has the same structure: `Actor.init()` → scrape → `Actor.pushData()` → `Actor.exit()`
- The development loop: describe → generate → run → check → fix → repeat
- `apify run` executes locally, results land in `storage/datasets/default/`
