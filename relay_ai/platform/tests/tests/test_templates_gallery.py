"""Tests for template gallery and cloning."""

import tempfile
from pathlib import Path

import pytest
import yaml

from relay_ai.templates import (
    CUSTOM_TEMPLATES_DIR,
    InputDef,
    TemplateDef,
    clone_template,
    delete_custom_template,
    list_templates,
    update_template_yaml,
)


def create_test_template_file(version: str = "1.0") -> Path:
    """Helper to create a test template file."""
    template_data = {
        "name": "Test Template",
        "version": version,
        "description": "Test description",
        "context": "markdown",
        "inputs": [{"id": "name", "label": "Name", "type": "string", "required": True}],
        "rendering": {"body": "Hello {{name}}"},
    }

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False, encoding="utf-8") as f:
        yaml.dump(template_data, f)
        return Path(f.name)


def test_clone_template_creates_file():
    """Cloning should create a file in templates/custom/."""
    temp_path = create_test_template_file()

    source = TemplateDef(
        path=temp_path,
        name="Test Template",
        version="1.0",
        description="Test description",
        context="markdown",
        inputs=[InputDef(id="name", label="Name", type="string", required=True)],
        body="Hello {{name}}",
    )

    try:
        import time

        new_name = f"Cloned Template {int(time.time())}"

        cloned_path = clone_template(source, new_name, "Cloned description")

        try:
            assert cloned_path.exists()
            assert cloned_path.parent == CUSTOM_TEMPLATES_DIR
            assert cloned_path.suffix == ".yaml"

            content = cloned_path.read_text(encoding="utf-8")
            assert new_name in content
            assert "Cloned description" in content
            assert "1.1" in content  # Version bumped from 1.0 to 1.1
        finally:
            if cloned_path.exists():
                cloned_path.unlink()
    finally:
        temp_path.unlink()


def test_clone_template_increments_version():
    """Cloning should increment minor version."""
    temp_path = create_test_template_file(version="2.3")

    source = TemplateDef(
        path=temp_path,
        name="Test Template",
        version="2.3",
        description="Test",
        context="markdown",
        inputs=[],
        body="Hello",
    )

    try:
        import time

        new_name = f"Cloned V{int(time.time())}"
        cloned_path = clone_template(source, new_name)

        try:
            content = cloned_path.read_text(encoding="utf-8")
            assert "2.4" in content  # Version bumped from 2.3 to 2.4
        finally:
            cloned_path.unlink()
    finally:
        temp_path.unlink()


def test_clone_template_prevents_duplicate():
    """Cannot clone to existing filename."""
    temp_path = create_test_template_file()

    source = TemplateDef(
        path=temp_path,
        name="Test Template",
        version="1.0",
        description="Test",
        context="markdown",
        inputs=[],
        body="Hello",
    )

    try:
        import time

        new_name = f"Duplicate Test {int(time.time())}"
        cloned_path = clone_template(source, new_name)

        try:
            # Try to clone again with same name
            with pytest.raises(ValueError, match="already exists"):
                clone_template(source, new_name)
        finally:
            cloned_path.unlink()
    finally:
        temp_path.unlink()


def test_clone_template_invalid_name():
    """Invalid template name should raise error."""
    temp_path = create_test_template_file()

    source = TemplateDef(
        path=temp_path,
        name="Test Template",
        version="1.0",
        description="Test",
        context="markdown",
        inputs=[],
        body="Hello",
    )

    try:
        with pytest.raises(ValueError, match="Invalid template name"):
            clone_template(source, "!!!")  # Invalid characters
    finally:
        temp_path.unlink()


def test_update_template_yaml_validates():
    """Updating template should validate YAML."""
    temp_path = create_test_template_file()

    source = TemplateDef(
        path=temp_path,
        name="Test Template",
        version="1.0",
        description="Test",
        context="markdown",
        inputs=[],
        body="Hello",
    )

    try:
        import time

        new_name = f"Update Test {int(time.time())}"
        cloned_path = clone_template(source, new_name)

        try:
            # Valid update
            valid_yaml = """name: Updated Template
version: "1.2"
description: Updated description
context: markdown
inputs:
  - id: name
    label: Name
    type: string
    required: true
rendering:
  body: "Updated: Hello {{name}}"
"""
            success, errors = update_template_yaml(cloned_path, valid_yaml)

            assert success is True
            assert len(errors) == 0

            # Check file was updated
            content = cloned_path.read_text(encoding="utf-8")
            assert "Updated Template" in content
            assert "Updated description" in content
        finally:
            if cloned_path.exists():
                cloned_path.unlink()
    finally:
        temp_path.unlink()


def test_update_template_yaml_rejects_invalid():
    """Invalid YAML should be rejected with errors."""
    temp_path = create_test_template_file()

    source = TemplateDef(
        path=temp_path,
        name="Test Template",
        version="1.0",
        description="Test",
        context="markdown",
        inputs=[],
        body="Hello",
    )

    try:
        import time

        new_name = f"Invalid Test {int(time.time())}"
        cloned_path = clone_template(source, new_name)

        try:
            # Invalid YAML syntax
            invalid_yaml = "name: Broken\n  invalid indentation"
            success, errors = update_template_yaml(cloned_path, invalid_yaml)

            assert success is False
            assert len(errors) > 0
            # Just check that we got errors - message format may vary
            assert errors[0]  # Should have at least one non-empty error
        finally:
            if cloned_path.exists():
                cloned_path.unlink()
    finally:
        temp_path.unlink()


def test_update_template_yaml_blocks_builtin():
    """Cannot update built-in templates."""
    # Try to update a non-custom template
    builtin_path = Path("templates/some_template.yaml")

    yaml_content = "name: Hacked\nversion: '1.0'"
    success, errors = update_template_yaml(builtin_path, yaml_content)

    assert success is False
    assert len(errors) > 0
    assert any("built-in" in err.lower() or "clone" in err.lower() for err in errors)


def test_delete_custom_template():
    """Should be able to delete custom templates."""
    temp_path = create_test_template_file()

    source = TemplateDef(
        path=temp_path,
        name="Test Template",
        version="1.0",
        description="Test",
        context="markdown",
        inputs=[],
        body="Hello",
    )

    try:
        import time

        new_name = f"Delete Test {int(time.time())}"
        cloned_path = clone_template(source, new_name)

        assert cloned_path.exists()

        # Delete it
        success, error = delete_custom_template(cloned_path)

        assert success is True
        assert error == ""
        assert not cloned_path.exists()
    finally:
        temp_path.unlink()


def test_delete_blocks_builtin():
    """Cannot delete built-in templates."""
    builtin_path = Path("templates/some_template.yaml")

    success, error = delete_custom_template(builtin_path)

    assert success is False
    assert "built-in" in error.lower()


def test_cloned_template_appears_in_list():
    """Cloned templates should appear in list_templates()."""
    temp_path = create_test_template_file()

    source = TemplateDef(
        path=temp_path,
        name="Test Template",
        version="1.0",
        description="Test",
        context="markdown",
        inputs=[],
        body="Hello",
    )

    try:
        import time

        new_name = f"List Test {int(time.time())}"
        cloned_path = clone_template(source, new_name)

        try:
            # Reload templates
            templates = list_templates()

            # Find the cloned template
            found = any(t.name == new_name for t in templates)

            assert found, f"Cloned template '{new_name}' not found in list"
        finally:
            if cloned_path.exists():
                cloned_path.unlink()
    finally:
        temp_path.unlink()
