"""Sprint 51 Phase 2: Unit tests for rate limiting.

Test categories:
1. In-process rate limiter: token bucket refill, limit enforcement
2. Redis rate limiter: fixed window counters, expiry
3. Rate limiter exception: 429 with headers
4. Integration: execute endpoint returns 429 on breach
"""

from unittest.mock import MagicMock, patch

import pytest

# --- Test Category 1: In-Process Rate Limiter ---


def test_inproc_limiter_allows_within_limit():
    """In-process limiter allows requests within rate limit."""
    from src.limits.limiter import InProcessRateLimiter

    limiter = InProcessRateLimiter(limit_per_min=60)
    current_time = 1000.0

    # First request should succeed
    allowed, remaining, reset_ts, retry_after = limiter.check_rate_limit("workspace1", current_time)

    assert allowed is True
    assert remaining == 59  # Started with 60, consumed 1
    assert reset_ts > current_time
    assert retry_after == 0


def test_inproc_limiter_refills_tokens_over_time():
    """In-process limiter refills tokens based on time passed."""
    from src.limits.limiter import InProcessRateLimiter

    limiter = InProcessRateLimiter(limit_per_min=60)
    current_time = 1000.0

    # Consume all 60 tokens
    for _ in range(60):
        allowed, _, _, _ = limiter.check_rate_limit("workspace1", current_time)
        assert allowed is True

    # Next request should be blocked
    allowed, remaining, reset_ts, retry_after = limiter.check_rate_limit("workspace1", current_time)
    assert allowed is False
    assert remaining == 0
    assert retry_after == 1  # 60 tokens per min = 1 second per token

    # After 10 seconds, should have refilled 10 tokens (60/min = 1/sec)
    current_time += 10.0

    # First check after 10 seconds should refill 10 tokens
    allowed, remaining, _, _ = limiter.check_rate_limit("workspace1", current_time)
    assert allowed is True
    assert remaining == 9  # Had 10, consumed 1

    # Consume the remaining 9 tokens (don't advance time to avoid refill)
    for _ in range(1, 10):
        allowed, _, _, _ = limiter.check_rate_limit("workspace1", current_time)
        assert allowed is True

    # All 10 tokens consumed, next request should be blocked
    allowed, remaining, _, _ = limiter.check_rate_limit("workspace1", current_time)
    assert allowed is False
    assert remaining == 0


def test_inproc_limiter_isolates_workspaces():
    """In-process limiter isolates rate limits per workspace."""
    from src.limits.limiter import InProcessRateLimiter

    limiter = InProcessRateLimiter(limit_per_min=60)
    current_time = 1000.0

    # Consume all tokens for workspace1
    for _ in range(60):
        allowed, _, _, _ = limiter.check_rate_limit("workspace1", current_time)
        assert allowed is True

    # workspace1 should be blocked
    allowed, _, _, _ = limiter.check_rate_limit("workspace1", current_time)
    assert allowed is False

    # workspace2 should still have tokens
    allowed, remaining, _, _ = limiter.check_rate_limit("workspace2", current_time)
    assert allowed is True
    assert remaining == 59


# --- Test Category 2: Redis Rate Limiter ---


def test_redis_limiter_allows_within_limit():
    """Redis limiter allows requests within rate limit."""
    from src.limits.limiter import RedisRateLimiter

    mock_redis = MagicMock()
    mock_redis.incr.return_value = 1  # First request in window
    limiter = RedisRateLimiter(mock_redis, limit_per_min=60)

    current_time = 1000.0
    allowed, remaining, reset_ts, retry_after = limiter.check_rate_limit("workspace1", current_time)

    assert allowed is True
    assert remaining == 59
    assert retry_after == 0
    # Verify Redis commands
    mock_redis.incr.assert_called_once()
    mock_redis.expire.assert_called_once()


def test_redis_limiter_blocks_at_limit():
    """Redis limiter blocks requests at rate limit."""
    from src.limits.limiter import RedisRateLimiter

    mock_redis = MagicMock()
    mock_redis.incr.return_value = 61  # Exceeded limit of 60
    limiter = RedisRateLimiter(mock_redis, limit_per_min=60)

    current_time = 1000.0
    allowed, remaining, reset_ts, retry_after = limiter.check_rate_limit("workspace1", current_time)

    assert allowed is False
    assert remaining == 0
    assert retry_after > 0  # Should have retry-after


