#!/usr/bin/env python3
"""
Generate personalized email variables for each company using Claude Haiku.

Reads Industries + Description columns from the Google Sheet, generates:
- Startup Type (e.g., "FinTech startups")
- Type of Talent (e.g., "tech talent")
- Type of Recruiters (e.g., "tech recruiters")

Writes results back to 3 new columns in the sheet.
"""

import os
import sys
import json
import argparse
import time
from dotenv import load_dotenv
import anthropic
import gspread
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

load_dotenv()

CHECKPOINT_FILE = '.tmp/email_variables_checkpoint.json'


def get_credentials():
    scopes = [
        'https://www.googleapis.com/auth/spreadsheets',
        'https://www.googleapis.com/auth/drive'
    ]
    creds = None
    if os.path.exists('token.json'):
        try:
            with open('token.json', 'r') as token:
                token_data = json.load(token)
                creds = Credentials.from_authorized_user_info(token_data, scopes)
        except Exception as e:
            print(f"Error loading token: {e}")

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            print("Error: No valid credentials.", file=sys.stderr)
            sys.exit(1)
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
    return creds


def read_sheet(sheet_url):
    """Read the sheet and return (worksheet, all_values, headers)."""
    creds = get_credentials()
    client = gspread.authorize(creds)

    if '/d/' in sheet_url:
        sheet_id = sheet_url.split('/d/')[1].split('/')[0]
    else:
        sheet_id = sheet_url

    spreadsheet = client.open_by_key(sheet_id)

    gid = None
    if 'gid=' in sheet_url:
        gid = sheet_url.split('gid=')[1].split('#')[0].split('&')[0]

    if gid:
        for ws in spreadsheet.worksheets():
            if str(ws.id) == gid:
                worksheet = ws
                break
        else:
            worksheet = spreadsheet.sheet1
    else:
        worksheet = spreadsheet.sheet1

    all_values = worksheet.get_all_values()
    headers = all_values[0] if all_values else []
    print(f"Read {len(all_values) - 1} rows from sheet.")
    return worksheet, all_values, headers


def load_checkpoint():
    if os.path.exists(CHECKPOINT_FILE):
        with open(CHECKPOINT_FILE) as f:
            return json.load(f)
    return {}


def save_checkpoint(data):
    os.makedirs('.tmp', exist_ok=True)
    with open(CHECKPOINT_FILE, 'w') as f:
        json.dump(data, f, indent=2)


def generate_variables(company_name, industries, description):
    """Call Claude Haiku to generate email personalization variables."""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("Error: ANTHROPIC_API_KEY not found in .env", file=sys.stderr)
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)

    prompt = f"""I'm writing a cold email to a startup founder. The email says:

"Been keeping an eye on [startup_type] in the GCC building up their team after a new funding round. Most of them prefer private access to pre-vetted [talent_type], and I connect them with [recruiter_type] who understand the [talent_type] landscape and can give them an edge before the roles are live."

Fill in the 3 variables so the email sounds natural and human-written. Not too generic, not too niche.

Company: {company_name}
Industries: {industries}
Description: {description}

Guidelines:
- startup_type: a recognized category + "startups". Good: "FinTech startups", "AI startups", "gaming startups", "cybersecurity startups". Bad: "Islamic FinTech startups", "TradeTech startups" (too niche or made-up).
- talent_type: something a founder would actually say. Good: "tech talent", "engineering talent", "product and engineering talent", "software talent". Bad: "blockchain engineering talent", "payments tech talent", "semiconductor talent" (too narrow, sounds robotic).
- recruiter_type: how you'd describe recruiters in conversation. Good: "tech recruiters", "specialized recruiters", "industry-focused recruiters". Bad: "crypto tech recruiters", "data governance recruiters", "AgTech recruiters" (no one talks like that).

Return JSON only:
{{
  "startup_type": "...",
  "talent_type": "...",
  "recruiter_type": "..."
}}"""

    try:
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}]
        )
        text = response.content[0].text.strip()

        # Extract JSON from response
        if text.startswith('{'):
            return json.loads(text)
        # Try to find JSON in the response
        start = text.find('{')
        end = text.rfind('}') + 1
        if start >= 0 and end > start:
            return json.loads(text[start:end])

        print(f"  Warning: Could not parse response for {company_name}: {text[:100]}")
        return None

    except Exception as e:
        print(f"  Error for {company_name}: {e}")
        return None


