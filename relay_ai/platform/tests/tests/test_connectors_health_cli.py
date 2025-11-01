"""Tests for connector health CLI."""

import json
import subprocess
import sys

import pytest


@pytest.fixture
def setup_test_env(tmp_path, monkeypatch):
    """Setup test environment with temp paths."""
    metrics_path = tmp_path / "metrics.jsonl"
    circuit_path = tmp_path / "circuit_state.jsonl"
    registry_path = tmp_path / "connectors.jsonl"

    monkeypatch.setenv("CONNECTOR_METRICS_PATH", str(metrics_path))
    monkeypatch.setenv("CIRCUIT_STATE_PATH", str(circuit_path))
    monkeypatch.setenv("CONNECTOR_REGISTRY_PATH", str(registry_path))
    monkeypatch.setenv("USER_ROLE", "Operator")
    monkeypatch.setenv("PYTHONIOENCODING", "utf-8")

    import os

    return dict(os.environ)


def test_list_no_connectors(setup_test_env):
    """List returns empty when no connectors registered."""
    result = subprocess.run(
        [sys.executable, "scripts/connectors_health.py", "list"],
        capture_output=True,
        text=True,
        env=setup_test_env,
    )

    assert result.returncode == 0
    assert "No connectors enabled" in result.stdout


def test_list_json_output(setup_test_env):
    """List outputs valid JSON with --json flag."""
    result = subprocess.run(
        [sys.executable, "scripts/connectors_health.py", "list", "--json"],
        capture_output=True,
        text=True,
        env=setup_test_env,
    )

    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert "connectors" in data
    assert data["connectors"] == []


def test_rbac_denied(setup_test_env):
    """CLI exits with code 2 when RBAC denied."""
    env = dict(setup_test_env)
    env["USER_ROLE"] = "Viewer"

    result = subprocess.run(
        [sys.executable, "scripts/connectors_health.py", "list"],
        capture_output=True,
        text=True,
        env=env,
    )

    assert result.returncode == 2
    assert "Insufficient permissions" in result.stderr


def test_drill_connector_not_found(setup_test_env):
    """Drill returns exit code 3 when connector not found."""
    result = subprocess.run(
        [sys.executable, "scripts/connectors_health.py", "drill", "nonexistent"],
        capture_output=True,
        text=True,
        env=setup_test_env,
    )

    assert result.returncode == 3
    assert "not found" in result.stdout.lower()


def test_drill_json_output(setup_test_env):
    """Drill outputs valid JSON with --json flag."""
    # Register a connector
    from src.connectors.registry import register_connector

    register_connector("test-conn", "src.connectors.sandbox", "SandboxConnector")

    result = subprocess.run(
        [sys.executable, "scripts/connectors_health.py", "drill", "test-conn", "--json"],
        capture_output=True,
        text=True,
        env=setup_test_env,
    )

    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert data["connector_id"] == "test-conn"
    assert "health" in data
    assert "metrics" in data
    assert "circuit_state" in data


def test_list_healthy_connector(setup_test_env):
    """List shows healthy connector with metrics."""
    from src.connectors.metrics import record_call
    from src.connectors.registry import register_connector

    # Register connector
    register_connector("test-conn", "src.connectors.sandbox", "SandboxConnector")

    # Record successful calls
    for _ in range(10):
        record_call("test-conn", "list_resources", "success", 100.0)

    result = subprocess.run(
        [sys.executable, "scripts/connectors_health.py", "list"],
        capture_output=True,
        env=setup_test_env,
        encoding="utf-8",
        errors="replace",
    )

    assert result.returncode == 0
    assert "test-conn" in result.stdout
    assert "healthy" in result.stdout.lower()


def test_list_degraded_connector(setup_test_env):
    """List returns exit code 1 when connector degraded."""
    from src.connectors.metrics import record_call
    from src.connectors.registry import register_connector

    # Lower threshold for testing
    env = dict(setup_test_env)
    env["CONNECTOR_HEALTH_P95_MS"] = "50"

    # Register connector
    register_connector("test-conn", "src.connectors.sandbox", "SandboxConnector")

    # Record slow calls
    for _ in range(10):
        record_call("test-conn", "list_resources", "success", 1000.0)

    result = subprocess.run(
        [sys.executable, "scripts/connectors_health.py", "list"],
        capture_output=True,
        env=env,
        encoding="utf-8",
        errors="replace",
    )

    assert result.returncode == 1
    assert "test-conn" in result.stdout
    assert "degraded" in result.stdout.lower()


def test_drill_shows_recent_failures(setup_test_env):
    """Drill shows recent failures in output."""
    from src.connectors.metrics import record_call
    from src.connectors.registry import register_connector

    # Register connector
    register_connector("test-conn", "src.connectors.sandbox", "SandboxConnector")

    # Record some failures
    for i in range(3):
        record_call("test-conn", "connect", "error", 100.0, error=f"Failure {i}")

    result = subprocess.run(
        [sys.executable, "scripts/connectors_health.py", "drill", "test-conn"],
        capture_output=True,
        env=setup_test_env,
        encoding="utf-8",
        errors="replace",
    )

    # Exit code 1 for degraded (high error rate)
    assert result.returncode == 1
    assert "Recent Failures" in result.stdout
    assert "connect" in result.stdout
    assert "Failure" in result.stdout
