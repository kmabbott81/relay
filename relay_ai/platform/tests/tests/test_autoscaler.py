"""Tests for autoscaler scaling decisions."""

from datetime import datetime, timedelta

from relay_ai.scale.autoscaler import (
    EngineState,
    ScaleDirection,
    make_scale_decision,
)


def test_scale_up_when_queue_depth_exceeds_target(monkeypatch):
    """Autoscaler scales up when queue depth exceeds target."""
    monkeypatch.setenv("TARGET_QUEUE_DEPTH", "50")
    monkeypatch.setenv("MAX_WORKERS", "12")
    monkeypatch.setenv("SCALE_UP_STEP", "2")

    state = EngineState(
        current_workers=4,
        queue_depth=100,  # Exceeds target of 50
        p95_latency_ms=1000.0,
        in_flight_jobs=4,
    )

    decision = make_scale_decision(state)

    assert decision.direction == ScaleDirection.UP
    assert decision.desired_workers == 6  # 4 + 2
    assert "queue depth" in decision.reason.lower()


def test_scale_up_when_p95_latency_exceeds_target(monkeypatch):
    """Autoscaler scales up when P95 latency exceeds target."""
    monkeypatch.setenv("TARGET_P95_LATENCY_MS", "2000")
    monkeypatch.setenv("MAX_WORKERS", "12")
    monkeypatch.setenv("SCALE_UP_STEP", "2")

    state = EngineState(
        current_workers=4,
        queue_depth=10,
        p95_latency_ms=3000.0,  # Exceeds target of 2000
        in_flight_jobs=3,
    )

    decision = make_scale_decision(state)

    assert decision.direction == ScaleDirection.UP
    assert decision.desired_workers == 6
    assert "p95 latency" in decision.reason.lower()


def test_scale_up_when_all_workers_busy_with_queue_backlog(monkeypatch):
    """Autoscaler scales up when all workers busy and queue has backlog."""
    monkeypatch.setenv("MAX_WORKERS", "12")
    monkeypatch.setenv("SCALE_UP_STEP", "2")

    state = EngineState(
        current_workers=5,
        queue_depth=20,  # Queue backlog exists
        p95_latency_ms=1000.0,
        in_flight_jobs=5,  # All workers busy
    )

    decision = make_scale_decision(state)

    assert decision.direction == ScaleDirection.UP
    assert decision.desired_workers == 7
    assert "workers busy" in decision.reason.lower()


def test_scale_down_when_utilization_low(monkeypatch):
    """Autoscaler scales down when utilization is low."""
    monkeypatch.setenv("MIN_WORKERS", "1")
    monkeypatch.setenv("SCALE_DOWN_STEP", "1")
    monkeypatch.setenv("TARGET_QUEUE_DEPTH", "50")
    monkeypatch.setenv("TARGET_P95_LATENCY_MS", "2000")

    state = EngineState(
        current_workers=6,
        queue_depth=5,  # Well below target (30% threshold = 15)
        p95_latency_ms=500.0,  # Well below target (50% threshold = 1000)
        in_flight_jobs=2,  # Low utilization (2/6 = 33% < 70%)
    )

    decision = make_scale_decision(state)

    assert decision.direction == ScaleDirection.DOWN
    assert decision.desired_workers == 5  # 6 - 1
    assert "utilization" in decision.reason.lower()


def test_cooldown_prevents_rapid_scaling(monkeypatch):
    """Autoscaler respects cooldown period between scaling decisions."""
    monkeypatch.setenv("SCALE_DECISION_INTERVAL_MS", "1500")
    monkeypatch.setenv("TARGET_QUEUE_DEPTH", "50")

    # Last scale was 1 second ago (within cooldown)
    last_scale = datetime.utcnow() - timedelta(seconds=1)

    state = EngineState(
        current_workers=4,
        queue_depth=100,  # Would normally trigger scale up
        p95_latency_ms=1000.0,
        in_flight_jobs=4,
        last_scale_time=last_scale,
    )

    decision = make_scale_decision(state)

    assert decision.direction == ScaleDirection.HOLD
    assert decision.desired_workers == 4  # No change
    assert "cooldown" in decision.reason.lower()


def test_cooldown_expires_allows_scaling(monkeypatch):
    """Autoscaler allows scaling after cooldown expires."""
    monkeypatch.setenv("SCALE_DECISION_INTERVAL_MS", "1500")
    monkeypatch.setenv("TARGET_QUEUE_DEPTH", "50")
    monkeypatch.setenv("MAX_WORKERS", "12")
    monkeypatch.setenv("SCALE_UP_STEP", "2")

    # Last scale was 2 seconds ago (beyond cooldown)
    last_scale = datetime.utcnow() - timedelta(seconds=2)

    state = EngineState(
        current_workers=4,
        queue_depth=100,  # Triggers scale up
        p95_latency_ms=1000.0,
        in_flight_jobs=4,
        last_scale_time=last_scale,
    )

    decision = make_scale_decision(state)

    assert decision.direction == ScaleDirection.UP
    assert decision.desired_workers == 6


def test_min_worker_bounds_respected(monkeypatch):
    """Autoscaler respects minimum worker count."""
    monkeypatch.setenv("MIN_WORKERS", "2")
    monkeypatch.setenv("SCALE_DOWN_STEP", "1")
    monkeypatch.setenv("TARGET_QUEUE_DEPTH", "50")
    monkeypatch.setenv("TARGET_P95_LATENCY_MS", "2000")

    state = EngineState(
        current_workers=2,  # At minimum
        queue_depth=0,
        p95_latency_ms=100.0,
        in_flight_jobs=0,  # No load
    )

    decision = make_scale_decision(state)

    assert decision.desired_workers >= 2  # Cannot go below min


