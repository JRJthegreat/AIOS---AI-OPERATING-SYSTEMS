import json
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

with open('token.json') as f:
    token_data = json.load(f)
creds = Credentials.from_authorized_user_file('token.json', token_data.get('scopes', []))
if creds.expired and creds.refresh_token:
    creds.refresh(Request())
sheets = build('sheets', 'v4', credentials=creds)

with open('.tmp/proposals_retry.json') as f:
    jobs = [j for j in json.load(f) if j.get('cover_letter')]

def row(j):
    s = j.get('skills', [])
    if isinstance(s, list): s = ', '.join(s[:5])
    c = j.get('client', {})
    return [j.get('title',''), j.get('url',''), j.get('budget',''), j.get('experience_level',''), s,
            j.get('category',''), c.get('country','') if isinstance(c,dict) else '',
            f"${c.get('total_spent',0):,.0f}" if isinstance(c,dict) else '',
            c.get('total_hires',0) if isinstance(c,dict) else '', j.get('connects_cost',''),
            'Yes' if j.get('is_featured') else 'No', j.get('rank_score',''),
            j.get('tier',1), j.get('source','direct'), j.get('apply_link',''),
            j.get('cover_letter',''), j.get('proposal_doc','')]

sheets.spreadsheets().values().append(
    spreadsheetId='11lFodM6A7CwDhdbag0rfCd1rNfwopOggxYLjN10qTQY',
    range='Jobs!A1', valueInputOption='RAW', insertDataOption='INSERT_ROWS',
    body={'values': [row(j) for j in jobs]}
).execute()
print(f'Appended {len(jobs)} rows to original sheet')
