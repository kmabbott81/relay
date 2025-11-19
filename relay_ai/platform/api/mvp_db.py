"""
MVP Database Access Layer

Simple asyncpg-based database access for MVP internal users, threads, and messages.
Reuses the existing asyncpg connection pool from the knowledge API.

NO RLS enforcement needed - this is internal-only for MVP operators.
"""

import json
import logging
import uuid
from typing import Optional

from relay_ai.platform.api.knowledge.db.asyncpg_client import _pool, get_connection

logger = logging.getLogger(__name__)

# Cache for default user (Kyle)
_default_user_id: Optional[uuid.UUID] = None


async def get_default_user_id() -> uuid.UUID:
    """Get the default user ID (Kyle) for MVP requests without explicit user_id."""
    global _default_user_id

    if _default_user_id:
        return _default_user_id

    conn = await get_connection()
    try:
        row = await conn.fetchrow("SELECT id FROM mvp_users WHERE display_name = $1", "Kyle")
        if not row:
            raise RuntimeError("Default MVP user 'Kyle' not found in mvp_users table")

        _default_user_id = row["id"]
        logger.info(f"Default MVP user loaded: Kyle ({_default_user_id})")
        return _default_user_id
    finally:
        if conn and _pool:
            await _pool.release(conn)


async def create_thread(user_id: uuid.UUID, title: Optional[str] = None) -> uuid.UUID:
    """Create a new conversation thread."""
    conn = await get_connection()
    try:
        row = await conn.fetchrow(
            """
            INSERT INTO mvp_threads (user_id, title, created_at, updated_at)
            VALUES ($1, $2, NOW(), NOW())
            RETURNING id
            """,
            user_id,
            title,
        )
        thread_id = row["id"]
        logger.info(f"Created thread {thread_id} for user {user_id}")
        return thread_id
    finally:
        if conn and _pool:
            await _pool.release(conn)


async def get_thread(thread_id: uuid.UUID) -> Optional[dict]:
    """Get a thread by ID."""
    conn = await get_connection()
    try:
        row = await conn.fetchrow(
            """
            SELECT id, user_id, title, created_at, updated_at
            FROM mvp_threads
            WHERE id = $1
            """,
            thread_id,
        )
        return dict(row) if row else None
    finally:
        if conn and _pool:
            await _pool.release(conn)


async def list_threads(user_id: uuid.UUID, limit: int = 50) -> list[dict]:
    """List threads for a user, ordered by most recent first."""
    conn = await get_connection()
    try:
        rows = await conn.fetch(
            """
            SELECT id, user_id, title, created_at, updated_at
            FROM mvp_threads
            WHERE user_id = $1
            ORDER BY updated_at DESC
            LIMIT $2
            """,
            user_id,
            limit,
        )
        return [dict(row) for row in rows]
    finally:
        if conn and _pool:
            await _pool.release(conn)


async def create_message(
    thread_id: uuid.UUID,
    user_id: uuid.UUID,
    role: str,
    content: str,
    model_name: Optional[str] = None,
    model_key: Optional[str] = None,
    model_id: Optional[str] = None,
    token_usage_json: Optional[dict] = None,
) -> uuid.UUID:
    """Create a new message in a thread.

    Args:
        thread_id: Thread ID
        user_id: User ID
        role: Message role (user, assistant, system)
        content: Message content
        model_name: Legacy model name field (for backward compatibility)
        model_key: Logical model key (e.g., "gpt-fast")
        model_id: Actual provider model ID (e.g., "gpt-4o-mini")
        token_usage_json: Token usage metadata
    """
    conn = await get_connection()
    try:
        # Update thread's updated_at timestamp
        await conn.execute("UPDATE mvp_threads SET updated_at = NOW() WHERE id = $1", thread_id)

        # Convert dict to JSON for JSONB column (asyncpg handles this automatically, but explicit is better)
        token_usage_jsonb = json.dumps(token_usage_json) if token_usage_json else None

        # Insert message
        row = await conn.fetchrow(
            """
            INSERT INTO mvp_messages (thread_id, user_id, role, model_name, model_key, model_id, content, token_usage_json, created_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb, NOW())
            RETURNING id
            """,
            thread_id,
            user_id,
            role,
            model_name,
            model_key,
            model_id,
            content,
            token_usage_jsonb,
        )
        message_id = row["id"]
        logger.debug(f"Created message {message_id} in thread {thread_id}")
        return message_id
    finally:
        if conn and _pool:
            await _pool.release(conn)