def test_redis_limiter_uses_fixed_window():
    """Redis limiter uses fixed 1-minute windows."""
    from src.limits.limiter import RedisRateLimiter

    mock_redis = MagicMock()
    mock_redis.incr.return_value = 1
    limiter = RedisRateLimiter(mock_redis, limit_per_min=60)

    # At 1000.0 seconds (epoch_min = 16)
    current_time = 1000.0
    epoch_min = int(current_time // 60)
    limiter.check_rate_limit("workspace1", current_time)

    # Verify key format: rl:{workspace_id}:{epoch_min}
    expected_key = f"rl:workspace1:{epoch_min}"
    mock_redis.incr.assert_called_with(expected_key)

    # At 1060.0 seconds (epoch_min = 17), should use new key
    mock_redis.reset_mock()
    current_time = 1060.0
    new_epoch_min = int(current_time // 60)
    limiter.check_rate_limit("workspace1", current_time)

    new_expected_key = f"rl:workspace1:{new_epoch_min}"
    mock_redis.incr.assert_called_with(new_expected_key)
    assert new_expected_key != expected_key


def test_redis_limiter_fails_open_on_error():
    """Redis limiter fails open (allows request) if Redis is unavailable."""
    from src.limits.limiter import RedisRateLimiter

    mock_redis = MagicMock()
    mock_redis.incr.side_effect = Exception("Redis connection failed")
    limiter = RedisRateLimiter(mock_redis, limit_per_min=60)

    current_time = 1000.0
    allowed, remaining, reset_ts, retry_after = limiter.check_rate_limit("workspace1", current_time)

    # Should allow request despite Redis failure (fail-open for availability)
    assert allowed is True
    assert retry_after == 0


# --- Test Category 3: Rate Limit Exception ---


def test_rate_limit_exception_has_correct_headers():
    """RateLimitExceeded exception includes retry headers."""
    from src.limits.limiter import RateLimitExceeded

    exc = RateLimitExceeded(retry_after=30, limit=60, remaining=0, reset=2000)

    assert exc.status_code == 429
    assert exc.headers["Retry-After"] == "30"
    assert exc.headers["X-RateLimit-Limit"] == "60"
    assert exc.headers["X-RateLimit-Remaining"] == "0"
    assert exc.headers["X-RateLimit-Reset"] == "2000"
    assert "Rate limit exceeded" in exc.detail


# --- Test Category 4: Rate Limiter Integration ---


def test_rate_limiter_respects_env_flags():
    """Rate limiter respects RATE_LIMIT_ENABLED and RATE_LIMIT_EXEC_PER_MIN env vars."""
    with patch.dict("os.environ", {"RATE_LIMIT_ENABLED": "false"}):
        from src.limits.limiter import RateLimiter

        limiter = RateLimiter()
        # Should not raise even if called many times
        for _ in range(100):
            limiter.check_limit("workspace1")  # Should not raise

    with patch.dict("os.environ", {"RATE_LIMIT_ENABLED": "true", "RATE_LIMIT_EXEC_PER_MIN": "10"}):
        from src.limits.limiter import RateLimiter

        limiter = RateLimiter()
        assert limiter.limit_per_min == 10


def test_rate_limiter_check_limit_raises_on_breach():
    """Rate limiter check_limit raises RateLimitExceeded on breach."""
    from src.limits.limiter import InProcessRateLimiter, RateLimiter, RateLimitExceeded

    # Patch RateLimiter to use in-process backend with low limit
    with patch.dict("os.environ", {"RATE_LIMIT_ENABLED": "true", "RATE_LIMIT_EXEC_PER_MIN": "2"}):
        limiter = RateLimiter()
        limiter.backend = InProcessRateLimiter(limit_per_min=2)

        # First 2 requests should succeed
        limiter.check_limit("workspace1")
        limiter.check_limit("workspace1")

        # Third request should raise
        with pytest.raises(RateLimitExceeded) as exc_info:
            limiter.check_limit("workspace1")

        assert exc_info.value.status_code == 429
        assert "Rate limit exceeded" in str(exc_info.value.detail)


# --- Test Category 5: Smoke Tests ---


def test_rate_limiter_module_imports():
    """Rate limiter module imports successfully."""
    from src.limits import limiter

    assert hasattr(limiter, "get_rate_limiter")
    assert hasattr(limiter, "RateLimitExceeded")
    assert hasattr(limiter, "InProcessRateLimiter")
    assert hasattr(limiter, "RedisRateLimiter")


def test_webapi_rate_limit_handler_exists():
    """webapi defines rate limit exception handler."""
    # Check exception handlers include RateLimitExceeded
    from src.limits.limiter import RateLimitExceeded
    from src.webapi import app

    assert RateLimitExceeded in app.exception_handlers
