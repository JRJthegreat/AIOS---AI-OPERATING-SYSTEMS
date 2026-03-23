# How We Built a £1M+ Lead Generation Pipeline in Under 60 Minutes — Live

**Author:** Saad Belcaid
**Date:** March 19, 2026
**Built with:** Claude Code (Claude Opus 4.6, 1M context)

---

## What Did We Actually Build?

A fully automated system that every single day:

1. Downloads public UK financial filings (from Companies House — the UK government database)
2. Finds companies making £1M+ profit (EBITDA)
3. Looks up who owns and runs each company — names, nationality, shareholding
4. Delivers a clean list of qualified leads — ready for outreach

**The output:** ~13 new leads per day, ~3,250 per year. Each lead includes the company name, financials, director names, owner names, address, and industry.

**Who is this for?** A referral partner who helps UK business owners with exits, acquisitions, or PE fundraising. Instead of manually hunting for companies, this pipeline delivers qualified leads to their inbox every morning.

**Total cost to run:** Essentially free. The Companies House API is free. Apify free tier covers the compute.

---

## The 5 Principles That Made This Build Work

### Principle 1: Start With the Data Source, Not the Code

Before writing a single line of code, we validated the entire pipeline manually:

- Can we actually get the data? → Yes, Companies House publishes free daily XBRL bulk files
- Does the data contain what we need? → Yes, financial accounts with turnover, profit, etc.
- How many leads does this realistically produce? → We parsed one day's file: 24,334 accounts, 471 with P&L, 13 qualifying at £1M+ EBITDA
- Is there an API to enrich the data? → Yes, free CH API gives directors, owners, SIC codes

**Lesson:** Most people start coding before they know if the data even exists. Validate the source first. If the data isn't there, no amount of code fixes that.

### Principle 2: Use a Detailed Plan, Not Vague Instructions

We didn't say "build me a lead gen tool." We gave Claude a precise, structured plan that included:

- Exact project structure (9 files, no more)
- Pipeline flow diagram showing every step
- Module responsibilities — what each file does and doesn't do
- Input/output schemas — exact fields, types, defaults
- Error handling table — every failure mode and what to do
- Implementation order — which file to build first and why

**Lesson:** Claude Code is extremely capable, but it's not a mind reader. The quality of your output is directly proportional to the quality of your plan. A 10-minute plan saves hours of back-and-forth.

### Principle 3: Pick the Right Tool for the Job (Even If It's Unconventional)

Every existing Apify actor in our stack is Node.js. This one is Python. Why?

- The only battle-tested XBRL parser (`stream-read-xbrl`) is Python-only
- It's maintained by UK Government / Department for Trade
- It handles all the nasty edge cases: iXBRL vs XBRL formats, namespace resolution, taxonomy quirks
- Building our own JS parser would be a correctness risk and a maintenance nightmare

**Lesson:** Don't force-fit a technology because "that's what we usually use." Pick what actually solves the problem. In this case, Python was the obviously correct choice even though it broke our convention.

### Principle 4: Test Incrementally, Not All at Once

We didn't write everything and then pray it works. The sequence was:

1. **Test the API key** — Simple curl request to verify authentication works
2. **Test each endpoint** — Company profile, officers, PSC — verified with known company numbers (Tesco for a PLC, a smaller company for PSC data)
3. **Deploy and watch logs** — Pushed to Apify and monitored the actual parsing + enrichment in real-time
4. **Verify error handling** — Watched it gracefully handle bad XML files and 502 server errors

**Lesson:** Each test gives you confidence to move to the next step. If we'd tested nothing until the end, a single typo could have cost 30 minutes of debugging.

### Principle 5: Design for Zero Maintenance

This pipeline runs daily with no human intervention. That means:

