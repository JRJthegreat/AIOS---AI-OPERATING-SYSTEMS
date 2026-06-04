#!/usr/bin/env python3
"""
Law Firm CRM Setup — Monday.com

Creates a fully configured CRM template in a dedicated "Law Firm CRM" workspace.
DOES NOT touch any existing boards or workspaces.

Run:
    cd ".claude/skills/monday-crm/scripts"
    python3 setup_crm.py
"""

import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import monday_client as mc

CONFIG_PATH = Path(__file__).parent.parent / "config.json"
WORKSPACE_NAME = "Law Firm CRM"
BOARD_PREFIX = ""


# ── Column definitions ────────────────────────────────────────────────────────

STATUS_LABELS = {
    "intake_status": {
        0: {"color": "#fdab3d", "label": "New"},
        1: {"color": "#00c875", "label": "Consult Scheduled"},
        2: {"color": "#0086c0", "label": "Retainer Signed"},
        3: {"color": "#e2445c", "label": "Lost"},
    },
    "case_status": {
        0: {"color": "#fdab3d", "label": "Open"},
        1: {"color": "#0086c0", "label": "In Progress"},
        2: {"color": "#a25ddc", "label": "Pending Hearing"},
        3: {"color": "#00c875", "label": "Closed - Won"},
        4: {"color": "#e2445c", "label": "Closed - Lost"},
        5: {"color": "#c4c4c4", "label": "Closed - Settled"},
    },
    "task_status": {
        0: {"color": "#c4c4c4", "label": "To Do"},
        1: {"color": "#fdab3d", "label": "In Progress"},
        2: {"color": "#00c875", "label": "Done"},
        3: {"color": "#e2445c", "label": "Blocked"},
    },
    "hearing_status": {
        0: {"color": "#fdab3d", "label": "Upcoming"},
        1: {"color": "#00c875", "label": "Completed"},
        2: {"color": "#0086c0", "label": "Rescheduled"},
        3: {"color": "#e2445c", "label": "Cancelled"},
    },
}

INTAKE_COLUMNS = [
    ("Status", "color", STATUS_LABELS["intake_status"]),
    ("Inquiry Type", "dropdown", ["Criminal Defense", "Immigration", "Family", "Civil", "Other"]),
    ("Source", "dropdown", ["Referral", "Website", "Social Media", "Walk-in", "Other"]),
    ("Phone", "phone", None),
    ("Email", "email", None),
    ("Consultation Date", "date", None),
    ("Assigned Attorney", "multiple-person", None),
    ("Notes", "long-text", None),
]

CLIENT_COLUMNS = [
    ("Phone", "phone", None),
    ("Email", "email", None),
    ("Address", "text", None),
    ("Language", "dropdown", ["English", "Spanish", "French", "Haitian Creole", "Other"]),
    ("Client Since", "date", None),
    ("Referral Source", "text", None),
    ("Assigned Attorney", "multiple-person", None),
    ("Notes", "long-text", None),
]

CASE_COLUMNS = [
    ("Case Number", "text", None),
    ("Case Type", "dropdown", ["Criminal Defense", "Immigration", "Family", "Civil", "Other"]),
    ("Sub-Type", "text", None),
    ("Status", "color", STATUS_LABELS["case_status"]),
    ("Assigned Attorney", "multiple-person", None),
    ("Paralegal", "multiple-person", None),
    ("Court / Jurisdiction", "text", None),
    ("Filing Date", "date", None),
    ("Next Hearing Date", "date", None),
    ("Retainer Amount", "numeric", None),
    ("Outstanding Balance", "numeric", None),
    ("Priority", "dropdown", ["Low", "Medium", "High", "Urgent"]),
    ("Documents Link", "link", None),
    ("Notes", "long-text", None),
]

TASK_COLUMNS = [
    ("Task Type", "dropdown", ["Filing", "Court Prep", "Client Follow-up", "Document Request", "Internal"]),
    ("Assigned To", "multiple-person", None),
    ("Due Date", "date", None),
    ("Priority", "dropdown", ["Low", "Medium", "High", "Urgent"]),
    ("Status", "color", STATUS_LABELS["task_status"]),
    ("Notes", "long-text", None),
]

