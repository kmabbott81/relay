"""Tests for rate limiting (Sprint 29)."""

import os
import time

from src.queue.ratelimit import TokenBucketLimiter


def test_token_bucket_initial_capacity():
    """Test bucket starts at full capacity."""
    bucket = TokenBucketLimiter(rate=10.0, capacity=10)
    state = bucket.get_state()
    assert state["tokens"] == 10
    assert state["capacity"] == 10


def test_token_bucket_consume():
    """Test consuming tokens."""
    bucket = TokenBucketLimiter(rate=10.0, capacity=10)

    assert bucket.allow(1.0) is True
    state = bucket.get_state()
    # Allow small refill during execution
    assert 8.9 <= state["tokens"] <= 9.1


def test_token_bucket_exhaustion():
    """Test bucket exhaustion."""
    bucket = TokenBucketLimiter(rate=10.0, capacity=5)

    # Consume all tokens
    for _ in range(5):
        assert bucket.allow(1.0) is True

    # Next request should be denied
    assert bucket.allow(1.0) is False


def test_token_bucket_refill():
    """Test tokens refill over time."""
    bucket = TokenBucketLimiter(rate=100.0, capacity=10)

    # Consume all tokens
    for _ in range(10):
        bucket.allow(1.0)

    # Wait for refill (0.1 second = 10 tokens at 100/sec)
    # TODO(Sprint 45): replace with wait_until(...) for faster polling
    time.sleep(0.15)

    # Should have refilled
    assert bucket.allow(1.0) is True


def test_rate_limiter_global_limit():
    """Test global rate limit."""
    os.environ["GLOBAL_QPS_LIMIT"] = "5"
    os.environ["TENANT_QPS_LIMIT"] = "10"

    # Create new limiter instance
    from src.queue.ratelimit import RateLimiter

    limiter = RateLimiter()

    # Should allow up to global limit (capacity is 2x)
    for _ in range(10):
        assert limiter.allow("tenant-1", 1.0) is True

    # Next request should be rate limited by global
    assert limiter.allow("tenant-1", 1.0) is False


def test_rate_limiter_tenant_limit():
    """Test per-tenant rate limit."""
    os.environ["GLOBAL_QPS_LIMIT"] = "100"
    os.environ["TENANT_QPS_LIMIT"] = "3"

    from src.queue.ratelimit import RateLimiter

    limiter = RateLimiter()

    # Tenant-1 should be limited at 6 (capacity is 2x rate)
    for _ in range(6):
        assert limiter.allow("tenant-1", 1.0) is True

    assert limiter.allow("tenant-1", 1.0) is False

    # Tenant-2 should still have capacity
    assert limiter.allow("tenant-2", 1.0) is True


def test_rate_limiter_refund_on_tenant_limit():
    """Test global tokens refunded when tenant limit hit."""
    os.environ["GLOBAL_QPS_LIMIT"] = "100"
    os.environ["TENANT_QPS_LIMIT"] = "2"

    from src.queue.ratelimit import RateLimiter

    limiter = RateLimiter()

    # Consume tenant limit (capacity is 2x = 4 tokens)
    for _ in range(4):
        limiter.allow("tenant-1", 1.0)

    # Next should be rejected and global tokens refunded
    global_before = limiter.global_bucket.get_state()["tokens"]
    limiter.allow("tenant-1", 1.0)
    global_after = limiter.global_bucket.get_state()["tokens"]

    # Global tokens should be similar (refunded)
    assert abs(global_after - global_before) < 1.5  # Allow for rounding
