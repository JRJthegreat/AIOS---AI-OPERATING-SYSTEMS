#!/usr/bin/env python3
"""
PreToolUse hook for the unattended upwork-followups run (wired in headless_settings.json).

The run reads untrusted client messages and is allowed to send on Upwork, so the model alone must
not decide what goes out. This allows mcp__upwork__upwork__send_message only when:
  - action is "send" on Jude's freelancer org, with nothing but room_id + message,
  - room_id is in .tmp/upwork_followups/send_queue.json (written by `followups.py queue`),
  - message is exactly the queued text,
  - the room has not already been sent to by this guard in the last 20 hours (ledger).
On allow it records the room in the ledger before the call runs, so a retry can't double-send.

Fails closed: any parse error or unexpected shape blocks (exit 2). Only exit 0 allows.
"""

import json
import os
import sys
import time

ORG_UID = "1318336437461753857"
LEDGER_HOURS = 20


def work_dir() -> str:
    root = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    return os.path.join(root, ".tmp", "upwork_followups")


def check(event) -> list:
    tool_input = event.get("tool_input") if isinstance(event, dict) else None
    if not isinstance(tool_input, dict):
        return ["tool_input is not an object"]
    problems = []
    if tool_input.get("action") != "send":
        problems.append(f"only action=send is allowed, got {tool_input.get('action')!r}")
    if tool_input.get("org_uid") != ORG_UID:
        problems.append("wrong org_uid")
    extra = sorted(k for k in tool_input if k not in ("action", "org_uid", "params"))
    if extra:
        problems.append(f"fields not allowed: {extra}")
    params = tool_input.get("params")
    if not isinstance(params, dict):
        return problems + ["params is not an object"]
    extra = sorted(k for k, v in params.items() if k not in ("room_id", "message") and v not in (None, "", [], {}))
    if extra:
        problems.append(f"params not allowed: {extra}")
    room, message = params.get("room_id"), params.get("message")

    with open(os.path.join(work_dir(), "send_queue.json")) as f:
        queue = json.load(f)
    item = queue.get(room) if isinstance(queue, dict) else None
    if not isinstance(item, dict):
        return problems + [f"room {room!r} is not in send_queue.json"]
    if message != item.get("message"):
        problems.append("message differs from the queued draft")

    ledger_path = os.path.join(work_dir(), "send_ledger.json")
    ledger = {}
    if os.path.exists(ledger_path):
        with open(ledger_path) as f:
            ledger = json.load(f)
    last = ledger.get(room)
    if isinstance(last, (int, float)) and time.time() - last < LEDGER_HOURS * 3600:
        problems.append(f"room already sent to in the last {LEDGER_HOURS} hours")
    if not problems:
        ledger[room] = time.time()
        with open(ledger_path, "w") as f:
            json.dump(ledger, f)
    return problems


def main() -> None:
    try:
        problems = check(json.load(sys.stdin))
    except Exception as exc:  # fail closed on anything unexpected
        problems = [f"guard error: {type(exc).__name__}: {exc}"]
    if problems:
        print("Blocked by upwork-followups send guard: " + "; ".join(problems), file=sys.stderr)
        sys.exit(2)
    sys.exit(0)


if __name__ == "__main__":
    main()
