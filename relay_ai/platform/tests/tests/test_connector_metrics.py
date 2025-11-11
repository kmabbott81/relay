"""Tests for connector metrics."""


import pytest

from relay_ai.connectors.metrics import health_status, record_call, summarize


@pytest.fixture
def temp_metrics(tmp_path, monkeypatch):
    """Temporary metrics file."""
    metrics_path = tmp_path / "metrics.jsonl"
    monkeypatch.setenv("CONNECTOR_METRICS_PATH", str(metrics_path))
    return metrics_path


def test_record_call_creates_file(temp_metrics):
    """Recording call creates metrics file."""
    record_call("test-conn", "connect", "success", 100.5)

    assert temp_metrics.exists()


def test_summarize_empty_returns_zeros(temp_metrics):
    """Summarizing with no data returns zeros."""
    summary = summarize("test-conn")

    assert summary["total_calls"] == 0
    assert summary["error_rate"] == 0.0


def test_summarize_computes_metrics(temp_metrics):
    """Summarize computes metrics correctly."""
    # Record some calls
    for i in range(10):
        status = "error" if i < 2 else "success"
        record_call("test-conn", "list_resources", status, 100 + (i * 50))

    summary = summarize("test-conn")

    assert summary["total_calls"] == 10
    assert summary["error_rate"] == 0.2  # 2/10
    assert summary["p95_ms"] > 0


def test_health_status_healthy(temp_metrics, monkeypatch):
    """Health status returns healthy when within thresholds."""
    monkeypatch.setenv("CONNECTOR_HEALTH_P95_MS", "2000")
    monkeypatch.setenv("CONNECTOR_HEALTH_ERROR_RATE", "0.10")

    # Record successful calls
    for _ in range(10):
        record_call("test-conn", "list_resources", "success", 100)

    health = health_status("test-conn")

    assert health["status"] == "healthy"


def test_health_status_degraded_latency(temp_metrics, monkeypatch):
    """Health status degraded when p95 exceeds threshold."""
    monkeypatch.setenv("CONNECTOR_HEALTH_P95_MS", "100")

    # Record slow calls
    for _ in range(20):
        record_call("test-conn", "list_resources", "success", 500)

    health = health_status("test-conn")

    assert health["status"] == "degraded"
    assert "p95 latency" in health["reason"]


def test_health_status_degraded_errors(temp_metrics, monkeypatch):
    """Health status degraded when error rate exceeds threshold."""
    monkeypatch.setenv("CONNECTOR_HEALTH_ERROR_RATE", "0.10")

    # Record calls with errors
    for i in range(10):
        status = "error" if i < 2 else "success"
        record_call("test-conn", "list_resources", status, 100.0 + float(i))

    health = health_status("test-conn")

    assert health["status"] == "degraded"


def test_health_status_down_high_errors(temp_metrics):
    """Health status down when error rate > 50%."""
    # Record mostly errors
    for i in range(10):
        status = "error" if i < 6 else "success"
        record_call("test-conn", "list_resources", status, 100)

    health = health_status("test-conn")

    assert health["status"] == "down"
