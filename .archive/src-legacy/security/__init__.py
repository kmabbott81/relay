"""
Security module for RBAC, ABAC, and audit logging.

Sprint 34A: Collaborative governance with teams, workspaces, and delegations.
"""

from .delegation import active_role_for, grant_delegation, list_active_delegations, revoke_delegation
from .teams import get_team_role, list_team_members, require_team_role, upsert_team_member
from .workspaces import (
    get_workspace_role,
    list_workspace_members,
    require_workspace_role,
    upsert_workspace_member,
)

__all__ = [
    "get_team_role",
    "list_team_members",
    "upsert_team_member",
    "require_team_role",
    "get_workspace_role",
    "list_workspace_members",
    "upsert_workspace_member",
    "require_workspace_role",
    "active_role_for",
    "grant_delegation",
    "revoke_delegation",
    "list_active_delegations",
]
