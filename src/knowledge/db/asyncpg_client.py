"""
Database client for Knowledge API (Phase 3).

Async PostgreSQL connectivity with RLS context setup.
- Connection pooling via asyncpg
- RLS user_hash context variable for row-level security
- Transaction management
"""

import logging
from typing import Optional

import asyncpg

logger = logging.getLogger(__name__)

# Phase 3 TODO: Initialize connection pool from DATABASE_URL env var
_pool: Optional[asyncpg.Pool] = None


async def init_pool(database_url: str, min_size: int = 5, max_size: int = 20) -> None:
    """Initialize asyncpg connection pool."""
    global _pool
    _pool = await asyncpg.create_pool(
        database_url,
        min_size=min_size,
        max_size=max_size,
        init=_init_connection,
    )
    logger.info("Database pool initialized")


async def _init_connection(conn: asyncpg.Connection) -> None:
    """Per-connection initialization: set RLS context if available."""
    # TODO: Set search_path, enable extensions, etc.
    pass


async def set_rls_context(conn: asyncpg.Connection, user_hash: str) -> None:
    """Set session variable for RLS policy enforcement."""
    await conn.execute("SET app.user_hash = $1", user_hash)


async def close_pool() -> None:
    """Close connection pool."""
    global _pool
    if _pool:
        await _pool.close()
        logger.info("Database pool closed")


async def get_connection() -> asyncpg.Connection:
    """Get connection from pool."""
    if not _pool:
        raise RuntimeError("Database pool not initialized")
    return await _pool.acquire()


async def execute_query(query: str, *args) -> list:
    """Execute read query and return rows."""
    async with await get_connection() as conn:
        return await conn.fetch(query, *args)


async def execute_mutation(query: str, *args) -> int:
    """Execute write query and return affected rows."""
    async with await get_connection() as conn:
        return await conn.execute(query, *args)
