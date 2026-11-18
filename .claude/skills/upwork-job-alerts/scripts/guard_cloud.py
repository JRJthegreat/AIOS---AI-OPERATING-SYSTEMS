#!/usr/bin/env python3
"""
PreToolUse hook for the CLOUD upwork-job-alerts run (wired in the repo's .claude/settings.json with
matcher "mcp__.*", because claude.ai connector tool names differ from the local ones).

Only enforces inside a cloud session (CLAUDE_CODE_REMOTE set); Jude's local interactive sessions and
the local launchd run (which loads its own headless_settings.json) are untouched.

In the cloud it allows exactly:
  - Upwork read tools: find_jobs, find_saved_jobs, get_tool_help
  - Upwork save_job, through guard_save's rules (action=save, job in this run's candidates.json)
  - Gmail send_message, through guard_email's rules (recipient pinned by sha256)
and blocks every other MCP tool (no Upwork sends, proposals, unsaves; no other Gmail actions; no other
connectors). Fails closed (exit 2) on anything unexpected.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import guard_email  # noqa: E402
import guard_save  # noqa: E402

UPWORK_READ = {"find_jobs", "find_saved_jobs", "get_tool_help"}


def check(event) -> list:
    name = str(event.get("tool_name", ""))
    parts = name.split("__")
    if len(parts) < 3 or parts[0] != "mcp":
        return []  # not an MCP tool: out of scope for this guard
    server, tool = "__".join(parts[1:-1]).lower(), parts[-1]
    if "upwork" in server:
        if tool in UPWORK_READ:
            return []
        if tool == "save_job":
            return guard_save.check(event)
        return [f"Upwork tool {tool} is not allowed in the job-alerts run"]
    if "gmail" in server:
        if tool == "send_message":
            return guard_email.check(event)
        return [f"Gmail tool {tool} is not allowed in the job-alerts run"]
    return [f"connector {server} is not allowed in the job-alerts run"]


def main() -> None:
    if not os.environ.get("CLAUDE_CODE_REMOTE"):
        sys.exit(0)
    try:
        problems = check(json.load(sys.stdin))
    except Exception as exc:
        problems = [f"guard error: {type(exc).__name__}: {exc}"]
    if problems:
        print("Blocked by upwork-job-alerts cloud guard: " + "; ".join(problems), file=sys.stderr)
        sys.exit(2)
    sys.exit(0)


if __name__ == "__main__":
    main()
