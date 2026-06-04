#!/usr/bin/env python3
"""
Monday.com GraphQL API client.
Handles auth, rate limiting, and error checking for all CRM scripts.
"""

import os
import time
import requests
from dotenv import load_dotenv

load_dotenv()

MONDAY_API_URL = "https://api.monday.com/v2"
MONDAY_API_KEY = os.getenv("MONDAY_API_KEY")

HEADERS = {
    "Authorization": MONDAY_API_KEY,
    "Content-Type": "application/json",
    "API-Version": "2023-10",
}

_last_request_time = 0
_MIN_INTERVAL = 0.1  # 10 req/sec max (Monday allows 15, we stay conservative)


def query(gql: str, variables: dict = None) -> dict:
    """
    Execute a Monday.com GraphQL query or mutation.
    Raises RuntimeError if the API returns errors.
    """
    global _last_request_time

    elapsed = time.time() - _last_request_time
    if elapsed < _MIN_INTERVAL:
        time.sleep(_MIN_INTERVAL - elapsed)

    payload = {"query": gql}
    if variables:
        payload["variables"] = variables

    response = requests.post(MONDAY_API_URL, json=payload, headers=HEADERS, timeout=30)
    _last_request_time = time.time()

    response.raise_for_status()
    data = response.json()

    if "errors" in data:
        raise RuntimeError(f"Monday API error: {data['errors']}")

    return data.get("data", {})


def get_me() -> dict:
    """Return info about the authenticated user."""
    result = query("{ me { id name email account { id name } } }")
    return result.get("me", {})


def list_workspaces() -> list:
    """List all workspaces in the account."""
    result = query("{ workspaces { id name kind description } }")
    return result.get("workspaces", [])


def list_boards(workspace_id: int = None) -> list:
    """List all boards, optionally filtered by workspace."""
    gql = "{ boards(limit: 200) { id name workspace { id name } } }"
    result = query(gql)
    boards = result.get("boards", [])
    if workspace_id:
        boards = [b for b in boards if b.get("workspace", {}).get("id") == str(workspace_id)]
    return boards


def create_workspace(name: str, kind: str = "open") -> dict:
    """Create a new workspace. kind: open or closed."""
    gql = """
    mutation($name: String!, $kind: WorkspaceKind!) {
        create_workspace(name: $name, kind: $kind) {
            id name kind
        }
    }
    """
    result = query(gql, {"name": name, "kind": kind})
    return result.get("create_workspace", {})


def create_board(name: str, kind: str = "public", workspace_id: int = None) -> dict:
    """Create a board, optionally inside a workspace."""
    gql = """
    mutation($name: String!, $kind: BoardKind!, $workspace_id: ID) {
        create_board(board_name: $name, board_kind: $kind, workspace_id: $workspace_id) {
            id name
        }
    }
    """
    variables = {"name": name, "kind": kind}
    if workspace_id:
        variables["workspace_id"] = workspace_id
    result = query(gql, variables)
    return result.get("create_board", {})


def create_column(board_id: int, title: str, col_type: str, defaults: dict = None) -> dict:
    """Add a column to a board."""
    gql = """
    mutation($board_id: ID!, $title: String!, $col_type: ColumnType!, $defaults: JSON) {
        create_column(board_id: $board_id, title: $title, column_type: $col_type, defaults: $defaults) {
            id title type
        }
    }
    """
    import json
    variables = {
        "board_id": str(board_id),
        "title": title,
        "col_type": col_type,
    }
    if defaults:
        variables["defaults"] = json.dumps(defaults)
    result = query(gql, variables)
    return result.get("create_column", {})


def create_group(board_id: int, name: str) -> dict:
    """Create a group (section) within a board."""
    gql = """
    mutation($board_id: ID!, $name: String!) {
        create_group(board_id: $board_id, group_name: $name) {
            id title
        }
    }
    """
    result = query(gql, {"board_id": str(board_id), "name": name})
    return result.get("create_group", {})


def get_groups(board_id: int) -> list:
    """Get all groups in a board."""
    gql = """
    query($board_id: [ID!]) {
        boards(ids: $board_id) {
            groups { id title }
        }
    }
    """
    result = query(gql, {"board_id": [str(board_id)]})
    boards = result.get("boards", [])
    return boards[0].get("groups", []) if boards else []


def delete_group(board_id: int, group_id: str) -> bool:
    """Delete a group from a board."""
    gql = """
    mutation($board_id: ID!, $group_id: String!) {
        delete_group(board_id: $board_id, group_id: $group_id) { id }
    }
    """
    result = query(gql, {"board_id": str(board_id), "group_id": group_id})
    return bool(result.get("delete_group"))


def create_item(board_id: int, group_id: str, name: str, column_values: dict = None) -> dict:
    """Create an item (row) in a board group."""
    import json
    gql = """
    mutation($board_id: ID!, $group_id: String!, $name: String!, $col_vals: JSON) {
        create_item(board_id: $board_id, group_id: $group_id, item_name: $name, column_values: $col_vals) {
            id name
        }
    }
    """
    variables = {
        "board_id": str(board_id),
        "group_id": group_id,
        "name": name,
    }
    if column_values:
        variables["col_vals"] = json.dumps(column_values)
    result = query(gql, variables)
    return result.get("create_item", {})


def create_dashboard(name: str) -> dict:
    """Create a Monday dashboard."""
    gql = """
    mutation($name: String!) {
        create_dashboard(name: $name, board_kind: public) {
            id name
        }
    }
    """
    result = query(gql, {"name": name})
    return result.get("create_dashboard", {})


def create_widget(dashboard_id: int, widget_type: str, settings: dict = None) -> dict:
    """Add a widget to a dashboard."""
    import json
    gql = """
    mutation($dashboard_id: ID!, $widget_type: DashboardWidgetType!, $settings: JSON) {
        create_widget(board_id: null, dashboard_id: $dashboard_id, type: $widget_type, settings_str: $settings) {
            id type
        }
    }
    """
    variables = {
        "dashboard_id": str(dashboard_id),
        "widget_type": widget_type,
    }
    if settings:
        variables["settings"] = json.dumps(settings)
    result = query(gql, variables)
    return result.get("create_widget", {})






def create_board_view(board_id: int, view_name: str, view_type: str) -> dict:
    """Add a view to a board. view_type: KanbanView, ChartView, CalendarView, TimelineView, etc."""
    gql = """
    mutation($board_id: ID!, $view_name: String!, $view_type: BoardViewType!) {
        create_board_view(board_id: $board_id, view_name: $view_name, view_type: $view_type) {
            id name type
        }
    }
    """
    result = query(gql, {"board_id": str(board_id), "view_name": view_name, "view_type": view_type})
    return result.get("create_board_view", {})
def delete_board(board_id: int) -> bool:
    """Delete a board by ID."""
    gql = """
    mutation($board_id: ID!) {
        delete_board(board_id: $board_id) { id }
    }
    """
    result = query(gql, {"board_id": str(board_id)})
    return bool(result.get("delete_board"))
def get_columns(board_id: int) -> list:
    """Get all columns for a board."""
    gql = """
    query($board_id: [ID!]) {
        boards(ids: $board_id) {
            columns { id title type }
        }
    }
    """
    result = query(gql, {"board_id": [str(board_id)]})
    boards = result.get("boards", [])
    return boards[0].get("columns", []) if boards else []
