-- R2 Knowledge API — Vector Storage Schema
-- Date: 2025-10-31
-- Purpose: PostgreSQL schema for file embeddings + RLS + AAD
-- Version: 1.0

-- ============================================================================
-- 1. EXTENSIONS
-- ============================================================================

-- Enable pgvector for similarity search
CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public;

-- ============================================================================
-- 2. TABLES
-- ============================================================================

-- ============================================================================
-- Table: files
-- Purpose: Track uploaded files and their processing status
-- Security: RLS enabled (user_hash isolation)
-- ============================================================================

CREATE TABLE IF NOT EXISTS files (
  -- Primary Key
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

  -- File Metadata
  title TEXT NOT NULL,
  description TEXT,
  file_size_bytes BIGINT NOT NULL,
  mime_type TEXT NOT NULL,

  -- Source & Processing
  source TEXT NOT NULL CHECK (source IN ('upload', 'api', 'email', 'slack')),
  s3_path TEXT,  -- Encrypted path in S3
  processing_status TEXT NOT NULL DEFAULT 'queued'
    CHECK (processing_status IN ('queued', 'processing', 'completed', 'failed')),

  -- Security (RLS)
  user_hash TEXT NOT NULL,

  -- Metadata (AAD-encrypted)
  tags TEXT[] DEFAULT '{}',
  metadata_encrypted BYTEA,  -- Encrypted: author, created_date, custom_fields
  metadata_aad TEXT,  -- HMAC(user_hash || file_id)

  -- Timestamps
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  indexed_at TIMESTAMP WITH TIME ZONE,
  last_accessed_at TIMESTAMP WITH TIME ZONE,

  -- Audit
  chunks_count INT DEFAULT 0,

  -- Partitioning
  CONSTRAINT files_user_hash_not_empty CHECK (LENGTH(user_hash) > 0),
  CONSTRAINT files_title_not_empty CHECK (LENGTH(title) > 0)
) PARTITION BY HASH (user_hash);

-- Create partitions (can be done dynamically, showing examples)
CREATE TABLE files_p0 PARTITION OF files FOR VALUES WITH (MODULUS 4, REMAINDER 0);
CREATE TABLE files_p1 PARTITION OF files FOR VALUES WITH (MODULUS 4, REMAINDER 1);
CREATE TABLE files_p2 PARTITION OF files FOR VALUES WITH (MODULUS 4, REMAINDER 2);
CREATE TABLE files_p3 PARTITION OF files FOR VALUES WITH (MODULUS 4, REMAINDER 3);

-- Indexes
CREATE INDEX idx_files_user_hash ON files (user_hash);
CREATE INDEX idx_files_source ON files (source);
CREATE INDEX idx_files_created_at ON files (created_at DESC);
CREATE INDEX idx_files_processing_status ON files (processing_status)
  WHERE processing_status IN ('queued', 'processing');

-- Enable RLS
ALTER TABLE files ENABLE ROW LEVEL SECURITY;

CREATE POLICY files_user_isolation
  ON files FOR ALL
  USING (user_hash = COALESCE(current_setting('app.user_hash'), ''))
  WITH CHECK (user_hash = COALESCE(current_setting('app.user_hash'), ''));

-- ============================================================================
-- Table: file_embeddings
-- Purpose: Vector embeddings for file chunks (normalized vectors)
-- Security: RLS enabled (user_hash isolation)
-- Vector Index: HNSW for cosine similarity search
-- ============================================================================

CREATE TABLE IF NOT EXISTS file_embeddings (
  -- Primary Key
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

  -- File Reference
  file_id UUID NOT NULL,
  chunk_index INT NOT NULL,
  UNIQUE(file_id, chunk_index),

  -- Content & Vector
  text_content TEXT NOT NULL,
  embedding vector(1536),  -- OpenAI ada-002: 1536 dimensions

  -- Security (RLS)
  user_hash TEXT NOT NULL,

  -- Metadata (AAD-encrypted)
  metadata_encrypted BYTEA NOT NULL,  -- {"title", "source", "tags", "position_in_file", "chunk_strategy"}
  metadata_aad TEXT NOT NULL,  -- HMAC(user_hash || file_id) for verification

  -- Timestamps
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

  -- Partitioning
  CONSTRAINT file_embeddings_user_hash_check CHECK (LENGTH(user_hash) > 0),
  CONSTRAINT file_embeddings_chunk_index_check CHECK (chunk_index >= 0),
  FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE
) PARTITION BY HASH (user_hash);

