"""RBAC permissions model - Sprint 58 Slice 5 foundations.

Baseline RBAC schema with support for:
- Exact action grants (provider.action)
- Wildcard grants (provider.*)
- Role-based bindings
- Permission filtering for plans
"""

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

# Safe defaults: minimal permissions for all users
DEFAULT_PERMISSIONS = {
    "viewer": ["actions:preview", "gmail.list", "calendar.list"],
    "developer": ["actions:preview", "actions:execute", "gmail.send", "calendar.create"],
    "admin": ["*"],  # All actions
}


class Permission(BaseModel):
    """Single permission (action or scope)."""

    model_config = ConfigDict(extra="forbid")

    action: str = Field(
        ...,
        description="Action ID or scope (provider.action, provider.*, or scope:operation)",
        min_length=1,
    )
    description: str = Field(default="", description="Human-readable permission description")


class PermissionSet(BaseModel):
    """Collection of permissions for a role."""

    model_config = ConfigDict(extra="forbid")

    role: str = Field(..., description="Role name (viewer, developer, admin, custom)", min_length=1)
    permissions: list[str] = Field(default_factory=list, description="List of action IDs or wildcards")

    def allows(self, action_id: str) -> bool:
        """Check if this permission set allows an action.

        Args:
            action_id: Action ID in provider.action format

        Returns:
            True if action is allowed (exact match or wildcard)
        """
        # Admin bypass
        if "*" in self.permissions:
            return True

        # Exact match
        if action_id in self.permissions:
            return True

        # Wildcard match (provider.*)
        if "." in action_id:
            provider = action_id.split(".")[0]
            if f"{provider}.*" in self.permissions:
                return True

        return False


class UserRoleBinding(BaseModel):
    """User-to-role mapping in a workspace."""

    model_config = ConfigDict(extra="forbid")

    user_id: str = Field(..., description="User UUID or identifier", min_length=1)
    role: str = Field(..., description="Assigned role name", min_length=1)
    workspace_id: Optional[str] = Field(None, description="Workspace UUID (optional for global roles)")


class EffectivePermissions(BaseModel):
    """Resolved permissions for a user in a workspace."""

    model_config = ConfigDict(extra="forbid")

    user_id: str
    role: str
    allowed_actions: list[str]  # Flattened list of allowed action IDs

    def can_execute(self, action_id: str) -> bool:
        """Check if user can execute an action."""
        # Admin bypass
        if "*" in self.allowed_actions:
            return True

        if action_id in self.allowed_actions:
            return True

        # Wildcard match
        if "." in action_id:
            provider = action_id.split(".")[0]
            if f"{provider}.*" in self.allowed_actions:
                return True

        return False


class RBACRegistry(BaseModel):
    """Registry of roles and user-role bindings."""

    model_config = ConfigDict(extra="forbid")

    roles: dict[str, list[str]] = Field(default_factory=dict, description="Map of role name to action list")
    bindings: list[UserRoleBinding] = Field(default_factory=list, description="User-role assignments")

    def get_user_permissions(self, user_id: str, workspace_id: Optional[str] = None) -> EffectivePermissions:
        """Resolve effective permissions for a user."""
        # Find user's role binding
        binding = next(
            (b for b in self.bindings if b.user_id == user_id and b.workspace_id == workspace_id),
            None,
        )

        if not binding:
            # Default to viewer if no binding
            role = "viewer"
        else:
            role = binding.role

        # Get actions for role
        allowed_actions = self.roles.get(role, DEFAULT_PERMISSIONS.get(role, []))

        return EffectivePermissions(
            user_id=user_id,
            role=role,
            allowed_actions=allowed_actions,
        )


def default_rbac() -> RBACRegistry:
    """Create default RBAC registry with built-in roles."""
    return RBACRegistry(
        roles={
            "viewer": DEFAULT_PERMISSIONS["viewer"],
            "developer": DEFAULT_PERMISSIONS["developer"],
            "admin": DEFAULT_PERMISSIONS["admin"],
        },
        bindings=[],  # Empty bindings; populate on startup or via API
    )