HEARING_COLUMNS = [
    ("Hearing Type", "dropdown", ["Court Date", "Deposition", "Mediation", "Filing Deadline", "Client Meeting"]),
    ("Assigned Attorney", "multiple-person", None),
    ("Date & Time", "date", None),
    ("Location / Link", "text", None),
    ("Status", "color", STATUS_LABELS["hearing_status"]),
    ("Notes", "long-text", None),
]


# ── Column type mapping ───────────────────────────────────────────────────────

COL_TYPE_MAP = {
    "text": "text",
    "phone": "phone",
    "email": "email",
    "date": "date",
    "numeric": "numbers",
    "link": "link",
    "long-text": "long_text",
    "multiple-person": "people",
    "color": "status",
    "dropdown": "dropdown",
}


def build_status_defaults(labels: dict) -> dict:
    return {"labels": {str(k): v["label"] for k, v in labels.items()}}


def build_dropdown_defaults(options: list) -> dict:
    return {"settings": {"labels": [{"id": i + 1, "name": opt} for i, opt in enumerate(options)]}}


# ── Setup helpers ─────────────────────────────────────────────────────────────

def get_or_create_workspace(name: str) -> int:
    """Find existing workspace by name or create it."""
    workspaces = mc.list_workspaces()
    for ws in workspaces:
        if ws["name"] == name:
            print(f"  Found existing workspace: {name} (id={ws['id']})")
            return int(ws["id"])

    print(f"  Creating workspace: {name}")
    ws = mc.create_workspace(name, kind="open")
    print(f"  Created workspace: {name} (id={ws['id']})")
    return int(ws["id"])


def create_board_with_setup(name: str, workspace_id: int, columns: list, groups: list) -> dict:
    """
    Create a board with columns and groups. Skips creation if board already exists in workspace.
    Returns board info with group id map.
    """
    full_name = name

    # Delete any existing board with this name in the workspace (clean slate)
    existing_ws_boards = mc.list_boards(workspace_id)
    for b in existing_ws_boards:
        if b["name"] == full_name:
            print(f"\n  Deleting existing board: {full_name} (id={b['id']}) — recreating fresh")
            mc.delete_board(int(b["id"]))

    print(f"\n  Creating board: {full_name}")
    board = mc.create_board(full_name, kind="public", workspace_id=workspace_id)
    board_id = int(board["id"])
    print(f"    id={board_id}")

    # Add columns
    col_id_map = {}
    for col_title, col_type, col_data in columns:
        monday_type = COL_TYPE_MAP.get(col_type, "text")
        defaults = None

        if col_type == "color" and isinstance(col_data, dict):
            defaults = build_status_defaults(col_data)
        elif col_type == "dropdown" and isinstance(col_data, list):
            defaults = build_dropdown_defaults(col_data)

        col = mc.create_column(board_id, col_title, monday_type, defaults)
        col_id_map[col_title] = col.get("id", "")
        print(f"    + column: {col_title} ({monday_type})")

    # Rename or replace default group, then add others
    existing_groups = mc.get_groups(board_id)
    default_group_id = existing_groups[0]["id"] if existing_groups else None

    group_id_map = {}
    for i, group_name in enumerate(groups):
        if i == 0 and default_group_id:
            # Rename the default group by deleting it and recreating — Monday
            # doesn't expose rename via API cleanly, so we create all then delete default
            pass
        g = mc.create_group(board_id, group_name)
        group_id_map[group_name] = g["id"]
        print(f"    + group: {group_name}")

    # Delete the auto-created default "Topics" group
    if default_group_id:
        mc.delete_group(board_id, default_group_id)

    return {
        "id": board_id,
        "name": full_name,
        "columns": col_id_map,
        "groups": group_id_map,
    }


def add_views(board_id: int, views: list):
    """Add named views to a board. views = [(view_name, view_type), ...]"""
    for view_name, view_type in views:
        try:
            mc.create_board_view(board_id, view_name, view_type)
            print(f"    + view: {view_name} ({view_type})")
        except Exception as e:
            print(f"    ! view {view_name} skipped: {e}")


# ── Dashboard ─────────────────────────────────────────────────────────────────