- **Deduplication built in:** A persistent store tracks every company we've ever surfaced. No duplicates, ever.
- **Graceful degradation:** Bad XBRL files get skipped (not crashed on). API 502 errors get retried then skipped. The company isn't marked as "seen" unless it's actually processed — so it'll be retried next run.
- **Weekend awareness:** Companies House doesn't publish on Sundays/Mondays. The actor detects this and exits cleanly instead of erroring.
- **Rate limiting baked in:** Token bucket algorithm stays under the 600 req/5min API limit automatically.

**Lesson:** "It works" and "it works every day for a year without anyone touching it" are two very different things. Design for the second one.

---

## The Actual Workflow — Step by Step

Here's exactly what happened during the build, in order. This is the playbook you can follow for your own projects.

### Step 1: Research Phase (Before Coding)

Before any code was written, we needed to understand the external dependency — the `stream-read-xbrl` Python library:

- What's the exact function signature?
- What columns does it return? (38 columns)
- How do you pass it a file? (It takes an iterable of bytes, not a file path)
- What are the gotchas? (Uses multiprocessing internally, needs `if __name__ == '__main__'` guard on Windows)

**Why this matters:** If we'd guessed the API wrong, we'd have to rewrite the core parsing module. 5 minutes of research saved potential hours.

### Step 2: Scaffold Everything at Once

We created all 9 files in rapid succession:

```
.actor/actor.json          — Tells Apify what this actor is
.actor/input_schema.json   — Defines the configuration form users see
.actor/Dockerfile          — How to build the container
requirements.txt           — Python dependencies
.gitignore                 — What not to commit
src/__init__.py            — Package marker (empty file)
src/__main__.py            — Entry point (4 lines)
src/pipeline.py            — Download + parse + filter
src/companies_house.py     — API client + enrichment
src/main.py                — Orchestrator that ties it all together
```

**Why this matters:** Creating the structure first means you can think about how modules connect before you're deep in implementation details.

### Step 3: Implement Bottom-Up

We built in dependency order — modules with no dependencies first:

1. **Config files** (.actor/, requirements.txt) — no code dependencies
2. **Entry point** (__init__.py, __main__.py) — trivial, just imports
3. **pipeline.py** — depends only on external library (stream-read-xbrl)
4. **companies_house.py** — depends only on httpx
5. **main.py** — orchestrator that imports pipeline.py and companies_house.py

**Why this matters:** Each module can theoretically be tested standalone. The orchestrator is the last thing written because it depends on everything else.

### Step 4: Syntax Check Before Deploy

Before pushing to Apify, we ran `python -m py_compile` on every file. All 5 Python files compiled cleanly.

**Why this matters:** Catching a syntax error locally takes 2 seconds. Catching it after a 3-minute Docker build wastes everyone's time.

### Step 5: API Verification

We tested the Companies House API key against three endpoints:

