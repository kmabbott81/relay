"""
Redis-backed rate limiting for Knowledge API (Phase 3).

Per-user token bucket rate limiting with sliding window.
- Track request count per user per hour
- Dynamic Retry-After calculation
- Configurable limits per tier (Free, Pro, Enterprise)
- Token bucket algorithm: increment counter, set 1-hour expiry
"""

import logging
import os
import time
from typing import Optional

logger = logging.getLogger(__name__)

# Redis configuration
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")

# Rate limits per tier (requests per hour)
RATE_LIMITS = {
    "free": 100,
    "pro": 1000,
    "enterprise": 10000,
}

# Lazy-loaded Redis client
_redis_client = None


def _get_redis_client():
    """Lazy init Redis client."""
    global _redis_client
    if _redis_client is None:
        try:
            import redis.asyncio as redis_async

            _redis_client = redis_async.from_url(REDIS_URL)
        except ImportError:
            logger.warning("redis not available; rate limiting disabled")
            return None
    return _redis_client


async def init_redis() -> None:
    """Initialize Redis connection."""
    client = _get_redis_client()
    if client:
        try:
            await client.ping()
            logger.info(f"Redis connected: {REDIS_URL}")
        except Exception as e:
            logger.error(f"Redis connection failed: {e}")


async def get_rate_limit(user_id: str, user_tier: str = "free") -> dict:
    """
    Check current rate limit status for user using token bucket algorithm.

    Returns: {limit, remaining, reset_at, retry_after}
    """
    limit = RATE_LIMITS.get(user_tier, RATE_LIMITS["free"])
    key = f"ratelimit:{user_id}"

    redis_client = _get_redis_client()
    if not redis_client:
        # No Redis: unlimited
        return {
            "limit": limit,
            "remaining": limit,
            "reset_at": int(time.time()) + 3600,
            "retry_after": 0,
        }

    try:
        # Use Redis pipeline for atomic operations
        pipe = redis_client.pipeline()

        # Increment counter, set 1-hour expiry
        pipe.incr(key)
        pipe.expire(key, 3600)  # 1 hour TTL
        pipe.ttl(key)

        results = await pipe.execute()
        count = results[0]  # Current count
        ttl = results[2]  # Time to live in seconds

        remaining = max(0, limit - int(count))
        reset_at = int(time.time()) + ttl
        retry_after = ttl if remaining <= 0 else 0

        logger.debug(f"Rate limit for {user_id}: {count}/{limit}, remaining={remaining}, retry_after={retry_after}s")

        return {
            "limit": limit,
            "remaining": remaining,
            "reset_at": reset_at,
            "retry_after": retry_after,
        }
    except Exception as e:
        logger.error(f"Rate limit check failed: {e}")
        # On error: allow the request
        return {
            "limit": limit,
            "remaining": limit,
            "reset_at": int(time.time()) + 3600,
            "retry_after": 0,
        }


async def is_rate_limited(user_id: str, user_tier: str = "free") -> tuple[bool, Optional[int]]:
    """
    Check if user is rate limited.

    Returns: (is_limited, retry_after_seconds)
    """
    status = await get_rate_limit(user_id, user_tier)
    is_limited = status["remaining"] <= 0
    retry_after = status["retry_after"] if is_limited else None
    return is_limited, retry_after


async def reset_user_limit(user_id: str) -> None:
    """Reset rate limit for user (admin operation)."""
    redis_client = _get_redis_client()
    if not redis_client:
        return

    try:
        key = f"ratelimit:{user_id}"
        await redis_client.delete(key)
        logger.info(f"Rate limit reset for user {user_id}")
    except Exception as e:
        logger.error(f"Rate limit reset failed: {e}")


async def close_redis() -> None:
    """Close Redis connection."""
    global _redis_client
    if _redis_client:
        await _redis_client.close()
        logger.info("Redis connection closed")
