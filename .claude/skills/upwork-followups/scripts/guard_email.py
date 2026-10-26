#!/usr/bin/env python3
"""
PreToolUse hook for the unattended upwork-followups run (wired in headless_settings.json).

The run reads untrusted client messages, so a message crafted to steer the model must not be able
to email anyone else. This blocks mcp__claude_ai_Gmail__send_message unless the ONLY recipient is
the configured notify_email and the call uses nothing but plain digest fields.

Fails closed: any parse error, unexpected shape or unknown field blocks (exit 2). Only exit 0 allows.
"""

import json
import os
import sys

CONFIG_PATH = os.path.expanduser("~/.config/upwork-followups/config.json")
ALLOWED_FIELDS = {"to", "subject", "body", "htmlBody", "includeSignature"}


def check(event) -> list:
    tool_input = event.get("tool_input") if isinstance(event, dict) else None
    if not isinstance(tool_input, dict):
        return ["tool_input is not an object"]
    with open(CONFIG_PATH) as f:
        cfg = json.load(f)
    allowed = cfg.get("notify_email") if isinstance(cfg, dict) else None
    if not isinstance(allowed, str) or "@" not in allowed:
        return [f"no valid notify_email in {CONFIG_PATH}"]
    allowed = allowed.strip().lower()

    problems = []
    extra = sorted(k for k, v in tool_input.items() if k not in ALLOWED_FIELDS and v not in (None, "", [], {}))
    if extra:
        problems.append(f"fields not allowed: {extra}")
    to = tool_input.get("to")
    if isinstance(to, str):
        to = [to]
    if not isinstance(to, list) or [str(a).strip().lower() for a in to] != [allowed]:
        problems.append(f"recipient must be exactly [{allowed}], got {tool_input.get('to')!r}")
    return problems


def main() -> None:
    try:
        problems = check(json.load(sys.stdin))
    except Exception as exc:  # fail closed on anything unexpected
        problems = [f"guard error: {type(exc).__name__}: {exc}"]
    if problems:
        print("Blocked by upwork-followups email guard: " + "; ".join(problems), file=sys.stderr)
        sys.exit(2)
    sys.exit(0)


if __name__ == "__main__":
    main()
