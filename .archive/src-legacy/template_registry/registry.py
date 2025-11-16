"""
Template Registry (Sprint 32)

JSONL-based registry for versioned workflow templates with RBAC enforcement.
"""

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def get_registry_path() -> Path:
    """Get registry file path."""
    registry_dir = Path(os.getenv("TEMPLATE_REGISTRY_PATH", "templates/registry"))
    registry_dir.mkdir(parents=True, exist_ok=True)
    return registry_dir / "templates.jsonl"


def get_rbac_role() -> str:
    """Get required RBAC role for write operations."""
    return os.getenv("TEMPLATE_RBAC_ROLE", "Author")


def check_rbac(operation: str) -> bool:
    """
    Check if user has permission for write operations.

    Args:
        operation: Operation name (for error messages)

    Returns:
        True if authorized

    Raises:
        PermissionError: If user lacks required role
    """
    user_role = os.getenv("USER_RBAC_ROLE", "Viewer")
    required_role = get_rbac_role()

    # Role hierarchy: Viewer < Author < Operator < Admin
    roles = {"Viewer": 0, "Author": 1, "Operator": 2, "Admin": 3}

    user_level = roles.get(user_role, 0)
    required_level = roles.get(required_role, 1)

    if user_level < required_level:
        raise PermissionError(f"{operation} requires {required_role} role, but user has {user_role}")

    return True


def register(
    name: str,
    version: str,
    workflow_ref: str,
    schema_ref: str | None = None,
    owner: str | None = None,
    tags: list[str] | None = None,
) -> dict[str, Any]:
    """
    Register a new template or update existing one.

    Args:
        name: Template name (unique identifier)
        version: Semantic version (e.g., "1.0.0")
        workflow_ref: Workflow function reference
        schema_ref: Schema file reference (optional)
        owner: Template owner (defaults to USER_RBAC_ROLE)
        tags: List of tags for categorization

    Returns:
        Template record

    Raises:
        PermissionError: If user lacks Author/Admin role
    """
    check_rbac("Template registration")

    registry_path = get_registry_path()

    # Generate unique ID
    template_id = f"{name}:{version}"

    # Get owner
    if owner is None:
        owner = os.getenv("USER_RBAC_ROLE", "Unknown")

    # Create record
    now = datetime.now(UTC).isoformat()
    record = {
        "id": template_id,
        "name": name,
        "version": version,
        "owner": owner,
        "created_at": now,
        "updated_at": now,
        "workflow_ref": workflow_ref,
        "schema_ref": schema_ref,
        "tags": tags or [],
        "status": "active",
    }

    # Append to registry
    with open(registry_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")

    return record


def list_templates(
    name: str | None = None,
    owner: str | None = None,
    tag: str | None = None,
    status: str | None = None,
) -> list[dict[str, Any]]:
    """
    List templates with optional filters.

    Args:
        name: Filter by template name
        owner: Filter by owner
        tag: Filter by tag (must be in tags list)
        status: Filter by status (active, deprecated)

    Returns:
        List of template records (most recent first)
    """
    registry_path = get_registry_path()

    if not registry_path.exists():
        return []

    # Build index: template_id -> latest record
    templates: dict[str, dict[str, Any]] = {}

    with open(registry_path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                record = json.loads(line)
                template_id = record["id"]

                # Always keep latest record (last one wins in JSONL append-only log)
                templates[template_id] = record

    # Filter
    results = list(templates.values())

    if name:
        results = [t for t in results if t.get("name") == name]

    if owner:
        results = [t for t in results if t.get("owner") == owner]

    if tag:
        results = [t for t in results if tag in t.get("tags", [])]

    if status:
        results = [t for t in results if t.get("status") == status]

    # Sort by created_at descending
    results.sort(key=lambda x: x.get("created_at", ""), reverse=True)

    return results


def get(name: str, version: str | None = None) -> dict[str, Any] | None:
    """
    Get template by name and optional version.

    Args:
        name: Template name
        version: Template version (if None, returns latest active version)

    Returns:
        Template record or None if not found
    """
    templates = list_templates(name=name)

    if not templates:
        return None

    if version:
        # Find exact version
        for template in templates:
            if template["version"] == version:
                return template
        return None

    # Return latest active version
    active = [t for t in templates if t.get("status") == "active"]
    if active:
        # Already sorted by created_at descending
        return active[0]

    # No active versions, return latest regardless of status
    return templates[0] if templates else None


def deprecate(name: str, version: str, reason: str) -> dict[str, Any]:
    """
    Deprecate a template version.

    Args:
        name: Template name
        version: Template version
        reason: Deprecation reason

    Returns:
        Updated template record

    Raises:
        PermissionError: If user lacks Author/Admin role
        ValueError: If template not found
    """
    check_rbac("Template deprecation")

    template = get(name, version)

    if not template:
        raise ValueError(f"Template {name}:{version} not found")

    registry_path = get_registry_path()

    # Create updated record
    updated = template.copy()
    updated["status"] = "deprecated"
    updated["updated_at"] = datetime.now(UTC).isoformat()
    updated["deprecation_reason"] = reason

    # Append to registry
    with open(registry_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(updated) + "\n")

    return updated
