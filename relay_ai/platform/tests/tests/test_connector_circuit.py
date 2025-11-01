"""Tests for circuit breaker."""


import pytest

from src.connectors.circuit import CircuitBreaker


@pytest.fixture
def temp_circuit(tmp_path, monkeypatch):
    """Temporary circuit state file."""
    state_path = tmp_path / "circuit_state.jsonl"
    monkeypatch.setenv("CIRCUIT_STATE_PATH", str(state_path))
    monkeypatch.setenv("CB_FAILURES_TO_OPEN", "3")
    monkeypatch.setenv("CB_COOLDOWN_S", "5")
    return state_path


def test_circuit_breaker_starts_closed(temp_circuit):
    """Circuit breaker starts in closed state."""
    cb = CircuitBreaker("test-conn")

    assert cb.state == "closed"
    assert cb.allow() is True


def test_circuit_breaker_opens_after_failures(temp_circuit):
    """Circuit opens after threshold failures."""
    cb = CircuitBreaker("test-conn")

    # Record failures
    for _ in range(3):
        cb.record_failure()

    assert cb.state == "open"
    assert cb.allow() is False


def test_circuit_breaker_resets_on_success(temp_circuit):
    """Success resets failure count."""
    cb = CircuitBreaker("test-conn")

    cb.record_failure()
    cb.record_failure()
    cb.record_success()

    assert cb.failure_count == 0
    assert cb.state == "closed"


def test_circuit_breaker_half_open_recovery(temp_circuit):
    """Half-open allows probabilistic recovery."""
    cb = CircuitBreaker("test-conn")

    # Open circuit
    for _ in range(3):
        cb.record_failure()

    assert cb.state == "open"

    # Force cooldown (manipulate state for testing)
    from datetime import datetime, timedelta

    cb.opened_at = datetime.now() - timedelta(seconds=10)

    # Check transitions to half-open
    cb.allow()  # Trigger state transition
    assert cb.state == "half_open"


def test_circuit_breaker_persists_state(temp_circuit):
    """Circuit breaker persists state to JSONL."""
    cb1 = CircuitBreaker("test-conn")
    cb1.record_failure()
    cb1.record_failure()

    # Create new instance (load from file)
    cb2 = CircuitBreaker("test-conn")

    assert cb2.failure_count == 2
    assert cb2.state == "closed"
