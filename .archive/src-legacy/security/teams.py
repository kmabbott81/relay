"""
Team management with member roles.

Sprint 34A: Collaborative governance.
"""

import json
import os
from datetime import UTC, datetime
from pathlib import Path


def get_teams_path() -> Path:
    """Get path to teams JSONL file."""
    return Path(os.getenv("TEAMS_PATH", "logs/teams.jsonl"))


def _read_teams() -> list[dict]:
    """Read all team records (last-wins per team_id)."""
    teams_path = get_teams_path()
    if not teams_path.exists():
        return []

    team_map = {}
    with open(teams_path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                try:
                    team = json.loads(line)
                    team_id = team.get("team_id")
                    if team_id:
                        team_map[team_id] = team
                except json.JSONDecodeError:
                    continue

    return list(team_map.values())


def get_team_role(user: str, team_id: str) -> str | None:
    """
    Get user's role in a team.

    Args:
        user: Username
        team_id: Team identifier

    Returns:
        Role string or None if user not in team

    Example:
        >>> get_team_role("alice", "team-eng")
        'Admin'
    """
    teams = _read_teams()

    for team in teams:
        if team.get("team_id") == team_id:
            members = team.get("members", [])
            for member in members:
                if member.get("user") == user:
                    return member.get("role")

    return None


def list_team_members(team_id: str) -> list[dict]:
    """
    List all members of a team.

    Args:
        team_id: Team identifier

    Returns:
        List of member dicts with 'user' and 'role'

    Example:
        >>> list_team_members("team-eng")
        [{'user': 'alice', 'role': 'Admin'}, {'user': 'bob', 'role': 'Operator'}]
    """
    teams = _read_teams()

    for team in teams:
        if team.get("team_id") == team_id:
            return team.get("members", [])

    return []


def upsert_team_member(team_id: str, user: str, role: str, team_name: str | None = None) -> dict:
    """
    Add or update a team member.

    Args:
        team_id: Team identifier
        user: Username
        role: Role to assign
        team_name: Team name (used if creating new team)

    Returns:
        Updated team record

    Example:
        >>> upsert_team_member("team-eng", "alice", "Admin", "Engineering")
        {'team_id': 'team-eng', 'name': 'Engineering', 'members': [...], ...}
    """
    teams_path = get_teams_path()
    teams_path.parent.mkdir(parents=True, exist_ok=True)

    teams = _read_teams()

    # Find existing team
    team = None
    for t in teams:
        if t.get("team_id") == team_id:
            team = t
            break

    if team is None:
        # Create new team
        team = {
            "team_id": team_id,
            "name": team_name or team_id,
            "members": [],
            "workspaces": [],
            "created_at": datetime.now(UTC).isoformat(),
        }

    # Update or add member
    members = team.get("members", [])
    found = False
    for member in members:
        if member.get("user") == user:
            member["role"] = role
            found = True
            break

    if not found:
        members.append({"user": user, "role": role})

    team["members"] = members
    team["updated_at"] = datetime.now(UTC).isoformat()

    # Append to JSONL
    with open(teams_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(team) + "\n")

    return team


def require_team_role(user: str, team_id: str, required_role: str) -> None:
    """
    Require user has at least the specified role in team.

    Args:
        user: Username
        team_id: Team identifier
        required_role: Minimum required role

    Raises:
        PermissionError: If user lacks required role

    Example:
        >>> require_team_role("alice", "team-eng", "Operator")
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

    user_role = get_team_role(user, team_id)
    if user_role is None:
        raise PermissionError(f"User {user} is not a member of team {team_id}")

    user_level = role_hierarchy.get(user_role, 0)
    required_level = role_hierarchy.get(required_role, 0)

    if user_level < required_level:
        raise PermissionError(f"User {user} has role {user_role} in team {team_id}, but {required_role} is required")
