#!/usr/bin/env python3
"""
Check an Upwork cover letter hook against Upwork's ~230-char preview cutoff.

Usage:
  python3 check_hook_length.py "Hi Ronald. I created a custom Loom video for your X project: https://www.loom.com/share/abc123"
  pbpaste | python3 check_hook_length.py
"""
import re
import sys

PRE_LINK_TARGET = 170
PREVIEW_TARGET = 230

URL_RE = re.compile(r"https?://\S+")


def main():
    text = sys.argv[1] if len(sys.argv) > 1 else sys.stdin.read()
    text = text.strip()
    if not text:
        sys.exit("ERROR: no hook text provided (arg or stdin).")

    m = URL_RE.search(text)
    if not m:
        sys.exit("ERROR: no URL found in the hook. The Loom link must be in the first line.")

    pre_link = len(text[: m.start()])
    through_link = m.end()

    print(f"Chars before link: {pre_link} (target < {PRE_LINK_TARGET})")
    print(f"Chars through end of link: {through_link} (target < {PREVIEW_TARGET})")

    ok = True
    if pre_link >= PRE_LINK_TARGET:
        print("FAIL: too much text before the link, it will push the URL out of the preview.")
        ok = False
    if through_link >= PREVIEW_TARGET:
        print("FAIL: link does not fully fit inside Upwork's ~230-char preview window.")
        ok = False
    if ok:
        print("PASS: hook fits inside the preview with the full link visible.")


if __name__ == "__main__":
    main()
