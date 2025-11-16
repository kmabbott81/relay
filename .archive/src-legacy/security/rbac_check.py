"""
RBAC Check for Approvals (Sprint 31)

Simple role hierarchy for checkpoint approval authorization.
"""


# Role hierarchy (ascending privilege)
ROLE_HIERARCHY = {
    "Viewer": 0,
    "Operator": 1,
    "Admin": 2,
}


def can_approve(user_role: str, required_role: str) -> bool:
    """
    Check if user role can approve a checkpoint requiring a specific role.

    Args:
        user_role: User's RBAC role
        required_role: Required role for approval

    Returns:
        True if user can approve, False otherwise

    Example:
        >>> can_approve("Admin", "Operator")
        True
        >>> can_approve("Operator", "Admin")
        False
        >>> can_approve("Viewer", "Operator")
        False
    """
    user_level = ROLE_HIERARCHY.get(user_role, -1)
    required_level = ROLE_HIERARCHY.get(required_role, 999)

    return user_level >= required_level
