#!/usr/bin/env python3
"""
Pre-render lint for an authored proposal body HTML, so house-style bugs are caught
BEFORE a Google Doc round trip, not after (Aug 2026: a spacing bug where the header
metadata block and two intro paragraphs ran together with zero gap only got caught
when Jude saw the live doc; the fix belongs before render, not after).

Checks (all deterministic, no LLM call):
  1. No em dash (U+2014) or &mdash; anywhere.
  2. No bracketed placeholder like [X] anywhere (the LLM-JSON path emits these on
     purpose mid-generation, but none may survive into what gets rendered).
  3. No two consecutive bare <p>...</p><p>...</p> without a <p>&nbsp;</p> gap between
     them, UNLESS the second <p> immediately follows an <h1>/<h2>/<h3> (headings carry
     their own space-before/after from Google Docs' Heading style).
  4. Exactly one <h1> present (the doc title).
  5. Body length. Jude, Aug 2026: "nobody is gonna sit down and read eight pages of
     documents." Calibrated against three docs that actually won work: 538 words (the
     Paris boat operator, won a paid two-developer bake-off), 1,140 (the quotation
     follow-up system), 2,436 (the HubSpot build, the outlier). A 3,129-word draft got
     sent back. Under 1,200 is the target, over 1,800 fails unless you pass --allow-long.

Usage:
  python3 check_proposal_html.py .tmp/body.html [--allow-long]
Exit code 0 and "PASS" if clean; exit code 1 and a list of problems otherwise.
"""
import re
import sys
from pathlib import Path

EM_DASH_RE = re.compile(r"—|&mdash;")
PLACEHOLDER_RE = re.compile(r"\[[A-Za-z][^\]\n]{0,40}\]")
# strip the (often huge) base64 image payload before any text-based checks; use a
# non-bracket token so it can't itself trip the placeholder check below
IMG_DATA_RE = re.compile(r'(src="data:image/[a-zA-Z]+;base64,)[^"]+(")')
SIGNOFF_OPENERS = {"best,", "cheers,", "regards,", "sincerely,"}

# Length budget, in visible words (tags and base64 stripped). See the docstring for
# where these numbers come from.
WORDS_TARGET = 1200   # above this: warn, and say what to cut
WORDS_HARD = 1800     # above this: fail, unless --allow-long is passed


def visible_word_count(html):
    """Words a human actually reads: no tags, no base64 payload, no &nbsp; spacers."""
    text = strip_image_data(html)
    text = re.sub(r"<[^>]+>", " ", text)
    text = text.replace("&nbsp;", " ")
    return len(text.split())


def strip_image_data(html):
    return IMG_DATA_RE.sub(r"\1IMGDATA\2", html)


def _text_only(p_html):
    return re.sub(r"<[^>]+>", "", p_html).strip().lower()


def find_spacing_gaps(html):
    """Return a list of (index, snippet) for consecutive <p> tags with no gap.

    Exceptions (no gap required, matches known-good doc patterns): a <p> containing
    only an <img> immediately followed by its caption <p>; a sign-off opener like
    "Best," immediately followed by the name line.
    """
    problems = []
    tag_re = re.compile(
        r"<h[1-3][^>]*>.*?</h[1-3]>"
        r"|<p[^>]*>\s*(?:&nbsp;|<span[^>]*>\s*&nbsp;\s*</span>)\s*</p>"  # gap paragraph
        r"|<p[^>]*>.*?</p>",
        re.DOTALL,
    )
    prev_kind = None  # 'heading' | 'gap' | 'text_p' | 'image_p' | 'signoff_p'
    for m in tag_re.finditer(html):
        tok = m.group(0)
        if tok.startswith("<h"):
            kind = "heading"
        elif re.fullmatch(r"<p[^>]*>\s*(?:&nbsp;|<span[^>]*>\s*&nbsp;\s*</span>)\s*</p>", tok):
            kind = "gap"
        elif "<img" in tok:
            kind = "image_p"
        elif _text_only(tok) in SIGNOFF_OPENERS:
            kind = "signoff_p"
        else:
            kind = "text_p"

        needs_gap_before = kind in ("text_p",) and prev_kind in ("text_p", "image_p")
        # a caption right after an image, or a name right after a sign-off opener, is fine
        if kind == "text_p" and prev_kind in ("image_p", "signoff_p"):
            needs_gap_before = False
        if needs_gap_before:
            problems.append((m.start(), tok[:70]))
        prev_kind = kind
    return problems


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    allow_long = "--allow-long" in sys.argv
    if len(args) != 1:
        sys.exit("Usage: check_proposal_html.py <file.html> [--allow-long]")
    path = Path(args[0])
    html = path.read_text(encoding="utf-8")
    html_stripped = strip_image_data(html)

    problems = []

    if EM_DASH_RE.search(html_stripped):
        problems.append("Em dash (or &mdash;) found. House rule: no em dashes, ever.")

    placeholders = PLACEHOLDER_RE.findall(html_stripped)
    if placeholders:
        problems.append(f"Bracketed placeholder(s) found, must not survive to render: {placeholders[:5]}")

    gaps = find_spacing_gaps(html_stripped)
    if gaps:
        for idx, snippet in gaps:
            problems.append(f"Missing <p>&nbsp;</p> gap before paragraph at char {idx}: {snippet!r}")

    h1_count = len(re.findall(r"<h1[^>]*>", html_stripped))
    if h1_count == 0:
        problems.append("No <h1> title found. Every proposal doc needs one.")
    elif h1_count > 1:
        problems.append(f"Found {h1_count} <h1> tags, expected exactly 1.")

    words = visible_word_count(html)
    if words > WORDS_HARD and not allow_long:
        problems.append(
            f"Body is {words} words, over the {WORDS_HARD} hard limit. Nobody reads a "
            f"proposal this long. Cut it to one proof story instead of a case-study list, "
            f"one-sentence answers instead of paragraphs, and let the flowchart carry the "
            f"architecture. Pass --allow-long only if the JD genuinely demands this much."
        )

    if problems:
        print("FAIL:")
        for p in problems:
            print(" -", p)
        sys.exit(1)

    print("PASS: no em dashes, no bracketed placeholders, spacing consistent, one <h1>.")
    if words > WORDS_TARGET:
        print(
            f"WARNING: {words} words, over the {WORDS_TARGET}-word target. It will render "
            f"long. Trim unless the JD demands the extra length (a mandated question list, "
            f"for example)."
        )
    else:
        print(f"Length: {words} words, within the {WORDS_TARGET}-word target.")


if __name__ == "__main__":
    main()