| Test | Company | Result |
|---|---|---|
| Company profile | Tesco (00445790) | 200 OK — name, SIC, address |
| Officers | Tesco | 74 officers returned |
| PSC | Tesco | 0 (expected — PLCs don't have individual 25%+ owners) |
| PSC | Small private company (10720904) | Individual owner with 75-100% shares |

**Why this matters:** We verified not just "does auth work" but "does each endpoint return the data structure we expect." The PSC test on a small company was critical — that's the actual use case.

### Step 6: Deploy and Monitor

Pushed to Apify with `apify push`, watched the build succeed, then ran it. Monitored logs in real-time:

- Saw XBRL parsing working (bad XML files skipped gracefully)
- Saw API enrichment running (profile + officers + PSC calls firing)
- Saw 502 error handled correctly (3 retries, then skip, move on)

---

## How to Talk to Claude Code Effectively

These are the interaction patterns that made this build fast and successful.

### Give It a Complete Plan Upfront

Don't drip-feed requirements. Give Claude the full picture:

- What you're building and why
- Exact file structure
- What each module does
- Input/output formats
- Error handling expectations
- Implementation order

The plan we used was ~200 lines. That's not excessive — that's thorough. Claude can consume and execute on a detailed plan much faster than it can guess what you want through 20 rounds of back-and-forth.

### Let It Research What It Doesn't Know

When Claude needed to understand the `stream-read-xbrl` API, we let it spawn a research agent to look up the exact function signatures, column names, and gotchas. This took ~30 seconds and gave it everything it needed to write correct code on the first try.

**Anti-pattern:** Telling Claude "just figure it out" and hoping it guesses the API correctly.

### Test Assertions, Not Vibes

When we got the API key, we didn't say "I think it works." We ran actual API calls against real endpoints and verified specific responses:

- Did we get HTTP 200?
- Does the response contain the fields we expect?
- Does PSC data show up for the right type of company?

### React to Logs, Don't Guess

When the actor started running, we watched the actual logs and discussed what we saw:

- "Bad XML" messages → Expected, handled correctly
- 502 errors → Expected, retry logic working
- Parse completion → Confirmed qualifying companies found

---

## The Tech Stack (For Reference)

| Component | What It Is | Why We Chose It |
|---|---|---|
| **Apify** | Cloud platform for running web scrapers and data pipelines | Scheduling, storage, monitoring — all built in. No servers to manage. |
| **Python 3.12** | Programming language | Only language with a battle-tested XBRL parser |
| **stream-read-xbrl** | UK Government XBRL parser | Handles all the nasty edge cases. Open source, actively maintained. |
| **httpx** | HTTP client | Modern async Python HTTP library. Supports streaming downloads. |
| **Companies House API** | Free UK government API | Company profiles, directors, owners. 600 requests per 5 minutes, no cost. |

---

## Key Numbers

| Metric | Value |
|---|---|
| Total files written | 9 |
| Lines of Python code | ~650 |
| Build time | Under 60 minutes (live) |
| Daily bulk file size | ~90 MB |
| Accounts parsed per day | ~24,000 |
| Accounts with P&L data | ~471 |
| Companies qualifying at £1M+ EBITDA | ~13 per day |
| Projected annual leads | ~3,250 |
| API cost | Free |
| Compute cost | Apify free tier |
| Maintenance required | Zero |

---

## Common Questions

**Q: What if Companies House changes their file format?**
A: The `stream-read-xbrl` library is maintained by UK Government (Department for Trade). They update it when formats change. We just run `pip install --upgrade` periodically.

**Q: What if we miss a day?**
A: Use the `bulkFileDate` parameter to backfill any missed date. Run it manually with yesterday's date and it'll process those filings.

**Q: What if a company appears multiple times?**
A: The deduplication store (`uk-ma-seen-companies`) tracks every company number we've ever surfaced. Once a company appears in our dataset, it will never appear again — even across months of runs.

**Q: Can I filter to specific industries?**
A: Yes. Use `targetSicCodes` for exact matches (e.g., `62012` = software companies) or `targetSicPrefixes` for broad sectors (e.g., `62` = all IT companies).

**Q: What does EBITDA mean?**
A: Earnings Before Interest, Taxes, Depreciation, and Amortization. It's a rough measure of how much cash profit a business generates. We estimate it conservatively as: operating profit + depreciation.

**Q: Is this legal?**
A: Yes. All data comes from Companies House, which is a public register. UK company accounts are public record. The API is free and intended for this type of use.

---

## What Makes This Different From Manual Research

| Manual Approach | This Pipeline |
|---|---|
| Browse Companies House website one company at a time | Processes all 24,000 daily filings automatically |
| Guess which companies are profitable | Calculates actual EBITDA from filed accounts |
| Look up directors manually | Fetches all directors and ownership data via API |
| Maintain a spreadsheet of contacted companies | Automatic deduplication — never surfaces the same company twice |
| Spend 2-3 hours per day researching | Runs in 10-15 minutes, zero human effort |
| Miss days when you're busy | Runs on a schedule, never misses a filing day |

---

*This pipeline was built live in under 60 minutes by Saad Belcaid using Claude Code. The entire interaction — from plan to deployed, running actor — demonstrates what's possible when you combine clear thinking with AI-assisted development.*