def main():
    parser = argparse.ArgumentParser(description="Generate email personalization variables via Claude")
    parser.add_argument("--sheet_url", required=True, help="Google Sheet URL")
    parser.add_argument("--test", action="store_true", help="Run on first 3 companies only")
    parser.add_argument("--dry_run", action="store_true", help="Generate but don't write to sheet")
    parser.add_argument("--resume", action="store_true", help="Skip companies already enriched")

    args = parser.parse_args()

    # Step 1: Read sheet
    print("=== Step 1: Reading Google Sheet ===")
    worksheet, all_values, headers = read_sheet(args.sheet_url)

    col_indices = {}
    for i, h in enumerate(headers):
        col_indices[h] = i

    name_idx = col_indices.get('Organization Name', 0)
    industries_idx = col_indices.get('Industries')
    desc_idx = col_indices.get('Description')

    if industries_idx is None:
        print("Error: 'Industries' column not found in sheet.", file=sys.stderr)
        sys.exit(1)

    # Ensure output columns exist
    output_cols = ['Startup Type', 'Type of Talent', 'Type of Recruiters']
    output_col_indices = {}
    for col_name in output_cols:
        if col_name in col_indices:
            output_col_indices[col_name] = col_indices[col_name] + 1  # 1-based for gspread
        else:
            new_col = len(headers) + 1
            if new_col > worksheet.col_count:
                worksheet.resize(cols=new_col)
            worksheet.update_cell(1, new_col, col_name)
            output_col_indices[col_name] = new_col
            headers.append(col_name)
            col_indices[col_name] = new_col - 1
            print(f"  Added column '{col_name}' at position {new_col}")

    # Step 2: Build list of companies to process
    companies = []
    for row_idx, row in enumerate(all_values[1:], start=2):
        name = row[name_idx].strip() if len(row) > name_idx else ''
        industries = row[industries_idx].strip() if len(row) > industries_idx else ''
        description = row[desc_idx].strip() if desc_idx is not None and len(row) > desc_idx else ''

        if not name:
            continue

        # Check if already enriched (resume mode)
        if args.resume:
            st_idx = col_indices.get('Startup Type')
            if st_idx is not None and len(row) > st_idx and row[st_idx].strip():
                continue

        companies.append((row_idx, name, industries, description))

    print(f"Companies to process: {len(companies)}")

    if args.test:
        companies = companies[:3]
        print(f"TEST MODE: Limited to {len(companies)} companies")

    if not companies:
        print("Nothing to process.")
        return

    # Step 3: Load checkpoint
    checkpoint = load_checkpoint()

    # Step 4: Generate variables
    print(f"\n=== Step 2: Generating email variables ({len(companies)} companies) ===")

    results = {}  # {row_idx: {startup_type, talent_type, recruiter_type}}
    for i, (row_idx, name, industries, description) in enumerate(companies, 1):
        # Check checkpoint
        key = str(row_idx)
        if key in checkpoint and checkpoint[key]:
            print(f"  [{i}/{len(companies)}] {name} -> cached")
            results[row_idx] = checkpoint[key]
            continue

        print(f"  [{i}/{len(companies)}] {name} ({industries[:50]})...")
        variables = generate_variables(name, industries, description)

        if variables:
            results[row_idx] = variables
            checkpoint[key] = variables
            save_checkpoint(checkpoint)
            print(f"    -> {variables['startup_type']}, {variables['talent_type']}, {variables['recruiter_type']}")
        else:
            print(f"    -> FAILED")

        # Small delay to avoid rate limiting
        if i < len(companies):
            time.sleep(0.2)

    # Step 5: Write to sheet
    found = len(results)
    print(f"\nGenerated variables for {found}/{len(companies)} companies")

    if results and not args.dry_run:
        print(f"\n=== Step 3: Updating Google Sheet ===")
        updates = []
        for row_idx, vars in results.items():
            updates.append(gspread.Cell(row_idx, output_col_indices['Startup Type'], vars.get('startup_type', '')))
            updates.append(gspread.Cell(row_idx, output_col_indices['Type of Talent'], vars.get('talent_type', '')))
            updates.append(gspread.Cell(row_idx, output_col_indices['Type of Recruiters'], vars.get('recruiter_type', '')))

        batch_size = 1000
        for start in range(0, len(updates), batch_size):
            batch = updates[start:start + batch_size]
            worksheet.update_cells(batch, value_input_option='RAW')
            print(f"  Updated cells {start + 1}-{start + len(batch)}")

        print(f"Successfully updated {len(updates)} cells.")
    elif args.dry_run:
        print(f"\n=== DRY RUN: Would update {found * 3} cells ===")
        for row_idx, vars in results.items():
            name = all_values[row_idx - 1][name_idx] if row_idx - 1 < len(all_values) else '?'
            print(f"  {name}: {vars}")

    # Summary
    print(f"\n=== Summary ===")
    print(f"Companies processed: {len(companies)}")
    print(f"Variables generated: {found}")
    print(f"Failed: {len(companies) - found}")


if __name__ == "__main__":
    main()
