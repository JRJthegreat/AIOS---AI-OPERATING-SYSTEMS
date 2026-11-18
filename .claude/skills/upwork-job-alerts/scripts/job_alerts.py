#!/usr/bin/env python3
"""
upwork-job-alerts: deterministic half of the sweep. Python 3.9, stdlib only (runs in a cloud VM too).

Claude runs the Upwork searches and judges fit; this script owns everything that must not drift:
the freshness window, the country allowlist, the hourly floor, the proposal cap, dedupe, the email
HTML, and the recipient pin.

  job_alerts.py start                       clear last run's scratch, print the lanes + window
  job_alerts.py filter [--window-min 40]    merge .tmp/upwork_job_alerts/raw/*.json -> candidates.json
  job_alerts.py digest --to ADDRESS         picks.json + candidates.json -> digest.json (email payload)
  job_alerts.py error --to ADDRESS "msg"    digest.json for a failed run (Upwork unreachable, etc.)
  job_alerts.py record                      add this run's picks to seen.json (local runs only)
  job_alerts.py wait SECONDS                sleep (max 60) after a find_jobs rate-limit error

Scratch dir: .tmp/upwork_job_alerts/ under the repo root (CLAUDE_PROJECT_DIR or CWD).
"""

import argparse
import glob
import hashlib
import html
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG = json.load(open(os.path.join(SKILL_DIR, "config.json")))


def root() -> str:
    return os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()


def work(*parts) -> str:
    return os.path.join(root(), ".tmp", "upwork_job_alerts", *parts)


def now() -> datetime:
    return datetime.now(timezone.utc)


