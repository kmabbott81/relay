"""Rate limiting and quota enforcement for /api/v1/stream.

Sprint 61b R0.5 Security Hotfix: Redis-backed rate limits + quotas.

Patterns:
- Rate limit: Per-user and per-IP (token bucket via Lua)
- Quotas: Anonymous session quotas (hourly + total)
"""

import os
import time
from typing import Optional

import redis.asyncio as aioredis
from fastapi import HTTPException, status

# Configuration
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")

# Rate limit: 30 requests per 30 seconds per user, 60 per IP
RATE_LIMIT_WINDOW = 30  # seconds
USER_RATE_LIMIT = 30  # req per window
IP_RATE_LIMIT = 60  # req per window

# Quotas: anonymous only
ANON_QUOTA_HOURLY = 20  # messages per hour
ANON_QUOTA_TOTAL = 100  # messages total (lifetime)

# Lua script for atomic rate limiting (token bucket)
RATE_LIMIT_LUA = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local burst = tonumber(ARGV[3])

-- Current count for this window
local count = redis.call('INCR', key)

-- Set expiration on first increment
if count == 1 then
    redis.call('PEXPIRE', key, math.floor(window * 1000))
end

-- Check if over limit
if count > burst then
    return 0
else
    return count
end
"""

# Quota Lua script (atomic increment + check)
QUOTA_LUA = """
local key = KEYS[1]
local limit = tonumber(ARGV[1])
local ttl = tonumber(ARGV[2])

local count = redis.call('INCR', key)

if count == 1 then
    redis.call('EXPIRE', key, ttl)
end

if count > limit then
    return 0
else
    return count
end
"""


class RateLimiter:
    """Redis-backed rate limiter with quota enforcement."""

    def __init__(self, redis_url: str = REDIS_URL):
        self.redis_url = redis_url
        self._redis: Optional[aioredis.Redis] = None

    async def connect(self):
        """Connect to Redis."""
        self._redis = await aioredis.from_url(self.redis_url)

    async def close(self):
        """Close Redis connection."""
        if self._redis:
            await self._redis.close()

    async def _get_redis(self) -> aioredis.Redis:
        """Lazy connect on first use."""
        if not self._redis:
            await self.connect()
        return self._redis

    async def check_rate_limit(self, user_id: str, ip_address: str, namespace: str = "stream") -> bool:
        """Check rate limits for user and IP.

        Returns:
            True if allowed, False if rate limited

        Raises:
            HTTPException: 429 if rate limited
        """
        redis = await self._get_redis()
        now = int(time.time())

        # Per-user rate limit
        user_key = f"rl:{namespace}:user:{user_id}:{now // RATE_LIMIT_WINDOW}"
        user_count = await redis.eval(RATE_LIMIT_LUA, 1, user_key, now, RATE_LIMIT_WINDOW, USER_RATE_LIMIT)

        if user_count == 0:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limited (user): {USER_RATE_LIMIT} requests per {RATE_LIMIT_WINDOW}s",
                headers={"Retry-After": str(RATE_LIMIT_WINDOW)},
            )

        # Per-IP rate limit
        ip_key = f"rl:{namespace}:ip:{ip_address}:{now // RATE_LIMIT_WINDOW}"
        ip_count = await redis.eval(RATE_LIMIT_LUA, 1, ip_key, now, RATE_LIMIT_WINDOW, IP_RATE_LIMIT)

        if ip_count == 0:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limited (IP): {IP_RATE_LIMIT} requests per {RATE_LIMIT_WINDOW}s",
                headers={"Retry-After": str(RATE_LIMIT_WINDOW)},
            )

        return True

    async def check_anonymous_quotas(self, user_id: str) -> tuple[int, int]:
        """Check anonymous session quotas (hourly + total).

        Args:
            user_id: Anonymous session user ID (format: anon_<uuid>)

        Returns:
            Tuple of (hourly_remaining, total_remaining)

        Raises:
            HTTPException: 429 if quota exceeded
        """
        redis = await self._get_redis()
        now = int(time.time())

        # Hourly quota (reset every hour)
        hour_str = time.strftime("%Y%m%d%H", time.gmtime(now))
        hourly_key = f"q:anon:hour:{user_id}:{hour_str}"
        hourly_count = await redis.eval(QUOTA_LUA, 1, hourly_key, ANON_QUOTA_HOURLY, 3700)  # 1 hour + 100s buffer

        if hourly_count == 0:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Anonymous hourly quota exceeded ({ANON_QUOTA_HOURLY} messages/hour)",
                headers={"Retry-After": "3600"},
            )

        # Total quota (lifetime for this session)
        total_key = f"q:anon:tot:{user_id}"
        total_count = await redis.eval(
            QUOTA_LUA,
            1,
            total_key,
            ANON_QUOTA_TOTAL,
            604800,  # 7 days (anon session TTL)
        )

        if total_count == 0:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Anonymous total quota exceeded ({ANON_QUOTA_TOTAL} messages lifetime)",
                headers={"Retry-After": "86400"},
            )

        return (ANON_QUOTA_HOURLY - hourly_count + 1, ANON_QUOTA_TOTAL - total_count + 1)

    async def record_message(self, user_id: str, is_anonymous: bool, ip_address: str):
        """Record a message for metrics/monitoring.

        Args:
            user_id: User or session ID
            is_anonymous: True if anonymous
            ip_address: Client IP
        """
        redis = await self._get_redis()
        now = int(time.time())

        # Record metric: messages per minute
        metric_key = f"metrics:stream:msgs:{now // 60}"
        await redis.incr(metric_key)
        await redis.expire(metric_key, 3600)  # Keep for 1 hour

        if is_anonymous:
            # Track anonymous usage separately
            anon_key = f"metrics:stream:anon:{now // 60}"
            await redis.incr(anon_key)
            await redis.expire(anon_key, 3600)


# Global rate limiter instance
_limiter: Optional[RateLimiter] = None


async def get_rate_limiter() -> RateLimiter:
    """Lazy-load global rate limiter instance."""
    global _limiter
    if _limiter is None:
        _limiter = RateLimiter(REDIS_URL)
        await _limiter.connect()
    return _limiter


async def shutdown_limiter():
    """Close rate limiter on app shutdown."""
    global _limiter
    if _limiter:
        await _limiter.close()
        _limiter = None