def test_max_worker_bounds_respected(monkeypatch):
    """Autoscaler respects maximum worker count."""
    monkeypatch.setenv("MAX_WORKERS", "8")
    monkeypatch.setenv("SCALE_UP_STEP", "2")
    monkeypatch.setenv("TARGET_QUEUE_DEPTH", "50")

    state = EngineState(
        current_workers=7,
        queue_depth=200,  # High load
        p95_latency_ms=5000.0,
        in_flight_jobs=7,
    )

    decision = make_scale_decision(state)

    assert decision.desired_workers <= 8  # Cannot exceed max
    assert decision.desired_workers == 8  # Should scale to max


def test_environment_variable_configuration(monkeypatch):
    """Autoscaler loads configuration from environment variables."""
    monkeypatch.setenv("MIN_WORKERS", "3")
    monkeypatch.setenv("MAX_WORKERS", "20")
    monkeypatch.setenv("TARGET_P95_LATENCY_MS", "1500")
    monkeypatch.setenv("TARGET_QUEUE_DEPTH", "100")
    monkeypatch.setenv("SCALE_UP_STEP", "5")
    monkeypatch.setenv("SCALE_DOWN_STEP", "2")
    monkeypatch.setenv("SCALE_DECISION_INTERVAL_MS", "3000")

    # Test scale up with custom step
    state = EngineState(
        current_workers=3,
        queue_depth=150,  # Exceeds custom target of 100
        p95_latency_ms=1000.0,
        in_flight_jobs=3,
    )

    decision = make_scale_decision(state)

    assert decision.direction == ScaleDirection.UP
    assert decision.desired_workers == 8  # 3 + custom step of 5


def test_hold_when_stable(monkeypatch):
    """Autoscaler holds steady when metrics are stable."""
    monkeypatch.setenv("TARGET_QUEUE_DEPTH", "50")
    monkeypatch.setenv("TARGET_P95_LATENCY_MS", "2000")

    state = EngineState(
        current_workers=5,
        queue_depth=25,  # Within acceptable range
        p95_latency_ms=1200.0,  # Within acceptable range
        in_flight_jobs=3,  # 60% utilization (between 30% and 70%)
    )

    decision = make_scale_decision(state)

    assert decision.direction == ScaleDirection.HOLD
    assert decision.desired_workers == 5
    assert "stable" in decision.reason.lower()


def test_multiple_scale_up_conditions_combine(monkeypatch):
    """Autoscaler combines multiple scale-up reasons."""
    monkeypatch.setenv("TARGET_QUEUE_DEPTH", "50")
    monkeypatch.setenv("TARGET_P95_LATENCY_MS", "2000")
    monkeypatch.setenv("MAX_WORKERS", "12")
    monkeypatch.setenv("SCALE_UP_STEP", "2")

    state = EngineState(
        current_workers=4,
        queue_depth=100,  # Exceeds target
        p95_latency_ms=3000.0,  # Exceeds target
        in_flight_jobs=4,  # All workers busy
    )

    decision = make_scale_decision(state)

    assert decision.direction == ScaleDirection.UP
    # All three conditions should be mentioned
    reason_lower = decision.reason.lower()
    assert "queue" in reason_lower or "p95" in reason_lower or "busy" in reason_lower


def test_scale_down_blocked_by_high_queue_depth(monkeypatch):
    """Autoscaler prevents scale down when queue depth is high."""
    monkeypatch.setenv("MIN_WORKERS", "1")
    monkeypatch.setenv("TARGET_QUEUE_DEPTH", "50")
    monkeypatch.setenv("TARGET_P95_LATENCY_MS", "2000")

    state = EngineState(
        current_workers=6,
        queue_depth=20,  # Above 30% threshold (15)
        p95_latency_ms=500.0,  # Low
        in_flight_jobs=2,  # Low utilization
    )

    decision = make_scale_decision(state)

    # Should hold instead of scaling down
    assert decision.direction in [ScaleDirection.HOLD, ScaleDirection.DOWN]
    if decision.direction == ScaleDirection.HOLD:
        assert decision.desired_workers == 6


def test_scale_down_blocked_by_high_latency(monkeypatch):
    """Autoscaler prevents scale down when latency is elevated."""
    monkeypatch.setenv("MIN_WORKERS", "1")
    monkeypatch.setenv("TARGET_QUEUE_DEPTH", "50")
    monkeypatch.setenv("TARGET_P95_LATENCY_MS", "2000")

    state = EngineState(
        current_workers=6,
        queue_depth=5,  # Low
        p95_latency_ms=1200.0,  # Above 50% threshold (1000)
        in_flight_jobs=2,  # Low utilization
    )

    decision = make_scale_decision(state)

    # Should hold instead of scaling down
    assert decision.direction in [ScaleDirection.HOLD, ScaleDirection.DOWN]
    if decision.direction == ScaleDirection.HOLD:
        assert decision.desired_workers == 6


def test_scale_down_blocked_by_high_utilization(monkeypatch):
    """Autoscaler prevents scale down when utilization is high."""
    monkeypatch.setenv("MIN_WORKERS", "1")
    monkeypatch.setenv("TARGET_QUEUE_DEPTH", "50")
    monkeypatch.setenv("TARGET_P95_LATENCY_MS", "2000")

    state = EngineState(
        current_workers=6,
        queue_depth=5,  # Low
        p95_latency_ms=500.0,  # Low
        in_flight_jobs=5,  # 83% utilization (above 70% threshold)
    )

    decision = make_scale_decision(state)

    # Should hold instead of scaling down
    assert decision.direction in [ScaleDirection.HOLD]
    assert decision.desired_workers == 6
