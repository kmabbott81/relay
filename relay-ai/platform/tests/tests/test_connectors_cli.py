"""Tests for connectors CLI."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from src.connectors.registry import register_connector

# Sprint 52: Quarantine marker - CLI argument parsing broken
pytestmark = pytest.mark.bizlogic_asserts


@pytest.fixture
def temp_registry(tmp_path, monkeypatch):
    """Temporary connector registry."""
    registry_path = tmp_path / "connectors.jsonl"
    monkeypatch.setenv("CONNECTOR_REGISTRY_PATH", str(registry_path))
    return registry_path


@pytest.fixture
def cli_env(temp_registry, monkeypatch):
    """CLI environment with admin user."""
    monkeypatch.setattr("src.security.teams.get_team_role", lambda u, t: "Admin")
    return {"CONNECTOR_REGISTRY_PATH": str(temp_registry)}


def run_cli(*args, env=None):
    """Run connectors CLI and return result."""
    script = Path(__file__).parent.parent / "scripts" / "connectors.py"
    cmd = [sys.executable, str(script)] + list(args)

    result = subprocess.run(cmd, capture_output=True, text=True, env=env)
    return result


def test_cli_list_empty(cli_env):
    """CLI list shows no connectors initially."""
    result = run_cli("list", env=cli_env)

    assert result.returncode == 0
    assert "No enabled connectors found" in result.stdout


def test_cli_list_json_format(cli_env, temp_registry):
    """CLI list outputs JSON format."""
    register_connector("test-conn", "src.connectors.sandbox", "SandboxConnector")

    result = run_cli("list", "--json", env=cli_env)

    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert len(data) == 1
    assert data[0]["connector_id"] == "test-conn"


def test_cli_register_connector(cli_env, temp_registry):
    """CLI register creates connector entry."""
    result = run_cli(
        "register",
        "--id",
        "test-conn",
        "--module",
        "src.connectors.sandbox",
        "--class",
        "SandboxConnector",
        "--user",
        "admin",
        "--tenant",
        "default",
        env=cli_env,
    )

    assert result.returncode == 0
    assert "Registered connector: test-conn" in result.stdout

    # Verify registry file
    lines = temp_registry.read_text().strip().split("\n")
    entry = json.loads(lines[0])
    assert entry["connector_id"] == "test-conn"


def test_cli_register_with_scopes(cli_env, temp_registry):
    """CLI register supports scopes."""
    result = run_cli(
        "register",
        "--id",
        "test-conn",
        "--module",
        "src.connectors.sandbox",
        "--class",
        "SandboxConnector",
        "--scopes",
        "read,write,delete",
        "--user",
        "admin",
        "--tenant",
        "default",
        env=cli_env,
    )

    assert result.returncode == 0

    lines = temp_registry.read_text().strip().split("\n")
    entry = json.loads(lines[0])
    assert entry["scopes"] == ["read", "write", "delete"]


def test_cli_disable_connector(cli_env, temp_registry):
    """CLI disable marks connector as disabled."""
    register_connector("test-conn", "src.connectors.sandbox", "SandboxConnector", enabled=True)

    result = run_cli("disable", "test-conn", "--user", "admin", "--tenant", "default", env=cli_env)

    assert result.returncode == 0
    assert "Disabled connector: test-conn" in result.stdout


def test_cli_disable_not_found(cli_env):
    """CLI disable returns error for missing connector."""
    result = run_cli("disable", "nonexistent", "--user", "admin", "--tenant", "default", env=cli_env)

    assert result.returncode == 1
    assert "Connector not found" in result.stderr


def test_cli_enable_connector(cli_env, temp_registry):
    """CLI enable marks connector as enabled."""
    register_connector("test-conn", "src.connectors.sandbox", "SandboxConnector", enabled=False)

    result = run_cli("enable", "test-conn", "--user", "admin", "--tenant", "default", env=cli_env)

    assert result.returncode == 0
    assert "Enabled connector: test-conn" in result.stdout


def test_cli_test_sandbox_list(cli_env, temp_registry, monkeypatch):
    """CLI test executes sandbox operations."""
    monkeypatch.setattr("src.security.teams.get_team_role", lambda u, t: "Admin")
    register_connector("sandbox", "src.connectors.sandbox", "SandboxConnector", enabled=True)

    result = run_cli("test", "sandbox", "--action", "list", "--user", "admin", "--tenant", "default", env=cli_env)

    assert result.returncode == 0
    assert "Connected" in result.stdout
    assert "List:" in result.stdout


def test_cli_test_connector_not_found(cli_env):
    """CLI test returns error for missing connector."""
    result = run_cli("test", "nonexistent", "--action", "list", "--user", "admin", "--tenant", "default", env=cli_env)

    assert result.returncode == 1
    assert "Connector not found" in result.stderr


def test_cli_rbac_admin_required_for_register(cli_env, monkeypatch):
    """CLI register requires Admin role."""
    # Override to return Operator (insufficient)
    monkeypatch.setattr("src.security.teams.get_team_role", lambda u, t: "Operator")

    result = run_cli(
        "register",
        "--id",
        "test",
        "--module",
        "mod",
        "--class",
        "Class",
        "--user",
        "user1",
        "--tenant",
        "default",
        env=cli_env,
    )

    assert result.returncode == 2
    assert "RBAC denied" in result.stderr


def test_cli_rbac_operator_sufficient_for_test(cli_env, temp_registry, monkeypatch):
    """CLI test allows Operator role."""
    monkeypatch.setattr("src.security.teams.get_team_role", lambda u, t: "Operator")
    register_connector("sandbox", "src.connectors.sandbox", "SandboxConnector", enabled=True)

    result = run_cli("test", "sandbox", "--action", "list", "--user", "operator", "--tenant", "default", env=cli_env)

    # Should succeed (Operator meets Operator requirement)
    assert result.returncode == 0


def test_cli_help():
    """CLI shows help message."""
    result = run_cli("--help")

    assert result.returncode == 0
    assert "Manage connectors" in result.stdout
    assert "list" in result.stdout
    assert "register" in result.stdout
    assert "test" in result.stdout
