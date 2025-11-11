"""
Tests for Template Registry (Sprint 32)

Covers registration, listing, retrieval, deprecation, and RBAC enforcement.
"""

from pathlib import Path

import pytest

from relay_ai.template_registry import deprecate, get, list_templates, register


@pytest.fixture
def temp_registry(tmp_path: Path, monkeypatch):
    """Temporary registry for testing."""
    registry_dir = tmp_path / "registry"
    registry_dir.mkdir()
    monkeypatch.setenv("TEMPLATE_REGISTRY_PATH", str(registry_dir))
    return registry_dir


@pytest.fixture
def auth_user(monkeypatch):
    """Set user as Author."""
    monkeypatch.setenv("USER_RBAC_ROLE", "Author")


def test_register_template(temp_registry, auth_user):
    """Test basic template registration."""
    record = register(
        name="test_template",
        version="1.0.0",
        workflow_ref="inbox_drive_sweep",
        tags=["test", "demo"],
    )

    assert record["name"] == "test_template"
    assert record["version"] == "1.0.0"
    assert record["workflow_ref"] == "inbox_drive_sweep"
    assert record["status"] == "active"
    assert "test" in record["tags"]
    assert record["id"] == "test_template:1.0.0"


def test_register_requires_rbac(temp_registry, monkeypatch):
    """Test that registration requires Author role."""
    monkeypatch.setenv("USER_RBAC_ROLE", "Viewer")

    with pytest.raises(PermissionError, match="requires Author role"):
        register(name="test", version="1.0", workflow_ref="workflow")


def test_list_templates(temp_registry, auth_user):
    """Test listing templates."""
    # Register multiple templates
    register(name="template1", version="1.0", workflow_ref="workflow1", tags=["tag1"])
    register(name="template2", version="1.0", workflow_ref="workflow2", tags=["tag2"])
    register(name="template1", version="2.0", workflow_ref="workflow1", tags=["tag1"])

    # List all
    templates = list_templates()
    assert len(templates) == 3

    # Filter by name
    t1_templates = list_templates(name="template1")
    assert len(t1_templates) == 2
    assert all(t["name"] == "template1" for t in t1_templates)

    # Filter by tag
    tag1_templates = list_templates(tag="tag1")
    assert len(tag1_templates) == 2


def test_get_template_latest(temp_registry, auth_user):
    """Test getting latest active version."""
    register(name="test", version="1.0", workflow_ref="workflow")
    register(name="test", version="2.0", workflow_ref="workflow")

    # Get latest (should be 2.0 - most recently created)
    template = get("test")
    assert template is not None
    assert template["version"] == "2.0"


def test_get_template_specific_version(temp_registry, auth_user):
    """Test getting specific version."""
    register(name="test", version="1.0", workflow_ref="workflow")
    register(name="test", version="2.0", workflow_ref="workflow")

    # Get v1.0
    template = get("test", "1.0")
    assert template is not None
    assert template["version"] == "1.0"


def test_deprecate_template(temp_registry, auth_user):
    """Test deprecating a template."""
    register(name="test", version="1.0", workflow_ref="workflow")

    updated = deprecate("test", "1.0", "Superseded by 2.0")

    assert updated["status"] == "deprecated"
    assert updated["deprecation_reason"] == "Superseded by 2.0"

    # Verify in list
    templates = list_templates(name="test", status="deprecated")
    assert len(templates) == 1


def test_deprecate_requires_rbac(temp_registry, auth_user, monkeypatch):
    """Test that deprecation requires Author role."""
    register(name="test", version="1.0", workflow_ref="workflow")

    monkeypatch.setenv("USER_RBAC_ROLE", "Viewer")

    with pytest.raises(PermissionError, match="requires Author role"):
        deprecate("test", "1.0", "reason")


def test_get_latest_skips_deprecated(temp_registry, auth_user):
    """Test that get() returns latest active version."""
    register(name="test", version="1.0", workflow_ref="workflow")
    register(name="test", version="2.0", workflow_ref="workflow")

    # Deprecate v2.0
    deprecate("test", "2.0", "Bug found")

    # Get latest should return v1.0 (latest active)
    template = get("test")
    assert template["version"] == "1.0"


def test_register_with_owner(temp_registry, auth_user):
    """Test that owner is recorded."""
    record = register(name="test", version="1.0", workflow_ref="workflow", owner="CustomOwner")

    assert record["owner"] == "CustomOwner"


def test_register_with_schema_ref(temp_registry, auth_user):
    """Test registration with schema reference."""
    record = register(
        name="test",
        version="1.0",
        workflow_ref="workflow",
        schema_ref="test_schema.json",
    )

    assert record["schema_ref"] == "test_schema.json"