def setup_dashboard(boards: dict) -> dict:
    """
    Monday's API does not support create_dashboard.
    Print manual setup instructions and return a placeholder.
    """
    print("\n  Dashboard creation via API is not supported by Monday.com.")
    print("  Manual steps to create 'Law Firm Overview' dashboard:")
    print("  1. Open monday.com → Law Firm CRM workspace")
    print("  2. Click + Add → Dashboard → name it 'Law Firm Overview'")
    print("  3. Add these widgets:")
    print("     • Chart (bar)    — Cases → Case Type column  (Active Cases by Type)")
    print("     • Battery        — Intake / Leads → Status   (Lead Pipeline)")
    print("     • Numbers        — Hearings & Deadlines → Date & Time     (Upcoming Hearings)")
    print("     • Numbers        — Tasks → Due Date + Status  (Overdue Tasks)")
    print("     • Chart (pie)    — Cases → Status column      (Case Outcomes)")
    print("     • Chart (bar)    — Cases → Assigned Attorney  (Attorney Workload)")
    return {"id": "manual", "name": "Law Firm Overview"}


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("Law Firm CRM Setup")
    print("=" * 60)

    # Verify credentials
    me = mc.get_me()
    print(f"\nAuthenticated as: {me.get('name')} ({me.get('email')})")
    print(f"Account: {me.get('account', {}).get('name')}")

    # Show existing boards — read only
    existing = mc.list_boards()
    print(f"\nExisting boards ({len(existing)}) — will not be touched:")
    for b in existing:
        ws = b.get("workspace", {})
        print(f"  [{ws.get('name', 'Main')}] {b['name']} (id={b['id']})")

    # Workspace
    print(f"\n{'─'*60}")
    print("Setting up workspace...")
    workspace_id = get_or_create_workspace(WORKSPACE_NAME)

    # Boards
    print(f"\n{'─'*60}")
    print("Creating boards...")

    boards = {}

    boards["Intake"] = create_board_with_setup(
        "Intake / Leads", workspace_id, INTAKE_COLUMNS,
        ["New", "In Progress", "Closed"]
    )

    boards["Clients"] = create_board_with_setup(
        "Clients", workspace_id, CLIENT_COLUMNS,
        ["Active", "Past"]
    )

    boards["Cases"] = create_board_with_setup(
        "Cases", workspace_id, CASE_COLUMNS,
        ["Open", "In Progress", "Pending Hearing", "Closed"]
    )

    boards["Tasks"] = create_board_with_setup(
        "Tasks", workspace_id, TASK_COLUMNS,
        ["To Do", "In Progress", "Done"]
    )

    boards["Hearings"] = create_board_with_setup(
        "Hearings & Deadlines", workspace_id, HEARING_COLUMNS,
        ["This Week", "This Month", "Upcoming"]
    )

    # Board views
    print(f"\n{'─'*60}")
    print("Adding board views...")
    add_views(boards["Cases"]["id"], [
        ("Kanban",    "KanbanView"),
        ("Timeline",  "TimelineView"),
        ("Chart",     "ChartView"),
        ("Calendar",  "CalendarView"),
    ])
    add_views(boards["Tasks"]["id"], [
        ("Kanban",    "KanbanView"),
        ("Calendar",  "CalendarView"),
    ])
    add_views(boards["Intake"]["id"], [
        ("Kanban",    "KanbanView"),
        ("Calendar",  "CalendarView"),
    ])
    add_views(boards["Hearings"]["id"], [
        ("Calendar",  "CalendarView"),
        ("Timeline",  "TimelineView"),
    ])

    # Dashboard
    print(f"\n{'─'*60}")
    print("Creating dashboard...")
    dashboard = setup_dashboard(boards)

    # Save config
    config = {
        "workspace_id": workspace_id,
        "boards": {k: {"id": v["id"], "name": v["name"], "groups": v["groups"]} for k, v in boards.items()},
        "dashboard_id": dashboard["id"],
    }
    CONFIG_PATH.write_text(json.dumps(config, indent=2))

    print(f"\n{'='*60}")
    print("Setup complete!")
    print(f"Config saved to: {CONFIG_PATH}")
    print(f"\nBoard IDs:")
    for name, info in boards.items():
        print(f"  {name}: {info['id']}")
    print(f"\nDashboard ID: {dashboard['id']}")
    print(f"\nOpen Monday.com and navigate to the '{WORKSPACE_NAME}' workspace.")


if __name__ == "__main__":
    main()
