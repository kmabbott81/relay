"""Tests for retry policy with exponential backoff."""

import time

from relay_ai.queue.retry import (
    IdempotencyTracker,
    RetryConfig,
    RetryState,
    calculate_backoff_ms,
    retry_with_backoff,
    should_retry,
)


def test_exponential_backoff_calculation():
    """Exponential backoff increases with attempt number."""
    config = RetryConfig(max_retries=3, base_delay_ms=400, jitter_pct=0.0)

    # Attempt 0: 400ms
    backoff_0 = calculate_backoff_ms(0, config)
    assert backoff_0 == 400

    # Attempt 1: 800ms (400 * 2^1)
    backoff_1 = calculate_backoff_ms(1, config)
    assert backoff_1 == 800

    # Attempt 2: 1600ms (400 * 2^2)
    backoff_2 = calculate_backoff_ms(2, config)
    assert backoff_2 == 1600


def test_jitter_adds_randomness():
    """Jitter adds randomness to backoff delays."""
    config = RetryConfig(max_retries=3, base_delay_ms=1000, jitter_pct=0.2)

    # Calculate multiple backoffs for same attempt
    backoffs = [calculate_backoff_ms(0, config) for _ in range(20)]

    # Should have variation due to jitter
    unique_values = set(backoffs)
    assert len(unique_values) > 1  # Not all the same

    # All values should be within jitter range (1000 +/- 200)
    for backoff in backoffs:
        assert 800 <= backoff <= 1200


def test_jitter_range_is_symmetric():
    """Jitter can be positive or negative."""
    config = RetryConfig(max_retries=3, base_delay_ms=1000, jitter_pct=0.3)

    # Calculate many backoffs
    backoffs = [calculate_backoff_ms(0, config) for _ in range(100)]

    # Should have values both above and below base
    has_above = any(b > 1000 for b in backoffs)
    has_below = any(b < 1000 for b in backoffs)

    assert has_above and has_below


def test_max_retries_respected():
    """Retry logic respects max retry limit."""
    config = RetryConfig(max_retries=2, base_delay_ms=100, jitter_pct=0.0)

    state = RetryState(job_id="test-job", attempt=2, max_attempts=2)

    # At max retries, should not retry
    assert should_retry(state, config) is False


def test_should_retry_when_attempts_remain():
    """Should retry when attempts remain."""
    config = RetryConfig(max_retries=3, base_delay_ms=100, jitter_pct=0.0)

    state = RetryState(job_id="test-job", attempt=1, max_attempts=3)

    assert should_retry(state, config) is True


def test_successful_execution_on_first_try():
    """Retry logic succeeds on first attempt without retries."""
    call_count = []

    def successful_task():
        call_count.append(1)

    config = RetryConfig(max_retries=3, base_delay_ms=100, jitter_pct=0.0)

    success, error = retry_with_backoff(
        job_id="test-job",
        task=successful_task,
        config=config,
    )

    assert success is True
    assert error is None
    assert len(call_count) == 1  # Called only once


def test_successful_retry_after_transient_failure():
    """Retry logic succeeds after transient failures."""
    call_count = []

    def flaky_task():
        call_count.append(1)
        if len(call_count) < 3:
            raise ValueError("Transient error")
        # Success on 3rd attempt

    config = RetryConfig(max_retries=5, base_delay_ms=50, jitter_pct=0.0)

    success, error = retry_with_backoff(
        job_id="test-job",
        task=flaky_task,
        config=config,
    )

    assert success is True
    assert error is None
    assert len(call_count) == 3  # Failed twice, succeeded on 3rd


def test_retry_exhaustion_returns_failure():
    """Retry logic returns failure when retries exhausted."""
    call_count = []

    def always_fails():
        call_count.append(1)
        raise ValueError("Permanent error")

    config = RetryConfig(max_retries=2, base_delay_ms=50, jitter_pct=0.0)

    success, error = retry_with_backoff(
        job_id="test-job",
        task=always_fails,
        config=config,
    )

    assert success is False
    assert error is not None
    assert isinstance(error, ValueError)
    assert str(error) == "Permanent error"
    assert len(call_count) == 3  # Initial attempt + 2 retries


def test_retry_with_args_and_kwargs():
    """Retry logic passes args and kwargs to task."""
    results = []

    def task_with_params(a, b, c=None):
        results.append((a, b, c))

    config = RetryConfig(max_retries=2, base_delay_ms=50, jitter_pct=0.0)

    success, error = retry_with_backoff(
        job_id="test-job",
        task=task_with_params,
        args=(1, 2),
        kwargs={"c": 3},
        config=config,
    )

    assert success is True
    assert results == [(1, 2, 3)]


def test_retry_config_loads_from_env(monkeypatch):
    """RetryConfig loads from environment variables."""
    monkeypatch.setenv("MAX_RETRIES", "5")
    monkeypatch.setenv("RETRY_BASE_MS", "600")
    monkeypatch.setenv("RETRY_JITTER_PCT", "0.25")

    config = RetryConfig.from_env()

    assert config.max_retries == 5
    assert config.base_delay_ms == 600
    assert config.jitter_pct == 0.25


