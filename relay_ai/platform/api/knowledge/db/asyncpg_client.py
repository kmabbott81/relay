"""
Database client for Knowledge API (Phase 3).

Async PostgreSQL connectivity with RLS context setup.
- Connection pooling via asyncpg
- RLS user_hash context variable for row-level security
- Transaction management
- Schema initialization
"""

import logging
import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Optional

import asyncpg

logger = logging.getLogger(__name__)


class SecurityError(Exception):
    """Raised when RLS context is missing or invalid."""

    pass


# Connection pool
_pool: Optional[asyncpg.Pool] = None


async def init_pool(
    database_url: Optional[str] = None,
    min_size: int = 5,
    max_size: int = 20,
) -> None:
    """Initialize asyncpg connection pool."""
    global _pool
    url = database_url or os.getenv("DATABASE_URL")
    if not url:
        raise ValueError("DATABASE_URL not set")

    _pool = await asyncpg.create_pool(
        url,
        min_size=min_size,
        max_size=max_size,
        init=_init_connection,
    )
    logger.info("Database pool initialized (min=%d, max=%d)", min_size, max_size)

    # Initialize schema
    await init_schema()


async def _init_connection(conn: asyncpg.Connection) -> None:
    """Per-connection initialization."""
    # Enable extensions (graceful degradation if not available)
    try:
        await conn.execute("CREATE EXTENSION IF NOT EXISTS pgvector")
    except Exception as e:
        logger.debug(f"pgvector extension not available (expected on Railway): {e}")

    try:
        await conn.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    except Exception as e:
        logger.debug(f"pg_trgm extension not available: {e}")


async def init_schema() -> None:
    """
    Idempotent schema initialization with RLS policies.

    NOTE: This is for Phase 2/3 Knowledge API. Phase 1 MVP doesn't use these tables.
    Gracefully degrades if tables don't exist yet.
    """
    # Skip schema initialization if pool is not available (MVP Phase 1 doesn't need this)
    if not _pool:
        logger.debug("Skipping schema initialization - database pool not available (expected for MVP Phase 1)")
        return

    conn = None
    try:
        conn = await get_connection()

        # Enable RLS on files table (if it exists)
        try:
            await conn.execute("ALTER TABLE files ENABLE ROW LEVEL SECURITY")

            # RLS Policy: Users see only their own files
            await conn.execute(
                """
                CREATE POLICY IF NOT EXISTS files_user_isolation ON files
                USING (user_hash = current_setting('app.user_hash'))
                WITH CHECK (user_hash = current_setting('app.user_hash'))
                """
            )

            # RLS Policy: File embeddings isolated by file user_hash
            await conn.execute(
                """
                CREATE POLICY IF NOT EXISTS embeddings_user_isolation ON file_embeddings
                USING (
                    file_id IN (
                        SELECT id FROM files WHERE user_hash = current_setting('app.user_hash')
                    )
                )
                """
            )

            logger.info("Schema initialized with RLS policies")
        except Exception as e:
            # Expected for MVP Phase 1 - files/file_embeddings tables don't exist yet
            logger.debug(f"Schema initialization skipped (tables not found, expected for MVP Phase 1): {e}")
    except Exception as e:
        logger.error(f"Schema initialization error: {e}")
    finally:
        # CRITICAL: Release connection back to pool (not close)
        if conn and _pool:
            await _pool.release(conn)


async def set_rls_context(conn: asyncpg.Connection, user_hash: str) -> None:
    """Set session variable for RLS policy enforcement."""
    await conn.execute("SET app.user_hash = $1", user_hash)
    logger.debug(f"RLS context set for user {user_hash[:8]}...")


async def close_pool() -> None:
    """Close connection pool."""
    global _pool
    if _pool:
        await _pool.close()
        logger.info("Database pool closed")


async def get_connection() -> asyncpg.Connection:
    """Get connection from pool."""
    if not _pool:
        raise RuntimeError("Database pool not initialized; call init_pool first")
    return await _pool.acquire()


@asynccontextmanager
async def with_user_conn(user_hash: str) -> AsyncGenerator[asyncpg.Connection, None]:
    """
    Context manager for per-user, per-transaction RLS enforcement.

    CRITICAL SECURITY: Sets RLS context before any query, ensures transaction scope,
    releases to pool on exit. Fail-closed: raises SecurityError if user_hash missing.

    Usage:
        async with with_user_conn(user_hash) as conn:
            await conn.fetch("SELECT * FROM files", ...)
    """
    if not user_hash:
        raise SecurityError("user_hash is required for RLS enforcement")

    conn = await get_connection()
    try:
        # Open transaction
        async with conn.transaction():
            # Set RLS context with PARAMETERIZED QUERY (prevents SQL injection)
            await conn.execute(
                "SELECT set_config($1, $2, true)",
                "app.user_hash",
                user_hash,
            )
            logger.debug(f"RLS context set for user {user_hash[:8]}... (txn scope)")
            yield conn
    except SecurityError:
        raise
    except Exception as e:
        logger.error(f"RLS context error for user {user_hash[:8]}: {e}")
        raise
    finally:
        await _pool.release(conn)


async def assert_current_user(conn: asyncpg.Connection, user_hash: str) -> None:
    """
    Verify that the connection has the correct RLS context set.

    DEFENSIVE: Guard against pool/connection reuse bugs.
    """
    current_value = await conn.fetchval("SELECT current_setting('app.user_hash')")
    if current_value != user_hash:
        raise SecurityError(
            f"RLS context mismatch: expected {user_hash[:8]}, got {current_value[:8] if current_value else 'NONE'}"
        )


async def execute_query(user_hash: str, query: str, *args) -> list[dict]:
    """
    Execute read query with RLS context and return rows as dicts.

    CRITICAL: user_hash is REQUIRED and enforced via with_user_conn().
    """
    async with with_user_conn(user_hash) as conn:
        rows = await conn.fetch(query, *args)
        return [dict(row) for row in rows]


async def execute_query_one(user_hash: str, query: str, *args) -> Optional[dict]:
    """
    Execute read query with RLS context and return first row as dict.

    CRITICAL: user_hash is REQUIRED and enforced via with_user_conn().
    """
    async with with_user_conn(user_hash) as conn:
        row = await conn.fetchrow(query, *args)
        return dict(row) if row else None


async def execute_mutation(user_hash: str, query: str, *args) -> int:
    """
    Execute write query with RLS context and return affected rows.

    CRITICAL: user_hash is REQUIRED and enforced via with_user_conn().
    """
    async with with_user_conn(user_hash) as conn:
        result = await conn.execute(query, *args)
        # Result is "UPDATE 5" style, extract count
        return int(result.split()[-1]) if result else 0
