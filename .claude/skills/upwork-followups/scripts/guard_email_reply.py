#!/usr/bin/env python3
"""
PreToolUse hook for the unattended email follow-up run (wired in headless_settings.json, matcher
mcp__claude_ai_Gmail__reply).

Allows a Gmail reply only when it is exactly a follow-up `email_followups.py plan` queued:
  - nothing but messageId, to, body (no cc/bcc/html/attachments/replyAll),
  - messageId + to + body match one entry of .tmp/upwork_followups/email_send_queue.json verbatim,
  - that lead has not been sent to by this guard in the last 20 hours (ledger next to the config).
Records the send in the ledger before the call runs, so a retry can't double-send.
Fails closed: any parse error or unexpected shape blocks (exit 2). Only exit 0 allows.
"""

import json
import os
import sys
import time

LEDGER_HOURS = 20
CONFIG_PATH = os.environ.get("EMAIL_FOLLOWUPS_CONFIG") or os.path.expanduser(
    "~/.config/upwork-followups/email_leads.json")
LEDGER = os.path.join(os.path.dirname(CONFIG_PATH), "email_send_ledger.json")


def check(event) -> list:
    ti = event.get("tool_input") if isinstance(event, dict) else None
    if not isinstance(ti, dict):
        return ["tool_input is not an object"]
    extra = sorted(k for k, v in ti.items() if k not in ("messageId", "to", "body") and v not in (None, "", [], {}, False))
    if extra:
        return [f"fields not allowed: {extra}"]
    root = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    with open(os.path.join(root, ".tmp", "upwork_followups", "email_send_queue.json")) as f:
        queue = json.load(f)
    to = ti.get("to")
    to = [to] if isinstance(to, str) else to
    match = None
    for lid, item in queue.items():
        if (ti.get("messageId") == item.get("messageId")
                and isinstance(to, list) and [a.strip().lower() for a in to] == [a.lower() for a in item["to"]]
                and ti.get("body") == item.get("body")):
            match = lid
    if not match:
        return ["reply does not match any queued follow-up (messageId, to and body must be verbatim)"]
    ledger = {}
    if os.path.exists(LEDGER):
        with open(LEDGER) as f:
            ledger = json.load(f)
    last = ledger.get(match)
    if isinstance(last, (int, float)) and time.time() - last < LEDGER_HOURS * 3600:
        return [f"{match} already sent to in the last {LEDGER_HOURS} hours"]
    ledger[match] = time.time()
    with open(LEDGER, "w") as f:
        json.dump(ledger, f)
    return []


def main() -> None:
    try:
        problems = check(json.load(sys.stdin))
    except Exception as exc:  # fail closed
        problems = [f"guard error: {type(exc).__name__}: {exc}"]
    if problems:
        print("Blocked by email follow-up guard: " + "; ".join(problems), file=sys.stderr)
        sys.exit(2)
    sys.exit(0)


if __name__ == "__main__":
    main()
