"""
Data classification labels and clearance checking.

Sprint 33B: Label-based access control.
"""

import os


def parse_labels(env_str: str | None = None) -> list[str]:
    """
    Parse classification labels from environment string.

    Args:
        env_str: Comma-separated label string (or None to use CLASS_LABELS env)

    Returns:
        Ordered list of labels from least to most sensitive

    Examples:
        >>> parse_labels("Public,Internal,Confidential,Restricted")
        ['Public', 'Internal', 'Confidential', 'Restricted']
    """
    if env_str is None:
        env_str = os.getenv("CLASS_LABELS", "Public,Internal,Confidential,Restricted")

    labels = [label.strip() for label in env_str.split(",") if label.strip()]
    return labels


def can_access(user_clearance: str, label: str) -> bool:
    """
    Check if user clearance allows access to labeled data.

    Uses total order: user can access data at their level or below.

    Args:
        user_clearance: User's clearance level
        label: Data classification label

    Returns:
        True if access allowed, False otherwise

    Examples:
        >>> can_access("Confidential", "Internal")
        True
        >>> can_access("Internal", "Confidential")
        False
    """
    labels = parse_labels()

    # If label or clearance not in known labels, deny access
    if label not in labels or user_clearance not in labels:
        return False

    user_level = labels.index(user_clearance)
    data_level = labels.index(label)

    # User can access data at their level or below
    return user_level >= data_level


def effective_label(requested: str | None, default: str | None = None) -> str:
    """
    Determine effective label with fallback to default.

    Args:
        requested: Requested label (may be None or invalid)
        default: Default label (uses DEFAULT_LABEL env if None)

    Returns:
        Valid label from the classification hierarchy

    Examples:
        >>> effective_label("Confidential")
        'Confidential'
        >>> effective_label(None)  # Uses DEFAULT_LABEL
        'Internal'
        >>> effective_label("InvalidLabel")
        'Internal'
    """
    labels = parse_labels()

    if default is None:
        default = os.getenv("DEFAULT_LABEL", "Internal")

    # If requested label is valid, use it
    if requested and requested in labels:
        return requested

    # Fall back to default
    if default in labels:
        return default

    # Ultimate fallback: first label (least sensitive)
    return labels[0] if labels else "Public"
