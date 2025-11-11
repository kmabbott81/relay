"""Tests for backoff policy (Sprint 29)."""

from relay_ai.queue.backoff import compute_delay


def test_backoff_first_attempt():
    """Test first retry uses base delay."""
    delay = compute_delay(500, 0, 60000, 0.0)  # No jitter
    assert delay == 500


def test_backoff_exponential_growth():
    """Test exponential growth: 500, 1000, 2000, 4000."""
    assert compute_delay(500, 0, 60000, 0.0) == 500
    assert compute_delay(500, 1, 60000, 0.0) == 1000
    assert compute_delay(500, 2, 60000, 0.0) == 2000
    assert compute_delay(500, 3, 60000, 0.0) == 4000


def test_backoff_cap_honored():
    """Test delay is capped at maximum."""
    delay = compute_delay(500, 10, 5000, 0.0)  # 500 * 2^10 = 512000, cap at 5000
    assert delay == 5000


def test_backoff_jitter_bounds():
    """Test jitter stays within bounds."""
    base = 1000
    jitter_pct = 0.2  # ±20%

    # Run multiple times to test randomness
    delays = [compute_delay(base, 0, 60000, jitter_pct) for _ in range(100)]

    # All delays should be within base ± 20%
    for delay in delays:
        assert 800 <= delay <= 1200  # 1000 * (1 ± 0.2)


def test_backoff_negative_attempt():
    """Test negative attempt treated as zero."""
    delay = compute_delay(500, -5, 60000, 0.0)
    assert delay == 500


def test_backoff_jitter_with_cap():
    """Test jitter applied before cap."""
    # With jitter, should still respect cap
    delay = compute_delay(500, 10, 5000, 0.2)
    assert 0 <= delay <= 6000  # Cap with jitter: 5000 * 1.2
