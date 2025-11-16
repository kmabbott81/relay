"""Authorization and access control (RBAC + ABAC)."""

import os
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class Role(str, Enum):
    """User roles in the system."""

    ADMIN = "admin"
    EDITOR = "editor"
    VIEWER = "viewer"


class Action(str, Enum):
    """Actions that can be performed on resources."""

    READ = "read"
    WRITE = "write"
    DELETE = "delete"
    EXECUTE = "execute"
    APPROVE = "approve"
    EXPORT = "export"


class ResourceType(str, Enum):
    """Types of resources in the system."""

    TEMPLATE = "template"
    ARTIFACT = "artifact"
    WORKFLOW = "workflow"
    BATCH = "batch"
    CONFIG = "config"


@dataclass
class Principal:
    """User or service principal."""

    user_id: str
    tenant_id: str
    role: Role
    email: Optional[str] = None


@dataclass
class Resource:
    """Resource being accessed."""

    resource_type: ResourceType
    resource_id: str
    tenant_id: str
    owner_id: Optional[str] = None


@dataclass
class AuthzContext:
    """Authorization context for a request."""

    principal: Principal
    action: Action
    resource: Resource


class AuthorizationError(Exception):
    """Raised when authorization fails."""

    pass


# Role-based permissions matrix
ROLE_PERMISSIONS = {
    Role.ADMIN: {
        ResourceType.TEMPLATE: {Action.READ, Action.WRITE, Action.DELETE, Action.EXECUTE},
        ResourceType.ARTIFACT: {Action.READ, Action.WRITE, Action.DELETE, Action.EXPORT},
        ResourceType.WORKFLOW: {Action.READ, Action.WRITE, Action.DELETE, Action.EXECUTE},
        ResourceType.BATCH: {Action.READ, Action.WRITE, Action.DELETE, Action.EXECUTE},
        ResourceType.CONFIG: {Action.READ, Action.WRITE},
    },
    Role.EDITOR: {
        ResourceType.TEMPLATE: {Action.READ, Action.EXECUTE},
        ResourceType.ARTIFACT: {Action.READ, Action.EXPORT},
        ResourceType.WORKFLOW: {Action.READ, Action.EXECUTE, Action.APPROVE},
        ResourceType.BATCH: {Action.READ, Action.EXECUTE},
        ResourceType.CONFIG: {Action.READ},
    },
    Role.VIEWER: {
        ResourceType.TEMPLATE: {Action.READ},
        ResourceType.ARTIFACT: {Action.READ},
        ResourceType.WORKFLOW: {Action.READ},
        ResourceType.BATCH: {Action.READ},
        ResourceType.CONFIG: {Action.READ},
    },
}


def check_permission(principal: Principal, action: Action, resource: Resource) -> bool:
    """
    Check if principal has permission to perform action on resource.

    Args:
        principal: User or service making the request
        action: Action being attempted
        resource: Resource being accessed

    Returns:
        True if permission granted, False otherwise
    """
    # Feature flag check
    if not os.getenv("FEATURE_RBAC_ENFORCE", "false").lower() == "true":
        # RBAC not enforced - allow all (dev mode)
        return True

    # Tenant isolation: principal can only access resources in their tenant
    if principal.tenant_id != resource.tenant_id:
        return False

    # Check role-based permissions
    role_perms = ROLE_PERMISSIONS.get(principal.role, {})
    resource_perms = role_perms.get(resource.resource_type, set())

    return action in resource_perms


def require_permission(principal: Principal, action: Action, resource: Resource) -> None:
    """
    Require permission or raise AuthorizationError.

    Args:
        principal: User or service making the request
        action: Action being attempted
        resource: Resource being accessed

    Raises:
        AuthorizationError: If permission denied
    """
    if not check_permission(principal, action, resource):
        raise AuthorizationError(
            f"Permission denied: {principal.role} cannot {action.value} "
            f"{resource.resource_type.value} {resource.resource_id} "
            f"in tenant {resource.tenant_id}"
        )


def create_principal_from_headers(headers: dict, default_tenant: str = "default") -> Principal:
    """
    Extract principal from request headers.

    Args:
        headers: Request headers dict
        default_tenant: Default tenant if not specified

    Returns:
        Principal extracted from headers

    Headers:
        X-User-ID: User identifier
        X-Tenant-ID: Tenant identifier
        X-User-Role: User role (admin/editor/viewer)
        X-User-Email: User email (optional)
    """
    user_id = headers.get("x-user-id", "anonymous")
    tenant_id = headers.get("x-tenant-id", default_tenant)
    role_str = headers.get("x-user-role", "viewer")
    email = headers.get("x-user-email")

    try:
        role = Role(role_str.lower())
    except ValueError:
        role = Role.VIEWER

    return Principal(user_id=user_id, tenant_id=tenant_id, role=role, email=email)


def get_default_tenant() -> str:
    """Get default tenant ID from environment or fallback."""
    return os.getenv("DEFAULT_TENANT_ID", "default")


# ABAC (Attribute-Based Access Control) hooks for future extension
def abac_check(context: AuthzContext, **attributes) -> bool:
    """
    ABAC check with custom attributes (extensible).

    Args:
        context: Authorization context
        **attributes: Additional attributes for ABAC rules

    Returns:
        True if ABAC rules allow access

    Example attributes:
        - time_of_day: Allow only during business hours
        - ip_address: Allow only from specific networks
        - resource_sensitivity: Require higher role for sensitive data
    """
    # For now, just delegate to RBAC
    # Future: add custom ABAC rules here
    return check_permission(context.principal, context.action, context.resource)
