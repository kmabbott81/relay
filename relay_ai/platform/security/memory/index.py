"""Memory chunk indexing with encryption and RLS

TASK B Integration: Write path encryption

Provides:
- index_memory_chunk() → encrypt + store chunk with AAD binding
- Maintains RLS isolation (user_hash context)
- Supports batch operations with transaction safety
"""

import json
import logging
from typing import Any, Optional

import asyncpg

from relay_ai.memory.rls import hmac_user, set_rls_context
from relay_ai.memory.security import seal

logger = logging.getLogger(__name__)


async def index_memory_chunk(
    conn: asyncpg.Connection,
    user_id: str,
    doc_id: str,
    source: str,
    text: str,
    embedding: list[float],
    metadata: Optional[dict[str, Any]] = None,
    chunk_index: int = 0,
    char_start: Optional[int] = None,
    char_end: Optional[int] = None,
    tags: Optional[list[str]] = None,
    model: str = "text-embedding-3-small",
) -> dict[str, Any]:
    """Index a memory chunk with encryption and RLS enforcement.

    Flow:
    1. Compute user_hash = HMAC-SHA256(MEMORY_TENANT_HMAC_KEY, user_id)
    2. Set RLS context: SET app.user_hash = user_hash
    3. Encrypt text with AAD=user_hash (prevents cross-tenant decryption)
    4. Encrypt metadata with AAD=user_hash
    5. Encrypt embedding backup with AAD=user_hash
    6. INSERT into memory_chunks (RLS policy filters by user_hash)
    7. Return chunk ID + computed fields

    Args:
        conn: asyncpg database connection
        user_id: User identifier (UUID or string)
        doc_id: Source document identifier
        source: Chunk source ('chat', 'upload', 'api', 'email', etc.)
        text: Chunk text content to encrypt
        embedding: Float vector [1536] for ANN search
        metadata: Optional JSON metadata (dict)
        chunk_index: Order within document (default: 0)
        char_start: Character offset in source (optional)
        char_end: Character offset in source (optional)
        tags: Searchable tags (optional, unencrypted)
        model: Embedding model name for version tracking

    Returns:
        Dict with:
        - id: UUID of inserted chunk
        - user_hash: Computed tenant key
        - doc_id, source, text_length
        - created_at timestamp
        - encrypted: bool (always True)

    Raises:
        asyncpg.PostgresError: Database error (includes RLS violations)
        ValueError: Invalid input (missing required fields)
        Exception: Encryption errors

    Example:
        >>> chunk = await index_memory_chunk(
        ...     conn,
        ...     user_id="user_123",
        ...     doc_id="doc_abc",
        ...     source="chat",
        ...     text="How do I reset my password?",
        ...     embedding=[0.1, 0.2, ...],  # 1536-dim vector
        ...     metadata={"session_id": "sess_xyz"},
        ...     tags=["password", "account"]
        ... )
        >>> chunk["id"]
        "550e8400-e29b-41d4-a716-446655440000"
    """
    # Validate required fields
    if not user_id or not doc_id or not source or not text or not embedding:
        raise ValueError("Required fields missing: user_id, doc_id, source, text, embedding")

    # Compute tenant hash
    user_hash = hmac_user(user_id)
    logger.debug(f"Indexing chunk for user={user_id[:20]}..., hash={user_hash[:16]}...")

    try:
        # Set RLS context for this user
        async with set_rls_context(conn, user_id):
            # Prepare encrypted payloads with AAD binding (user_hash)
            aad = user_hash.encode()  # AAD = user_hash

            # 1. Encrypt text
            text_cipher = seal(text.encode("utf-8"), aad=aad)
            logger.debug(f"Encrypted text: {len(text)} chars → {len(text_cipher)} bytes")

            # 2. Encrypt metadata (JSON)
            metadata = metadata or {}
            meta_json = json.dumps(metadata).encode("utf-8")
            meta_cipher = seal(meta_json, aad=aad)
            logger.debug(f"Encrypted metadata: {len(meta_json)} bytes → {len(meta_cipher)} bytes")

            # 3. Encrypt embedding (backup, for recovery if needed)
            # Store as comma-separated float values
            embedding_bytes = ",".join(str(x) for x in embedding).encode("utf-8")
            emb_cipher = seal(embedding_bytes, aad=aad)
            logger.debug(f"Encrypted embedding: {len(embedding_bytes)} bytes → {len(emb_cipher)} bytes")

            # 4. Prepare embedding string for pgvector (plaintext for ANN)
            # Format: [0.1, 0.2, ..., 0.1536]
            embedding_str = "[" + ",".join(str(x) for x in embedding) + "]"

            # 5. INSERT into memory_chunks with all encrypted fields
            # RLS policy will filter based on user_hash match with SET app.user_hash
            query = """
                INSERT INTO memory_chunks (
                    user_hash, doc_id, source,
                    text_cipher, meta_cipher, embedding, emb_cipher,
                    chunk_index, char_start, char_end, tags, model,
                    created_at, updated_at
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, NOW(), NOW())
                RETURNING id, user_hash, doc_id, source, created_at, updated_at
            """

            result = await conn.fetchrow(
                query,
                user_hash,  # $1
                doc_id,  # $2
                source,  # $3
                text_cipher,  # $4
                meta_cipher,  # $5
                embedding_str,  # $6
                emb_cipher,  # $7
                chunk_index,  # $8
                char_start,  # $9
                char_end,  # $10
                tags,  # $11
                model,  # $12
            )

            logger.info(
                f"Indexed chunk: id={result['id']}, user={user_id[:20]}..., " f"source={source}, text_len={len(text)}"
            )

            return {
                "id": result["id"],
                "user_hash": user_hash,
                "doc_id": result["doc_id"],
                "source": result["source"],
                "text_length": len(text),
                "metadata_size": len(meta_json),
                "embedding_size": len(embedding),
                "encrypted": True,
                "aad_binding": True,  # AAD binding enforced
                "created_at": result["created_at"],
                "updated_at": result["updated_at"],
            }

    except Exception as e:
        logger.error(f"Failed to index chunk: {e}")
        raise