-- Create partitions
CREATE TABLE file_embeddings_p0 PARTITION OF file_embeddings FOR VALUES WITH (MODULUS 4, REMAINDER 0);
CREATE TABLE file_embeddings_p1 PARTITION OF file_embeddings FOR VALUES WITH (MODULUS 4, REMAINDER 1);
CREATE TABLE file_embeddings_p2 PARTITION OF file_embeddings FOR VALUES WITH (MODULUS 4, REMAINDER 2);
CREATE TABLE file_embeddings_p3 PARTITION OF file_embeddings FOR VALUES WITH (MODULUS 4, REMAINDER 3);

-- Indexes
CREATE INDEX idx_file_embeddings_user_hash ON file_embeddings (user_hash);
CREATE INDEX idx_file_embeddings_file_id ON file_embeddings (file_id);
CREATE INDEX idx_file_embeddings_created_at ON file_embeddings (created_at DESC);

-- HNSW Vector Index (for cosine similarity)
CREATE INDEX idx_file_embeddings_vector_hnsw
  ON file_embeddings USING hnsw (embedding vector_cosine_ops)
  WITH (m=16, ef_construction=200);

-- Fallback IVFFlat index (if HNSW unavailable on older PostgreSQL)
-- CREATE INDEX idx_file_embeddings_vector_ivfflat
--   ON file_embeddings USING ivfflat (embedding vector_cosine_ops)
--   WITH (lists=100);

-- Enable RLS
ALTER TABLE file_embeddings ENABLE ROW LEVEL SECURITY;

CREATE POLICY file_embeddings_user_isolation
  ON file_embeddings FOR ALL
  USING (user_hash = COALESCE(current_setting('app.user_hash'), ''))
  WITH CHECK (user_hash = COALESCE(current_setting('app.user_hash'), ''));

-- ============================================================================
-- Table: embedding_jobs
-- Purpose: Track async embedding generation jobs
-- Security: RLS enabled (user_hash isolation)
-- ============================================================================

CREATE TABLE IF NOT EXISTS embedding_jobs (
  -- Primary Key
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

  -- File Reference
  file_id UUID NOT NULL,
  user_hash TEXT NOT NULL,

  -- Job Configuration
  chunk_strategy TEXT NOT NULL DEFAULT 'smart'
    CHECK (chunk_strategy IN ('smart', 'fixed_size', 'semantic')),
  embedding_model TEXT NOT NULL DEFAULT 'ada-002'
    CHECK (embedding_model IN ('ada-002', 'local', 'custom')),

  -- Job Status
  status TEXT NOT NULL DEFAULT 'queued'
    CHECK (status IN ('queued', 'processing', 'completed', 'failed', 'retrying')),

  -- Results
  chunks_created INT DEFAULT 0,
  tokens_processed INT DEFAULT 0,
  latency_ms INT,
  error_message TEXT,

  -- Retry Tracking
  attempt_count INT DEFAULT 0,
  max_attempts INT DEFAULT 3,
  next_retry_at TIMESTAMP WITH TIME ZONE,

  -- Timestamps
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  started_at TIMESTAMP WITH TIME ZONE,
  completed_at TIMESTAMP WITH TIME ZONE,

  -- Audit
  CONSTRAINT embedding_jobs_user_hash_check CHECK (LENGTH(user_hash) > 0),
  FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE
);

-- Indexes
CREATE INDEX idx_embedding_jobs_user_hash ON embedding_jobs (user_hash);
CREATE INDEX idx_embedding_jobs_file_id ON embedding_jobs (file_id);
CREATE INDEX idx_embedding_jobs_status ON embedding_jobs (status)
  WHERE status IN ('queued', 'processing', 'retrying');
CREATE INDEX idx_embedding_jobs_next_retry ON embedding_jobs (next_retry_at)
  WHERE status = 'retrying';

-- RLS (optional: might not need if only admin access)
ALTER TABLE embedding_jobs ENABLE ROW LEVEL SECURITY;

CREATE POLICY embedding_jobs_user_isolation
  ON embedding_jobs FOR ALL
  USING (user_hash = COALESCE(current_setting('app.user_hash'), ''));

-- ============================================================================
-- Table: vector_search_cache
-- Purpose: Cache frequently searched queries for performance
-- Expiration: 24 hours (managed by background job)
-- ============================================================================

CREATE TABLE IF NOT EXISTS vector_search_cache (
  -- Primary Key
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

  -- Query
  query_text TEXT NOT NULL,
  query_embedding_hash TEXT NOT NULL,  -- SHA256(embedding vector)
  user_hash TEXT NOT NULL,

  -- Cache Results
  cached_result_ids UUID[] NOT NULL,  -- Top-k cached result IDs
  similarity_scores FLOAT[] NOT NULL,  -- Corresponding scores

  -- Metadata
  cache_hit_count INT DEFAULT 1,
  last_accessed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  expires_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() + INTERVAL '24 hours',

  CONSTRAINT vector_search_cache_user_hash_check CHECK (LENGTH(user_hash) > 0)
);

