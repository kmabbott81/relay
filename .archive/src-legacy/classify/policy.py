"""
Classification policy enforcement for artifacts and exports.

Sprint 33B: Export policies and label assignment.
"""


from .labels import can_access, effective_label


def label_for_artifact(meta: dict) -> str:
    """
    Determine classification label for artifact based on metadata.

    Args:
        meta: Artifact metadata (may contain 'label', 'tenant', etc.)

    Returns:
        Classification label (falls back to DEFAULT_LABEL)

    Examples:
        >>> label_for_artifact({"label": "Confidential"})
        'Confidential'
        >>> label_for_artifact({})
        'Internal'
    """
    requested = meta.get("label")
    return effective_label(requested)


def export_allowed(label: str | None, user_clearance: str, require_labels: bool = False) -> bool:
    """
    Check if export is allowed based on label and clearance.

    Args:
        label: Data classification label (None if unlabeled)
        user_clearance: User's clearance level
        require_labels: If True, deny export of unlabeled data

    Returns:
        True if export allowed, False otherwise

    Examples:
        >>> export_allowed("Internal", "Confidential", require_labels=True)
        True
        >>> export_allowed(None, "Confidential", require_labels=True)
        False
        >>> export_allowed(None, "Confidential", require_labels=False)
        True
    """
    # If labels required and data is unlabeled, deny
    if require_labels and label is None:
        return False

    # If unlabeled and labels not required, allow
    if label is None:
        return True

    # Check clearance
    return can_access(user_clearance, label)


def redact_for_label(label: str, payload: dict | str | bytes) -> dict | str | bytes:
    """
    Redact payload based on classification label.

    Currently a no-op stub with hook in place for future implementation.

    Args:
        label: Classification label
        payload: Data to potentially redact

    Returns:
        Redacted payload (currently unchanged)

    Note:
        Future implementations might redact specific fields based on label.
        For now, this serves as a policy hook.
    """
    # Stub: future redaction logic could go here
    # Example: if label == "Restricted" and isinstance(payload, dict):
    #     return {k: "REDACTED" if k in SENSITIVE_FIELDS else v for k, v in payload.items()}
    return payload
