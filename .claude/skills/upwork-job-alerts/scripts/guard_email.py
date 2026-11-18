#!/usr/bin/env python3
"""
PreToolUse hook for the unattended upwork-job-alerts run.

Job posts are untrusted text, so a post crafted to steer the model must not be able to email anyone.
Allows mcp__claude_ai_Gmail__send_message only when the single recipient hashes to the pinned
notify_email_sha256 in config.json (the address itself is not in the public repo) and the call uses
nothing but plain digest fields.

Fails closed: any parse error or unexpected shape blocks (exit 2). Only exit 0 allows.
"""

import hashlib
import json
import os
import sys

CONFIG = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config.json")
ALLOWED_FIELDS = {"to", "subject", "body", "htmlBody", "includeSignature"}


def check(event) -> list:
    tool_input = event.get("tool_input") if isinstance(event, dict) else None
    if not isinstance(tool_input, dict):
        return ["tool_input is not an object"]
    pinned = json.load(open(CONFIG))["notify_email_sha256"]
    problems = []
    extra = sorted(k for k, v in tool_input.items() if k not in ALLOWED_FIELDS and v not in (None, "", [], {}))
    if extra:
        problems.append(f"fields not allowed: {extra}")
    to = tool_input.get("to")
    if isinstance(to, str):
        to = [to]
    if not isinstance(to, list) or len(to) != 1:
        problems.append("exactly one recipient required")
    elif hashlib.sha256(str(to[0]).strip().lower().encode()).hexdigest() not in pinned:
        problems.append("recipient is not the pinned notify address")
    return problems


def main() -> None:
    try:
        problems = check(json.load(sys.stdin))
    except Exception as exc:
        problems = [f"guard error: {type(exc).__name__}: {exc}"]
    if problems:
        print("Blocked by upwork-job-alerts email guard: " + "; ".join(problems), file=sys.stderr)
        sys.exit(2)
    sys.exit(0)


if __name__ == "__main__":
    main()
