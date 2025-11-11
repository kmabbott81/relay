"""Tests for RBAC and authorization."""

import pytest

from relay_ai.security.authz import (
    Action,
    AuthorizationError,
    Principal,
    Resource,
    ResourceType,
    Role,
    check_permission,
    create_principal_from_headers,
    require_permission,
)


def test_admin_has_all_permissions():
    """Admin role has all permissions for their assigned resource types."""
    admin = Principal(user_id="admin1", tenant_id="tenant1", role=Role.ADMIN)

    # Test admin permissions on templates
    template = Resource(resource_type=ResourceType.TEMPLATE, resource_id="tpl1", tenant_id="tenant1")
    assert check_permission(admin, Action.READ, template)
    assert check_permission(admin, Action.WRITE, template)
    assert check_permission(admin, Action.DELETE, template)
    assert check_permission(admin, Action.EXECUTE, template)

    # Test admin permissions on workflows
    workflow = Resource(resource_type=ResourceType.WORKFLOW, resource_id="wf1", tenant_id="tenant1")
    assert check_permission(admin, Action.READ, workflow)
    assert check_permission(admin, Action.WRITE, workflow)
    assert check_permission(admin, Action.DELETE, workflow)
    assert check_permission(admin, Action.EXECUTE, workflow)

    # Test admin permissions on artifacts
    artifact = Resource(resource_type=ResourceType.ARTIFACT, resource_id="art1", tenant_id="tenant1")
    assert check_permission(admin, Action.READ, artifact)
    assert check_permission(admin, Action.WRITE, artifact)
    assert check_permission(admin, Action.DELETE, artifact)
    assert check_permission(admin, Action.EXPORT, artifact)


def test_editor_can_execute_workflows():
    """Editor can execute workflows but not delete them."""
    editor = Principal(user_id="editor1", tenant_id="tenant1", role=Role.EDITOR)
    workflow = Resource(resource_type=ResourceType.WORKFLOW, resource_id="wf1", tenant_id="tenant1")

    assert check_permission(editor, Action.READ, workflow)
    assert check_permission(editor, Action.EXECUTE, workflow)
    assert check_permission(editor, Action.APPROVE, workflow)
    assert not check_permission(editor, Action.DELETE, workflow)


def test_viewer_read_only():
    """Viewer can only read resources."""
    viewer = Principal(user_id="viewer1", tenant_id="tenant1", role=Role.VIEWER)
    template = Resource(resource_type=ResourceType.TEMPLATE, resource_id="tpl1", tenant_id="tenant1")

    assert check_permission(viewer, Action.READ, template)
    assert not check_permission(viewer, Action.WRITE, template)
    assert not check_permission(viewer, Action.DELETE, template)
    assert not check_permission(viewer, Action.EXECUTE, template)


def test_tenant_isolation():
    """Users cannot access resources in other tenants."""
    admin = Principal(user_id="admin1", tenant_id="tenant1", role=Role.ADMIN)
    resource_other_tenant = Resource(resource_type=ResourceType.TEMPLATE, resource_id="tpl1", tenant_id="tenant2")

    # Even admin cannot access other tenant's resources
    assert not check_permission(admin, Action.READ, resource_other_tenant)
    assert not check_permission(admin, Action.WRITE, resource_other_tenant)


def test_require_permission_success():
    """require_permission allows authorized actions."""
    admin = Principal(user_id="admin1", tenant_id="tenant1", role=Role.ADMIN)
    resource = Resource(resource_type=ResourceType.TEMPLATE, resource_id="tpl1", tenant_id="tenant1")

    # Should not raise
    require_permission(admin, Action.WRITE, resource)


def test_require_permission_denied():
    """require_permission raises on denied actions."""
    viewer = Principal(user_id="viewer1", tenant_id="tenant1", role=Role.VIEWER)
    resource = Resource(resource_type=ResourceType.TEMPLATE, resource_id="tpl1", tenant_id="tenant1")

    with pytest.raises(AuthorizationError, match="Permission denied"):
        require_permission(viewer, Action.WRITE, resource)


def test_create_principal_from_headers():
    """Principal extracted from headers."""
    headers = {
        "x-user-id": "user123",
        "x-tenant-id": "tenant456",
        "x-user-role": "editor",
        "x-user-email": "user@example.com",
    }

    principal = create_principal_from_headers(headers)

    assert principal.user_id == "user123"
    assert principal.tenant_id == "tenant456"
    assert principal.role == Role.EDITOR
    assert principal.email == "user@example.com"


def test_create_principal_defaults():
    """Principal defaults to viewer/anonymous if headers missing."""
    headers = {}

    principal = create_principal_from_headers(headers, default_tenant="default")

    assert principal.user_id == "anonymous"
    assert principal.tenant_id == "default"
    assert principal.role == Role.VIEWER


def test_editor_can_approve():
    """Editor role can approve artifacts."""
    editor = Principal(user_id="editor1", tenant_id="tenant1", role=Role.EDITOR)
    workflow = Resource(resource_type=ResourceType.WORKFLOW, resource_id="wf1", tenant_id="tenant1")

    assert check_permission(editor, Action.APPROVE, workflow)


def test_viewer_cannot_export():
    """Viewer cannot export artifacts."""
    viewer = Principal(user_id="viewer1", tenant_id="tenant1", role=Role.VIEWER)
    artifact = Resource(resource_type=ResourceType.ARTIFACT, resource_id="art1", tenant_id="tenant1")

    assert not check_permission(viewer, Action.EXPORT, artifact)


def test_editor_can_export():
    """Editor can export artifacts."""
    editor = Principal(user_id="editor1", tenant_id="tenant1", role=Role.EDITOR)
    artifact = Resource(resource_type=ResourceType.ARTIFACT, resource_id="art1", tenant_id="tenant1")

    assert check_permission(editor, Action.EXPORT, artifact)
