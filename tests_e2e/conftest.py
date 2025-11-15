"""Shared pytest fixtures for end-to-end smoke tests."""

import os
import time
from collections.abc import Generator
from http.client import HTTPConnection
from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def project_root() -> Path:
    """Get project root directory.

    Returns:
        Path to project root
    """
    return Path(__file__).parent.parent


@pytest.fixture(scope="session")
def health_server_port() -> int:
    """Get health server port from environment or default.

    Returns:
        Health server port number
    """
    return int(os.getenv("HEALTH_PORT", "8080"))


@pytest.fixture(scope="session")
def health_server_url(health_server_port: int) -> str:
    """Get health server base URL.

    Args:
        health_server_port: Port number from fixture

    Returns:
        Base URL for health server
    """
    return f"http://localhost:{health_server_port}"


@pytest.fixture(scope="session")
def ensure_health_server(health_server_port: int) -> Generator[int, None, None]:
    """Ensure health server is running.

    This fixture attempts to connect to the health server. If it's not running,
    it starts it in the background. The server runs for the entire test session.

    Args:
        health_server_port: Port number from fixture

    Yields:
        Port number of running health server
    """
    # Check if server is already running
    try:
        conn = HTTPConnection("localhost", health_server_port, timeout=2)
        conn.request("GET", "/health")
        response = conn.getresponse()
        conn.close()

        if response.status == 200:
            # Server already running
            yield health_server_port
            return
    except (ConnectionRefusedError, OSError):
        # Server not running, need to start it
        pass

    # Start health server in background
    from relay_ai.ops.health_server import start_health_server

    # Set environment for health server
    os.environ["HEALTH_PORT"] = str(health_server_port)
    os.environ["DRY_RUN"] = "true"

    # Start server thread
    start_health_server(health_server_port)

    # Wait for server to be ready (with timeout)
    max_retries = 20
    retry_delay = 0.1

    for i in range(max_retries):
        try:
            conn = HTTPConnection("localhost", health_server_port, timeout=2)
            conn.request("GET", "/health")
            response = conn.getresponse()
            conn.close()

            if response.status == 200:
                break
        except (ConnectionRefusedError, OSError) as e:
            if i == max_retries - 1:
                raise RuntimeError(
                    f"Health server failed to start on port {health_server_port} after {max_retries} retries"
                ) from e
            time.sleep(retry_delay)

    yield health_server_port

    # Cleanup handled by daemon thread


@pytest.fixture
def dry_run_env(monkeypatch):
    """Set up dry-run environment for connectors.

    This fixture configures the environment to use DRY_RUN mode for all
    connectors, ensuring no real API calls are made.

    Args:
        monkeypatch: pytest monkeypatch fixture
    """
    monkeypatch.setenv("DRY_RUN", "true")
    monkeypatch.setenv("SANDBOX_LATENCY_MS", "0")
    monkeypatch.setenv("SANDBOX_ERROR_RATE", "0.0")

    # Mock connector tokens (not used in dry-run, but required for init)
    monkeypatch.setenv("OUTLOOK_TOKEN", "mock-token")
    monkeypatch.setenv("TEAMS_TOKEN", "mock-token")
    monkeypatch.setenv("SLACK_TOKEN", "mock-token")
    monkeypatch.setenv("GMAIL_TOKEN", "mock-token")
    monkeypatch.setenv("NOTION_TOKEN", "mock-token")


@pytest.fixture
def mock_rbac(monkeypatch):
    """Mock RBAC to grant all permissions.

    Args:
        monkeypatch: pytest monkeypatch fixture
    """

    def mock_get_team_role(user_id: str, tenant_id: str) -> str:
        return "Admin"

    monkeypatch.setattr("src.connectors.base.get_team_role", mock_get_team_role)


@pytest.fixture
def temp_urg_index(tmp_path, monkeypatch):
    """Create temporary URG index for testing.

    Args:
        tmp_path: pytest tmp_path fixture
        monkeypatch: pytest monkeypatch fixture

    Returns:
        Path to temporary index directory
    """
    index_dir = tmp_path / "urg_index"
    index_dir.mkdir()

    monkeypatch.setenv("URG_INDEX_PATH", str(index_dir))

    return index_dir


def http_get_with_retry(host: str, port: int, path: str, max_retries: int = 3, timeout: float = 2.0) -> tuple:
    """Make HTTP GET request with retry logic.

    Args:
        host: Server hostname
        port: Server port
        path: Request path
        max_retries: Maximum number of retries
        timeout: Request timeout in seconds

    Returns:
        Tuple of (status_code, response_body)

    Raises:
        ConnectionError: If all retries fail
    """
    last_error = None

    for i in range(max_retries):
        try:
            conn = HTTPConnection(host, port, timeout=timeout)
            conn.request("GET", path)
            response = conn.getresponse()
            body = response.read().decode()
            status = response.status
            conn.close()

            return (status, body)

        except (ConnectionRefusedError, OSError, TimeoutError) as e:
            last_error = e
            if i < max_retries - 1:
                time.sleep(0.1 * (i + 1))  # Exponential backoff
            continue

    raise ConnectionError(f"Failed to connect after {max_retries} retries: {last_error}")


# Export helper for use in tests
__all__ = ["http_get_with_retry"]


# Sprint 42: HTTP mocking for external calls (Issue #15)


@pytest.fixture(autouse=True)
def mock_external_http(monkeypatch):
    """Mock external HTTP calls in e2e tests.

    Automatically applies to all e2e tests to prevent real network calls.
    Uses httpx MockTransport if available, otherwise falls back to
    requests monkeypatch.

    Provides stub responses for common connector API patterns.
    """
    from tests.utils.http_fakes import install_httpx_transport, install_requests_fake, make_httpx_mock

    # Standard stub response for connector APIs
    payload = {
        "ok": True,
        "items": [],
        "messages": [],
        "files": [],
        "note": "stubbed by e2e mock",
    }

    handler = make_httpx_mock(payload)
    if handler is not None:
        install_httpx_transport(monkeypatch, handler)
    else:
        install_requests_fake(monkeypatch, payload)

    yield
