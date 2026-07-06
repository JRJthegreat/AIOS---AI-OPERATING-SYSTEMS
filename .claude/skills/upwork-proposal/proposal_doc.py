#!/usr/bin/env python3
"""
Upwork proposal Google Doc driver.

Turns an authored HTML body into a native Google Doc, updates one in place,
exports the live doc (to review a client's hand-edits before re-uploading),
and dumps a case-study Google Sheet for the "Why me?" section.

House style is enforced automatically:
  - refuses to upload if an em dash (U+2014 or &mdash;) is present
  - injects the Bricolage Grotesque font onto bare block tags (no-ops on
    already-styled HTML, e.g. a Google export, so it is safe to re-upload)

Auth: token.json in the CWD (Drive + Sheets scope). No Docs API needed.
Run from the repo root. Generate token.json once with setup_google_auth.py.

Subcommands:
  create  --title T  --html FILE      create a new Google Doc, print URL + ID
  update  --id ID    --html FILE      replace a doc's content in place (URL unchanged)
  export  --id ID   [--html]          print the live doc as text (or HTML) to stdout
  sheet   --id ID                     print every tab of a Google Sheet (case studies)

Safe-edit workflow for a doc the client has been editing by hand:
  1) export --id ID --html > cur.html   (work off the LIVE doc, not your script)
  2) edit cur.html (insert/move sections; reuse the doc's own inline styles)
  3) update --id ID --html cur.html     (font no-ops, em-dash guard still runs)
"""
import argparse, re, sys
from googleapiclient.discovery import build
from googleapiclient.http import MediaInMemoryUpload
from google.oauth2.credentials import Credentials as UC

SCOPES = ["https://www.googleapis.com/auth/spreadsheets",
          "https://www.googleapis.com/auth/drive"]
FONT = "font-family:'Bricolage Grotesque',sans-serif"


def _creds():
    c = UC.from_authorized_user_file("token.json", SCOPES)
    if c.expired and c.refresh_token:
        from google.auth.transport.requests import Request
        c.refresh(Request())
    return c


def _drive():
    return build("drive", "v3", credentials=_creds())


def _prep(html):
    if "—" in html or "&mdash;" in html:
        sys.exit("ERROR: em dash found in body. Remove all em dashes (house rule) before upload.")
    # add the font to BARE block tags only; tags that already carry a
    # style="..." (e.g. from a Google HTML export) are left untouched.
    return re.sub(r"<(h1|h2|h3|p|li|td|th)>",
                  lambda m: '<%s style="%s">' % (m.group(1), FONT), html)


def cmd_create(a):
    html = _prep(open(a.html, encoding="utf-8").read())
    media = MediaInMemoryUpload(html.encode("utf-8"), mimetype="text/html", resumable=False)
    meta = {"name": a.title, "mimeType": "application/vnd.google-apps.document"}
    f = _drive().files().create(body=meta, media_body=media, fields="id,webViewLink").execute()
    print("URL:", f["webViewLink"])
    print("ID:", f["id"])


def cmd_update(a):
    html = _prep(open(a.html, encoding="utf-8").read())
    media = MediaInMemoryUpload(html.encode("utf-8"), mimetype="text/html", resumable=False)
    f = _drive().files().update(fileId=a.id, media_body=media, fields="id,webViewLink").execute()
    print("URL:", f["webViewLink"])


def cmd_export(a):
    mt = "text/html" if a.html else "text/plain"
    data = _drive().files().export(fileId=a.id, mimeType=mt).execute()
    sys.stdout.write(data.decode("utf-8"))


def cmd_sheet(a):
    svc = build("sheets", "v4", credentials=_creds())
    meta = svc.spreadsheets().get(spreadsheetId=a.id).execute()
    for s in meta.get("sheets", []):
        title = s["properties"]["title"]
        vals = svc.spreadsheets().values().get(spreadsheetId=a.id, range=title).execute().get("values", [])
        print("=== %s (%d rows) ===" % (title, len(vals)))
        for i, row in enumerate(vals):
            print(i, row)


def main():
    p = argparse.ArgumentParser(description="Upwork proposal Google Doc driver")
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("create"); c.add_argument("--title", required=True); c.add_argument("--html", required=True); c.set_defaults(fn=cmd_create)
    u = sub.add_parser("update"); u.add_argument("--id", required=True); u.add_argument("--html", required=True); u.set_defaults(fn=cmd_update)
    e = sub.add_parser("export"); e.add_argument("--id", required=True); e.add_argument("--html", action="store_true"); e.set_defaults(fn=cmd_export)
    s = sub.add_parser("sheet"); s.add_argument("--id", required=True); s.set_defaults(fn=cmd_sheet)
    a = p.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
