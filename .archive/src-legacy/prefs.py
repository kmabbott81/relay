"""User preferences service with RBAC and tenant isolation."""

import json
import os
from typing import Any, Optional

from relay_ai.security.audit import AuditAction, get_audit_logger
from relay_ai.security.authz import Principal, Role

# Feature flag
FEATURE_HOME = os.getenv("FEATURE_HOME", "true").lower() == "true"

# Allowed preference keys with size limits
ALLOWED_PREFS = {
    "favorite_templates": 10240,  # 10KB max (list of template slugs)
    "layout": 5120,  # 5KB max (UI layout config)
    "default_preset": 1024,  # 1KB max (default preset name)
    "recent_chats": 10240,  # 10KB max (list of recent chat IDs)
    "theme": 256,  # 256B max (theme name)
    "dashboard_cards": 5120,  # 5KB max (card visibility/order)
}


class PrefsError(Exception):
    """Base exception for preferences errors."""

    pass


class PrefsValidationError(PrefsError):
    """Raised when preference validation fails."""

    pass


class PrefsAuthorizationError(PrefsError):
    """Raised when user lacks permission for prefs operation."""

    pass


def get_prefs(user_id: str, tenant_id: str, principal: Optional[Principal] = None) -> dict[str, Any]:
    """
    Get all preferences for a user in a tenant.

    Args:
        user_id: User identifier
        tenant_id: Tenant identifier
        principal: Principal making the request (for RBAC)

    Returns:
        Dictionary of preference key-value pairs

    Raises:
        PrefsAuthorizationError: If principal lacks permission
    """
    if not FEATURE_HOME:
        return {}

    # Check authorization
    if principal:
        # Users can read their own prefs, admins can read any prefs
        if principal.user_id != user_id and principal.role != Role.ADMIN:
            raise PrefsAuthorizationError(f"User {principal.user_id} cannot read prefs for {user_id}")

        # Check tenant isolation
        if principal.tenant_id != tenant_id:
            raise PrefsAuthorizationError(f"User {principal.user_id} cannot read prefs in tenant {tenant_id}")

    # Import here to avoid circular dependency
    from relay_ai.metadata import get_user_prefs

    prefs = get_user_prefs(user_id, tenant_id)

    # Parse JSON values
    parsed = {}
    for key, value_str in prefs.items():
        try:
            parsed[key] = json.loads(value_str) if value_str else None
        except (json.JSONDecodeError, TypeError):
            parsed[key] = value_str

    return parsed


def set_pref(user_id: str, tenant_id: str, key: str, value: Any, principal: Optional[Principal] = None) -> None:
    """
    Set a preference for a user in a tenant.

    Args:
        user_id: User identifier
        tenant_id: Tenant identifier
        key: Preference key (must be in ALLOWED_PREFS)
        value: Preference value (will be JSON-encoded)
        principal: Principal making the request (for RBAC)

    Raises:
        PrefsValidationError: If key invalid or value too large
        PrefsAuthorizationError: If principal lacks permission
    """
    if not FEATURE_HOME:
        return

    # Validate key
    if key not in ALLOWED_PREFS:
        raise PrefsValidationError(f"Invalid preference key: {key}. Allowed: {list(ALLOWED_PREFS.keys())}")

    # Check authorization
    if principal:
        # Viewers cannot write any prefs (read-only role)
        if principal.role == Role.VIEWER:
            raise PrefsAuthorizationError("Viewer role cannot write prefs")

        # Users (editors) can write their own prefs, admins can write any prefs
        if principal.user_id != user_id and principal.role != Role.ADMIN:
            raise PrefsAuthorizationError(f"User {principal.user_id} cannot write prefs for {user_id}")

        # Check tenant isolation
        if principal.tenant_id != tenant_id:
            raise PrefsAuthorizationError(f"User {principal.user_id} cannot write prefs in tenant {tenant_id}")

    # Encode value
    value_str = json.dumps(value) if not isinstance(value, str) else value

    # Validate size
    max_size = ALLOWED_PREFS[key]
    if len(value_str) > max_size:
        raise PrefsValidationError(f"Preference {key} exceeds max size {max_size} bytes (got {len(value_str)} bytes)")

    # Save to metadata
    from relay_ai.metadata import set_user_pref

    set_user_pref(user_id, tenant_id, key, value_str)

    # Audit log
    logger = get_audit_logger()
    logger.log_success(
        tenant_id=tenant_id,
        user_id=principal.user_id if principal else user_id,
        action=AuditAction.AUTH_FAILURE,  # Reuse closest action (should add PREFS_UPDATE)
        resource_type="prefs",
        resource_id=f"{user_id}:{key}",
        metadata={"key": key, "value_size": len(value_str)},
    )


