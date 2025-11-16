"""Minimal rollout gate implementation.

Sprint 54: Percentage-based rollout with Redis backing and consistent hashing.

This implementation provides rollout gating using:
- Redis for configuration storage
- Consistent hashing (SHA-256) for stable user bucketing
- Local caching to reduce Redis load

Redis keys:
- flags:{feature}:rollout_percent = "0" to "100"

Key features:
- Sticky user experience: same actor_id → same decision across requests
- Optional workspace salting for tenant-level controls
- 5-second local cache to avoid Redis hammering

Future upgrade path:
- Add more sophisticated bucketing strategies (geo, attributes, etc.)
- Swap to ControllerGate when automated rollout is needed
"""

import hashlib
import os
import time
from typing import Optional


def _bucket(value: str) -> int:
    """Compute stable hash bucket (1-100) for a string value.

    Uses SHA-256 for stable, deterministic bucketing. Same input always
    produces same bucket, enabling sticky user experiences.

    Args:
        value: String to hash (e.g., actor_id or workspace:actor)

    Returns:
        Bucket number from 1 to 100 (inclusive)
    """
    h = hashlib.sha256(value.encode("utf-8")).hexdigest()
    return (int(h[:8], 16) % 100) + 1


class MinimalGate:
    """Minimal rollout gate with Redis backing and local cache.

    Uses consistent hashing for rollout decisions, ensuring users get
    stable experiences (same user → same decision across requests).
    Caches rollout percentages locally to avoid hammering Redis.

    Example:
        gate = MinimalGate(redis_client, cache_ttl_sec=5)

        # Check if feature is enabled
        if gate.allow("google", {"actor_id": "user_123"}):
            print("Feature enabled!")

        # Get current percentage
        print(f"Current rollout: {gate.percent('google')}%")
    """

    def __init__(self, redis_client, cache_ttl_sec: int = 5):
        """Initialize minimal gate.

        Args:
            redis_client: Redis client (from redis.from_url(...))
            cache_ttl_sec: How long to cache rollout percentages (default 5s)
        """
        self.redis = redis_client
        self.cache_ttl = cache_ttl_sec
        self._cache: dict[str, tuple[int, float]] = {}

    def _read_percent(self, feature: str) -> int:
        """Read rollout percentage from Redis with local caching.

        Args:
            feature: Feature name (e.g., "google")

        Returns:
            Rollout percentage (0-100)
        """
        now = time.time()

        # Check cache first
        if feature in self._cache:
            pct, cached_at = self._cache[feature]
            if now - cached_at < self.cache_ttl:
                return pct

        # Read from Redis
        key = f"flags:{feature}:rollout_percent"
        val: Optional[bytes] = self.redis.get(key)

        # Fall back to env var if Redis key not set
        if val is None:
            env_key = f"FLAGS_{feature.upper()}_ROLLOUT_PERCENT"
            val_str = os.getenv(env_key, "0")
        else:
            val_str = val.decode().strip() if isinstance(val, bytes) else str(val)

        # Parse and clamp to 0-100
        try:
            pct = max(0, min(100, int(val_str)))
        except (ValueError, AttributeError):
            pct = 0

        # Update cache
        self._cache[feature] = (pct, now)
        return pct

    def percent(self, feature: str) -> int:
        """Get current rollout percentage for feature.

        Args:
            feature: Feature name (e.g., "google")

        Returns:
            Current rollout percentage (0-100)
        """
        return self._read_percent(feature)

    def allow(self, feature: str, context: dict) -> bool:
        """Decide if feature is allowed for this request.

        Uses consistent hashing based on actor_id for stable user bucketing.
        Same user always gets same decision (sticky experience).

        Args:
            feature: Feature name (e.g., "google")
            context: Request context with actor_id, user_id, or workspace_id

        Returns:
            True if feature should be enabled for this request
        """
        pct = self.percent(feature)

        # Build stable hash key from context
        actor_id = context.get("actor_id") or context.get("user_id") or "anon"
        workspace_id = context.get("workspace_id")

        # Optional: salt with workspace_id for tenant-level controls
        key = f"{workspace_id}:{actor_id}" if workspace_id else actor_id

        # Consistent hash: same key → same bucket → stable decision
        return _bucket(key) <= pct
