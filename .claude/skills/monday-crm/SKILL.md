---
name: monday-crm
description: Law Firm CRM on Monday.com — set up boards, add cases, update leads, manage hearings and tasks. Use when user asks to add a case, update lead status, check upcoming hearings, add a client, or manage anything in the law firm CRM.
allowed-tools: Bash, Read, Write, Edit
---

# Law Firm CRM — Monday.com

## Goal
Manage a fully configured law firm CRM on Monday.com with 5 boards:
- `[LF] Intake / Leads` — potential clients and consultation pipeline
- `[LF] Clients` — signed clients
- `[LF] Cases` — active and closed cases with full case details
- `[LF] Tasks` — case-linked tasks assigned to attorneys/paralegals
- `[LF] Hearings & Deadlines` — upcoming court dates and deadlines

## Environment
```
MONDAY_API_KEY=<in .env>
```

## Scripts

### Initial Setup (run once)
```bash
cd ".claude/skills/monday-crm/scripts"
python3 setup_crm.py
```
Creates the `Law Firm CRM` workspace, all 5 boards with columns and groups, and the "Law Firm Overview" dashboard. Saves board IDs to `config.json`.

### Seed Dummy Data (run once after setup)
```bash
cd ".claude/skills/monday-crm/scripts"
python3 seed_sample_data.py
```
Populates all boards with fictional but realistic law firm data (6 leads, 4 clients, 8 cases, 8 tasks, 5 hearings).

## Board IDs
After running setup, board IDs are in:
`.claude/skills/monday-crm/config.json`

## Dashboard
**Law Firm Overview** dashboard contains:
- Active Cases by Type (bar chart)
- Lead Pipeline (battery)
- Upcoming Hearings (numbers)
- Overdue Tasks (numbers)
- Case Outcomes (chart)
- Attorney Workload (chart)

## Views per Board
| Board | Views |
|-------|-------|
| Cases | Table, Kanban (by Status), Timeline (Filing → Hearing), Chart (by Type), Calendar |
| Tasks | Table, Kanban (by Status), Calendar |
| Intake | Table, Kanban (by Status), Calendar |
| Hearings | Table, Calendar, Timeline |
| Clients | Table |

## Recommended Automations (set up manually in Monday)
After running the scripts, configure these in Monday's Automation Center:

1. **Hearing reminder** — When date arrives in 7 days → notify assigned attorney
2. **Task overdue** — When due date passes and status is not Done → notify assigned person
3. **Intake → Client** — When Intake status changes to "Retainer Signed" → create item in Clients board
4. **Case closed** — When Case status changes to Closed → send notification to firm admin

## Troubleshooting
- **401 error** — Check `MONDAY_API_KEY` in `.env`
- **Rate limit** — The client sleeps 0.1s between calls; if you hit limits, increase `_MIN_INTERVAL` in `monday_client.py`
- **Widget creation fails** — Some widget types require a paid Monday plan; widgets are skipped gracefully and can be added manually
- **Board IDs missing** — Re-run `setup_crm.py`; it will find the existing workspace and skip re-creating it