async def index_memory_batch(
    conn: asyncpg.Connection,
    user_id: str,
    chunks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Index multiple memory chunks in a transaction.

    Each chunk is encrypted with AAD binding (user_hash).
    Transaction ensures atomicity: all succeed or all fail.

    Args:
        conn: asyncpg database connection
        user_id: User identifier (same for all chunks in batch)
        chunks: List of chunk dicts:
            - doc_id, source, text, embedding (required)
            - metadata, tags, char_start, char_end (optional)

    Returns:
        List of indexed chunk dicts (same format as index_memory_chunk)

    Example:
        >>> chunks_to_index = [
        ...     {
        ...         "doc_id": "doc1",
        ...         "source": "upload",
        ...         "text": "First paragraph...",
        ...         "embedding": [0.1, ...],
        ...         "metadata": {"page": 1}
        ...     },
        ...     {
        ...         "doc_id": "doc1",
        ...         "source": "upload",
        ...         "text": "Second paragraph...",
        ...         "embedding": [0.2, ...],
        ...         "metadata": {"page": 1}
        ...     }
        ... ]
        >>> results = await index_memory_batch(conn, user_id, chunks_to_index)
        >>> len(results)
        2
    """
    if not chunks:
        return []

    results = []
    async with conn.transaction():
        for i, chunk in enumerate(chunks):
            result = await index_memory_chunk(
                conn,
                user_id=user_id,
                doc_id=chunk.get("doc_id"),
                source=chunk.get("source"),
                text=chunk.get("text"),
                embedding=chunk.get("embedding"),
                metadata=chunk.get("metadata"),
                chunk_index=i,
                char_start=chunk.get("char_start"),
                char_end=chunk.get("char_end"),
                tags=chunk.get("tags"),
                model=chunk.get("model", "text-embedding-3-small"),
            )
            results.append(result)

    logger.info(f"Indexed {len(results)} chunks for user={user_id[:20]}...")
    return results
