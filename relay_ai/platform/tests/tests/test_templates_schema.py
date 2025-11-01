"""Tests for template schema validation."""


import pytest

from src.templates import TemplateDef, TemplateValidationError, _parse_template, list_templates


def test_valid_templates_load():
    """All default templates should load without errors."""
    templates = list_templates()
    assert len(templates) >= 3, "Should have at least 3 default templates"

    for tmpl in templates:
        assert isinstance(tmpl, TemplateDef)
        assert tmpl.name
        assert tmpl.version
        assert tmpl.description
        assert tmpl.context in ("markdown", "docx", "html")
        assert len(tmpl.inputs) > 0


def test_template_version_format():
    """Templates should have semantic version format."""
    templates = list_templates()

    for tmpl in templates:
        assert "." in tmpl.version, f"{tmpl.name} version should be X.Y format"
        parts = tmpl.version.split(".")
        assert len(parts) == 2, f"{tmpl.name} version should be major.minor"
        assert parts[0].isdigit() and parts[1].isdigit()


def test_template_inputs_have_required_fields():
    """All template inputs should have id, label, and type."""
    templates = list_templates()

    for tmpl in templates:
        for inp in tmpl.inputs:
            assert inp.id, f"Input in {tmpl.name} missing id"
            assert inp.label, f"Input {inp.id} in {tmpl.name} missing label"
            assert inp.type in (
                "string",
                "text",
                "int",
                "float",
                "bool",
                "enum",
                "date",
                "email",
                "url",
                "multiselect",
            ), f"Input {inp.id} has invalid type: {inp.type}"


def test_enum_inputs_have_choices():
    """Enum and multiselect inputs should have choices validator."""
    templates = list_templates()

    for tmpl in templates:
        for inp in tmpl.inputs:
            if inp.type in ("enum", "multiselect"):
                assert "choices" in inp.validators, f"Enum/multiselect {inp.id} in {tmpl.name} missing choices"
                assert isinstance(inp.validators["choices"], list)
                assert len(inp.validators["choices"]) > 0


def test_invalid_template_missing_required_field(tmp_path):
    """Template missing required field should raise validation error."""
    invalid_yaml = tmp_path / "invalid.yaml"
    invalid_yaml.write_text(
        """
name: Test Template
description: Missing version and other required fields
"""
    )

    with pytest.raises(TemplateValidationError) as exc_info:
        _parse_template(invalid_yaml)

    assert "version" in str(exc_info.value).lower()


def test_invalid_template_wrong_context(tmp_path):
    """Template with invalid context should raise validation error."""
    invalid_yaml = tmp_path / "invalid.yaml"
    invalid_yaml.write_text(
        """
name: Test Template
version: "1.0"
description: Test
context: invalid_context
inputs: []
rendering:
  body: "Test"
"""
    )

    with pytest.raises(TemplateValidationError) as exc_info:
        _parse_template(invalid_yaml)

    assert "context" in str(exc_info.value).lower()


def test_invalid_template_bad_input_type(tmp_path):
    """Template with invalid input type should raise validation error."""
    invalid_yaml = tmp_path / "invalid.yaml"
    invalid_yaml.write_text(
        """
name: Test Template
version: "1.0"
description: Test
context: markdown
inputs:
  - id: test_field
    label: Test
    type: invalid_type
rendering:
  body: "Test {{test_field}}"
"""
    )

    with pytest.raises(TemplateValidationError) as exc_info:
        _parse_template(invalid_yaml)

    assert "type" in str(exc_info.value).lower()


def test_template_body_required(tmp_path):
    """Template without rendering body should raise validation error."""
    invalid_yaml = tmp_path / "invalid.yaml"
    invalid_yaml.write_text(
        """
name: Test Template
version: "1.0"
description: Test
context: markdown
inputs: []
rendering:
  something_else: "Not body"
"""
    )

    with pytest.raises(TemplateValidationError) as exc_info:
        _parse_template(invalid_yaml)

    assert "body" in str(exc_info.value).lower()
