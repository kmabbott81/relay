"""
Time-bounded delegation system for authority grants.

Sprint 34A: Collaborative governance.
"""

import json
import os
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

from .teams import get_team_role
from .workspaces import get_workspace_role


def get_delegations_path() -> Path:
    """Get path to delegations JSONL file."""
    return Path(os.getenv("DELEGATIONS_PATH", "logs/delegations.jsonl"))


def _read_delegations() -> list[dict]:
    """Read all delegation records."""
    delegations_path = get_delegations_path()
    if not delegations_path.exists():
        return []

    delegations = []
    with open(delegations_path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                try:
                    delegation = json.loads(line)
                    delegations.append(delegation)
                except json.JSONDecodeError:
                    continue

    return delegations


def grant_delegation(
    granter: str,
    grantee: str,
    scope: str,
    scope_id: str,
    role: str,
    hours: int,
    reason: str,
) -> dict:
    """
    Grant time-bounded delegation.

    Args:
        granter: User granting the delegation
        grantee: User receiving the delegation
        scope: 'team' or 'workspace'
        scope_id: Team or workspace identifier
        role: Role being delegated
        hours: Duration in hours
        reason: Justification for delegation

    Returns:
        Delegation record

    Example:
        >>> grant_delegation("alice", "bob", "team", "team-eng", "Operator", 24, "On-call coverage")
        {'delegation_id': '...', 'grantee': 'bob', 'role': 'Operator', ...}
    """
    delegations_path = get_delegations_path()
    delegations_path.parent.mkdir(parents=True, exist_ok=True)

    now = datetime.now(UTC)
    delegation = {
        "delegation_id": str(uuid.uuid4()),
        "granter": granter,
        "grantee": grantee,
        "scope": scope,
        "scope_id": scope_id,
        "role": role,
        "starts_at": now.isoformat(),
        "expires_at": (now + timedelta(hours=hours)).isoformat(),
        "created_at": now.isoformat(),
        "reason": reason,
    }

    with open(delegations_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(delegation) + "\n")

    return delegation


def revoke_delegation(delegation_id: str) -> bool:
    """
    Revoke a delegation (mark as expired immediately).

    Args:
        delegation_id: Delegation identifier

    Returns:
        True if revoked, False if not found

    Example:
        >>> revoke_delegation("abc-123")
        True
    """
    delegations_path = get_delegations_path()
    delegations = _read_delegations()

    found = False
    for delegation in delegations:
        if delegation.get("delegation_id") == delegation_id:
            found = True
            # Mark as expired now
            delegation["expires_at"] = datetime.now(UTC).isoformat()
            delegation["revoked_at"] = datetime.now(UTC).isoformat()

            with open(delegations_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(delegation) + "\n")
            break

    return found


def list_active_delegations(scope: str, scope_id: str, now: datetime | None = None) -> list[dict]:
    """
    List active delegations for a scope.

    Args:
        scope: 'team' or 'workspace'
        scope_id: Team or workspace identifier
        now: Current time (defaults to UTC now)

    Returns:
        List of active delegation records

    Example:
        >>> list_active_delegations("team", "team-eng")
        [{'delegation_id': '...', 'grantee': 'bob', 'role': 'Operator', ...}]
    """
    if now is None:
        now = datetime.now(UTC)

    delegations = _read_delegations()

    # Deduplicate: last entry per delegation_id wins
    delegation_map = {}
    for d in delegations:
        delegation_id = d.get("delegation_id")
        if delegation_id:
            delegation_map[delegation_id] = d

    active = []
    for delegation in delegation_map.values():
        if delegation.get("scope") == scope and delegation.get("scope_id") == scope_id:
            # Check if active (not expired)
            expires_at_str = delegation.get("expires_at")
            if expires_at_str:
                expires_at = datetime.fromisoformat(expires_at_str.rstrip("Z")).replace(tzinfo=UTC)
                if expires_at > now:
                    active.append(delegation)

    return active


def active_role_for(user: str, scope: str, scope_id: str, now: datetime | None = None) -> str | None:
    """
    Get effective role for user considering delegations.

    Returns highest role from: base role + active delegations.

    Args:
        user: Username
        scope: 'team' or 'workspace'
        scope_id: Team or workspace identifier
        now: Current time (defaults to UTC now)

    Returns:
        Effective role or None if no access

    Example:
        >>> active_role_for("bob", "team", "team-eng")
        'Operator'  # May be from base role or delegation
    """
    if now is None:
        now = datetime.now(UTC)

    role_hierarchy = {
        "Viewer": 0,
        "Author": 1,
        "Operator": 2,
        "Auditor": 3,
        "Compliance": 4,
        "Admin": 5,
    }

    # Get base role
    if scope == "team":
        base_role = get_team_role(user, scope_id)
    elif scope == "workspace":
        base_role = get_workspace_role(user, scope_id)
    else:
        base_role = None

    max_level = role_hierarchy.get(base_role, -1) if base_role else -1

    # Check active delegations
    delegations = list_active_delegations(scope, scope_id, now)
    for delegation in delegations:
        if delegation.get("grantee") == user:
            delegated_role = delegation.get("role")
            if delegated_role:
                level = role_hierarchy.get(delegated_role, -1)
                if level > max_level:
                    max_level = level

    if max_level == -1:
        return None

    # Find role name for level
    for role_name, level in role_hierarchy.items():
        if level == max_level:
            return role_name

    return None
