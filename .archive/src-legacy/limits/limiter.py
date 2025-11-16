"""Rate limiter with Redis backend and in-process fallback.

Strategy:
- If REDIS_URL set: Use Redis with fixed-window counters (1-minute buckets)
- If no Redis: Use in-process token bucket per workspace
- Key format: rl:{workspace_id}:{epoch_min}
- Returns 429 with headers: Retry-After, X-RateLimit-Limit, X-RateLimit-Remaining, X-RateLimit-Reset
"""

from __future__ import annotations

import os
import time
from typing import Any

from fastapi import HTTPException


class RateLimitExceeded(HTTPException):
    """Rate limit exceeded exception with retry headers."""

    def __init__(self, retry_after: int, limit: int, remaining: int, reset: int):
        self.retry_after = retry_after
        self.limit = limit
        self.remaining = remaining
        self.reset = reset
        super().__init__(
            status_code=429,
            detail=f"Rate limit exceeded. Try again in {retry_after} seconds.",
            headers={
                "Retry-After": str(retry_after),
                "X-RateLimit-Limit": str(limit),
                "X-RateLimit-Remaining": str(remaining),
                "X-RateLimit-Reset": str(reset),
            },
        )


class InProcessRateLimiter:
    """In-process token bucket rate limiter (fallback when Redis unavailable)."""

    def __init__(self, limit_per_min: int = 60):
        self.limit_per_min = limit_per_min
        self.buckets: dict[str, dict[str, Any]] = {}

    def check_rate_limit(self, workspace_id: str, current_time: float | None = None) -> tuple[bool, int, int, int]:
        """Check if request is within rate limit.

        Returns:
            (allowed, remaining, reset_timestamp, retry_after_seconds)
        """
        if current_time is None:
            current_time = time.time()

        # Initialize bucket if first request
        if workspace_id not in self.buckets:
            self.buckets[workspace_id] = {"tokens": self.limit_per_min, "last_refill": current_time}

        bucket = self.buckets[workspace_id]
        time_passed = current_time - bucket["last_refill"]

        # Refill tokens based on time passed (1 token per second, max limit_per_min)
        tokens_to_add = int(time_passed * (self.limit_per_min / 60.0))
        if tokens_to_add > 0:
            bucket["tokens"] = min(self.limit_per_min, bucket["tokens"] + tokens_to_add)
            bucket["last_refill"] = current_time

        # Check if tokens available
        if bucket["tokens"] > 0:
            bucket["tokens"] -= 1
            remaining = bucket["tokens"]
            # Next refill time
            reset_timestamp = int(current_time + ((self.limit_per_min - remaining) / (self.limit_per_min / 60.0)))
            return (True, remaining, reset_timestamp, 0)
        else:
            # Calculate retry-after (seconds until next token)
            retry_after = int(60.0 / self.limit_per_min)
            reset_timestamp = int(current_time + retry_after)
            return (False, 0, reset_timestamp, retry_after)


class RedisRateLimiter:
    """Redis-backed fixed-window rate limiter (1-minute buckets)."""

    def __init__(self, redis_client: Any, limit_per_min: int = 60):
        self.redis = redis_client
        self.limit_per_min = limit_per_min

    def check_rate_limit(self, workspace_id: str, current_time: float | None = None) -> tuple[bool, int, int, int]:
        """Check if request is within rate limit using Redis.

        Returns:
            (allowed, remaining, reset_timestamp, retry_after_seconds)
        """
        if current_time is None:
            current_time = time.time()

        # Fixed window: current minute epoch
        epoch_min = int(current_time // 60)
        key = f"rl:{workspace_id}:{epoch_min}"
        reset_timestamp = (epoch_min + 1) * 60

        try:
            # Increment counter and set expiry (2 minutes to handle clock skew)
            count = self.redis.incr(key)
            if count == 1:
                self.redis.expire(key, 120)

            remaining = max(0, self.limit_per_min - count)

            if count <= self.limit_per_min:
                return (True, remaining, reset_timestamp, 0)
            else:
                retry_after = reset_timestamp - int(current_time)
                return (False, 0, reset_timestamp, retry_after)

        except Exception as e:
            # Redis failure: fail open (allow request but log warning)
            print(f"[WARN] Redis rate limiter failed: {e}. Allowing request (fail-open).")
            return (True, self.limit_per_min - 1, reset_timestamp, 0)


class RateLimiter:
    """Unified rate limiter interface with Redis or in-process backend."""

    def __init__(self):
        self.enabled = os.getenv("RATE_LIMIT_ENABLED", "true").lower() == "true"
        self.limit_per_min = int(os.getenv("RATE_LIMIT_EXEC_PER_MIN", "60"))
        self.redis_url = os.getenv("REDIS_URL")

        if self.redis_url:
            try:
                import redis

                self.redis_client = redis.from_url(self.redis_url, decode_responses=True)
                # Test connection
                self.redis_client.ping()
                self.backend = RedisRateLimiter(self.redis_client, self.limit_per_min)
                print(f"[INFO] Rate limiter: Using Redis backend ({self.limit_per_min}/min)")
            except Exception as e:
                print(f"[WARN] Redis connection failed: {e}. Falling back to in-process limiter.")
                self.backend = InProcessRateLimiter(self.limit_per_min)
        else:
            self.backend = InProcessRateLimiter(self.limit_per_min)
            print(f"[INFO] Rate limiter: Using in-process backend ({self.limit_per_min}/min)")

    def check_limit(self, workspace_id: str) -> None:
        """Check rate limit for workspace. Raises RateLimitExceeded if breached."""
        if not self.enabled:
            return

        allowed, remaining, reset_timestamp, retry_after = self.backend.check_rate_limit(workspace_id)

        if not allowed:
            raise RateLimitExceeded(
                retry_after=retry_after, limit=self.limit_per_min, remaining=remaining, reset=reset_timestamp
            )

    def get_headers(self, workspace_id: str) -> dict[str, str]:
        """Get rate limit headers for current state (for successful requests)."""
        if not self.enabled:
            return {}

        allowed, remaining, reset_timestamp, _ = self.backend.check_rate_limit(workspace_id)
        return {
            "X-RateLimit-Limit": str(self.limit_per_min),
            "X-RateLimit-Remaining": str(remaining),
            "X-RateLimit-Reset": str(reset_timestamp),
        }


# Global rate limiter instance
_limiter: RateLimiter | None = None


def get_rate_limiter() -> RateLimiter:
    """Get or create global rate limiter instance."""
    global _limiter
    if _limiter is None:
        _limiter = RateLimiter()
    return _limiter