-- Indexes
CREATE INDEX idx_vector_search_cache_user_hash_query ON vector_search_cache (user_hash, query_embedding_hash);
CREATE INDEX idx_vector_search_cache_expires_at ON vector_search_cache (expires_at);

-- No RLS on cache (it's ephemeral and managed by cleanup job)

-- ============================================================================
-- 3. AUDIT TABLES
-- ============================================================================

-- ============================================================================
-- Table: file_access_audit
-- Purpose: Track all file access for security/compliance
-- Security: Immutable append-only log
-- ============================================================================

CREATE TABLE IF NOT EXISTS file_access_audit (
  -- Primary Key
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

  -- File Access
  file_id UUID NOT NULL,
  user_hash TEXT NOT NULL,

  -- Operation
  operation TEXT NOT NULL
    CHECK (operation IN ('upload', 'index', 'search', 'download', 'delete', 'view_metadata')),

  -- Result
  success BOOLEAN NOT NULL,
  error_code TEXT,

  -- Context
  ip_address TEXT,
  user_agent TEXT,
  request_id UUID,

  -- Timestamp
  accessed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

  CONSTRAINT file_access_audit_user_hash_check CHECK (LENGTH(user_hash) > 0)
) PARTITION BY RANGE (accessed_at);

-- Create partitions by month (auto-management recommended)
CREATE TABLE file_access_audit_202510 PARTITION OF file_access_audit
  FOR VALUES FROM ('2025-10-01') TO ('2025-11-01');
CREATE TABLE file_access_audit_202511 PARTITION OF file_access_audit
  FOR VALUES FROM ('2025-11-01') TO ('2025-12-01');

-- Indexes
CREATE INDEX idx_file_access_audit_file_id ON file_access_audit (file_id);
CREATE INDEX idx_file_access_audit_user_hash ON file_access_audit (user_hash);
CREATE INDEX idx_file_access_audit_accessed_at ON file_access_audit (accessed_at DESC);

-- Make table immutable
ALTER TABLE file_access_audit ENABLE ROW LEVEL SECURITY;

CREATE POLICY file_access_audit_no_delete ON file_access_audit FOR DELETE USING (FALSE);
CREATE POLICY file_access_audit_append_only ON file_access_audit FOR INSERT WITH CHECK (TRUE);
CREATE POLICY file_access_audit_read_own ON file_access_audit FOR SELECT
  USING (user_hash = COALESCE(current_setting('app.user_hash'), ''));

-- ============================================================================
-- 4. VIEWS
-- ============================================================================

-- ============================================================================
-- View: file_statistics
-- Purpose: Aggregate statistics for files and embeddings
-- ============================================================================

CREATE OR REPLACE VIEW file_statistics AS
SELECT
  f.id as file_id,
  f.user_hash,
  f.title,
  f.source,
  f.file_size_bytes,
  COUNT(fe.id) as embedding_count,
  COUNT(fe.id) FILTER (WHERE fe.created_at > NOW() - INTERVAL '1 day') as embeddings_last_24h,
  AVG(LENGTH(fe.text_content)) as avg_chunk_length,
  MIN(fe.created_at) as oldest_embedding,
  MAX(fe.created_at) as newest_embedding,
  f.created_at as file_created_at,
  f.indexed_at
FROM files f
LEFT JOIN file_embeddings fe ON f.id = fe.file_id AND f.user_hash = fe.user_hash
GROUP BY f.id, f.user_hash, f.title, f.source, f.file_size_bytes, f.created_at, f.indexed_at;

-- ============================================================================
-- View: search_quality_metrics
-- Purpose: Monitor vector search performance
-- ============================================================================

CREATE OR REPLACE VIEW search_quality_metrics AS
SELECT
  user_hash,
  DATE_TRUNC('hour', accessed_at) as hour,
  COUNT(*) as search_count,
  AVG(
    CASE
      WHEN operation = 'search' THEN 1
      ELSE 0
    END
  )::numeric * 100 as search_success_rate,
  COUNT(DISTINCT file_id) as files_accessed
FROM file_access_audit
GROUP BY user_hash, DATE_TRUNC('hour', accessed_at)
ORDER BY hour DESC;

-- ============================================================================
-- 5. FUNCTIONS
-- ============================================================================

-- ============================================================================
-- Function: update_file_embeddings_timestamp
-- Purpose: Auto-update updated_at timestamp on file_embeddings
-- ============================================================================

CREATE OR REPLACE FUNCTION update_file_embeddings_timestamp()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER file_embeddings_updated_at
  BEFORE UPDATE ON file_embeddings
  FOR EACH ROW
  EXECUTE FUNCTION update_file_embeddings_timestamp();

-- ============================================================================
-- Function: set_user_hash_from_context
-- Purpose: Auto-set user_hash from current_setting('app.user_hash')
-- ============================================================================

CREATE OR REPLACE FUNCTION set_user_hash_from_context()
RETURNS TRIGGER AS $$
BEGIN
  NEW.user_hash = COALESCE(current_setting('app.user_hash', true), '');
  IF NEW.user_hash = '' THEN
    RAISE EXCEPTION 'app.user_hash not set in session';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER files_set_user_hash
  BEFORE INSERT ON files
  FOR EACH ROW
  EXECUTE FUNCTION set_user_hash_from_context();

CREATE TRIGGER file_embeddings_set_user_hash
  BEFORE INSERT ON file_embeddings
  FOR EACH ROW
  EXECUTE FUNCTION set_user_hash_from_context();

-- ============================================================================
-- Function: cleanup_expired_cache
-- Purpose: Remove expired cache entries (daily job)
-- ============================================================================

CREATE OR REPLACE FUNCTION cleanup_expired_cache()
RETURNS INT AS $$
DECLARE
  deleted_count INT;
BEGIN
  DELETE FROM vector_search_cache
  WHERE expires_at < NOW();

  GET DIAGNOSTICS deleted_count = ROW_COUNT;
  RETURN deleted_count;
END;
$$ LANGUAGE plpgsql;

-- Schedule: SELECT cron.schedule('cleanup_vector_cache', '0 2 * * *', 'SELECT cleanup_expired_cache()');

-- ============================================================================
-- 6. GRANTS (RBAC)
-- ============================================================================

-- Application Role (non-superuser)
CREATE ROLE app_knowledge_user WITH LOGIN;

-- Permissions
GRANT USAGE ON SCHEMA public TO app_knowledge_user;
GRANT SELECT, INSERT, UPDATE ON files TO app_knowledge_user;
GRANT SELECT, INSERT ON file_embeddings TO app_knowledge_user;
GRANT SELECT, INSERT, UPDATE ON embedding_jobs TO app_knowledge_user;
GRANT SELECT, INSERT ON vector_search_cache TO app_knowledge_user;
GRANT SELECT, INSERT ON file_access_audit TO app_knowledge_user;

-- Execute permissions for functions
GRANT EXECUTE ON FUNCTION update_file_embeddings_timestamp TO app_knowledge_user;
GRANT EXECUTE ON FUNCTION set_user_hash_from_context TO app_knowledge_user;
GRANT EXECUTE ON FUNCTION cleanup_expired_cache TO app_knowledge_user;

-- Read permissions on views
GRANT SELECT ON file_statistics TO app_knowledge_user;
GRANT SELECT ON search_quality_metrics TO app_knowledge_user;

-- ============================================================================
-- 7. COMMENTS (Documentation)
-- ============================================================================

COMMENT ON TABLE files IS
  'Metadata for uploaded files. RLS enforced per user_hash.';

COMMENT ON TABLE file_embeddings IS
  'Vector embeddings for file chunks. Indexed with HNSW for similarity search. RLS + AAD encrypted metadata.';

COMMENT ON COLUMN file_embeddings.embedding IS
  'Vector embedding (1536 dimensions for ada-002). Supports cosine similarity search.';

COMMENT ON COLUMN file_embeddings.metadata_aad IS
  'Additional Authenticated Data: HMAC(user_hash || file_id). Prevents cross-user metadata access.';

COMMENT ON TABLE embedding_jobs IS
  'Async job tracking for file-to-embedding pipeline. Supports retry with exponential backoff.';

COMMENT ON FUNCTION cleanup_expired_cache() IS
  'Daily cleanup job to remove cache entries older than 24 hours. Schedule with pg_cron.';

-- ============================================================================
-- 8. MIGRATION NOTES
-- ============================================================================

/*
Rollback Path (if needed):
  DROP TABLE IF EXISTS file_access_audit CASCADE;
  DROP TABLE IF EXISTS vector_search_cache CASCADE;
  DROP TABLE IF EXISTS embedding_jobs CASCADE;
  DROP TABLE IF EXISTS file_embeddings CASCADE;
  DROP TABLE IF EXISTS files CASCADE;
  DROP EXTENSION IF EXISTS vector CASCADE;

Scaling Considerations:
  - Partition by user_hash (HASH) for horizontal scaling
  - HNSW index tuning: increase m=16, ef_construction=200 for accuracy
  - Archive old embeddings after 90 days if storage is concern
  - Consider separate database for audit logs (compliance)

Performance Tuning:
  - HNSW parameters: m (connections per node), ef_construction (quality vs speed)
  - VACUUM and ANALYZE embeddings table weekly
  - Index bloat cleanup: REINDEX INDEX idx_file_embeddings_vector_hnsw
  - Monitor query plans: EXPLAIN ANALYZE SELECT ... FROM file_embeddings WHERE ...
*/

-- ============================================================================
-- End of Schema
-- ============================================================================