def test_retry_config_defaults(monkeypatch):
    """RetryConfig uses defaults when env vars not set."""
    monkeypatch.delenv("MAX_RETRIES", raising=False)
    monkeypatch.delenv("RETRY_BASE_MS", raising=False)
    monkeypatch.delenv("RETRY_JITTER_PCT", raising=False)

    config = RetryConfig.from_env()

    assert config.max_retries == 3
    assert config.base_delay_ms == 400
    assert config.jitter_pct == 0.2


def test_retry_with_backoff_uses_env_config(monkeypatch):
    """retry_with_backoff loads config from env when not provided."""
    monkeypatch.setenv("MAX_RETRIES", "1")
    monkeypatch.setenv("RETRY_BASE_MS", "50")
    monkeypatch.setenv("RETRY_JITTER_PCT", "0.0")

    call_count = []

    def always_fails():
        call_count.append(1)
        raise ValueError("Error")

    success, error = retry_with_backoff(
        job_id="test-job",
        task=always_fails,
    )

    assert success is False
    # Should use MAX_RETRIES=1 from env (1 initial + 1 retry = 2 calls)
    assert len(call_count) == 2


def test_idempotency_tracker_prevents_duplicates():
    """IdempotencyTracker prevents duplicate job execution."""
    tracker = IdempotencyTracker()

    # First execution
    is_dup_1 = tracker.is_duplicate("job-123")
    assert is_dup_1 is False

    # Second execution (duplicate)
    is_dup_2 = tracker.is_duplicate("job-123")
    assert is_dup_2 is True


def test_idempotency_tracker_different_jobs():
    """IdempotencyTracker allows different job IDs."""
    tracker = IdempotencyTracker()

    is_dup_1 = tracker.is_duplicate("job-1")
    is_dup_2 = tracker.is_duplicate("job-2")
    is_dup_3 = tracker.is_duplicate("job-3")

    assert is_dup_1 is False
    assert is_dup_2 is False
    assert is_dup_3 is False


def test_idempotency_tracker_mark_completed():
    """IdempotencyTracker keeps completed jobs in seen set."""
    tracker = IdempotencyTracker()

    tracker.is_duplicate("job-1")  # Mark as seen
    tracker.mark_completed("job-1")

    # Still tracked after completion
    is_dup = tracker.is_duplicate("job-1")
    assert is_dup is True


def test_idempotency_tracker_clear():
    """IdempotencyTracker can be cleared."""
    tracker = IdempotencyTracker()

    tracker.is_duplicate("job-1")
    tracker.is_duplicate("job-2")

    tracker.clear()

    # After clear, jobs can be executed again
    is_dup_1 = tracker.is_duplicate("job-1")
    is_dup_2 = tracker.is_duplicate("job-2")

    assert is_dup_1 is False
    assert is_dup_2 is False


def test_idempotency_tracker_thread_safe():
    """IdempotencyTracker is thread-safe."""
    import threading

    tracker = IdempotencyTracker()
    results = []

    def check_duplicate(job_id):
        is_dup = tracker.is_duplicate(job_id)
        results.append((job_id, is_dup))

    # Start multiple threads checking same job ID
    threads = []
    for _ in range(10):
        thread = threading.Thread(target=check_duplicate, args=("job-concurrent",))
        threads.append(thread)
        thread.start()

    for thread in threads:
        thread.join()

    # Exactly one thread should see it as not duplicate
    not_duplicates = [r for r in results if r[1] is False]
    assert len(not_duplicates) == 1


def test_retry_backoff_timing():
    """Retry backoff actually delays between attempts."""
    config = RetryConfig(max_retries=2, base_delay_ms=100, jitter_pct=0.0)
    call_times = []

    def failing_task():
        call_times.append(time.time())
        raise ValueError("Error")

    start = time.time()
    success, error = retry_with_backoff(
        job_id="test-job",
        task=failing_task,
        config=config,
    )
    elapsed = time.time() - start

    assert success is False
    assert len(call_times) == 3

    # Should have delays between attempts
    # Attempt 0->1: ~100ms, Attempt 1->2: ~200ms
    # Total: at least 300ms
    assert elapsed >= 0.3


def test_retry_state_tracking():
    """RetryState tracks job retry information."""
    state = RetryState(
        job_id="test-job",
        attempt=2,
        max_attempts=5,
        last_error="Connection timeout",
    )

    assert state.job_id == "test-job"
    assert state.attempt == 2
    assert state.max_attempts == 5
    assert state.last_error == "Connection timeout"
    assert state.next_retry_at is None


def test_zero_jitter_is_deterministic():
    """Zero jitter produces deterministic backoff."""
    config = RetryConfig(max_retries=3, base_delay_ms=500, jitter_pct=0.0)

    backoffs = [calculate_backoff_ms(1, config) for _ in range(10)]

    # All values should be identical
    assert len(set(backoffs)) == 1
    assert backoffs[0] == 1000  # 500 * 2^1
