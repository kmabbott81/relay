"""Tests for template input validation and widget behavior."""

from pathlib import Path

from relay_ai.templates import InputDef, TemplateDef, validate_inputs


def create_test_template_with_inputs(inputs: list[InputDef]) -> TemplateDef:
    """Helper to create a template with specific inputs."""
    return TemplateDef(
        path=Path("test.yaml"),
        name="Test",
        version="1.0",
        description="Test",
        context="markdown",
        inputs=inputs,
        body="Test {{test}}",
    )


def test_required_field_validation():
    """Required fields should fail validation when empty."""
    template = create_test_template_with_inputs([InputDef(id="name", label="Name", type="string", required=True)])

    errors = validate_inputs(template, {"name": ""})
    assert len(errors) > 0
    assert "required" in errors[0].lower()

    errors = validate_inputs(template, {"name": None})
    assert len(errors) > 0

    errors = validate_inputs(template, {"name": "Valid"})
    assert len(errors) == 0


def test_int_min_max_validation():
    """Integer inputs should validate min/max constraints."""
    template = create_test_template_with_inputs(
        [InputDef(id="age", label="Age", type="int", validators={"min": 0, "max": 120})]
    )

    errors = validate_inputs(template, {"age": -5})
    assert len(errors) > 0
    assert "at least 0" in errors[0]

    errors = validate_inputs(template, {"age": 150})
    assert len(errors) > 0
    assert "at most 120" in errors[0]

    errors = validate_inputs(template, {"age": 25})
    assert len(errors) == 0


def test_float_min_max_validation():
    """Float inputs should validate min/max constraints."""
    template = create_test_template_with_inputs(
        [InputDef(id="price", label="Price", type="float", validators={"min": 0.0, "max": 1000.0})]
    )

    errors = validate_inputs(template, {"price": -1.5})
    assert len(errors) > 0

    errors = validate_inputs(template, {"price": 1500.0})
    assert len(errors) > 0

    errors = validate_inputs(template, {"price": 49.99})
    assert len(errors) == 0


def test_email_validation():
    """Email inputs should validate email format."""
    template = create_test_template_with_inputs([InputDef(id="email", label="Email", type="email")])

    errors = validate_inputs(template, {"email": "invalid"})
    assert len(errors) > 0
    assert "email" in errors[0].lower()

    errors = validate_inputs(template, {"email": "invalid@"})
    assert len(errors) > 0

    errors = validate_inputs(template, {"email": "@invalid.com"})
    assert len(errors) > 0

    errors = validate_inputs(template, {"email": "valid@example.com"})
    assert len(errors) == 0


def test_url_validation():
    """URL inputs should validate URL format."""
    template = create_test_template_with_inputs([InputDef(id="website", label="Website", type="url")])

    errors = validate_inputs(template, {"website": "invalid"})
    assert len(errors) > 0
    assert "url" in errors[0].lower()

    errors = validate_inputs(template, {"website": "example.com"})  # Missing protocol
    assert len(errors) > 0

    errors = validate_inputs(template, {"website": "https://example.com"})
    assert len(errors) == 0

    errors = validate_inputs(template, {"website": "http://example.org"})
    assert len(errors) == 0


def test_enum_validation():
    """Enum inputs should validate against choices."""
    template = create_test_template_with_inputs(
        [InputDef(id="priority", label="Priority", type="enum", validators={"choices": ["low", "medium", "high"]})]
    )

    errors = validate_inputs(template, {"priority": "invalid"})
    assert len(errors) > 0
    assert "one of" in errors[0].lower()

    errors = validate_inputs(template, {"priority": "medium"})
    assert len(errors) == 0


def test_multiselect_validation():
    """Multiselect inputs should validate all selections against choices."""
    template = create_test_template_with_inputs(
        [InputDef(id="tags", label="Tags", type="multiselect", validators={"choices": ["a", "b", "c"]})]
    )

    errors = validate_inputs(template, {"tags": ["a", "invalid"]})
    assert len(errors) > 0
    assert "invalid" in errors[0]

    errors = validate_inputs(template, {"tags": ["a", "b"]})
    assert len(errors) == 0

    errors = validate_inputs(template, {"tags": []})
    assert len(errors) == 0


def test_string_length_validation():
    """String inputs should validate min/max length."""
    template = create_test_template_with_inputs(
        [InputDef(id="title", label="Title", type="string", validators={"min": 3, "max": 50})]
    )

    errors = validate_inputs(template, {"title": "ab"})
    assert len(errors) > 0
    assert "at least 3 characters" in errors[0]

    errors = validate_inputs(template, {"title": "a" * 100})
    assert len(errors) > 0
    assert "at most 50 characters" in errors[0]

    errors = validate_inputs(template, {"title": "Valid Title"})
    assert len(errors) == 0


def test_text_length_validation():
    """Text inputs should validate min/max length."""
    template = create_test_template_with_inputs(
        [InputDef(id="description", label="Description", type="text", validators={"min": 10, "max": 200})]
    )

    errors = validate_inputs(template, {"description": "Short"})
    assert len(errors) > 0

    errors = validate_inputs(template, {"description": "a" * 250})
    assert len(errors) > 0

    errors = validate_inputs(template, {"description": "This is a valid description with enough text."})
    assert len(errors) == 0


def test_regex_validation():
    """Inputs with regex validators should validate pattern."""
    template = create_test_template_with_inputs(
        [InputDef(id="code", label="Code", type="string", validators={"regex": r"^[A-Z]{3}-\d{3}$"})]
    )

    errors = validate_inputs(template, {"code": "invalid"})
    assert len(errors) > 0
    assert "pattern" in errors[0].lower()

    errors = validate_inputs(template, {"code": "ABC-123"})
    assert len(errors) == 0


def test_multiple_validation_errors():
    """Multiple validation errors should all be reported."""
    template = create_test_template_with_inputs(
        [
            InputDef(id="name", label="Name", type="string", required=True),
            InputDef(id="age", label="Age", type="int", validators={"min": 0, "max": 120}),
            InputDef(id="email", label="Email", type="email"),
        ]
    )

    errors = validate_inputs(template, {"name": "", "age": 150, "email": "invalid"})

    assert len(errors) == 3
    assert any("required" in e.lower() for e in errors)
    assert any("at most" in e for e in errors)
    assert any("email" in e.lower() for e in errors)


def test_optional_fields_can_be_empty():
    """Optional fields should not fail validation when empty."""
    template = create_test_template_with_inputs(
        [InputDef(id="optional", label="Optional", type="string", required=False)]
    )

    errors = validate_inputs(template, {"optional": ""})
    assert len(errors) == 0

    errors = validate_inputs(template, {"optional": None})
    assert len(errors) == 0

    errors = validate_inputs(template, {})
    assert len(errors) == 0
