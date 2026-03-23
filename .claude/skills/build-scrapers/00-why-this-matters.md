# Lesson 0: Why This Matters

## What you'll learn
- Why scrapers are the most underrated growth tool for non-technical founders
- The difference between data and signal (and why signal is what you sell)
- What you'll build in this course — 4 production scrapers, each teaching a different pattern
- How this connects to real revenue

## The Problem Every Founder Has

You're trying to sell something. You need to find the right companies at the right moment. So you do what everyone does — you buy a list, blast emails, and hope.

Here's why that doesn't work: **lists are static, but business is dynamic.**

The company that had a data breach last week needs security consulting *right now*. The startup that just posted 12 engineering jobs is scaling *right now*. The wealth management firm with $500M and 3 employees needs automation *right now*.

That's not on any list you can buy. That's a **signal** — and signals have a shelf life. By the time it's in a database you can purchase, 50 other people already called.

## Scrapers = Automated Signal Detection

A scraper isn't just a tool that pulls data from websites. It's a **deal flow tap** that you control.

Think about it:
- **Government websites** publish breach reports, regulatory filings, contract awards — all public, all free, all timestamped
- **Job boards** tell you exactly which companies are scaling, pivoting, or desperate to hire
- **Conference sites** tell you which executives are speaking where — that's intent data
- **SEC filings** tell you firm size, client type, compensation model — that's qualification data

The data is sitting there. Nobody's scraping it because most founders think scraping requires a CS degree.

It doesn't. Not anymore.

## The Real Product Isn't Data — It's Intelligence

Here's the key insight that separates this course from every scraping tutorial on YouTube:

**Other scrapers give you data. Yours will give you intelligence.**

When we built the HIPAA breach scraper, we didn't just pull company names and breach dates. We added:
- **Severity scoring** — combining scale (how many people affected) + recency (how recently it happened) + type (hacking vs. lost laptop)
- **The "why call today" signal** — "500K records breached 12 days ago via hacking incident. Currently under investigation."

When we built the wealth management scraper, we didn't just pull firm names and AUM. We added:
- **Opportunity signals** — "Sub-5 person team with $100M+ AUM — prime candidate for outsourced services"
- **Client focus classification** — retail, institutional, high-net-worth — so you know who they serve

That's the difference between a spreadsheet and a weapon.

## What You'll Build

This course has 4 scrapers, each teaching a different technical pattern:

| Lesson | Scraper | Pattern | Why This Pattern |
|--------|---------|---------|------------------|
| 02 | HIPAA Breaches | HTML table on government site | Simplest case — just read a table |
| 03 | LinkedIn Jobs | Hidden API, no browser needed | 10x faster than browser scraping |
| 04 | Conference Speakers | JavaScript-rendered SPA | When you need a real browser |
| 05 | SEC Wealth Management | CSV/ZIP download | When the government hands you the data |

Then in Lesson 06, you'll add enrichment (company size, domain) and scoring (severity, urgency, opportunity signals) to turn raw data into actionable intelligence.

Finally in Lesson 07, you'll deploy to Apify's cloud so your scrapers run on autopilot.

## No Coding Experience Needed

Here's the part that changes everything: **Claude Code writes the code for you.**

You describe what you want in plain English. Claude Code generates the project structure, the scraping logic, the error handling, the deployment files — everything.

Your job is to:
1. Know what data you want and where it lives
2. Tell Claude Code what to build
3. Test it locally
4. Deploy it

That's it. The technical skill you'll learn isn't programming — it's **prompting**. How to describe what you want precisely enough that the AI builds it right the first time.

## How This Feeds Into Revenue

Let's make this concrete. Here are three ways scraped signals turn into money:

**1. Direct outreach**
You scrape HIPAA breaches. You find a hospital that lost 200K records last week. You sell cybersecurity consulting. That's a warm lead with a ticking clock — they NEED you right now.

**2. Market intelligence**
You scrape SEC filings. You find 47 wealth management firms in Texas with $100M+ AUM and fewer than 5 employees. That's a market segment you can build an entire product around.

**3. Platform data**
You scrape conference speakers. You know who's speaking where, what their title is, what company they're at. That's relationship intelligence — the foundation of any connector business.

The scrapers are the tap. What you do with the water is up to you.

## What You'll Need

- A laptop (Mac, Windows, or Linux)
- ~30 minutes per lesson
- An Apify account (free tier is fine for learning)
- Willingness to experiment — some sites will fight back, and that's part of the fun

## Let's Go

Start with [Lesson 01: Setup](./01-setup.md) — you'll be running your first scraper in under 10 minutes.

## What you just learned

- Scrapers are automated signal detectors, not just data pullers
- The differentiator is intelligence (scoring, signals, context) — not raw data
- You'll build 4 scrapers across 4 different technical patterns
- Claude Code writes the code — your skill is knowing what to ask for
- This course requires zero coding experience
