#!/usr/bin/env python3
"""
PreToolUse hook for the unattended upwork-job-alerts run.

The only Upwork write this run may make is bookmarking a job. Allows mcp__upwork__upwork__save_job
only for action=save on Jude's freelancer org with a job_id that `job_alerts.py filter` put in
.tmp/upwork_job_alerts/candidates.json. No unsave, hide or unhide: Jude curates the list himself.

Fails closed: any parse error or unexpected shape blocks (exit 2). Only exit 0 allows.
"""

import json
import os
import sys

SKILL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ORG_UID = json.load(open(os.path.join(SKILL, "config.json")))["org_uid"]


def check(event) -> list:
    tool_input = event.get("tool_input") if isinstance(event, dict) else None
    if not isinstance(tool_input, dict):
        return ["tool_input is not an object"]
    problems = []
    if tool_input.get("action") != "save":
        problems.append(f"only action=save is allowed, got {tool_input.get('action')!r}")
    if tool_input.get("org_uid") != ORG_UID:
        problems.append("wrong org_uid")
    params = tool_input.get("params")
    if not isinstance(params, dict) or set(params) != {"job_id"}:
        problems.append("params must be exactly {job_id}")
        return problems
    root = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    with open(os.path.join(root, ".tmp", "upwork_job_alerts", "candidates.json")) as f:
        ids = {str(c.get("id")) for c in json.load(f)}
    if str(params["job_id"]) not in ids:
        problems.append(f"job_id {params['job_id']} is not in this run's candidates.json")
    return problems


def main() -> None:
    try:
        problems = check(json.load(sys.stdin))
    except Exception as exc:
        problems = [f"guard error: {type(exc).__name__}: {exc}"]
    if problems:
        print("Blocked by upwork-job-alerts save guard: " + "; ".join(problems), file=sys.stderr)
        sys.exit(2)
    sys.exit(0)


if __name__ == "__main__":
    main()
