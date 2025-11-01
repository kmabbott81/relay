"""Tests for connector base class."""

import os

import pytest

from src.connectors.base import Connector, ConnectorResult


class TestConnector(Connector):
    """Test implementation of Connector."""

    def connect(self):
        return ConnectorResult(status="success", message="Connected")

    def disconnect(self):
        return ConnectorResult(status="success", message="Disconnected")

    def list_resources(self, resource_type, filters=None):
        return ConnectorResult(status="success", data=[], message="Listed")

    def get_resource(self, resource_type, resource_id):
        return ConnectorResult(status="success", data={"id": resource_id}, message="Retrieved")

    def create_resource(self, resource_type, payload):
        return ConnectorResult(status="success", data=payload, message="Created")

    def update_resource(self, resource_type, resource_id, payload):
        return ConnectorResult(status="success", data=payload, message="Updated")

    def delete_resource(self, resource_type, resource_id):
        return ConnectorResult(status="success", message="Deleted")


def test_connector_result_dataclass():
    """ConnectorResult dataclass works."""
    result = ConnectorResult(status="success", data={"foo": "bar"}, message="Test")

    assert result.status == "success"
    assert result.data == {"foo": "bar"}
    assert result.message == "Test"


def test_connector_result_defaults():
    """ConnectorResult has sensible defaults."""
    result = ConnectorResult(status="error")

    assert result.status == "error"
    assert result.data is None
    assert result.message == ""


def test_connector_initialization():
    """Connector initializes with required params."""
    connector = TestConnector("test-conn", "tenant-1", "user-1")

    assert connector.connector_id == "test-conn"
    assert connector.tenant_id == "tenant-1"
    assert connector.user_id == "user-1"
    assert connector.connected is False
    assert connector.required_role == "Operator"


def test_connector_rbac_role_from_env():
    """Connector reads required role from env."""
    os.environ["CONNECTOR_RBAC_ROLE"] = "Admin"
    connector = TestConnector("test-conn", "tenant-1", "user-1")

    assert connector.required_role == "Admin"

    # Cleanup
    del os.environ["CONNECTOR_RBAC_ROLE"]


def test_connector_abstract_methods():
    """Connector enforces abstract methods."""
    with pytest.raises(TypeError):
        # Cannot instantiate abstract class
        Connector("test", "tenant", "user")  # type: ignore


def test_connector_check_rbac_no_role(monkeypatch):
    """RBAC check fails if user has no role."""
    monkeypatch.setattr("src.connectors.base.get_team_role", lambda u, t: None)

    connector = TestConnector("test-conn", "tenant-1", "user-1")
    assert connector.check_rbac() is False


def test_connector_check_rbac_insufficient_role(monkeypatch):
    """RBAC check fails if user role is insufficient."""
    monkeypatch.setattr("src.connectors.base.get_team_role", lambda u, t: "Viewer")

    connector = TestConnector("test-conn", "tenant-1", "user-1")
    connector.required_role = "Operator"
    assert connector.check_rbac() is False


def test_connector_check_rbac_sufficient_role(monkeypatch):
    """RBAC check passes if user role is sufficient."""
    monkeypatch.setattr("src.connectors.base.get_team_role", lambda u, t: "Operator")

    connector = TestConnector("test-conn", "tenant-1", "user-1")
    connector.required_role = "Operator"
    assert connector.check_rbac() is True


def test_connector_check_rbac_higher_role(monkeypatch):
    """RBAC check passes if user has higher role."""
    monkeypatch.setattr("src.connectors.base.get_team_role", lambda u, t: "Admin")

    connector = TestConnector("test-conn", "tenant-1", "user-1")
    connector.required_role = "Operator"
    assert connector.check_rbac() is True


def test_connector_role_hierarchy(monkeypatch):
    """Role hierarchy is correctly enforced."""
    roles_in_order = ["Viewer", "Author", "Operator", "Auditor", "Compliance", "Admin"]

    for i, current_user_role in enumerate(roles_in_order):
        # Use default argument to bind loop variable
        monkeypatch.setattr("src.connectors.base.get_team_role", lambda u, t, r=current_user_role: r)
        connector = TestConnector("test-conn", "tenant-1", "user-1")

        # User should have access to all roles at or below their level
        for j, required_role in enumerate(roles_in_order):
            connector.required_role = required_role
            if i >= j:
                assert connector.check_rbac() is True, f"{current_user_role} should have access to {required_role}"
            else:
                assert connector.check_rbac() is False, f"{current_user_role} should NOT have access to {required_role}"
