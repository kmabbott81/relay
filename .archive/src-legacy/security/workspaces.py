"""
Workspace management with member roles.

Sprint 34A: Collaborative governance.
"""

import json
import os
from datetime import UTC, datetime
from pathlib import Path


def get_workspaces_path() -> Path:
    """Get path to workspaces JSONL file."""
    return Path(os.getenv("WORKSPACES_PATH", "logs/workspaces.jsonl"))


def _read_workspaces() -> list[dict]:
    """Read all workspace records (last-wins per workspace_id)."""
    workspaces_path = get_workspaces_path()
    if not workspaces_path.exists():
        return []

    workspace_map = {}
    with open(workspaces_path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                try:
                    workspace = json.loads(line)
                    workspace_id = workspace.get("workspace_id")
                    if workspace_id:
                        workspace_map[workspace_id] = workspace
                except json.JSONDecodeError:
                    continue

    return list(workspace_map.values())


def get_workspace_role(user: str, workspace_id: str) -> str | None:
    """
    Get user's role in a workspace.

    Args:
        user: Username
        workspace_id: Workspace identifier

    Returns:
        Role string or None if user not in workspace

    Example:
        >>> get_workspace_role("alice", "ws-project-a")
        'Operator'
    """
    workspaces = _read_workspaces()

    for workspace in workspaces:
        if workspace.get("workspace_id") == workspace_id:
            members = workspace.get("members", [])
            for member in members:
                if member.get("user") == user:
                    return member.get("role")

    return None


def list_workspace_members(workspace_id: str) -> list[dict]:
    """
    List all members of a workspace.

    Args:
        workspace_id: Workspace identifier

    Returns:
        List of member dicts with 'user' and 'role'

    Example:
        >>> list_workspace_members("ws-project-a")
        [{'user': 'alice', 'role': 'Operator'}, {'user': 'bob', 'role': 'Viewer'}]
    """
    workspaces = _read_workspaces()

    for workspace in workspaces:
        if workspace.get("workspace_id") == workspace_id:
            return workspace.get("members", [])

    return []


def upsert_workspace_member(
    workspace_id: str,
    user: str,
    role: str,
    workspace_name: str | None = None,
    team_id: str | None = None,
) -> dict:
    """
    Add or update a workspace member.

    Args:
        workspace_id: Workspace identifier
        user: Username
        role: Role to assign
        workspace_name: Workspace name (used if creating new workspace)
        team_id: Parent team ID

    Returns:
        Updated workspace record

    Example:
        >>> upsert_workspace_member("ws-project-a", "alice", "Operator", "Project A", "team-eng")
        {'workspace_id': 'ws-project-a', 'name': 'Project A', 'team_id': 'team-eng', ...}
    """
    workspaces_path = get_workspaces_path()
    workspaces_path.parent.mkdir(parents=True, exist_ok=True)

    workspaces = _read_workspaces()

    # Find existing workspace
    workspace = None
    for w in workspaces:
        if w.get("workspace_id") == workspace_id:
            workspace = w
            break

    if workspace is None:
        # Create new workspace
        workspace = {
            "workspace_id": workspace_id,
            "name": workspace_name or workspace_id,
            "team_id": team_id,
            "members": [],
            "created_at": datetime.now(UTC).isoformat(),
        }

    # Update or add member
    members = workspace.get("members", [])
    found = False
    for member in members:
        if member.get("user") == user:
            member["role"] = role
            found = True
            break

    if not found:
        members.append({"user": user, "role": role})

    workspace["members"] = members
    workspace["updated_at"] = datetime.now(UTC).isoformat()

    # Append to JSONL
    with open(workspaces_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(workspace) + "\n")

    return workspace


def require_workspace_role(user: str, workspace_id: str, required_role: str) -> None:
    """
    Require user has at least the specified role in workspace.

    Args:
        user: Username
        workspace_id: Workspace identifier
        required_role: Minimum required role

    Raises:
        PermissionError: If user lacks required role

    Example:
        >>> require_workspace_role("alice", "ws-project-a", "Operator")
        # Passes if alice is Operator, Admin, etc.
    """
    role_hierarchy = {
        "Viewer": 0,
        "Author": 1,
        "Operator": 2,
        "Auditor": 3,
        "Compliance": 4,
        "Admin": 5,
    }

    user_role = get_workspace_role(user, workspace_id)
    if user_role is None:
        raise PermissionError(f"User {user} is not a member of workspace {workspace_id}")

    user_level = role_hierarchy.get(user_role, 0)
    required_level = role_hierarchy.get(required_role, 0)

    if user_level < required_level:
        raise PermissionError(
            f"User {user} has role {user_role} in workspace {workspace_id}, but {required_role} is required"
        )
