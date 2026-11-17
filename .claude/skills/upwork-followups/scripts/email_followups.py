#!/usr/bin/env python3
"""
Email follow-ups for leads whose conversation moved off Upwork to Gmail (e.g. a proposal sent by email
after a call). Runs unattended once a day at the lead's send time via run_email.sh.

Jude approves every message word for word up front: each lead carries a fixed `messages` sequence in the
private config. This script decides IF a follow-up is due and WHICH approved message goes next; the
model only reads the Gmail thread, sends exactly what `plan` queued, and emails Jude a digest.
guard_email_reply.py blocks any Gmail reply that is not the queued one.

Private config (outside the public repo): EMAIL_FOLLOWUPS_CONFIG or ~/.config/upwork-followups/email_leads.json
  {
    "self_emails": ["jude@ainexam.com"],
    "notify_email": "jude@ainexam.com",
    "timezone": "Asia/Taipei",
    "leads": [{
      "id": "acme", "name": "Pat", "email": "pat@example.com", "active": true,
      "thread_id": "...", "reply_to_message_id": "...",
      "anchor_at": "2026-11-16T12:05:39Z",      # any message from the lead after this = replied, stop
      "send_window": ["18:00", "23:59"],         # local time; on-demand runs outside it never send
      "daily_count": 7, "repeat_every_days": 7,  # messages[0..daily_count-1] daily, then the last one weekly
      "signature": "Best,\nJude\n...",
      "messages": ["...", "..."]
    }]
  }
State (sent count, replied flag): email_state.json next to the config. Guard ledger: email_send_ledger.json.

Commands (run from the repo root):
  leads                      print active leads' thread ids to read
  plan                       read .tmp/upwork_followups/email_threads.json, write email_send_queue.json
  mark-sent <lead> <msg_id>  record a send
  digest                     print TO / SUBJECT / BODY <path>, or NOTHING_TO_SEND
"""

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

CONFIG_PATH = os.environ.get("EMAIL_FOLLOWUPS_CONFIG") or os.path.expanduser(
    "~/.config/upwork-followups/email_leads.json")
STATE_PATH = os.path.join(os.path.dirname(CONFIG_PATH), "email_state.json")
WORK = os.path.join(os.getcwd(), ".tmp", "upwork_followups")
THREADS = os.path.join(WORK, "email_threads.json")
QUEUE = os.path.join(WORK, "email_send_queue.json")
EVENTS = os.path.join(WORK, "email_events.json")
DIGEST = os.path.join(WORK, "email_digest.txt")

DAILY_MIN_HOURS = 20          # daily phase: at least this long since Jude's last email in the thread
WEEKLY_SLACK_HOURS = 4        # weekly phase: repeat_every_days minus this


def load_json(path, default):
    if not os.path.exists(path):
        return default
    with open(path) as f:
        return json.load(f)


def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)


def parse_ts(s):
    s = str(s).strip()
    if s.isdigit():
        return datetime.fromtimestamp(int(s) / 1000, tz=timezone.utc)
    dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def now_utc():
    override = os.environ.get("EMAIL_FOLLOWUPS_NOW")  # tests only
    return parse_ts(override) if override else datetime.now(timezone.utc)


def body_for(lead, index):
    msgs = lead["messages"]
    text = msgs[min(index, len(msgs) - 1)].strip()
    sig = lead.get("signature", "").strip()
    return f"{text}\n\n{sig}" if sig else text


def in_window(lead, tz, now):
    start, end = lead.get("send_window", ["00:00", "23:59"])
    local = now.astimezone(ZoneInfo(tz)).strftime("%H:%M")
    return start <= local <= end


def active_leads(cfg, state):
    return [l for l in cfg.get("leads", []) if l.get("active") and not state.get(l["id"], {}).get("replied")]


def cmd_leads(cfg, state):
    for p in (QUEUE, EVENTS, DIGEST, THREADS):
        if os.path.exists(p):
            os.remove(p)
    leads = active_leads(cfg, state)
    if not leads:
        print("NO_ACTIVE_LEADS")
    for l in leads:
        print(f"LEAD {l['id']} thread_id={l['thread_id']}")


