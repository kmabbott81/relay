"""Tests for connector dashboard panel rendering."""

import pytest

# Sprint 52: Quarantine marker - requires streamlit dependency
pytestmark = pytest.mark.requires_streamlit


@pytest.fixture
def setup_test_env(tmp_path, monkeypatch):
    """Setup test environment with temp paths."""
    metrics_path = tmp_path / "metrics.jsonl"
    circuit_path = tmp_path / "circuit_state.jsonl"
    registry_path = tmp_path / "connectors.jsonl"

    monkeypatch.setenv("CONNECTOR_METRICS_PATH", str(metrics_path))
    monkeypatch.setenv("CIRCUIT_STATE_PATH", str(circuit_path))
    monkeypatch.setenv("CONNECTOR_REGISTRY_PATH", str(registry_path))

    return {
        "metrics_path": metrics_path,
        "circuit_path": circuit_path,
        "registry_path": registry_path,
    }


def test_render_no_connectors(setup_test_env):
    """Panel handles empty connector list."""
    from dashboards.observability_tab import _render_connectors

    # Should not raise exception
    try:
        # Mock streamlit calls (panel should handle gracefully)
        _render_connectors()
    except ImportError:
        # Streamlit not available in test env, skip
        pytest.skip("Streamlit not available")


def test_render_with_healthy_connector(setup_test_env):
    """Panel renders healthy connector data."""
    from relay_ai.connectors.metrics import record_call
    from relay_ai.connectors.registry import register_connector

    # Register connector
    register_connector("test-conn", "src.connectors.sandbox", "SandboxConnector")

    # Record successful calls
    for _ in range(10):
        record_call("test-conn", "list_resources", "success", 100.0)

    from dashboards.observability_tab import _render_connectors

    try:
        _render_connectors()
    except ImportError:
        pytest.skip("Streamlit not available")


def test_render_with_degraded_connector(setup_test_env, monkeypatch):
    """Panel renders degraded connector with warning."""
    from relay_ai.connectors.metrics import record_call
    from relay_ai.connectors.registry import register_connector

    monkeypatch.setenv("CONNECTOR_HEALTH_P95_MS", "50")

    # Register connector
    register_connector("test-conn", "src.connectors.sandbox", "SandboxConnector")

    # Record slow calls
    for _ in range(10):
        record_call("test-conn", "list_resources", "success", 1000.0)

    from dashboards.observability_tab import _render_connectors

    try:
        _render_connectors()
    except ImportError:
        pytest.skip("Streamlit not available")


def test_render_with_circuit_open(setup_test_env):
    """Panel shows circuit state correctly."""
    from relay_ai.connectors.circuit import CircuitBreaker
    from relay_ai.connectors.registry import register_connector

    # Register connector
    register_connector("test-conn", "src.connectors.sandbox", "SandboxConnector")

    # Open circuit
    cb = CircuitBreaker("test-conn")
    for _ in range(5):
        cb.record_failure()

    assert cb.state == "open"

    from dashboards.observability_tab import _render_connectors

    try:
        _render_connectors()
    except ImportError:
        pytest.skip("Streamlit not available")


def test_panel_data_collection_no_metrics(setup_test_env):
    """Panel data collection handles no metrics gracefully."""
    from relay_ai.connectors.circuit import CircuitBreaker
    from relay_ai.connectors.metrics import health_status
    from relay_ai.connectors.registry import list_enabled_connectors, register_connector

    # Register connector but no metrics
    register_connector("test-conn", "src.connectors.sandbox", "SandboxConnector")

    enabled = list_enabled_connectors()
    assert len(enabled) == 1

    # Get health (should return unknown)
    health = health_status("test-conn")
    assert health["status"] == "unknown"

    # Get circuit state (should be closed)
    cb = CircuitBreaker("test-conn")
    assert cb.state == "closed"


def test_panel_data_collection_mixed_states(setup_test_env, monkeypatch):
    """Panel data collection handles mixed connector states."""
    from relay_ai.connectors.circuit import CircuitBreaker
    from relay_ai.connectors.metrics import health_status, record_call
    from relay_ai.connectors.registry import register_connector

    monkeypatch.setenv("CONNECTOR_HEALTH_ERROR_RATE", "0.10")

    # Register two connectors
    register_connector("healthy-conn", "src.connectors.sandbox", "SandboxConnector")
    register_connector("degraded-conn", "src.connectors.sandbox", "SandboxConnector")

    # Healthy connector: all success
    for _ in range(10):
        record_call("healthy-conn", "list_resources", "success", 100.0)

    # Degraded connector: some failures
    for i in range(10):
        status = "error" if i < 3 else "success"
        record_call("degraded-conn", "list_resources", status, 100.0)

    # Check health
    healthy_health = health_status("healthy-conn")
    degraded_health = health_status("degraded-conn")

    assert healthy_health["status"] == "healthy"
    assert degraded_health["status"] == "degraded"

    # Circuit states
    healthy_cb = CircuitBreaker("healthy-conn")
    degraded_cb = CircuitBreaker("degraded-conn")

    assert healthy_cb.state == "closed"
    assert degraded_cb.state == "closed"  # Not enough failures to open
