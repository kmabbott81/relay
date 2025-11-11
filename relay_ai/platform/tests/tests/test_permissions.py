"""Tests for RBAC permissions model and orchestrator guards."""

import pytest
from pydantic import ValidationError

from relay_ai.ai.orchestrator import AIOrchestrator
from relay_ai.schemas.ai_plan import PlannedAction, PlanResult
from relay_ai.schemas.permissions import (
    PermissionSet,
    UserRoleBinding,
    default_rbac,
)


class TestPermissionSet:
    """Test PermissionSet allow/deny logic."""

    def test_exact_allow(self):
        """Test exact action match."""
        perms = PermissionSet(role="developer", permissions=["gmail.send", "calendar.create"])
        assert perms.allows("gmail.send")
        assert perms.allows("calendar.create")
        assert not perms.allows("gmail.read")

    def test_wildcard_allow(self):
        """Test provider.* wildcard."""
        perms = PermissionSet(role="developer", permissions=["gmail.*", "calendar.create"])
        assert perms.allows("gmail.send")
        assert perms.allows("gmail.read")
        assert perms.allows("calendar.create")
        assert not perms.allows("slack.post")

    def test_admin_bypass(self):
        """Test admin * bypass."""
        perms = PermissionSet(role="admin", permissions=["*"])
        assert perms.allows("gmail.send")
        assert perms.allows("anything.anything")


class TestRBACRegistry:
    """Test RBAC registry and role resolution."""

    def test_default_rbac(self):
        """Test default RBAC creation."""
        rbac = default_rbac()
        assert "viewer" in rbac.roles
        assert "developer" in rbac.roles
        assert "admin" in rbac.roles

    def test_viewer_permissions(self):
        """Test viewer role is restricted."""
        rbac = default_rbac()
        viewer_perms = rbac.get_user_permissions("user_1")
        assert viewer_perms.role == "viewer"
        assert viewer_perms.can_execute("actions:preview")
        assert not viewer_perms.can_execute("gmail.send")

    def test_developer_permissions(self):
        """Test developer role has more access."""
        rbac = default_rbac()
        binding = UserRoleBinding(user_id="user_2", role="developer")
        rbac.bindings.append(binding)
        dev_perms = rbac.get_user_permissions("user_2")
        assert dev_perms.role == "developer"
        assert dev_perms.can_execute("gmail.send")
        assert dev_perms.can_execute("actions:execute")

    def test_admin_permissions(self):
        """Test admin role has all access."""
        rbac = default_rbac()
        binding = UserRoleBinding(user_id="user_3", role="admin")
        rbac.bindings.append(binding)
        admin_perms = rbac.get_user_permissions("user_3")
        assert admin_perms.can_execute("anything.anything")


class TestAIOrchestrator:
    """Test orchestrator permission guarding."""

    def test_guard_plan_steps_filters_denied(self):
        """Test that _guard_plan_steps removes disallowed actions."""
        rbac = default_rbac()
        rbac.bindings.append(UserRoleBinding(user_id="viewer_1", role="viewer"))
        orch = AIOrchestrator(rbac)

        plan = PlanResult(
            prompt="Send email and schedule",
            intent="email_and_schedule",
            steps=[
                PlannedAction(
                    action_id="gmail.send",
                    description="Send email",
                    params={"to": "user@example.com"},
                ),
                PlannedAction(
                    action_id="calendar.create",
                    description="Create event",
                    params={"title": "Meeting"},
                ),
            ],
            confidence=0.9,
            explanation="Send email and create calendar event",
        )

        # Viewer can only do actions:preview, not gmail.send or calendar.create
        guarded = orch._guard_plan_steps("viewer_1", plan)
        assert len(guarded.steps) == 0
        assert "filtered by permissions" in guarded.explanation

    def test_guard_plan_steps_allows_permitted(self):
        """Test that permitted actions pass through."""
        rbac = default_rbac()
        rbac.bindings.append(UserRoleBinding(user_id="dev_1", role="developer"))
        orch = AIOrchestrator(rbac)

        plan = PlanResult(
            prompt="Send email",
            intent="send_email",
            steps=[
                PlannedAction(
                    action_id="gmail.send",
                    description="Send email",
                    params={"to": "user@example.com"},
                )
            ],
            confidence=0.95,
            explanation="Send thank you email",
        )

        guarded = orch._guard_plan_steps("dev_1", plan)
        assert len(guarded.steps) == 1
        assert guarded.steps[0].action_id == "gmail.send"

    def test_extra_forbid_on_permissions(self):
        """Test that extra fields are rejected."""
        with pytest.raises(ValidationError):
            PermissionSet(
                role="developer",
                permissions=["gmail.send"],
                extra_field="should_fail",  # type: ignore
            )
