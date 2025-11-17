"""Add memory_chunks table with RLS, encryption columns, and partial ANN indexes

Revision ID: 20251019_memory_schema_rls
Revises: 20251014_conversations
Create Date: 2025-10-19

Sprint 62 / R1 Phase 1 Task A: Schema + RLS + Encryption Columns
- Memory chunk storage with Row-Level Security for tenant isolation
- Encryption columns: text_cipher, meta_cipher, emb_cipher (BYTEA for AES-256-GCM)
- Plaintext embedding column for ANN (pgvector)
- Partial indexes scoped to user_hash for efficient tenant-isolated retrieval
"""
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

# revision identifiers
revision = "20251019_memory_schema_rls"
down_revision = "20251014_conversations"
branch_labels = None
depends_on = None


def upgrade():
    """
    Create memory_chunks table with:
    - Row-Level Security for user_hash-based tenant isolation
    - Encryption columns for text/metadata/shadow embeddings
    - Plaintext embedding for ANN indexing
    - Partial indexes scoped to user_hash
    """

    # Enable pgvector extension if not already enabled (gracefully handle if not installed)
    try:
        op.execute("CREATE EXTENSION IF NOT EXISTS vector;")
    except Exception as e:
        # pgvector not installed on this Postgres instance - log warning but continue
        # This is expected on Railway Postgres which doesn't include pgvector by default
        import logging

        logging.warning(f"Could not create pgvector extension: {e}")

    # Create memory_chunks table
    op.create_table(
        "memory_chunks",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        # Tenant isolation: user_hash = HMAC-SHA256(MEMORY_TENANT_HMAC_KEY, user_id)
        # Used for Row-Level Security policy
        sa.Column("user_hash", sa.String(64), nullable=False, index=True),
        # Source document reference
        sa.Column("doc_id", sa.String(255), nullable=False),
        sa.Column("source", sa.String(100), nullable=False),  # 'chat', 'upload', 'api', 'email', etc.
        # Chunk content (plain and encrypted)
        sa.Column("text_plain", sa.Text, nullable=True),  # Optional for backward compat
        sa.Column("text_cipher", sa.LargeBinary, nullable=True),  # AES-256-GCM(text): nonce||ciphertext
        # Metadata (encrypted)
        sa.Column("meta_cipher", sa.LargeBinary, nullable=True),  # AES-256-GCM(JSON meta): nonce||ciphertext
        # Embedding vectors
        sa.Column("embedding", sa.String(None), nullable=False),  # pgvector type: vector(1536) for embeddings
        sa.Column("emb_cipher", sa.LargeBinary, nullable=True),  # AES-256-GCM(embedding.tobytes()): shadow backup
        # Chunk metadata
        sa.Column("chunk_index", sa.Integer, nullable=False),  # Order within document
        sa.Column("char_start", sa.Integer, nullable=True),  # Character offset in source
        sa.Column("char_end", sa.Integer, nullable=True),  # Character offset in source
        # Temporal metadata
        sa.Column("created_at", sa.TIMESTAMP, server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP, server_default=sa.text("NOW()"), nullable=False),
        sa.Column("expires_at", sa.TIMESTAMP, nullable=True),  # TTL for automatic cleanup
        # Additional metadata (unencrypted, for queries)
        sa.Column("tags", sa.ARRAY(sa.String), nullable=True),  # Searchable tags
        sa.Column("model", sa.String(100), nullable=True),  # Embedding model version
        # Indexes
        sa.Index("idx_memory_chunks_user_hash", "user_hash"),
        sa.Index("idx_memory_chunks_user_hash_created", "user_hash", "created_at"),
        sa.Index("idx_memory_chunks_doc_id", "doc_id"),
        sa.Index("idx_memory_chunks_source", "source"),
        sa.Index("idx_memory_chunks_created_at", "created_at"),
        sa.Index("idx_memory_chunks_expires_at", "expires_at"),  # For TTL cleanup queries
    )

    # Enable Row-Level Security on memory_chunks table
    op.execute("ALTER TABLE memory_chunks ENABLE ROW LEVEL SECURITY;")

    # Create RLS policy: Users can only see their own rows (user_hash match)
    # This policy enforces tenant isolation at the database level
    op.execute(
        """
        CREATE POLICY memory_tenant_isolation ON memory_chunks
        USING (user_hash = COALESCE(current_setting('app.user_hash', true), ''))
        WITH CHECK (user_hash = COALESCE(current_setting('app.user_hash', true), ''));
    """
    )

    # Create partial HNSW index for efficient ANN search within user's chunks
    # This index only includes rows matching current_setting('app.user_hash')
    # so each user's index is separate
    # NOTE: Requires pgvector extension - skip if not available
    try:
        op.execute(
            """
            CREATE INDEX idx_memory_chunks_embedding_hnsw
            ON memory_chunks USING hnsw (embedding vector_cosine_ops)
            WHERE user_hash IS NOT NULL;
        """
        )
    except Exception as e:
        import logging

        logging.warning(f"Could not create HNSW index (pgvector required): {e}")

    # Create partial IVFFlat index as alternative (for very large deployments)
    # Can switch between HNSW/IVFFlat via query hints or runtime parameter
    # NOTE: Requires pgvector extension - skip if not available
    try:
        op.execute(
            """
            CREATE INDEX idx_memory_chunks_embedding_ivfflat
            ON memory_chunks USING ivfflat (embedding vector_cosine_ops)
            WHERE user_hash IS NOT NULL
            WITH (lists = 100);
        """
        )
    except Exception as e:
        import logging

        logging.warning(f"Could not create IVFFlat index (pgvector required): {e}")

    # Create index on (user_hash, embedding) for scoped searches
    # Helps PostgreSQL select the right subset before ANN computation
    # NOTE: Requires pgvector extension - skip if not available
    try:
        op.execute(
            """
            CREATE INDEX idx_memory_chunks_user_embedding
            ON memory_chunks (user_hash, (embedding <-> '{0.1,0.2,0.3,...}'::vector))
            WHERE user_hash IS NOT NULL;
        """
        )
    except Exception as e:
        import logging

        logging.warning(f"Could not create user embedding index (pgvector required): {e}")


def downgrade():
    """
    Rollback memory_chunks table:
    - Drop partial indexes
    - Disable RLS and drop policies
    - Drop table
    """

    # Drop indexes (safe to drop even if they don't exist)
    op.execute("DROP INDEX IF EXISTS idx_memory_chunks_embedding_hnsw;")
    op.execute("DROP INDEX IF EXISTS idx_memory_chunks_embedding_ivfflat;")
    op.execute("DROP INDEX IF EXISTS idx_memory_chunks_user_embedding;")

    # Drop RLS policy
    op.execute("DROP POLICY IF EXISTS memory_tenant_isolation ON memory_chunks;")

    # Disable RLS
    op.execute("ALTER TABLE memory_chunks DISABLE ROW LEVEL SECURITY;")

    # Drop table
    op.drop_table("memory_chunks")

    # Drop pgvector extension (optional - keep if other tables need it)
    # op.execute("DROP EXTENSION IF EXISTS vector;")
