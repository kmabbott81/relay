"""
Tests for Template Loader Integration (Sprint 32)

Covers loading templates, schemas, and validation integration.
"""

import json

import pytest
import yaml

from relay_ai.template_registry.loader import load_and_validate, load_schema, load_template_yaml


@pytest.fixture
def temp_templates(tmp_path, monkeypatch):
    """Create temporary template and schema files."""
    # Setup paths
    registry_dir = tmp_path / "registry"
    schemas_dir = tmp_path / "schemas"
    registry_dir.mkdir()
    schemas_dir.mkdir()

    monkeypatch.setenv("TEMPLATE_REGISTRY_PATH", str(registry_dir))
    monkeypatch.setenv("TEMPLATE_SCHEMAS_PATH", str(schemas_dir))

    # Create template YAML
    template_yaml = registry_dir / "test_1.0.yaml"
    template_yaml.write_text(
        yaml.dump(
            {
                "workflow_ref": "inbox_drive_sweep",
                "description": "Test template",
                "parameters": {"max_tokens": 1000},
            }
        )
    )

    # Create schema JSON
    schema_json = schemas_dir / "test_1.0.schema.json"
    schema_json.write_text(
        json.dumps(
            {
                "fields": {
                    "input1": {"type": "string", "required": True},
                    "input2": {"type": "int", "required": False, "default": 10},
                }
            }
        )
    )

    return registry_dir, schemas_dir


def test_load_template_yaml(temp_templates):
    """Test loading template YAML."""
    template_def = load_template_yaml("test", "1.0")

    assert template_def["workflow_ref"] == "inbox_drive_sweep"
    assert template_def["description"] == "Test template"


def test_load_schema(temp_templates):
    """Test loading schema."""
    schema = load_schema("test_1.0.schema.json")

    assert "fields" in schema
    assert "input1" in schema["fields"]


def test_load_and_validate_success(temp_templates, monkeypatch):
    """Test successful load and validation."""
    # Register template
    from src.template_registry.registry import register

    monkeypatch.setenv("USER_RBAC_ROLE", "Author")
    register(
        name="test",
        version="1.0",
        workflow_ref="inbox_drive_sweep",
        schema_ref="test_1.0.schema.json",
    )

    # Load and validate
    template_def, resolved_params = load_and_validate("test", "1.0", {"input1": "value1"})

    assert template_def["workflow_ref"] == "inbox_drive_sweep"
    assert resolved_params["input1"] == "value1"
    assert resolved_params["input2"] == 10  # Default applied


def test_load_and_validate_failure(temp_templates, monkeypatch):
    """Test validation failure."""
    from src.template_registry.registry import register

    monkeypatch.setenv("USER_RBAC_ROLE", "Author")
    register(
        name="test",
        version="1.0",
        workflow_ref="inbox_drive_sweep",
        schema_ref="test_1.0.schema.json",
    )

    # Missing required param
    with pytest.raises(ValueError, match="Parameter validation failed"):
        load_and_validate("test", "1.0", {})


def test_load_and_validate_deprecated(temp_templates, monkeypatch):
    """Test loading deprecated template fails."""
    from src.template_registry.registry import deprecate, register

    monkeypatch.setenv("USER_RBAC_ROLE", "Author")
    register(name="test", version="1.0", workflow_ref="inbox_drive_sweep")
    deprecate("test", "1.0", "Superseded")

    with pytest.raises(ValueError, match="is deprecated"):
        load_and_validate("test", "1.0", {})


def test_load_and_validate_no_schema(temp_templates, monkeypatch):
    """Test loading template without schema."""
    from src.template_registry.registry import register

    monkeypatch.setenv("USER_RBAC_ROLE", "Author")
    register(name="test", version="1.0", workflow_ref="inbox_drive_sweep")

    # Should succeed without schema
    template_def, resolved_params = load_and_validate("test", "1.0", {"any": "param"})

    assert resolved_params == {"any": "param"}


def test_load_template_not_found(temp_templates):
    """Test loading non-existent template."""
    with pytest.raises(FileNotFoundError, match="Template file not found"):
        load_template_yaml("nonexistent", "1.0")


def test_load_schema_not_found(temp_templates):
    """Test loading non-existent schema."""
    with pytest.raises(FileNotFoundError, match="Schema file not found"):
        load_schema("nonexistent.json")
