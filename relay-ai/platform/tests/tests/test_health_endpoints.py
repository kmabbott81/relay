"""Tests for health and readiness check endpoints."""

import json
import os
import time
from http.client import HTTPConnection

import pytest

from src.ops.health_server import start_health_server

# Sprint 52: Quarantine marker - fixed port 18086 conflicts in CI parallel execution
pytestmark = pytest.mark.port_conflict


@pytest.fixture
def health_server():
    """Start health server on random port for testing."""
    port = 18086  # Test port
    os.environ["HEALTH_PORT"] = str(port)

    start_health_server(port)
    # TODO(Sprint 45): replace with wait_until(...) for faster polling
    time.sleep(0.1)  # Give server time to start

    yield port

    # Cleanup handled by daemon thread


def test_health_endpoint_always_returns_200(health_server, monkeypatch):
    """Health endpoint returns 200 even with missing config."""
    # Clear all env vars to simulate broken config
    monkeypatch.delenv("REGIONS", raising=False)
    monkeypatch.delenv("PRIMARY_REGION", raising=False)

    conn = HTTPConnection("localhost", health_server)
    conn.request("GET", "/health")
    response = conn.getresponse()

    assert response.status == 200

    data = json.loads(response.read().decode())
    assert data["status"] == "healthy"
    assert data["checks"]["process"] == "up"

    conn.close()


def test_ready_endpoint_fails_when_required_env_missing(health_server, monkeypatch):
    """Ready endpoint returns 503 when REQUIRED_ENVS not satisfied."""
    # Set required env but don't provide it
    monkeypatch.setenv("REQUIRED_ENVS", "DATABASE_URL,REDIS_URL")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("REDIS_URL", raising=False)

    conn = HTTPConnection("localhost", health_server)
    conn.request("GET", "/ready")
    response = conn.getresponse()

    assert response.status == 503

    data = json.loads(response.read().decode())
    assert data["status"] == "not_ready"
    assert "DATABASE_URL" in data["checks"]["required_envs"]["missing"]
    assert "REDIS_URL" in data["checks"]["required_envs"]["missing"]

    conn.close()


def test_ready_endpoint_succeeds_when_required_envs_present(health_server, monkeypatch):
    """Ready endpoint returns 200 when all required envs present."""
    # Set required envs and provide them
    monkeypatch.setenv("REQUIRED_ENVS", "API_KEY,TENANT_ID")
    monkeypatch.setenv("API_KEY", "test-key")
    monkeypatch.setenv("TENANT_ID", "test-tenant")

    conn = HTTPConnection("localhost", health_server)
    conn.request("GET", "/ready")
    response = conn.getresponse()

    assert response.status == 200

    data = json.loads(response.read().decode())
    assert data["status"] == "ready"
    assert data["checks"]["required_envs"]["ok"] is True
    assert len(data["checks"]["required_envs"]["missing"]) == 0

    conn.close()


def test_ready_endpoint_validates_multi_region_config(health_server, monkeypatch):
    """Ready endpoint validates region config when FEATURE_MULTI_REGION enabled."""
    # Enable multi-region but provide invalid config
    monkeypatch.setenv("FEATURE_MULTI_REGION", "true")
    monkeypatch.setenv("REGIONS", "us-east,us-west")
    monkeypatch.setenv("PRIMARY_REGION", "eu-west")  # Not in REGIONS

    conn = HTTPConnection("localhost", health_server)
    conn.request("GET", "/ready")
    response = conn.getresponse()

    assert response.status == 503

    data = json.loads(response.read().decode())
    assert data["status"] == "not_ready"
    assert data["checks"]["regions"]["ok"] is False
    assert "PRIMARY_REGION" in data["checks"]["regions"]["error"]

    conn.close()


def test_ready_endpoint_validates_blue_green_rbac(health_server, monkeypatch):
    """Ready endpoint validates DEPLOY_RBAC_ROLE when FEATURE_BLUE_GREEN enabled."""
    # Enable blue/green but provide invalid role
    monkeypatch.setenv("FEATURE_BLUE_GREEN", "true")
    monkeypatch.setenv("DEPLOY_RBAC_ROLE", "Viewer")  # Invalid for deploy

    conn = HTTPConnection("localhost", health_server)
    conn.request("GET", "/ready")
    response = conn.getresponse()

    assert response.status == 503

    data = json.loads(response.read().decode())
    assert data["status"] == "not_ready"
    assert data["checks"]["deploy_rbac"]["ok"] is False
    assert "Invalid DEPLOY_RBAC_ROLE" in data["checks"]["deploy_rbac"]["error"]

    conn.close()


def test_meta_endpoint_returns_build_info(health_server, monkeypatch):
    """Meta endpoint returns build metadata."""
    monkeypatch.setenv("BUILD_VERSION", "1.2.3")
    monkeypatch.setenv("GIT_SHA", "abc123")
    monkeypatch.setenv("CURRENT_REGION", "us-east")

    conn = HTTPConnection("localhost", health_server)
    conn.request("GET", "/__meta")
    response = conn.getresponse()

    assert response.status == 200

    data = json.loads(response.read().decode())
    assert data["version"] == "1.2.3"
    assert data["git_sha"] == "abc123"
    assert data["region"] == "us-east"

    conn.close()


def test_unknown_endpoint_returns_404(health_server):
    """Unknown endpoints return 404."""
    conn = HTTPConnection("localhost", health_server)
    conn.request("GET", "/unknown")
    response = conn.getresponse()

    assert response.status == 404

    conn.close()
