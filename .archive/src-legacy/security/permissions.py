"""Action Permission System - Sprint 58 Slice 5 Foundations.

Simple allowlist-based permissions for action execution.
Controls which actions a user/workspace can execute based on configured allowlists.

Sprint 58 Foundations: Basic implementation for testing and scaffolding.
Future: Integrate with RBAC, workspace-level policies, and audit logging.
"""

import os
from typing import Optional

# Default action allowlist (empty = all actions allowed)
# Format: List of "provider.action" strings or "*" for wildcard
DEFAULT_ACTION_ALLOWLIST: list[str] = []

# Global action denylist (takes precedence over allowlists)
# Used for disabling dangerous or deprecated actions system-wide
GLOBAL_ACTION_DENYLIST: list[str] = [
    # Example: "filesystem.delete_recursive"
]


def can_execute(action_id: str, user_id: Optional[str] = None, workspace_id: Optional[str] = None) -> bool:
    """Check if user/workspace can execute the specified action.

    Args:
        action_id: Action identifier (e.g., "gmail.send")
        user_id: Optional user identifier (future: per-user permissions)
        workspace_id: Optional workspace identifier (future: per-workspace permissions)

    Returns:
        True if action is allowed, False otherwise

    Examples:
        >>> can_execute("gmail.send")
        True

        >>> can_execute("gmail.send", user_id="user_123")
        True

        >>> can_execute("filesystem.delete_recursive")  # On global denylist
        False
    """
    # Global denylist check (highest priority)
    if action_id in GLOBAL_ACTION_DENYLIST:
        return False

    # Check allowlist from environment variable
    allowlist_env = os.getenv("ACTION_ALLOWLIST", "")
    if allowlist_env:
        allowlist = [a.strip() for a in allowlist_env.split(",") if a.strip()]
    else:
        allowlist = DEFAULT_ACTION_ALLOWLIST

    # Empty allowlist = all actions allowed (permissive default)
    if not allowlist:
        return True

    # Wildcard "*" = all actions allowed
    if "*" in allowlist:
        return True

    # Check exact match
    if action_id in allowlist:
        return True

    # Check provider-level wildcard (e.g., "gmail.*")
    provider = action_id.split(".")[0] if "." in action_id else action_id
    provider_wildcard = f"{provider}.*"
    if provider_wildcard in allowlist:
        return True

    return False


def get_allowed_actions(user_id: Optional[str] = None, workspace_id: Optional[str] = None) -> list[str]:
    """Get list of allowed action IDs for user/workspace.

    Args:
        user_id: Optional user identifier
        workspace_id: Optional workspace identifier

    Returns:
        List of allowed action_id strings, or ["*"] if all actions allowed

    Examples:
        >>> get_allowed_actions()
        ['*']

        >>> os.environ["ACTION_ALLOWLIST"] = "gmail.send,calendar.create_event"
        >>> get_allowed_actions()
        ['gmail.send', 'calendar.create_event']
    """
    allowlist_env = os.getenv("ACTION_ALLOWLIST", "")
    if allowlist_env:
        allowlist = [a.strip() for a in allowlist_env.split(",") if a.strip()]
    else:
        allowlist = DEFAULT_ACTION_ALLOWLIST

    # Empty allowlist = all actions allowed
    if not allowlist:
        return ["*"]

    # Filter out globally denied actions
    return [action for action in allowlist if action not in GLOBAL_ACTION_DENYLIST]


def add_to_denylist(action_id: str) -> None:
    """Add action to global denylist (for runtime configuration).

    Args:
        action_id: Action identifier to deny globally

    Note:
        This modifies the global denylist at runtime.
        For production, use environment variables or config files.
    """
    if action_id not in GLOBAL_ACTION_DENYLIST:
        GLOBAL_ACTION_DENYLIST.append(action_id)


def remove_from_denylist(action_id: str) -> None:
    """Remove action from global denylist (for runtime configuration).

    Args:
        action_id: Action identifier to un-deny

    Note:
        This modifies the global denylist at runtime.
        For production, use environment variables or config files.
    """
    if action_id in GLOBAL_ACTION_DENYLIST:
        GLOBAL_ACTION_DENYLIST.remove(action_id)


def is_action_globally_denied(action_id: str) -> bool:
    """Check if action is on the global denylist.

    Args:
        action_id: Action identifier to check

    Returns:
        True if action is globally denied
    """
    return action_id in GLOBAL_ACTION_DENYLIST
