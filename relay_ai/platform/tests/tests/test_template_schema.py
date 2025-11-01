"""
Tests for Template Schema Validation (Sprint 32)

Covers type checking, defaults, bounds, enums, and error messages.
"""


from src.template_registry.schemas import validate


def test_validate_required_field():
    """Test required field validation."""
    schema = {"fields": {"name": {"type": "string", "required": True}}}

    # Missing required field
    valid, errors, resolved = validate(schema, {})
    assert not valid
    assert "Required parameter missing: name" in errors

    # Provided required field
    valid, errors, resolved = validate(schema, {"name": "test"})
    assert valid
    assert resolved["name"] == "test"


def test_validate_defaults():
    """Test default value resolution."""
    schema = {
        "fields": {
            "name": {"type": "string", "required": False, "default": "default_name"},
            "count": {"type": "int", "required": False, "default": 10},
        }
    }

    # No params provided - should use defaults
    valid, errors, resolved = validate(schema, {})
    assert valid
    assert resolved["name"] == "default_name"
    assert resolved["count"] == 10

    # Params provided - should override defaults
    valid, errors, resolved = validate(schema, {"name": "custom", "count": 5})
    assert valid
    assert resolved["name"] == "custom"
    assert resolved["count"] == 5


def test_validate_string_type():
    """Test string type validation."""
    schema = {"fields": {"name": {"type": "string", "required": True}}}

    # Valid string
    valid, errors, resolved = validate(schema, {"name": "test"})
    assert valid

    # Invalid type
    valid, errors, resolved = validate(schema, {"name": 123})
    assert not valid
    assert "expected string" in errors[0]


def test_validate_int_type():
    """Test integer type validation."""
    schema = {"fields": {"count": {"type": "int", "required": True}}}

    # Valid int
    valid, errors, resolved = validate(schema, {"count": 42})
    assert valid

    # Invalid type
    valid, errors, resolved = validate(schema, {"count": "42"})
    assert not valid
    assert "expected int" in errors[0]

    # Bool should not be accepted as int
    valid, errors, resolved = validate(schema, {"count": True})
    assert not valid


def test_validate_int_bounds():
    """Test integer min/max bounds."""
    schema = {"fields": {"count": {"type": "int", "required": True, "min": 1, "max": 10}}}

    # Valid (within bounds)
    valid, errors, resolved = validate(schema, {"count": 5})
    assert valid

    # Below min
    valid, errors, resolved = validate(schema, {"count": 0})
    assert not valid
    assert "below minimum" in errors[0]

    # Above max
    valid, errors, resolved = validate(schema, {"count": 11})
    assert not valid
    assert "above maximum" in errors[0]


def test_validate_float_type():
    """Test float type validation."""
    schema = {"fields": {"value": {"type": "float", "required": True}}}

    # Valid float
    valid, errors, resolved = validate(schema, {"value": 3.14})
    assert valid

    # Valid int (should be accepted for float)
    valid, errors, resolved = validate(schema, {"value": 42})
    assert valid

    # Invalid type
    valid, errors, resolved = validate(schema, {"value": "3.14"})
    assert not valid


def test_validate_bool_type():
    """Test boolean type validation."""
    schema = {"fields": {"flag": {"type": "bool", "required": True}}}

    # Valid bool
    valid, errors, resolved = validate(schema, {"flag": True})
    assert valid

    valid, errors, resolved = validate(schema, {"flag": False})
    assert valid

    # Invalid type
    valid, errors, resolved = validate(schema, {"flag": 1})
    assert not valid


def test_validate_enum():
    """Test enum validation."""
    schema = {
        "fields": {
            "priority": {
                "type": "enum",
                "required": True,
                "enum": ["low", "medium", "high"],
            }
        }
    }

    # Valid enum value
    valid, errors, resolved = validate(schema, {"priority": "high"})
    assert valid

    # Invalid enum value
    valid, errors, resolved = validate(schema, {"priority": "critical"})
    assert not valid
    assert "not in enum" in errors[0]


def test_validate_unknown_param():
    """Test that unknown parameters are rejected."""
    schema = {"fields": {"name": {"type": "string"}}}

    # Unknown param provided
    valid, errors, resolved = validate(schema, {"name": "test", "unknown": "value"})
    assert not valid
    assert "Unknown parameter: unknown" in errors


def test_validate_multiple_errors():
    """Test that multiple errors are collected."""
    schema = {
        "fields": {
            "name": {"type": "string", "required": True},
            "count": {"type": "int", "required": True, "min": 1, "max": 10},
        }
    }

    # Multiple errors
    valid, errors, resolved = validate(schema, {"count": 0, "unknown": "value"})
    assert not valid
    assert len(errors) >= 2  # Missing name, count below min, unknown param


def test_validate_empty_schema():
    """Test validation with no fields defined."""
    schema = {"fields": {}}

    # No params required or allowed
    valid, errors, resolved = validate(schema, {})
    assert valid

    # Param provided for empty schema
    valid, errors, resolved = validate(schema, {"param": "value"})
    assert not valid
    assert "Unknown parameter" in errors[0]


def test_validate_float_bounds():
    """Test float min/max bounds."""
    schema = {"fields": {"value": {"type": "float", "required": True, "min": 0.0, "max": 1.0}}}

    # Valid
    valid, errors, resolved = validate(schema, {"value": 0.5})
    assert valid

    # Below min
    valid, errors, resolved = validate(schema, {"value": -0.1})
    assert not valid
    assert "below minimum" in errors[0]

    # Above max
    valid, errors, resolved = validate(schema, {"value": 1.5})
    assert not valid
    assert "above maximum" in errors[0]
