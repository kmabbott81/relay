"""
Template Loader (Sprint 32)

Loads templates from YAML and validates parameters using schemas.
"""

import json
import os
from pathlib import Path
from typing import Any

import yaml

from .registry import get
from .schemas import validate


def get_template_path(name: str, version: str) -> Path:
    """Get template YAML file path."""
    registry_dir = Path(os.getenv("TEMPLATE_REGISTRY_PATH", "templates/registry"))
    return registry_dir / f"{name}_{version}.yaml"


def get_schema_path(schema_ref: str) -> Path:
    """Get schema file path."""
    schemas_dir = Path(os.getenv("TEMPLATE_SCHEMAS_PATH", "templates/schemas"))
    # schema_ref can be .json or .yaml
    return schemas_dir / schema_ref


def load_template_yaml(name: str, version: str) -> dict[str, Any]:
    """
    Load template YAML file.

    Args:
        name: Template name
        version: Template version

    Returns:
        Template definition dict

    Raises:
        FileNotFoundError: If template file not found
    """
    template_path = get_template_path(name, version)

    if not template_path.exists():
        raise FileNotFoundError(f"Template file not found: {template_path}")

    with open(template_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_schema(schema_ref: str) -> dict[str, Any]:
    """
    Load schema definition.

    Args:
        schema_ref: Schema file reference (e.g., "my_schema.json")

    Returns:
        Schema definition dict

    Raises:
        FileNotFoundError: If schema file not found
    """
    schema_path = get_schema_path(schema_ref)

    if not schema_path.exists():
        raise FileNotFoundError(f"Schema file not found: {schema_path}")

    with open(schema_path, encoding="utf-8") as f:
        if schema_path.suffix == ".json":
            return json.load(f)
        else:
            # Assume YAML
            return yaml.safe_load(f)


def load_and_validate(
    name: str, version: str | None, user_params: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    """
    Load template, validate parameters, and resolve defaults.

    Args:
        name: Template name
        version: Template version (None for latest active)
        user_params: User-provided parameters

    Returns:
        Tuple of (template_def, resolved_params)

    Raises:
        ValueError: If template not found or validation fails
    """
    # Get template from registry
    template_record = get(name, version)

    if not template_record:
        if version:
            raise ValueError(f"Template {name}:{version} not found in registry")
        else:
            raise ValueError(f"Template {name} not found in registry")

    # Check if deprecated
    if template_record.get("status") == "deprecated":
        reason = template_record.get("deprecation_reason", "No reason provided")
        raise ValueError(f"Template {name}:{template_record['version']} is deprecated: {reason}")

    # Load template definition
    template_def = load_template_yaml(template_record["name"], template_record["version"])

    # Load schema if specified
    schema_ref = template_record.get("schema_ref")

    if schema_ref:
        schema = load_schema(schema_ref)

        # Validate params
        is_valid, errors, resolved_params = validate(schema, user_params)

        if not is_valid:
            error_msg = "\n".join(errors)
            raise ValueError(f"Parameter validation failed:\n{error_msg}")

        return template_def, resolved_params

    # No schema, return params as-is
    return template_def, user_params