async def list_messages(thread_id: uuid.UUID) -> list[dict]:
    """List all messages in a thread, ordered chronologically."""
    conn = await get_connection()
    try:
        rows = await conn.fetch(
            """
            SELECT id, thread_id, user_id, role, model_name, model_key, model_id, content, token_usage_json, created_at
            FROM mvp_messages
            WHERE thread_id = $1
            ORDER BY created_at ASC
            """,
            thread_id,
        )
        return [dict(row) for row in rows]
    finally:
        if conn and _pool:
            await _pool.release(conn)


async def verify_thread_ownership(thread_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    """Verify that a thread belongs to a user."""
    conn = await get_connection()
    try:
        row = await conn.fetchrow("SELECT 1 FROM mvp_threads WHERE id = $1 AND user_id = $2", thread_id, user_id)
        return row is not None
    finally:
        if conn and _pool:
            await _pool.release(conn)


# File Management Functions


async def create_file(
    user_id: uuid.UUID,
    thread_id: uuid.UUID,
    filename: str,
    file_size: int,
    mime_type: str,
    storage_path: str,
) -> uuid.UUID:
    """
    Create a new file record in the database.

    Args:
        user_id: User ID who uploaded the file
        thread_id: Thread ID where the file is attached
        filename: Original filename
        file_size: File size in bytes
        mime_type: MIME type (e.g., 'application/pdf')
        storage_path: Path where file is stored (e.g., '/tmp/uuid-filename')

    Returns:
        File ID (UUID)
    """
    conn = await get_connection()
    try:
        row = await conn.fetchrow(
            """
            INSERT INTO mvp_files (user_id, thread_id, filename, file_size, mime_type, storage_path, created_at)
            VALUES ($1, $2, $3, $4, $5, $6, NOW())
            RETURNING id
            """,
            user_id,
            thread_id,
            filename,
            file_size,
            mime_type,
            storage_path,
        )
        file_id = row["id"]
        logger.info(f"Created file {file_id} ({filename}) for thread {thread_id}")
        return file_id
    finally:
        if conn and _pool:
            await _pool.release(conn)


async def get_file(file_id: uuid.UUID) -> Optional[dict]:
    """Get a file record by ID."""
    conn = await get_connection()
    try:
        row = await conn.fetchrow(
            """
            SELECT id, user_id, thread_id, filename, file_size, mime_type, storage_path, created_at
            FROM mvp_files
            WHERE id = $1
            """,
            file_id,
        )
        return dict(row) if row else None
    finally:
        if conn and _pool:
            await _pool.release(conn)


async def list_thread_files(thread_id: uuid.UUID) -> list[dict]:
    """List all files attached to a thread."""
    conn = await get_connection()
    try:
        rows = await conn.fetch(
            """
            SELECT id, user_id, thread_id, filename, file_size, mime_type, storage_path, created_at
            FROM mvp_files
            WHERE thread_id = $1
            ORDER BY created_at DESC
            """,
            thread_id,
        )
        return [dict(row) for row in rows]
    finally:
        if conn and _pool:
            await _pool.release(conn)


async def list_user_files(user_id: uuid.UUID, limit: int = 100) -> list[dict]:
    """List all files uploaded by a user."""
    conn = await get_connection()
    try:
        rows = await conn.fetch(
            """
            SELECT id, user_id, thread_id, filename, file_size, mime_type, storage_path, created_at
            FROM mvp_files
            WHERE user_id = $1
            ORDER BY created_at DESC
            LIMIT $2
            """,
            user_id,
            limit,
        )
        return [dict(row) for row in rows]
    finally:
        if conn and _pool:
            await _pool.release(conn)


async def delete_file(file_id: uuid.UUID) -> bool:
    """Delete a file record. Returns True if deleted, False if not found."""
    conn = await get_connection()
    try:
        result = await conn.execute("DELETE FROM mvp_files WHERE id = $1", file_id)
        deleted = result != "DELETE 0"
        if deleted:
            logger.info(f"Deleted file {file_id}")
        return deleted
    finally:
        if conn and _pool:
            await _pool.release(conn)


async def verify_file_ownership(file_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    """Verify that a file belongs to a user."""
    conn = await get_connection()
    try:
        row = await conn.fetchrow("SELECT 1 FROM mvp_files WHERE id = $1 AND user_id = $2", file_id, user_id)
        return row is not None
    finally:
        if conn and _pool:
            await _pool.release(conn)
