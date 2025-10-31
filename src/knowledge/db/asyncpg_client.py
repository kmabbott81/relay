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
from typing import Optional

import asyncpg

logger = logging.getLogger(__name__)

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
    # Enable RLS extension and set defaults
    await conn.execute("CREATE EXTENSION IF NOT EXISTS pgvector")
    await conn.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")


async def init_schema() -> None:
    """Idempotent schema initialization with RLS policies."""
    conn = await get_connection()
    try:
        # Enable RLS on files table
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
        logger.error(f"Schema initialization error: {e}")
    finally:
        await conn.close()


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


async def execute_query(query: str, *args) -> list[dict]:
    """Execute read query and return rows as dicts."""
    conn = await get_connection()
    try:
        rows = await conn.fetch(query, *args)
        return [dict(row) for row in rows]
    finally:
        await _pool.release(conn)


async def execute_query_one(query: str, *args) -> Optional[dict]:
    """Execute read query and return first row as dict."""
    conn = await get_connection()
    try:
        row = await conn.fetchrow(query, *args)
        return dict(row) if row else None
    finally:
        await _pool.release(conn)


async def execute_mutation(query: str, *args) -> int:
    """Execute write query and return affected rows."""
    conn = await get_connection()
    try:
        result = await conn.execute(query, *args)
        # Result is "UPDATE 5" style, extract count
        return int(result.split()[-1]) if result else 0
    finally:
        await _pool.release(conn)
