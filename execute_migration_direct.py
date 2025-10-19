#!/usr/bin/env python3
"""
Direct SQL execution for TASK A migration (bypassing Alembic)
Handles pgvector availability gracefully
"""

import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
import os

db_url = os.environ.get("STAGING_DATABASE_URL")
if not db_url:
    print("ERROR: STAGING_DATABASE_URL not set")
    exit(1)

conn = psycopg2.connect(db_url)
conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
cur = conn.cursor()

print("TASK A Migration Execution")
print("=" * 80)

pgvector_available = False

try:
    # Step 1: Check pgvector extension
    print("\n1. Checking pgvector extension...")
    try:
        cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
        pgvector_available = True
        print("   OK (pgvector available)")
    except psycopg2.errors.FeatureNotSupported:
        pgvector_available = False
        print("   INFO (pgvector not available, using FLOAT8[] instead)")

    # Step 2: Create memory_chunks table
    print("\n2. Creating memory_chunks table...")

    # Prepare embedding column type
    if pgvector_available:
        embedding_col = "embedding vector"
    else:
        embedding_col = "embedding FLOAT8[]"

    create_table_sql = f"""
        CREATE TABLE IF NOT EXISTS memory_chunks (
            id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
            user_hash varchar(64) NOT NULL,
            doc_id varchar(255) NOT NULL,
            source varchar(100) NOT NULL,
            text_plain text,
            text_cipher bytea,
            meta_cipher bytea,
            {embedding_col},
            emb_cipher bytea,
            chunk_index integer NOT NULL,
            char_start integer,
            char_end integer,
            created_at timestamp DEFAULT NOW() NOT NULL,
            updated_at timestamp DEFAULT NOW() NOT NULL,
            expires_at timestamp,
            tags text[],
            model varchar(100)
        );
    """
    cur.execute(create_table_sql)
    print("   OK")

    # Step 3: Create indexes
    print("\n3. Creating B-tree indexes...")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_memory_chunks_user_hash ON memory_chunks (user_hash);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_memory_chunks_user_hash_created ON memory_chunks (user_hash, created_at);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_memory_chunks_doc_id ON memory_chunks (doc_id);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_memory_chunks_source ON memory_chunks (source);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_memory_chunks_created_at ON memory_chunks (created_at);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_memory_chunks_expires_at ON memory_chunks (expires_at);")
    print("   OK (6 B-tree indexes)")

    # Step 4: Enable RLS
    print("\n4. Enabling Row-Level Security...")
    cur.execute("ALTER TABLE memory_chunks ENABLE ROW LEVEL SECURITY;")
    print("   OK")

    # Step 5: Create RLS policy (handle if already exists)
    print("\n5. Creating RLS policy (memory_tenant_isolation)...")
    try:
        cur.execute("""
            CREATE POLICY memory_tenant_isolation ON memory_chunks
            USING (user_hash = COALESCE(current_setting('app.user_hash', true), ''))
            WITH CHECK (user_hash = COALESCE(current_setting('app.user_hash', true), ''));
        """)
        print("   OK (policy created)")
    except psycopg2.errors.DuplicateObject:
        print("   INFO (policy already exists)")

    # Step 6: Create ANN indexes (if pgvector is available)
    print("\n6. Creating indexes...")
    if pgvector_available:
        print("   Creating ANN indexes (HNSW, IVFFlat)...")
        try:
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_memory_chunks_embedding_hnsw
                ON memory_chunks USING hnsw (embedding vector_cosine_ops)
                WHERE user_hash IS NOT NULL;
            """)
            print("     OK (HNSW index)")
        except Exception as e:
            print(f"     WARNING: {str(e)[:80]}")

        try:
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_memory_chunks_embedding_ivfflat
                ON memory_chunks USING ivfflat (embedding vector_cosine_ops)
                WITH (lists = 100)
                WHERE user_hash IS NOT NULL;
            """)
            print("     OK (IVFFlat index)")
        except Exception as e:
            print(f"     WARNING: {str(e)[:80]}")
    else:
        print("   Skipping ANN indexes (pgvector not available)")

    print("\n" + "=" * 80)
    print("SUCCESS: TASK A migration executed")
    print("=" * 80)

    # Verification
    print("\nVerification:")
    cur.execute("""SELECT COUNT(*) FROM information_schema.tables
                   WHERE table_name='memory_chunks' AND table_schema='public';""")
    exists = cur.fetchone()[0]
    print(f"  - Table memory_chunks: {'CREATED' if exists else 'FAILED'}")

    if exists:
        cur.execute("SELECT relrowsecurity FROM pg_class WHERE relname='memory_chunks';")
        result = cur.fetchone()
        rls = result[0] if result else False
        print(f"  - RLS enabled: {rls}")

        cur.execute("""SELECT COUNT(*) FROM pg_indexes
                       WHERE tablename='memory_chunks' AND schemaname='public';""")
        idx_count = cur.fetchone()[0]
        print(f"  - Indexes: {idx_count}")

        cur.execute("""SELECT column_name, data_type FROM information_schema.columns
                       WHERE table_name='memory_chunks' AND table_schema='public'
                       ORDER BY ordinal_position;""")
        cols = cur.fetchall()
        print(f"  - Columns: {len(cols)}")

except Exception as e:
    print(f"\nERROR: {e}")
    import traceback
    traceback.print_exc()
    exit(1)

finally:
    cur.close()
    conn.close()
