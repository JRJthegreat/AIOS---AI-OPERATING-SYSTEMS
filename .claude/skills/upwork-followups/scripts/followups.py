#!/usr/bin/env python3
"""
Deterministic half of the upwork-followups skill: the Google Sheet that holds follow-up state,
the cadence math (what is due when), and the email digest.

Claude does the judgment (reading Upwork threads, classifying the stage, drafting in Jude's voice).
This script never talks to Upwork and never sends email.

Run from the REPO ROOT (token.json is resolved relative to CWD).

  python3 .claude/skills/upwork-followups/scripts/followups.py init
  python3 .claude/skills/upwork-followups/scripts/followups.py read
  python3 .claude/skills/upwork-followups/scripts/followups.py plan
  python3 .claude/skills/upwork-followups/scripts/followups.py digest
  python3 .claude/skills/upwork-followups/scripts/followups.py upsert [--notified]

Files (WORK_DIR = .tmp/upwork_followups/):
  classified.json  written by Claude: rooms it refreshed this run (see SKILL.md for the schema)
  plan.json        written by `plan`: every tracked row with cadence fields computed
  drafts.json      written by Claude: {room_id: draft text} for rows `plan` lists as needing one
  digest.html / digest_subject.txt   written by `digest`

Private config (client names, Sheet id, email) lives OUTSIDE the public repo in CONFIG_PATH.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import sys
import warnings
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

warnings.filterwarnings("ignore")  # google-auth / urllib3 EOL noise on the system Python 3.9

WORK_DIR = os.path.join(".tmp", "upwork_followups")
CONFIG_PATH = os.path.expanduser("~/.config/upwork-followups/config.json")

DEFAULT_CONFIG = {
    "sheet_id": "",
    "notify_email": "",  # set in the private config; guard_email.py blocks every send without it
    "timezone": "Asia/Taipei",
    # Clients whose rooms are ignored completely (dead relationships).
    "exclude_clients": [],
    # Clients who only ever get "reply" items, never sales nudges.
    "reply_only_clients": [],
    # Days after the anchor message at which each nudge is due.
    "cadence_days": {"pre_call": [2, 5], "sow_sent": [1, 2, 4, 7, 10, 14], "post_call": [0]},
    # Past the last offset, keep nudging every N days until the client replies (Jude's rule,
    # Nov 13 2026: never let a lead go quiet). Only a reply, a "no", or Mute ends it.
    "repeat_every_days": {"pre_call": 7, "sow_sent": 7},
    # Hours before a booked call that the reminder fires.
    "call_reminder_hours": 12,
    # Closed rows older than this many days are dropped from the Sheet.
    "prune_closed_after_days": 30,
}

COLUMNS = [
    "Due", "Action", "Client", "Company", "Job", "Stage", "Nudges sent", "Draft", "Room link",
    "Client last msg", "Your last msg", "Note", "Status", "Mute",
    "room_id", "link", "anchor_at", "meeting_at", "last_client_msg_at", "last_self_msg_at",
    "last_story_id", "next_due", "due_key", "notified_key", "draft_key", "updated_at",
]

STAGES = {"invite", "client_waiting", "pre_call", "call_booked", "post_call", "sow_sent",
          "active_contract", "closed", "excluded"}

SHEET_SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]


# ---------- config / io ----------

def load_config() -> dict:
    cfg = dict(DEFAULT_CONFIG)
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH) as f:
            cfg.update(json.load(f))
    return cfg


def save_config(cfg: dict) -> None:
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2)


def work_path(name: str) -> str:
    os.makedirs(WORK_DIR, exist_ok=True)
    return os.path.join(WORK_DIR, name)


def read_json(path: str, default):
    if not os.path.exists(path):
        return default
    with open(path) as f:
        return json.load(f)


def write_json(path: str, data) -> None:
    with open(path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


# ---------- time ----------

def now_utc() -> datetime:
    override = os.environ.get("FOLLOWUPS_NOW")  # tests only
    if override:
        return parse_ts(override)
    return datetime.now(timezone.utc)


def parse_ts(value) -> datetime | None:
    if value in (None, ""):
        return None
    s = str(value).strip()
    if s.isdigit():  # Upwork lastActivity is epoch millis
        return datetime.fromtimestamp(int(s) / 1000, tz=timezone.utc)
    s = s.replace("Z", "+00:00")
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def iso(dt: datetime | None) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if dt else ""


def local_str(dt: datetime | None, tz: str) -> str:
    return dt.astimezone(ZoneInfo(tz)).strftime("%b %d, %H:%M") if dt else ""


# ---------- cadence ----------

def matches(name: str, patterns) -> bool:
    n = (name or "").lower()
    return any(p.lower() in n for p in patterns if p)


def compute(row: dict, cfg: dict, now: datetime) -> dict:
    """Fill next_due / action / status / due_key for one row. Pure function of the row + config."""
    r = dict(row)
    stage = r.get("stage") or "closed"
    if stage not in STAGES:
        raise ValueError(f"unknown stage {stage!r} for room {r.get('room_id')}")
    who = f"{r.get('client', '')} {r.get('company', '')}"
    nudges = int(r.get("nudges_sent") or 0)
    anchor = parse_ts(r.get("anchor_at"))
    due, action, key = None, "", ""

    if matches(who, cfg["exclude_clients"]):
        stage = "excluded"
    elif stage not in ("client_waiting", "invite") and matches(who, cfg["reply_only_clients"]):
        stage = "active_contract" if stage != "closed" else stage

    if stage == "call_booked":
        meeting = parse_ts(r.get("meeting_at"))
        if meeting and meeting <= now - timedelta(hours=2):
            # The call is over and nothing new arrived in the room (a sent SOW would have changed the
            # room and been reclassified), so the next step is the SOW.
            stage, anchor, nudges = "post_call", meeting, 0

    if stage == "invite":
        due, action, key = anchor or now, "Respond to invite", f"invite:{r.get('room_id')}"
    elif stage == "client_waiting":
        due = parse_ts(r.get("last_client_msg_at")) or now
        # Keyed on the client's message time, not the room's latest story: system events after the
        # client's message must not re-notify the same unanswered message.
        action, key = "Reply now (client is waiting)", f"reply:{iso(due)}"
    elif stage == "call_booked":
        meeting = parse_ts(r.get("meeting_at"))
        if meeting:
            due = meeting - timedelta(hours=int(cfg["call_reminder_hours"]))
            action, key = f"Call at {local_str(meeting, cfg['timezone'])}", f"call:{iso(meeting)}"
    elif stage in ("pre_call", "sow_sent", "post_call"):
        offsets = cfg["cadence_days"][stage]
        if stage == "post_call":
            nudges = 0  # a "great talking" message after the call is not the SOW; stay due until it's sent
        repeat = int(cfg.get("repeat_every_days", {}).get(stage) or 0)
        if anchor and nudges < len(offsets):
            due = anchor + timedelta(days=offsets[nudges])
        elif anchor and repeat:
            due = anchor + timedelta(days=offsets[-1] + repeat * (nudges - len(offsets) + 1))
        if due:
            if stage == "post_call":
                action = "Send the SOW"
            elif nudges >= len(offsets):
                action = f"Follow-up {nudges + 1}: still on the cards?"
            elif stage == "pre_call" and nudges == 0:
                action = "Follow-up 1: add value"
            elif stage == "pre_call":
                action = "Follow-up 2: yes/no check"
            else:
                action = f"SOW follow-up {nudges + 1}"
            key = f"{stage}:{iso(anchor)}:{nudges}"
        else:
            stage = "closed" if anchor else stage

    muted = bool(str(r.get("mute") or "").strip())
    r["stage"] = stage
    r["next_due"] = iso(due)
    r["action"] = action
    r["due_key"] = key
    r["due_now"] = bool(due and due <= now and not muted)
    r["notify"] = bool(r["due_now"] and key and r.get("notified_key") != key)
    if muted:
        r["status"] = "Muted"
    elif not due:
        r["status"] = "Closed" if stage in ("closed", "excluded") else "No action"
    else:
        r["status"] = "Due" if r["due_now"] else "Waiting"
    return r


# ---------- sheet ----------

def sheet_client():
    import gspread
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request

    if not os.path.exists("token.json"):
        sys.exit("token.json not found: run from the repo root (see CLAUDE.md, Google OAuth).")
    creds = Credentials.from_authorized_user_file("token.json", SHEET_SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return gspread.authorize(creds)


def open_ws(cfg: dict):
    if not cfg.get("sheet_id"):
        sys.exit(f"No sheet_id in {CONFIG_PATH}: run `followups.py init` first.")
    return sheet_client().open_by_key(cfg["sheet_id"]).sheet1


def sheet_rows(cfg: dict) -> list:
    rows = []
    values = open_ws(cfg).get_all_values()
    header = values[0] if values else []
    for raw in values[1:]:
        rec = {c: "" for c in COLUMNS}
        rec.update({h: v for h, v in zip(header, raw) if h})
        if not rec.get("room_id"):
            continue
        rows.append({
            "room_id": rec["room_id"], "link": rec["link"], "client": rec["Client"], "company": rec["Company"],
            "job": rec["Job"], "stage": rec["Stage"], "nudges_sent": rec["Nudges sent"] or 0,
            "draft": rec["Draft"], "note": rec["Note"], "mute": rec["Mute"],
            "anchor_at": rec["anchor_at"], "meeting_at": rec["meeting_at"],
            "last_client_msg_at": rec["last_client_msg_at"], "last_self_msg_at": rec["last_self_msg_at"],
            "last_story_id": rec["last_story_id"], "notified_key": rec["notified_key"],
            "draft_key": rec["draft_key"], "updated_at": rec["updated_at"],
        })
    return rows


def room_url(room_id: str) -> str:
    return f"https://www.upwork.com/ab/messages/rooms/{room_id}" if room_id.startswith("room_") else ""


def gspread_col(n: int) -> str:
    out = ""
    while n:
        n, rem = divmod(n - 1, 26)
        out = chr(65 + rem) + out
    return out


def link_for(r: dict) -> str:
    link = str(r.get("link") or "")
    if not link.startswith("https://www.upwork.com/"):
        link = ""  # client-derived text: never let it become a non-Upwork link in the digest
    return link or room_url(str(r.get("room_id", "")))


def to_sheet_row(r: dict, tz: str) -> list:
    vals = {
        "Due": local_str(parse_ts(r.get("next_due")), tz), "Action": r.get("action", ""),
        "Client": r.get("client", ""), "Company": r.get("company", ""), "Job": r.get("job", ""),
        "Stage": r.get("stage", ""), "Nudges sent": r.get("nudges_sent", 0), "Draft": r.get("draft", ""),
        "Room link": link_for(r),
        "Client last msg": local_str(parse_ts(r.get("last_client_msg_at")), tz),
        "Your last msg": local_str(parse_ts(r.get("last_self_msg_at")), tz),
        "Note": r.get("note", ""), "Status": r.get("status", ""), "Mute": r.get("mute", ""),
    }
    for k in ("room_id", "link", "anchor_at", "meeting_at", "last_client_msg_at", "last_self_msg_at",
              "last_story_id", "next_due", "due_key", "notified_key", "draft_key", "updated_at"):
        vals[k] = r.get(k, "")
    return [vals[c] for c in COLUMNS]


def format_sheet(ws) -> None:
    widths = {"Due": 110, "Action": 230, "Client": 140, "Company": 160, "Job": 220, "Draft": 420,
              "Room link": 160, "Note": 260}
    requests = [
        {"updateDimensionProperties": {
            "range": {"sheetId": ws.id, "dimension": "ROWS", "startIndex": 0},
            "properties": {"pixelSize": 18}, "fields": "pixelSize"}},
        {"updateSheetProperties": {
            "properties": {"sheetId": ws.id, "gridProperties": {"frozenRowCount": 1}},
            "fields": "gridProperties.frozenRowCount"}},
        {"repeatCell": {
            "range": {"sheetId": ws.id, "startRowIndex": 0, "endRowIndex": 1},
            "cell": {"userEnteredFormat": {"textFormat": {"bold": True}}},
            "fields": "userEnteredFormat.textFormat.bold"}},
        {"repeatCell": {
            "range": {"sheetId": ws.id, "startRowIndex": 1},
            "cell": {"userEnteredFormat": {"wrapStrategy": "CLIP", "verticalAlignment": "TOP"}},
            "fields": "userEnteredFormat.wrapStrategy,userEnteredFormat.verticalAlignment"}},
    ]
    for name, px in widths.items():
        i = COLUMNS.index(name)
        requests.append({"updateDimensionProperties": {
            "range": {"sheetId": ws.id, "dimension": "COLUMNS", "startIndex": i, "endIndex": i + 1},
            "properties": {"pixelSize": px}, "fields": "pixelSize"}})
    first_hidden = COLUMNS.index("room_id")
    requests.append({"updateDimensionProperties": {
        "range": {"sheetId": ws.id, "dimension": "COLUMNS", "startIndex": first_hidden, "endIndex": len(COLUMNS)},
        "properties": {"hiddenByUser": True}, "fields": "hiddenByUser"}})
    ws.spreadsheet.batch_update({"requests": requests})


# ---------- commands ----------

def cmd_init(args) -> None:
    cfg = load_config()
    if cfg.get("sheet_id") and not args.force:
        print(f"Already initialised: https://docs.google.com/spreadsheets/d/{cfg['sheet_id']}")
        return
    sh = sheet_client().create("Upwork Follow-ups")
    ws = sh.sheet1
    ws.update(values=[COLUMNS], range_name="A1")
    format_sheet(ws)
    cfg["sheet_id"] = sh.id
    save_config(cfg)
    print(f"Created: https://docs.google.com/spreadsheets/d/{sh.id}")
    print(f"Config: {CONFIG_PATH}")


RUN_FILES = ("classified.json", "plan.json", "drafts.json", "digest.html", "digest_subject.txt")


def cmd_read(args) -> None:
    cfg = load_config()
    for name in RUN_FILES:
        if os.path.exists(work_path(name)):
            os.remove(work_path(name))
    rows = sheet_rows(cfg)
    write_json(work_path("state.json"), rows)
    # Compact view for Claude: what it needs to decide which rooms to re-read.
    for r in rows:
        print(json.dumps({k: r[k] for k in ("room_id", "client", "stage", "nudges_sent", "last_story_id",
                                            "anchor_at", "mute")}, ensure_ascii=False))
    print(f"# {len(rows)} tracked rows; full state in {work_path('state.json')}")


def cmd_plan(args) -> None:
    cfg = load_config()
    now = now_utc()
    existing = {r["room_id"]: r for r in read_json(work_path("state.json"), [])}
    classified = read_json(work_path("classified.json"), [])
    pending_invites = {c.get("room_id") for c in classified if c.get("stage") == "invite"}
    merged = dict(existing)
    for rid, row in existing.items():
        if row.get("stage") == "invite" and rid not in pending_invites:
            merged[rid] = {**row, "stage": "closed", "note": (row.get("note") or "") + " (invite answered or expired)"}
    for c in classified:
        if not c.get("room_id"):
            sys.exit(f"classified.json row missing room_id: {c}")
        prev = existing.get(c["room_id"], {})
        row = {**prev, **c}
        # Keep Jude's manual Mute and the notified marker across refreshes.
        row["mute"] = prev.get("mute", "")
        row["notified_key"] = prev.get("notified_key", "")
        row["updated_at"] = iso(now)
        merged[c["room_id"]] = row

    plan, needs_draft = [], []
    prune_before = now - timedelta(days=int(cfg["prune_closed_after_days"]))
    for row in merged.values():
        try:
            r = compute(row, cfg, now)
        except (ValueError, TypeError, KeyError) as exc:
            print(f"WARNING skipped bad row {row.get('room_id')}: {exc}")
            r = {**row, "status": "Error", "note": f"bad row: {exc}", "due_now": False, "notify": False,
                 "next_due": "", "due_key": "", "action": ""}
            plan.append(r)
            continue
        if r.get("draft_key") != r["due_key"]:
            r["draft"] = ""  # written for an earlier due point (or a different message): stale
        updated = parse_ts(r.get("updated_at")) or now
        if r["status"] in ("Closed", "No action") and updated < prune_before:
            continue
        plan.append(r)
        if r["due_now"] and not r.get("draft") and r["stage"] in ("client_waiting", "pre_call", "sow_sent"):
            needs_draft.append(r["room_id"])
    plan.sort(key=lambda r: (r["status"] not in ("Due",), r["next_due"] or "9999", r.get("client", "")))
    write_json(work_path("plan.json"), plan)
    due = [r for r in plan if r["due_now"]]
    print(f"{len(plan)} rows, {len(due)} due now, {sum(r['notify'] for r in plan)} to notify")
    print("NEEDS_DRAFT " + json.dumps(needs_draft))


def _drafts() -> dict:
    return read_json(work_path("drafts.json"), {})


def cmd_digest(args) -> None:
    cfg = load_config()
    tz = cfg["timezone"]
    now = now_utc()
    plan = read_json(work_path("plan.json"), [])
    drafts = _drafts()
    notify = [r for r in plan if r["notify"]]
    if not notify:
        for p in ("digest.html", "digest_subject.txt"):
            if os.path.exists(work_path(p)):
                os.remove(work_path(p))
        print("NOTHING_TO_SEND")
        return
    soon = [r for r in plan if not r["due_now"] and r["next_due"] and r["status"] == "Waiting"
            and parse_ts(r["next_due"]) <= now + timedelta(days=2)]

    groups = [
        ("Reply now", [r for r in notify if r["stage"] == "client_waiting"]),
        ("Invites", [r for r in notify if r["stage"] == "invite"]),
        ("Calls", [r for r in notify if r["stage"] == "call_booked"]),
        ("Send the SOW", [r for r in notify if r["stage"] == "post_call"]),
        ("Follow-ups due", [r for r in notify if r["stage"] in ("pre_call", "sow_sent")]),
    ]
    def e(value) -> str:
        return html.escape("" if value is None else str(value))

    parts = ['<div style="font-family:Arial,sans-serif;font-size:14px;color:#222;max-width:680px">']
    for title, rows in groups:
        if not rows:
            continue
        parts.append(f'<h3 style="margin:18px 0 6px">{e(title)} ({len(rows)})</h3>')
        for r in rows:
            draft = drafts.get(r["room_id"]) or r.get("draft") or ""
            who = e(r.get("client", "")) + (f" &middot; {e(r['company'])}" if r.get("company") else "")
            parts.append('<div style="border-left:3px solid #2b6cb0;padding:6px 10px;margin:8px 0">')
            parts.append(f"<b>{who}</b><br>{e(r['action'])}"
                         + (f" &middot; {e(r['job'])}" if r.get("job") else ""))
            if r.get("note"):
                parts.append(f'<br><span style="color:#666">{e(r["note"])}</span>')
            if draft:
                parts.append('<pre style="white-space:pre-wrap;font-family:inherit;background:#f5f7fa;'
                             f'padding:8px;margin:6px 0">{e(draft)}</pre>')
            parts.append(f'<a href="{e(link_for(r))}">Open in Upwork</a></div>')
    if soon:
        parts.append('<h3 style="margin:18px 0 6px">Coming up (next 2 days)</h3><ul>')
        for r in soon:
            parts.append(f"<li>{e(local_str(parse_ts(r['next_due']), tz))}: {e(r.get('client', ''))}, "
                         f"{e(r['action'])}</li>")
        parts.append("</ul>")
    sheet = f"https://docs.google.com/spreadsheets/d/{cfg['sheet_id']}" if cfg.get("sheet_id") else ""
    if sheet:
        parts.append(f'<p style="color:#666">Full queue: <a href="{sheet}">Upwork Follow-ups sheet</a>. '
                     "Type anything in a row's Mute column to silence it.</p>")
    parts.append("</div>")

    counts = []
    for title, rows in groups:
        if rows:
            counts.append(f"{len(rows)} {title.lower()}")
    subject = "Upwork follow-ups: " + ", ".join(counts)
    with open(work_path("digest.html"), "w") as f:
        f.write("\n".join(parts))
    with open(work_path("digest_subject.txt"), "w") as f:
        f.write(subject)
    print(f"TO {cfg['notify_email']}")
    print(f"SUBJECT {subject}")
    print(f"HTML {work_path('digest.html')}")


def cmd_upsert(args) -> None:
    cfg = load_config()
    tz = cfg["timezone"]
    plan = read_json(work_path("plan.json"), [])
    drafts = _drafts()
    live_mute = {r["room_id"]: r["mute"] for r in sheet_rows(cfg)}  # Jude may have muted mid-run
    for r in plan:
        if r["room_id"] in live_mute:
            r["mute"] = live_mute[r["room_id"]]
        if drafts.get(r["room_id"]):
            r["draft"] = drafts[r["room_id"]]
            r["draft_key"] = r["due_key"]
        if args.notified and r["notify"]:
            r["notified_key"] = r["due_key"]
            r["notify"] = False
    ws = open_ws(cfg)
    values = [COLUMNS] + [to_sheet_row(r, tz) for r in plan]
    ws.update(values=values, range_name="A1", value_input_option="RAW")
    if ws.row_count > len(values):  # trim rows left over from a longer previous write
        ws.batch_clear([f"A{len(values) + 1}:{gspread_col(len(COLUMNS))}{ws.row_count}"])
    format_sheet(ws)
    write_json(work_path("plan.json"), plan)
    print(f"Sheet updated: {len(plan)} rows (notified marked: {bool(args.notified)})")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("init"); p.add_argument("--force", action="store_true"); p.set_defaults(fn=cmd_init)
    sub.add_parser("read").set_defaults(fn=cmd_read)
    sub.add_parser("plan").set_defaults(fn=cmd_plan)
    sub.add_parser("digest").set_defaults(fn=cmd_digest)
    p = sub.add_parser("upsert"); p.add_argument("--notified", action="store_true"); p.set_defaults(fn=cmd_upsert)
    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
