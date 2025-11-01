"""Tests for retry logic."""


from src.connectors.retry import compute_backoff_ms


def test_compute_backoff_exponential():
    """Backoff grows exponentially."""
    backoff0 = compute_backoff_ms(0, base_ms=100, jitter_pct=0.0)
    backoff1 = compute_backoff_ms(1, base_ms=100, jitter_pct=0.0)
    backoff2 = compute_backoff_ms(2, base_ms=100, jitter_pct=0.0)

    assert backoff0 == 100  # 100 * 2^0
    assert backoff1 == 200  # 100 * 2^1
    assert backoff2 == 400  # 100 * 2^2


def test_compute_backoff_capped():
    """Backoff respects cap."""
    backoff = compute_backoff_ms(10, base_ms=100, cap_ms=1000, jitter_pct=0.0)

    assert backoff <= 1000


def test_compute_backoff_jitter():
    """Jitter adds randomness."""
    # Run multiple times to get different jitter values
    backoffs = [compute_backoff_ms(1, base_ms=100, jitter_pct=0.2) for _ in range(10)]

    # Should have variance
    assert len(set(backoffs)) > 1

    # All should be near 200ms ± 20%
    for b in backoffs:
        assert 160 <= b <= 240


def test_compute_backoff_from_env(monkeypatch):
    """Backoff reads from environment."""
    monkeypatch.setenv("RETRY_BASE_MS", "500")
    monkeypatch.setenv("RETRY_CAP_MS", "5000")
    monkeypatch.setenv("RETRY_JITTER_PCT", "0.0")

    backoff = compute_backoff_ms(0)

    assert backoff == 500
