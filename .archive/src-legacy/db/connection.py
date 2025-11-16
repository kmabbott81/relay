"""Database connection management.

Sprint 51 Phase 1: asyncpg connection pool.
"""
import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import asyncpg


class DatabasePool:
    """Async Postgres connection pool."""

    def __init__(self):
        """Initialize pool (lazy - created on first use)."""
        self._pool: asyncpg.Pool | None = None

    async def get_pool(self) -> asyncpg.Pool:
        """Get or create connection pool."""
        if self._pool is None:
            database_url = os.getenv("DATABASE_URL")
            if not database_url:
                raise ValueError("DATABASE_URL environment variable not set")

            # Replace postgres:// with postgresql:// for compatibility
            if database_url.startswith("postgres://"):
                database_url = database_url.replace("postgres://", "postgresql://", 1)

            self._pool = await asyncpg.create_pool(
                database_url,
                min_size=2,
                max_size=10,
                command_timeout=60.0,
            )

        return self._pool

    async def close(self):
        """Close connection pool."""
        if self._pool:
            await self._pool.close()
            self._pool = None


# Global instance
_pool = DatabasePool()


@asynccontextmanager
async def get_connection() -> AsyncGenerator[asyncpg.Connection, None]:
    """Get a database connection from the pool.

    Usage:
        async with get_connection() as conn:
            result = await conn.fetchrow("SELECT * FROM api_keys LIMIT 1")
    """
    pool = await _pool.get_pool()
    async with pool.acquire() as conn:
        yield conn


async def close_database():
    """Close the database pool (call on shutdown)."""
    await _pool.close()
