"""Connector registry for dynamic discovery and loading.

Manages connector registration via JSONL append-only log.
"""

import importlib
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from .base import Connector


def get_registry_path() -> Path:
    """Get connector registry JSONL path from environment.

    Returns:
        Path to connector registry file
    """
    return Path(os.environ.get("CONNECTOR_REGISTRY_PATH", "logs/connectors.jsonl"))


def register_connector(
    connector_id: str,
    module: str,
    class_name: str,
    enabled: bool = True,
    auth_type: str = "env",
    scopes: Optional[list[str]] = None,
) -> dict:
    """Register connector in JSONL registry.

    Args:
        connector_id: Unique connector identifier
        module: Python module path (e.g., "src.connectors.sandbox")
        class_name: Class name within module
        enabled: Whether connector is enabled
        auth_type: Authentication type (env, oauth, api_key)
        scopes: List of permission scopes (read, write, etc.)

    Returns:
        Registry entry dict
    """
    registry_path = get_registry_path()
    registry_path.parent.mkdir(parents=True, exist_ok=True)

    now = datetime.now().isoformat()
    entry = {
        "connector_id": connector_id,
        "module": module,
        "class_name": class_name,
        "enabled": enabled,
        "auth_type": auth_type,
        "scopes": scopes or ["read"],
        "created_at": now,
        "updated_at": now,
    }

    # Append to JSONL
    with open(registry_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")

    return entry


def load_connector(connector_id: str, tenant_id: str, user_id: str) -> Optional[Connector]:
    """Load connector instance by ID.

    Args:
        connector_id: Connector identifier
        tenant_id: Tenant for isolation
        user_id: User for RBAC

    Returns:
        Connector instance or None if not found/disabled
    """
    entry = _get_latest_entry(connector_id)
    if not entry or not entry.get("enabled", False):
        return None

    try:
        # Dynamic import
        module = importlib.import_module(entry["module"])
        connector_class = getattr(module, entry["class_name"])

        # Instantiate connector
        return connector_class(connector_id=connector_id, tenant_id=tenant_id, user_id=user_id)
    except (ImportError, AttributeError) as e:
        print(f"Error loading connector {connector_id}: {e}")
        return None


def list_enabled_connectors() -> list[dict]:
    """List all enabled connectors.

    Returns:
        List of enabled connector entries
    """
    registry_path = get_registry_path()
    if not registry_path.exists():
        return []

    connectors = {}
    with open(registry_path, encoding="utf-8") as f:
        for line in f:
            entry = json.loads(line.strip())
            connector_id = entry["connector_id"]
            connectors[connector_id] = entry

    # Return only enabled
    return [entry for entry in connectors.values() if entry.get("enabled", False)]


def disable_connector(connector_id: str) -> bool:
    """Disable connector by appending updated entry.

    Args:
        connector_id: Connector to disable

    Returns:
        True if successful, False if not found
    """
    entry = _get_latest_entry(connector_id)
    if not entry:
        return False

    # Update and append
    entry["enabled"] = False
    entry["updated_at"] = datetime.now().isoformat()

    registry_path = get_registry_path()
    with open(registry_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")

    return True


def enable_connector(connector_id: str) -> bool:
    """Enable connector by appending updated entry.

    Args:
        connector_id: Connector to enable

    Returns:
        True if successful, False if not found
    """
    entry = _get_latest_entry(connector_id)
    if not entry:
        return False

    # Update and append
    entry["enabled"] = True
    entry["updated_at"] = datetime.now().isoformat()

    registry_path = get_registry_path()
    with open(registry_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")

    return True


def _get_latest_entry(connector_id: str) -> Optional[dict]:
    """Get latest registry entry for connector (last-wins).

    Args:
        connector_id: Connector identifier

    Returns:
        Latest entry or None if not found
    """
    registry_path = get_registry_path()
    if not registry_path.exists():
        return None

    latest = None
    with open(registry_path, encoding="utf-8") as f:
        for line in f:
            entry = json.loads(line.strip())
            if entry["connector_id"] == connector_id:
                latest = entry

    return latest