def parse_ts(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError:
        return None


def load(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def save(path, data) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


# ---------- recipient pin (the address itself never lives in the public repo) ----------

def recipient_ok(addr: str) -> bool:
    digest = hashlib.sha256(addr.strip().lower().encode()).hexdigest()
    return digest in CONFIG["notify_email_sha256"]


# ---------- rules ----------

def country_ok(country):
    """True (allowlist) / False (blocklist) / None (missing or unrecognised: kept, flagged for Claude)."""
    if not country:
        return None
    c = str(country).strip().lower()
    if c in {x.lower() for x in CONFIG["country_allow"]}:
        return True
    if c in {x.lower() for x in CONFIG["country_block"]}:
        return False
    return None


def hourly_max(budget: str):
    """'15.00–35.00/hr' -> 35.0; '20.00/hr' -> 20.0; fixed or missing -> None."""
    if not budget or "/hr" not in budget:
        return None
    nums = [float(n.replace(",", "")) for n in re.findall(r"[\d,]+(?:\.\d+)?", budget)]
    return max(nums) if nums else None


def blocked_title(title: str):
    t = (title or "").lower()
    for word in CONFIG["title_block"]:
        if word in t:
            return word
    return None


# ---------- commands ----------

def cmd_start(_args) -> None:
    for name in ("raw", ):
        for f in glob.glob(work(name, "*.json")):
            os.remove(f)
    for f in ("candidates.json", "picks.json", "digest.json"):
        p = work(f)
        if os.path.exists(p):
            os.remove(p)
    os.makedirs(work("raw"), exist_ok=True)
    cutoff = now() - timedelta(minutes=CONFIG["window_min"])
    print(f"WINDOW published after {cutoff.strftime('%Y-%m-%dT%H:%M:%SZ')} ({CONFIG['window_min']} min)")
    print("LANES " + json.dumps(CONFIG["lanes"], ensure_ascii=False))
    print(f"SCRATCH {work()}")


def cmd_filter(args) -> None:
    window = args.window_min or CONFIG["window_min"]
    cutoff = now() - timedelta(minutes=window)
    seen = set(load(work("seen.json"), {}).keys())
    jobs = {}
    for path in sorted(glob.glob(work("raw", "*.json"))):
        data = load(path, {})
        rows = data.get("jobs", data) if isinstance(data, dict) else data
        if not isinstance(rows, list):
            continue
        for j in rows:
            if isinstance(j, dict) and j.get("id"):
                jobs.setdefault(str(j["id"]), j)

    kept, dropped = [], {}

    def drop(reason):
        dropped[reason] = dropped.get(reason, 0) + 1

    for jid, j in jobs.items():
        pub = parse_ts(j.get("published_date") or j.get("created_date"))
        if pub is None or pub < cutoff:
            drop("outside window")
            continue
        if jid in seen:
            drop("already alerted")
            continue
        if j.get("applied"):
            drop("already applied")
            continue
        client = j.get("client") or {}
        cok = country_ok(client.get("country"))
        if cok is False:
            drop("country not on allowlist")
            continue
        hmax = hourly_max(j.get("budget") or "")
        if hmax is not None and hmax < CONFIG["hourly_floor"]:
            drop("hourly below floor")
            continue
        props = j.get("proposal_count")
        if isinstance(props, (int, float)) and props >= CONFIG["proposal_cap"]:
            drop("too many proposals")
            continue
        bt = blocked_title(j.get("title"))
        if bt:
            drop(f"off-lane title ({bt})")
            continue
        act = j.get("job_activity") or {}
        kept.append({
            "id": jid,
            "title": j.get("title"),
            "url": f"https://www.upwork.com/jobs/~02{jid}",
            "age_min": int((now() - pub).total_seconds() // 60),
            "country": client.get("country") or "unknown",
            "country_unverified": cok is None,
            "client_spent": client.get("total_spent") or "$0",
            "client_rating": client.get("rating"),
            "client_jobs_posted": client.get("total_posted_jobs"),
            "job_type": j.get("job_type"),
            "budget": j.get("budget") or "not posted",
            "proposals": props,
            "interviewing": act.get("invited_to_interview"),
            "hired": act.get("total_hired"),
            "skills": (j.get("skills") or [])[:8],
            "snippet": re.sub(r"</?untrusted_participant_content>", "", j.get("description_snippet") or "").strip(),
        })
    kept.sort(key=lambda r: r["age_min"])
    save(work("candidates.json"), kept)
    print(f"CANDIDATES {len(kept)} of {len(jobs)} unique jobs")
    for reason, n in sorted(dropped.items(), key=lambda x: -x[1]):
        print(f"  dropped {n}: {reason}")
    for r in kept:
        flag = " [country unverified]" if r["country_unverified"] else ""
        print(f"- {r['id']} | {r['age_min']}m | {r['country']}{flag} | {r['budget']} | "
              f"{r['proposals']} props | spent {r['client_spent']} | {r['title']}")


ROW = """<tr><td style="padding:14px 0;border-bottom:1px solid #e5e5e5">
<div style="font-size:16px;font-weight:600"><a href="{url}" style="color:#14a800;text-decoration:none">{title}</a>{niche}</div>
<div style="color:#555;font-size:13px;margin:4px 0">{facts}</div>
<div style="font-size:14px;margin:6px 0"><b>Why:</b> {why}</div>
<div style="font-size:14px;margin:6px 0"><b>Watch out:</b> {watch}</div>
{keyword}</td></tr>"""


def cmd_digest(args) -> None:
    if not recipient_ok(args.to):
        sys.exit("refusing: --to does not match the pinned notify address")
    cands = {c["id"]: c for c in load(work("candidates.json"), [])}
    picks = load(work("picks.json"), [])
    rows, plain = [], []
    for p in picks:
        c = cands.get(str(p.get("id")))
        if not c:
            print(f"skip pick {p.get('id')}: not in candidates.json", file=sys.stderr)
            continue
        e = html.escape
        facts = (f"{c['age_min']} min old · {c['country']} · {c['budget']} · "
                 f"{c['proposals']} proposals · client spent {c['client_spent']}"
                 + (f" · {p['connects']} Connects" if p.get("connects") else ""))
        kw = p.get("keyword")
        rows.append(ROW.format(
            url=e(c["url"]), title=e(c["title"] or ""),
            niche=' <span style="background:#fff3cd;padding:1px 6px;border-radius:4px;font-size:12px">'
                  + e(p["niche"]) + "</span>" if p.get("niche") else "",
            facts=e(facts), why=e(p.get("why", "")), watch=e(p.get("watch_out", "none")),
            keyword=f'<div style="font-size:14px;color:#b00"><b>Required keyword:</b> {e(kw)}</div>' if kw else "",
        ))
        plain.append(f"{c['title']}\n{c['url']}\n{facts}\nWhy: {p.get('why','')}\n"
                     f"Watch out: {p.get('watch_out','none')}" + (f"\nKeyword: {kw}" if kw else ""))
    if not rows:
        print("NO_DIGEST (no valid picks)")
        return
    top = cands[str(picks[0]["id"])]["title"] or ""
    subject = f"Upwork: {len(rows)} fresh job{'s' if len(rows) > 1 else ''} - {top[:60]}"
    body_html = ('<div style="font-family:Arial,sans-serif;max-width:640px">'
                 '<p style="font-size:14px;color:#555">Saved to your Upwork saved list. Ranked by fit, then freshness.</p>'
                 '<table style="width:100%;border-collapse:collapse">' + "".join(rows) + "</table></div>")
    save(work("digest.json"), {"to": args.to.strip(), "subject": subject,
                               "htmlBody": body_html, "body": "\n\n".join(plain)})
    print(f"DIGEST {len(rows)} jobs -> {work('digest.json')}")


def cmd_error(args) -> None:
    if not recipient_ok(args.to):
        sys.exit("refusing: --to does not match the pinned notify address")
    msg = args.message[:500]
    save(work("digest.json"), {
        "to": args.to.strip(), "subject": "Upwork job alerts: run FAILED",
        "htmlBody": f"<p>The job alert run could not complete:</p><p><b>{html.escape(msg)}</b></p>"
                    "<p>No jobs were saved or alerted this run.</p>",
        "body": f"The job alert run could not complete: {msg}"})
    print(f"ERROR_DIGEST -> {work('digest.json')}")


def cmd_wait(args) -> None:
    import time
    time.sleep(max(1, min(int(args.seconds), 60)))
    print(f"WAITED {args.seconds}s")


def cmd_record(_args) -> None:
    seen = load(work("seen.json"), {})
    stamp = now().strftime("%Y-%m-%dT%H:%M:%SZ")
    for p in load(work("picks.json"), []):
        seen[str(p.get("id"))] = stamp
    cutoff = now() - timedelta(days=3)
    seen = {k: v for k, v in seen.items() if (parse_ts(v) or now()) > cutoff}
    save(work("seen.json"), seen)
    print(f"SEEN {len(seen)}")


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("start")
    f = sub.add_parser("filter")
    f.add_argument("--window-min", type=int)
    d = sub.add_parser("digest")
    d.add_argument("--to", required=True)
    e = sub.add_parser("error")
    e.add_argument("--to", required=True)
    e.add_argument("message")
    sub.add_parser("record")
    w = sub.add_parser("wait")
    w.add_argument("seconds", type=int)
    args = ap.parse_args()
    {"start": cmd_start, "filter": cmd_filter, "digest": cmd_digest,
     "error": cmd_error, "record": cmd_record, "wait": cmd_wait}[args.cmd](args)


if __name__ == "__main__":
    main()