def cmd_plan(cfg, state):
    threads = load_json(THREADS, None)
    if not isinstance(threads, dict):
        sys.exit(f"missing or bad {THREADS}")
    selfs = {a.lower() for a in cfg.get("self_emails", [])}
    tz = cfg.get("timezone", "Asia/Taipei")
    now = now_utc()
    queue, events = {}, []
    for lead in active_leads(cfg, state):
        lid = lead["id"]
        st = state.setdefault(lid, {"sent_count": 0, "sent": []})
        msgs = threads.get(lid)
        if not isinstance(msgs, list) or not msgs:
            events.append({"lead": lid, "kind": "error", "text": "thread not read"})
            print(f"ERROR {lid}: thread not read")
            continue
        anchor = parse_ts(lead["anchor_at"])
        parsed = [(str(m.get("sender", "")).lower(), parse_ts(m["date"])) for m in msgs]
        their = [d for s, d in parsed if s not in selfs and d > anchor]
        if their:
            st["replied"] = True
            st["replied_at"] = max(their).isoformat()
            events.append({"lead": lid, "kind": "replied",
                           "text": f"{lead['name']} replied ({max(their).astimezone(ZoneInfo(tz)):%b %d %H:%M}). "
                                   "Email follow-ups for this lead are stopped; set active/replied to re-arm."})
            print(f"REPLIED {lid}")
            continue
        last_self = max((d for s, d in parsed if s in selfs), default=anchor)
        idx = st.get("sent_count", 0)
        gap = timedelta(hours=DAILY_MIN_HOURS) if idx < lead.get("daily_count", 7) else \
            timedelta(days=lead.get("repeat_every_days", 7)) - timedelta(hours=WEEKLY_SLACK_HOURS)
        if now - last_self < gap:
            print(f"NOT_DUE {lid}: next after {(last_self + gap).astimezone(ZoneInfo(tz)):%b %d %H:%M}")
            continue
        if not in_window(lead, tz, now):
            print(f"OUTSIDE_WINDOW {lid}: due, sends in the {lead.get('send_window')} run")
            continue
        queue[lid] = {"messageId": lead["reply_to_message_id"], "to": [lead["email"]],
                      "body": body_for(lead, idx), "index": idx}
        print(f"SEND {lid} message {idx + 1}")
    save_json(QUEUE, queue)
    save_json(EVENTS, events)
    save_json(STATE_PATH, state)


def cmd_mark_sent(cfg, state, lid, msg_id):
    queue = load_json(QUEUE, {})
    if lid not in queue:
        sys.exit(f"{lid} not in queue")
    st = state.setdefault(lid, {"sent_count": 0, "sent": []})
    st["sent_count"] = queue[lid]["index"] + 1
    st.setdefault("sent", []).append({"at": now_utc().isoformat(), "message_id": msg_id, "index": queue[lid]["index"]})
    save_json(STATE_PATH, state)
    events = load_json(EVENTS, [])
    lead = next(l for l in cfg["leads"] if l["id"] == lid)
    events.append({"lead": lid, "kind": "sent",
                   "text": f"Sent follow-up {st['sent_count']} to {lead['name']} ({lead['email']}):\n\n{queue[lid]['body']}"})
    save_json(EVENTS, events)
    print(f"MARKED {lid} sent_count={st['sent_count']}")


def cmd_digest(cfg, state):
    events = load_json(EVENTS, [])
    if not events:
        print("NOTHING_TO_SEND")
        return
    sent = sum(e["kind"] == "sent" for e in events)
    other = len(events) - sent
    subject = f"Email follow-ups: {sent} sent" + (f", {other} need you" if other else "")
    with open(DIGEST, "w") as f:
        f.write("\n\n----\n\n".join(e["text"] for e in events))
    print(f"TO {cfg['notify_email']}")
    print(f"SUBJECT {subject}")
    print(f"BODY {DIGEST}")


def main():
    cfg = load_json(CONFIG_PATH, None)
    if not cfg:
        sys.exit(f"no config at {CONFIG_PATH}")
    state = load_json(STATE_PATH, {})
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "leads":
        cmd_leads(cfg, state)
    elif cmd == "plan":
        cmd_plan(cfg, state)
    elif cmd == "mark-sent" and len(sys.argv) == 4:
        cmd_mark_sent(cfg, state, sys.argv[2], sys.argv[3])
    elif cmd == "digest":
        cmd_digest(cfg, state)
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
