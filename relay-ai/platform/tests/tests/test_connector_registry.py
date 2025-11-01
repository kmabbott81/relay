"""Tests for connector registry."""

import json
import os
from pathlib import Path

import pytest

from src.connectors.registry import (
    disable_connector,
    enable_connector,
    get_registry_path,
    list_enabled_connectors,
    load_connector,
    register_connector,
)


@pytest.fixture
def temp_registry(tmp_path, monkeypatch):
    """Temporary connector registry."""
    registry_path = tmp_path / "connectors.jsonl"
    monkeypatch.setenv("CONNECTOR_REGISTRY_PATH", str(registry_path))
    return registry_path


def test_get_registry_path_default():
    """Registry path defaults to logs/connectors.jsonl."""
    if "CONNECTOR_REGISTRY_PATH" in os.environ:
        del os.environ["CONNECTOR_REGISTRY_PATH"]

    path = get_registry_path()
    assert path == Path("logs/connectors.jsonl")


def test_get_registry_path_from_env(monkeypatch):
    """Registry path reads from environment."""
    monkeypatch.setenv("CONNECTOR_REGISTRY_PATH", "/custom/path.jsonl")

    path = get_registry_path()
    assert path == Path("/custom/path.jsonl")


def test_register_connector_creates_file(temp_registry):
    """Registering connector creates JSONL file."""
    entry = register_connector(
        connector_id="test-conn",
        module="src.connectors.sandbox",
        class_name="SandboxConnector",
        enabled=True,
        auth_type="env",
        scopes=["read", "write"],
    )

    assert temp_registry.exists()
    assert entry["connector_id"] == "test-conn"
    assert entry["module"] == "src.connectors.sandbox"
    assert entry["class_name"] == "SandboxConnector"
    assert entry["enabled"] is True
    assert entry["scopes"] == ["read", "write"]


def test_register_connector_appends_to_jsonl(temp_registry):
    """Registering multiple connectors appends to JSONL."""
    register_connector("conn1", "mod1", "Class1")
    register_connector("conn2", "mod2", "Class2")

    lines = temp_registry.read_text().strip().split("\n")
    assert len(lines) == 2

    entry1 = json.loads(lines[0])
    entry2 = json.loads(lines[1])

    assert entry1["connector_id"] == "conn1"
    assert entry2["connector_id"] == "conn2"


def test_list_enabled_connectors_empty(temp_registry):
    """Listing connectors returns empty list if none registered."""
    connectors = list_enabled_connectors()
    assert connectors == []


def test_list_enabled_connectors_returns_enabled(temp_registry):
    """Listing connectors returns only enabled ones."""
    register_connector("conn1", "mod1", "Class1", enabled=True)
    register_connector("conn2", "mod2", "Class2", enabled=False)
    register_connector("conn3", "mod3", "Class3", enabled=True)

    connectors = list_enabled_connectors()
    assert len(connectors) == 2
    assert connectors[0]["connector_id"] == "conn1"
    assert connectors[1]["connector_id"] == "conn3"


def test_list_enabled_connectors_last_wins(temp_registry):
    """Last entry wins for duplicate connector IDs."""
    register_connector("conn1", "mod1", "Class1", enabled=True)
    register_connector("conn1", "mod2", "Class2", enabled=False)

    connectors = list_enabled_connectors()
    assert len(connectors) == 0  # Latest entry disabled it


def test_disable_connector_appends_update(temp_registry):
    """Disabling connector appends updated entry."""
    register_connector("conn1", "mod1", "Class1", enabled=True)

    success = disable_connector("conn1")
    assert success is True

    lines = temp_registry.read_text().strip().split("\n")
    assert len(lines) == 2

    latest = json.loads(lines[1])
    assert latest["enabled"] is False


def test_disable_connector_not_found(temp_registry):
    """Disabling non-existent connector returns False."""
    success = disable_connector("nonexistent")
    assert success is False


def test_enable_connector_appends_update(temp_registry):
    """Enabling connector appends updated entry."""
    register_connector("conn1", "mod1", "Class1", enabled=False)

    success = enable_connector("conn1")
    assert success is True

    lines = temp_registry.read_text().strip().split("\n")
    assert len(lines) == 2

    latest = json.loads(lines[1])
    assert latest["enabled"] is True


def test_load_connector_not_found(temp_registry):
    """Loading non-existent connector returns None."""
    connector = load_connector("nonexistent", "tenant1", "user1")
    assert connector is None


def test_load_connector_disabled(temp_registry):
    """Loading disabled connector returns None."""
    register_connector("conn1", "mod1", "Class1", enabled=False)

    connector = load_connector("conn1", "tenant1", "user1")
    assert connector is None


def test_load_connector_success(temp_registry):
    """Loading enabled sandbox connector succeeds."""
    register_connector(
        connector_id="sandbox",
        module="src.connectors.sandbox",
        class_name="SandboxConnector",
        enabled=True,
    )

    connector = load_connector("sandbox", "tenant1", "user1")
    assert connector is not None
    assert connector.connector_id == "sandbox"
    assert connector.tenant_id == "tenant1"
    assert connector.user_id == "user1"


def test_load_connector_invalid_module(temp_registry):
    """Loading connector with invalid module returns None."""
    register_connector("bad", "nonexistent.module", "Class", enabled=True)

    connector = load_connector("bad", "tenant1", "user1")
    assert connector is None


def test_load_connector_invalid_class(temp_registry):
    """Loading connector with invalid class returns None."""
    register_connector("bad", "src.connectors.sandbox", "NonExistentClass", enabled=True)

    connector = load_connector("bad", "tenant1", "user1")
    assert connector is None
