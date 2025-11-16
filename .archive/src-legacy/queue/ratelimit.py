"""
Rate Limiting (Sprint 29)

Token bucket rate limiter with global and per-tenant limits.
JSONL-based state for simplicity; supports Redis for production.
"""

import os
import threading
from datetime import UTC, datetime
from typing import Any


class TokenBucketLimiter:
    """
    Token bucket rate limiter.

    Tokens refill at constant rate. Operations consume tokens.
    """

    def __init__(self, rate: float, capacity: int):
        """
        Initialize token bucket.

        Args:
            rate: Tokens per second refill rate
            capacity: Maximum tokens in bucket
        """
        self.rate = rate
        self.capacity = capacity
        self.tokens = float(capacity)
        self.last_refill = datetime.now(UTC).timestamp()
        self.lock = threading.Lock()

    def _refill(self) -> None:
        """Refill tokens based on elapsed time."""
        now = datetime.now(UTC).timestamp()
        elapsed = now - self.last_refill

        # Add tokens based on elapsed time
        new_tokens = elapsed * self.rate
        self.tokens = min(self.capacity, self.tokens + new_tokens)
        self.last_refill = now

    def allow(self, tokens: float = 1.0) -> bool:
        """
        Check if operation is allowed and consume tokens.

        Args:
            tokens: Number of tokens to consume

        Returns:
            True if operation allowed
        """
        with self.lock:
            self._refill()

            if self.tokens >= tokens:
                self.tokens -= tokens
                return True

            return False

    def get_state(self) -> dict[str, Any]:
        """Get current bucket state."""
        with self.lock:
            self._refill()
            return {
                "tokens": self.tokens,
                "capacity": self.capacity,
                "rate": self.rate,
                "last_refill": self.last_refill,
            }


class RateLimiter:
    """
    Global, per-team, and per-tenant rate limiter (Sprint 34A).

    Uses token bucket algorithm with in-memory state.
    """

    def __init__(self):
        """Initialize rate limiter."""
        self.global_qps = int(os.getenv("GLOBAL_QPS_LIMIT", "30"))
        self.team_qps = int(os.getenv("TEAM_QPS_LIMIT", "10"))
        self.tenant_qps = int(os.getenv("TENANT_QPS_LIMIT", "5"))

        self.global_bucket = TokenBucketLimiter(rate=self.global_qps, capacity=self.global_qps * 2)

        self.team_buckets: dict[str, TokenBucketLimiter] = {}
        self.tenant_buckets: dict[str, TokenBucketLimiter] = {}
        self.lock = threading.Lock()

    def _get_team_bucket(self, team_id: str) -> TokenBucketLimiter:
        """Get or create team bucket (Sprint 34A)."""
        with self.lock:
            if team_id not in self.team_buckets:
                self.team_buckets[team_id] = TokenBucketLimiter(rate=self.team_qps, capacity=self.team_qps * 2)
            return self.team_buckets[team_id]

    def _get_tenant_bucket(self, tenant_id: str) -> TokenBucketLimiter:
        """Get or create tenant bucket."""
        with self.lock:
            if tenant_id not in self.tenant_buckets:
                self.tenant_buckets[tenant_id] = TokenBucketLimiter(rate=self.tenant_qps, capacity=self.tenant_qps * 2)
            return self.tenant_buckets[tenant_id]

    def allow(self, tenant_id: str, tokens: float = 1.0, team_id: str | None = None) -> bool:
        """
        Check if request is allowed for tenant.

        Args:
            tenant_id: Tenant identifier
            tokens: Number of tokens to consume
            team_id: Optional team identifier (Sprint 34A)

        Returns:
            True if request allowed (global, team, and tenant limits)
        """
        # Check global limit first
        if not self.global_bucket.allow(tokens):
            return False

        # Check team limit if team_id provided (Sprint 34A)
        if team_id:
            team_bucket = self._get_team_bucket(team_id)
            if not team_bucket.allow(tokens):
                # Refund global tokens if team limit hit
                with self.global_bucket.lock:
                    self.global_bucket.tokens = min(self.global_bucket.capacity, self.global_bucket.tokens + tokens)
                return False

        # Check tenant limit
        tenant_bucket = self._get_tenant_bucket(tenant_id)
        if not tenant_bucket.allow(tokens):
            # Refund global and team tokens if tenant limit hit
            with self.global_bucket.lock:
                self.global_bucket.tokens = min(self.global_bucket.capacity, self.global_bucket.tokens + tokens)
            if team_id:
                team_bucket = self._get_team_bucket(team_id)
                with team_bucket.lock:
                    team_bucket.tokens = min(team_bucket.capacity, team_bucket.tokens + tokens)
            return False

        return True

    def get_stats(self) -> dict[str, Any]:
        """Get rate limiter statistics."""
        return {
            "global": self.global_bucket.get_state(),
            "teams": {tid: bucket.get_state() for tid, bucket in self.team_buckets.items()},
            "tenants": {tid: bucket.get_state() for tid, bucket in self.tenant_buckets.items()},
        }


# Singleton instance
_limiter: RateLimiter | None = None
_limiter_lock = threading.Lock()


def get_rate_limiter() -> RateLimiter:
    """Get singleton rate limiter instance."""
    global _limiter

    if _limiter is None:
        with _limiter_lock:
            if _limiter is None:
                _limiter = RateLimiter()

    return _limiter