def delete_pref(user_id: str, tenant_id: str, key: str, principal: Optional[Principal] = None) -> None:
    """
    Delete a preference for a user in a tenant.

    Args:
        user_id: User identifier
        tenant_id: Tenant identifier
        key: Preference key
        principal: Principal making the request (for RBAC)

    Raises:
        PrefsAuthorizationError: If principal lacks permission
    """
    if not FEATURE_HOME:
        return

    # Check authorization
    if principal:
        # Users can delete their own prefs, admins can delete any prefs
        if principal.user_id != user_id and principal.role != Role.ADMIN:
            raise PrefsAuthorizationError(f"User {principal.user_id} cannot delete prefs for {user_id}")

        # Check tenant isolation
        if principal.tenant_id != tenant_id:
            raise PrefsAuthorizationError(f"User {principal.user_id} cannot delete prefs in tenant {tenant_id}")

    # Delete from metadata
    from relay_ai.metadata import delete_user_pref

    delete_user_pref(user_id, tenant_id, key)

    # Audit log
    logger = get_audit_logger()
    logger.log_success(
        tenant_id=tenant_id,
        user_id=principal.user_id if principal else user_id,
        action=AuditAction.AUTH_FAILURE,  # Reuse closest action
        resource_type="prefs",
        resource_id=f"{user_id}:{key}",
        metadata={"key": key, "action": "delete"},
    )


def toggle_favorite_template(
    user_id: str, tenant_id: str, template_slug: str, principal: Optional[Principal] = None
) -> bool:
    """
    Toggle a template as favorite for a user.

    Args:
        user_id: User identifier
        tenant_id: Tenant identifier
        template_slug: Template slug to favorite/unfavorite
        principal: Principal making the request (for RBAC)

    Returns:
        True if template is now favorited, False if unfavorited

    Raises:
        PrefsAuthorizationError: If principal lacks permission
    """
    if not FEATURE_HOME:
        return False

    # Get current favorites
    prefs = get_prefs(user_id, tenant_id, principal)
    favorites = prefs.get("favorite_templates", [])

    if not isinstance(favorites, list):
        favorites = []

    # Toggle
    if template_slug in favorites:
        favorites.remove(template_slug)
        is_favorite = False
    else:
        favorites.append(template_slug)
        is_favorite = True

    # Save
    set_pref(user_id, tenant_id, "favorite_templates", favorites, principal)

    # Audit log
    logger = get_audit_logger()
    logger.log_success(
        tenant_id=tenant_id,
        user_id=principal.user_id if principal else user_id,
        action=AuditAction.AUTH_FAILURE,  # Reuse closest action
        resource_type="template",
        resource_id=template_slug,
        metadata={"action": "favorite" if is_favorite else "unfavorite", "favorites_count": len(favorites)},
    )

    return is_favorite


def get_favorite_templates(user_id: str, tenant_id: str, principal: Optional[Principal] = None) -> list[str]:
    """
    Get list of favorite template slugs for a user.

    Args:
        user_id: User identifier
        tenant_id: Tenant identifier
        principal: Principal making the request (for RBAC)

    Returns:
        List of template slugs
    """
    if not FEATURE_HOME:
        return []

    prefs = get_prefs(user_id, tenant_id, principal)
    favorites = prefs.get("favorite_templates", [])

    return favorites if isinstance(favorites, list) else []


def is_template_favorite(
    user_id: str, tenant_id: str, template_slug: str, principal: Optional[Principal] = None
) -> bool:
    """
    Check if a template is favorited by a user.

    Args:
        user_id: User identifier
        tenant_id: Tenant identifier
        template_slug: Template slug to check
        principal: Principal making the request (for RBAC)

    Returns:
        True if template is favorited, False otherwise
    """
    if not FEATURE_HOME:
        return False

    favorites = get_favorite_templates(user_id, tenant_id, principal)
    return template_slug in favorites
