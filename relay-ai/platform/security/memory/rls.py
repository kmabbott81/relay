"""Row-Level Security plumbing for memory_chunks

Task A: Schema + RLS + Encryption Columns

Provides:
- user_hash computation (HMAC-SHA256 of user_id)
- app.user_hash session variable plumbing
- Context managers for scoped RLS enforcement
- Middleware integration for automatic user isolation
"""

import hashlib
import hmac
import logging
import os
from contextlib import asynccontextmanager
from typing import Optional

import asyncpg

logger = logging.getLogger(__name__)

# MEMORY_TENANT_HMAC_KEY: 32-byte base64 key for computing user_hash
# Used in: hmac_user(user_id) -> user_hash
MEMORY_TENANT_HMAC_KEY = os.getenv("MEMORY_TENANT_HMAC_KEY", "dev-hmac-key-change-in-production")


def hmac_user(user_id: str) -> str:
    """
    Compute user_hash from user_id using HMAC-SHA256.

    This hash is used for Row-Level Security isolation:
    - Stored in memory_chunks.user_hash column
    - Set as app.user_hash session variable for RLS policy enforcement
    - Ensures users cannot access other users' memory chunks

    Args:
        user_id: User identifier (UUID or string)

    Returns:
        Hex-encoded HMAC-SHA256 hash (64 characters)

    Example:
        >>> hmac_user("user_123")
        'a1b2c3d4e5f6...' (64 hex chars)
    """
    h = hmac.new(MEMORY_TENANT_HMAC_KEY.encode("utf-8"), user_id.encode("utf-8"), hashlib.sha256)
    return h.hexdigest()


@asynccontextmanager
async def set_rls_context(conn: asyncpg.Connection, user_id: str):
    """
    Set app.user_hash session variable for RLS enforcement.

    All queries executed within this context will have RLS policies applied
    based on the user_hash matching the connection's session variable.

    Usage:
        async with get_connection() as conn:
            async with set_rls_context(conn, user_id):
                # All queries here are scoped to user's rows only
                await conn.fetch("SELECT * FROM memory_chunks")

    Args:
        conn: asyncpg database connection
        user_id: User identifier for isolation

    Yields:
        The connection object (unchanged)

    Raises:
        asyncpg.PostgresError: If setting session variable fails
    """
    user_hash = hmac_user(user_id)

    try:
        # Set app.user_hash session variable for RLS policy
        # This is read by the PostgreSQL function:
        #   current_setting('app.user_hash', true) -> user_hash
        # CRITICAL SECURITY: Use parameterized query to prevent SQL injection
        await conn.execute(
            "SELECT set_config($1, $2, true)",
            "app.user_hash",
            user_hash,
        )
        logger.debug(f"RLS context set for user_id={user_id}, user_hash={user_hash[:16]}...")

        yield conn

    finally:
        # Clear session variable after context exits
        try:
            await conn.execute("RESET app.user_hash;")
            logger.debug("RLS context cleared")
        except Exception as e:
            logger.warning(f"Failed to clear app.user_hash: {e}")


async def set_rls_session_variable(conn: asyncpg.Connection, user_id: str) -> str:
    """
    Set app.user_hash session variable and return the user_hash.

    This is a simple setter without context manager wrapping.
    Useful for long-lived connections where you don't want automatic reset.

    Args:
        conn: asyncpg database connection
        user_id: User identifier for isolation

    Returns:
        The computed user_hash (64-character hex string)

    Raises:
        asyncpg.PostgresError: If setting session variable fails
    """
    user_hash = hmac_user(user_id)

    # CRITICAL SECURITY: Use parameterized query to prevent SQL injection
    await conn.execute(
        "SELECT set_config($1, $2, true)",
        "app.user_hash",
        user_hash,
    )
    logger.debug(f"RLS session variable set: user_id={user_id}, user_hash={user_hash[:16]}...")

    return user_hash


async def clear_rls_session_variable(conn: asyncpg.Connection) -> None:
    """
    Clear app.user_hash session variable.

    Used to clean up after long-lived connections or in error handlers.

    Args:
        conn: asyncpg database connection

    Raises:
        asyncpg.PostgresError: If clearing session variable fails
    """
    await conn.execute("RESET app.user_hash;")
    logger.debug("RLS session variable cleared")


async def verify_rls_isolation(conn: asyncpg.Connection, user_id: str) -> dict:
    """
    Verify that RLS policy is correctly enforcing isolation.

    This is a test/validation helper to confirm:
    1. Setting app.user_hash prevents cross-tenant access
    2. Same query returns different results for different users

    Args:
        conn: asyncpg database connection (must have memory_chunks table)
        user_id: User identifier to test

    Returns:
        Dict with verification results:
        {
            "user_hash": "...",
            "row_count": 42,
            "rls_enabled": True,
            "policy_active": True,
        }

    Example:
        >>> result = await verify_rls_isolation(conn, "user_123")
        >>> assert result["rls_enabled"]
        >>> assert result["policy_active"]
    """
    user_hash = hmac_user(user_id)

    try:
        # Check if RLS is enabled
        rls_enabled = await conn.fetchval(
            """
            SELECT relrowsecurity FROM pg_class
            WHERE relname = 'memory_chunks';
        """
        )

        # Check if policies exist
        policies = await conn.fetch(
            """
            SELECT polname FROM pg_policies
            WHERE tablename = 'memory_chunks' AND polname LIKE '%memory%';
        """
        )

        # Count rows visible with RLS applied
        async with set_rls_context(conn, user_id):
            visible_rows = await conn.fetchval(
                """
                SELECT COUNT(*) FROM memory_chunks;
            """
            )

        return {
            "user_hash": user_hash[:16] + "..." if user_hash else None,
            "row_count": visible_rows or 0,
            "rls_enabled": bool(rls_enabled),
            "policy_active": len(policies) > 0,
            "policy_names": [p["polname"] for p in policies],
        }

    except Exception as e:
        logger.error(f"RLS verification failed: {e}")
        return {
            "user_hash": user_hash[:16] + "..." if user_hash else None,
            "row_count": 0,
            "rls_enabled": False,
            "policy_active": False,
            "error": str(e),
        }


# --- Middleware Integration ---
# For use in FastAPI middleware to automatically set RLS context per request


class RLSMiddlewareContext:
    """Context object attached to FastAPI request for RLS enforcement."""

    def __init__(self, user_id: Optional[str] = None):
        """Initialize RLS context.

        Args:
            user_id: User ID from JWT token or session (None for unauthenticated)
        """
        self.user_id = user_id
        self.user_hash = hmac_user(user_id) if user_id else None

    async def apply_to_connection(self, conn: asyncpg.Connection) -> None:
        """Apply RLS context to a database connection.

        Args:
            conn: asyncpg connection to configure
        """
        if self.user_id:
            await set_rls_session_variable(conn, self.user_id)


async def get_rls_context(request_principal: dict) -> RLSMiddlewareContext:
    """Extract RLS context from request principal.

    Args:
        request_principal: Dict with user info from JWT/session
            Expected keys:
            - "user_id": User identifier
            - "is_anonymous": Bool (optional)

    Returns:
        RLSMiddlewareContext ready for connection application
    """
    user_id = request_principal.get("user_id")
    return RLSMiddlewareContext(user_id=user_id)
