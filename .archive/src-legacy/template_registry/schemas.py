"""
Parameter Schema Validation (Sprint 32)

Pure Python validation without pydantic dependency.
Supports typed parameters with defaults, enums, and bounds.
"""

from typing import Any


def validate(schema: dict[str, Any], params: dict[str, Any]) -> tuple[bool, list[str], dict[str, Any]]:
    """
    Validate parameters against schema and resolve defaults.

    Args:
        schema: Schema definition with fields
        params: User-provided parameters

    Returns:
        Tuple of (is_valid, errors, resolved_params)
        - is_valid: True if validation passed
        - errors: List of error messages
        - resolved_params: Parameters with defaults applied

    Schema format:
        {
            "fields": {
                "key": {
                    "type": "string|int|float|bool|enum",
                    "required": bool,
                    "default": any,
                    "enum": list,  # For enum type
                    "min": number,  # For int/float
                    "max": number,  # For int/float
                    "description": str  # Optional
                }
            }
        }
    """
    errors = []
    resolved = {}

    fields = schema.get("fields", {})

    # Check all provided params are in schema
    for key in params:
        if key not in fields:
            errors.append(f"Unknown parameter: {key}")

    # Validate each field
    for field_name, field_spec in fields.items():
        value = params.get(field_name)

        # Check required
        if field_spec.get("required", False) and value is None:
            if "default" in field_spec:
                # Use default
                resolved[field_name] = field_spec["default"]
            else:
                errors.append(f"Required parameter missing: {field_name}")
            continue

        # If not provided and not required, use default or skip
        if value is None:
            if "default" in field_spec:
                resolved[field_name] = field_spec["default"]
            continue

        # Type validation
        field_type = field_spec.get("type", "string")

        if field_type == "string":
            if not isinstance(value, str):
                errors.append(f"{field_name}: expected string, got {type(value).__name__}")
                continue

        elif field_type == "int":
            if not isinstance(value, int) or isinstance(value, bool):
                # In Python, bool is a subclass of int, so exclude it
                errors.append(f"{field_name}: expected int, got {type(value).__name__}")
                continue

            # Check min/max bounds
            if "min" in field_spec and value < field_spec["min"]:
                errors.append(f"{field_name}: value {value} below minimum {field_spec['min']}")
                continue

            if "max" in field_spec and value > field_spec["max"]:
                errors.append(f"{field_name}: value {value} above maximum {field_spec['max']}")
                continue

        elif field_type == "float":
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                errors.append(f"{field_name}: expected float, got {type(value).__name__}")
                continue

            # Check min/max bounds
            if "min" in field_spec and value < field_spec["min"]:
                errors.append(f"{field_name}: value {value} below minimum {field_spec['min']}")
                continue

            if "max" in field_spec and value > field_spec["max"]:
                errors.append(f"{field_name}: value {value} above maximum {field_spec['max']}")
                continue

        elif field_type == "bool":
            if not isinstance(value, bool):
                errors.append(f"{field_name}: expected bool, got {type(value).__name__}")
                continue

        elif field_type == "enum":
            enum_values = field_spec.get("enum", [])
            if value not in enum_values:
                errors.append(f"{field_name}: value '{value}' not in enum {enum_values}")
                continue

        else:
            errors.append(f"{field_name}: unknown type '{field_type}'")
            continue

        # Add validated value
        resolved[field_name] = value

    is_valid = len(errors) == 0
    return is_valid, errors, resolved
