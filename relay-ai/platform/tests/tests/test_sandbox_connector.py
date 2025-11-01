"""Tests for sandbox connector."""


import pytest

from src.connectors.sandbox import SandboxConnector


@pytest.fixture
def sandbox(monkeypatch):
    """Sandbox connector with admin role."""
    monkeypatch.setattr("src.connectors.base.get_team_role", lambda u, t: "Admin")
    monkeypatch.setenv("SANDBOX_LATENCY_MS", "0")
    monkeypatch.setenv("SANDBOX_ERROR_RATE", "0.0")
    return SandboxConnector("sandbox", "tenant1", "user1")


def test_sandbox_initialization(sandbox):
    """Sandbox connector initializes correctly."""
    assert sandbox.connector_id == "sandbox"
    assert sandbox.tenant_id == "tenant1"
    assert sandbox.user_id == "user1"
    assert sandbox.latency_ms == 0
    assert sandbox.error_rate == 0.0
    assert sandbox.resources == {}


def test_sandbox_latency_from_env(monkeypatch):
    """Sandbox reads latency from environment."""
    monkeypatch.setenv("SANDBOX_LATENCY_MS", "100")
    monkeypatch.setattr("src.connectors.base.get_team_role", lambda u, t: "Admin")

    sandbox = SandboxConnector("sandbox", "tenant1", "user1")
    assert sandbox.latency_ms == 100


def test_sandbox_error_rate_from_env(monkeypatch):
    """Sandbox reads error rate from environment."""
    monkeypatch.setenv("SANDBOX_ERROR_RATE", "0.5")
    monkeypatch.setattr("src.connectors.base.get_team_role", lambda u, t: "Admin")

    sandbox = SandboxConnector("sandbox", "tenant1", "user1")
    assert sandbox.error_rate == 0.5


def test_sandbox_connect_success(sandbox):
    """Sandbox connect succeeds."""
    result = sandbox.connect()

    assert result.status == "success"
    assert result.message == "Connected to sandbox"
    assert sandbox.connected is True


def test_sandbox_connect_rbac_denied(monkeypatch):
    """Sandbox connect fails without sufficient role."""
    monkeypatch.setattr("src.connectors.base.get_team_role", lambda u, t: "Viewer")

    sandbox = SandboxConnector("sandbox", "tenant1", "user1")
    result = sandbox.connect()

    assert result.status == "denied"
    assert "lacks Operator role" in result.message


def test_sandbox_disconnect(sandbox):
    """Sandbox disconnect succeeds."""
    sandbox.connect()
    result = sandbox.disconnect()

    assert result.status == "success"
    assert result.message == "Disconnected from sandbox"
    assert sandbox.connected is False


def test_sandbox_create_resource(sandbox):
    """Sandbox create resource works."""
    sandbox.connect()

    payload = {"id": "item1", "name": "Test Item", "value": 42}
    result = sandbox.create_resource("items", payload)

    assert result.status == "success"
    assert result.data == payload
    assert "Created items/item1" in result.message


def test_sandbox_create_without_id(sandbox):
    """Sandbox create requires 'id' field."""
    sandbox.connect()

    result = sandbox.create_resource("items", {"name": "No ID"})

    assert result.status == "error"
    assert "must include 'id' field" in result.message


def test_sandbox_list_resources_empty(sandbox):
    """Sandbox list returns empty for new resource type."""
    sandbox.connect()

    result = sandbox.list_resources("items")

    assert result.status == "success"
    assert result.data == []
    assert "Listed 0 items" in result.message


def test_sandbox_list_resources_populated(sandbox):
    """Sandbox list returns created resources."""
    sandbox.connect()
    sandbox.create_resource("items", {"id": "item1", "name": "Item 1"})
    sandbox.create_resource("items", {"id": "item2", "name": "Item 2"})

    result = sandbox.list_resources("items")

    assert result.status == "success"
    assert len(result.data) == 2
    assert result.data[0]["id"] == "item1"
    assert result.data[1]["id"] == "item2"


def test_sandbox_get_resource(sandbox):
    """Sandbox get retrieves created resource."""
    sandbox.connect()
    payload = {"id": "item1", "name": "Test Item"}
    sandbox.create_resource("items", payload)

    result = sandbox.get_resource("items", "item1")

    assert result.status == "success"
    assert result.data == payload


def test_sandbox_get_resource_not_found(sandbox):
    """Sandbox get returns error for missing resource."""
    sandbox.connect()

    result = sandbox.get_resource("items", "nonexistent")

    assert result.status == "error"
    assert "not found" in result.message


def test_sandbox_update_resource(sandbox):
    """Sandbox update modifies resource."""
    sandbox.connect()
    sandbox.create_resource("items", {"id": "item1", "name": "Original"})

    result = sandbox.update_resource("items", "item1", {"name": "Updated", "value": 100})

    assert result.status == "success"
    assert result.data["name"] == "Updated"
    assert result.data["value"] == 100
    assert result.data["id"] == "item1"


def test_sandbox_update_not_found(sandbox):
    """Sandbox update returns error for missing resource."""
    sandbox.connect()

    result = sandbox.update_resource("items", "nonexistent", {"name": "Test"})

    assert result.status == "error"
    assert "not found" in result.message


def test_sandbox_delete_resource(sandbox):
    """Sandbox delete removes resource."""
    sandbox.connect()
    sandbox.create_resource("items", {"id": "item1", "name": "To Delete"})

    result = sandbox.delete_resource("items", "item1")

    assert result.status == "success"
    assert "Deleted items/item1" in result.message

    # Verify resource is gone
    get_result = sandbox.get_resource("items", "item1")
    assert get_result.status == "error"


def test_sandbox_delete_not_found(sandbox):
    """Sandbox delete returns error for missing resource."""
    sandbox.connect()

    result = sandbox.delete_resource("items", "nonexistent")

    assert result.status == "error"
    assert "not found" in result.message


def test_sandbox_requires_connection(sandbox):
    """Sandbox operations require connection."""
    # Don't connect
    result = sandbox.list_resources("items")

    assert result.status == "error"
    assert result.message == "Not connected"


def test_sandbox_error_injection(monkeypatch):
    """Sandbox injects errors based on error rate."""
    monkeypatch.setattr("src.connectors.base.get_team_role", lambda u, t: "Admin")
    monkeypatch.setenv("SANDBOX_ERROR_RATE", "1.0")  # 100% error rate

    sandbox = SandboxConnector("sandbox", "tenant1", "user1")
    result = sandbox.connect()

    assert result.status == "error"
    assert "Simulated error injection" in result.message


def test_sandbox_latency_delay(monkeypatch):
    """Sandbox simulates latency."""
    import time

    monkeypatch.setattr("src.connectors.base.get_team_role", lambda u, t: "Admin")
    monkeypatch.setenv("SANDBOX_LATENCY_MS", "50")

    sandbox = SandboxConnector("sandbox", "tenant1", "user1")

    start = time.time()
    sandbox.connect()
    elapsed = time.time() - start

    assert elapsed >= 0.05  # At least 50ms


def test_sandbox_multiple_resource_types(sandbox):
    """Sandbox supports multiple resource types."""
    sandbox.connect()

    sandbox.create_resource("users", {"id": "user1", "name": "Alice"})
    sandbox.create_resource("posts", {"id": "post1", "title": "Hello"})

    users = sandbox.list_resources("users")
    posts = sandbox.list_resources("posts")

    assert len(users.data) == 1
    assert len(posts.data) == 1
    assert users.data[0]["id"] == "user1"
    assert posts.data[0]["id"] == "post1"
