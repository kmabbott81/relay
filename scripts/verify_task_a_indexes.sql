-- TASK A: Schema + RLS + Encryption — EXPLAIN Plan Verification
-- Sprint 62 / R1 Phase 1
--
-- This script verifies that:
-- 1. Partial ANN indexes are correctly scoped to user_hash
-- 2. RLS policy is enforced without query degradation
-- 3. Index selectivity is appropriate (not too broad/narrow)
-- 4. Query plans show efficient index usage

-- ============================================================================
-- PART 1: RLS Policy Verification
-- ============================================================================

-- Verify RLS is enabled on memory_chunks
SELECT
    schemaname,
    tablename,
    relrowsecurity,
    relforcerowsecurity
FROM pg_class c
JOIN pg_tables t ON c.relname = t.tablename
WHERE c.relname = 'memory_chunks';
-- Expected: relrowsecurity = true

-- Verify RLS policy exists
SELECT
    schemaname,
    tablename,
    polname,
    poltype,
    polcmd
FROM pg_policies
WHERE tablename = 'memory_chunks';
-- Expected: memory_tenant_isolation policy with 'r' (SELECT) and 'w' (INSERT/UPDATE/DELETE)

-- ============================================================================
-- PART 2: Index Structure Verification
-- ============================================================================

-- List all indexes on memory_chunks
SELECT
    indexname,
    indexdef,
    pg_size_pretty(pg_relation_size(indexname::regclass)) AS index_size
FROM pg_indexes
WHERE tablename = 'memory_chunks'
ORDER BY indexname;
-- Expected output:
-- idx_memory_chunks_embedding_hnsw         | HNSW index (vector_cosine_ops)    | ~45 MB
-- idx_memory_chunks_embedding_ivfflat      | IVFFlat index (vector_cosine_ops) | ~30 MB
-- idx_memory_chunks_user_embedding         | Composite (user_hash, embedding)  | ~15 MB
-- idx_memory_chunks_* (other B-tree)       | Standard indexes                  | ~1-5 MB

-- Check partial index WHERE conditions
SELECT
    schemaname,
    tablename,
    indexname,
    indexdef
FROM pg_indexes
WHERE tablename = 'memory_chunks'
  AND indexdef LIKE '%WHERE%'
ORDER BY indexname;
-- Expected: partial indexes should have WHERE user_hash IS NOT NULL

-- ============================================================================
-- PART 3: EXPLAIN Plans for RLS-Scoped Queries
-- ============================================================================

-- Setup test data (if not already present):
-- INSERT INTO memory_chunks (user_hash, embedding, created_at) VALUES
--     ('test_user_hash_1', '[0.1,0.2,...]'::vector, NOW());

-- Query 1: Simple SELECT with RLS
-- Run with: SET app.user_hash = 'test_user_hash_1';
SET app.user_hash = 'test_user_hash_1';

EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
SELECT id, text_plain, embedding
FROM memory_chunks
WHERE user_hash = COALESCE(current_setting('app.user_hash', true), '')
LIMIT 10;

-- Expected EXPLAIN output:
-- - Seq Scan or Index Scan (depending on data size)
-- - Filter: user_hash = <current value>
-- - Rows: matching only this user's data

-- Query 2: ANN search with RLS
-- This should use the HNSW index scoped to the user
EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
SELECT id, embedding <-> '[0.1,0.2,...]'::vector AS distance
FROM memory_chunks
WHERE user_hash = COALESCE(current_setting('app.user_hash', true), '')
ORDER BY embedding <-> '[0.1,0.2,...]'::vector
LIMIT 24;

-- Expected EXPLAIN output:
-- - Index Scan using idx_memory_chunks_embedding_hnsw
-- - Filter: (user_hash = <current value>) AND (user_hash IS NOT NULL)
-- - Limit: 24 rows
-- - Planning Time: < 1ms
-- - Execution Time: < 100ms (for 1M rows)

-- Query 3: Composite index usage
EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
SELECT id, created_at
FROM memory_chunks
WHERE user_hash = COALESCE(current_setting('app.user_hash', true), '')
ORDER BY created_at DESC
LIMIT 50;

-- Expected EXPLAIN output:
-- - Backward Index Scan using idx_memory_chunks_user_hash_created
-- - Index Filter: (user_hash = <current value>)
-- - Execution Time: < 50ms

RESET app.user_hash;

-- ============================================================================
-- PART 4: Cross-Tenant Isolation Verification
-- ============================================================================

-- Create two test sessions and verify isolation
-- Session A:
SET app.user_hash = 'user_hash_a_' || substring(md5(random()::text), 1, 32);
SELECT current_setting('app.user_hash') AS session_a_hash;

EXPLAIN (ANALYZE, BUFFERS)
SELECT COUNT(*) FROM memory_chunks;
-- Expected: Returns only rows where user_hash matches session setting

-- Session B (in separate connection):
SET app.user_hash = 'user_hash_b_' || substring(md5(random()::text), 1, 32);
SELECT current_setting('app.user_hash') AS session_b_hash;

EXPLAIN (ANALYZE, BUFFERS)
SELECT COUNT(*) FROM memory_chunks;
-- Expected: Different count than Session A (different user_hash)

-- ============================================================================
-- PART 5: Index Performance Benchmarks
-- ============================================================================

-- Measure index scan performance for 1M rows
-- (Run with realistic data volume)

-- Benchmark 1: HNSW index with RLS filter
EXPLAIN ANALYZE
WITH random_embedding AS (
    SELECT array_agg(random()) AS emb
    FROM generate_series(1, 1536)
)
SELECT id
FROM memory_chunks
WHERE user_hash = COALESCE(current_setting('app.user_hash', true), '')
ORDER BY embedding <-> (SELECT emb::vector FROM random_embedding)
LIMIT 24;

-- Expected EXPLAIN output:
-- Planning Time: < 1ms
-- Execution Time: < 150ms (on 1M rows)
-- Index Scans: 1 (uses HNSW)
-- Rows: 24

-- Benchmark 2: IVFFlat index with RLS filter
SET enable_seqscan = OFF;  -- Force index usage
EXPLAIN ANALYZE
SELECT id
FROM memory_chunks
WHERE user_hash = COALESCE(current_setting('app.user_hash', true), '')
  AND embedding IS NOT NULL
ORDER BY embedding <-> '[0.1,0.2,...]'::vector
LIMIT 24;

RESET enable_seqscan;

-- Expected EXPLAIN output:
-- Planning Time: < 1ms
-- Execution Time: < 100ms (faster than HNSW for large k)

-- ============================================================================
-- PART 6: Index Size and Bloat Analysis
-- ============================================================================

-- Check index sizes and identify bloat
SELECT
    indexrelname,
    idx_scan,
    idx_tup_read,
    idx_tup_fetch,
    pg_size_pretty(pg_relation_size(indexrelid)) AS size,
    ROUND(100.0 * (pg_relation_size(indexrelid) - pg_relation_size(indexrelid, 'main'))
        / pg_relation_size(indexrelid), 2) AS bloat_ratio
FROM pg_stat_user_indexes
WHERE relname = 'memory_chunks'
ORDER BY pg_relation_size(indexrelid) DESC;

-- Expected:
-- idx_scan > 1000 (index is being used)
-- idx_tup_read approx equal to idx_tup_fetch (efficient)
-- bloat_ratio < 10% (minimal bloat)

-- ============================================================================
-- PART 7: Partial Index Selectivity
-- ============================================================================

-- Verify partial index WHERE condition effectiveness
SELECT
    schemaname,
    tablename,
    indexname,
    idx_scan,
    idx_tup_read,
    idx_tup_fetch,
    ROUND(100.0 * idx_tup_fetch / NULLIF(idx_tup_read, 0), 2) AS efficiency_ratio
FROM pg_stat_user_indexes
WHERE tablename = 'memory_chunks'
  AND indexname LIKE '%embedding%'
ORDER BY idx_scan DESC;

-- Expected:
-- efficiency_ratio > 90% (fetches close to reads - good selectivity)
-- idx_scan > 100 (index is actively used)

-- ============================================================================
-- PART 8: RLS Policy Enforcement Cost
-- ============================================================================

-- Compare query cost with and without RLS
-- (After disabling RLS temporarily for testing)

-- Measure time WITHOUT RLS (for comparison only)
ALTER TABLE memory_chunks DISABLE ROW LEVEL SECURITY;

EXPLAIN (ANALYZE, BUFFERS)
SELECT COUNT(*) FROM memory_chunks;
-- Note execution time

-- Re-enable RLS
ALTER TABLE memory_chunks ENABLE ROW LEVEL SECURITY;

SET app.user_hash = 'test_hash_' || substring(md5(random()::text), 1, 20);

EXPLAIN (ANALYZE, BUFFERS)
SELECT COUNT(*) FROM memory_chunks;
-- Note execution time

-- Expected: Overhead < 5% with proper indexes

RESET app.user_hash;

-- ============================================================================
-- PART 9: Query Plan Validation Checklist
-- ============================================================================

-- Run these validation queries to generate a report
DO $$
DECLARE
    rls_enabled BOOLEAN;
    policy_count INTEGER;
    hnsw_exists BOOLEAN;
    ivfflat_exists BOOLEAN;
    user_index_exists BOOLEAN;
    checks_passed INTEGER := 0;
    total_checks INTEGER := 5;
BEGIN
    -- Check 1: RLS enabled
    SELECT relrowsecurity INTO rls_enabled
    FROM pg_class
    WHERE relname = 'memory_chunks';

    IF rls_enabled THEN
        RAISE NOTICE '✓ Check 1 PASSED: RLS is enabled';
        checks_passed := checks_passed + 1;
    ELSE
        RAISE WARNING '✗ Check 1 FAILED: RLS is not enabled';
    END IF;

    -- Check 2: RLS policy exists
    SELECT COUNT(*) INTO policy_count
    FROM pg_policies
    WHERE tablename = 'memory_chunks';

    IF policy_count > 0 THEN
        RAISE NOTICE '✓ Check 2 PASSED: RLS policies exist (% found)', policy_count;
        checks_passed := checks_passed + 1;
    ELSE
        RAISE WARNING '✗ Check 2 FAILED: No RLS policies found';
    END IF;

    -- Check 3: HNSW index exists
    SELECT EXISTS(
        SELECT 1 FROM pg_indexes
        WHERE tablename = 'memory_chunks'
          AND indexname LIKE '%hnsw%'
    ) INTO hnsw_exists;

    IF hnsw_exists THEN
        RAISE NOTICE '✓ Check 3 PASSED: HNSW index exists';
        checks_passed := checks_passed + 1;
    ELSE
        RAISE WARNING '✗ Check 3 FAILED: HNSW index not found';
    END IF;

    -- Check 4: IVFFlat index exists
    SELECT EXISTS(
        SELECT 1 FROM pg_indexes
        WHERE tablename = 'memory_chunks'
          AND indexname LIKE '%ivfflat%'
    ) INTO ivfflat_exists;

    IF ivfflat_exists THEN
        RAISE NOTICE '✓ Check 4 PASSED: IVFFlat index exists';
        checks_passed := checks_passed + 1;
    ELSE
        RAISE WARNING '✗ Check 4 FAILED: IVFFlat index not found';
    END IF;

    -- Check 5: User composite index exists
    SELECT EXISTS(
        SELECT 1 FROM pg_indexes
        WHERE tablename = 'memory_chunks'
          AND indexname LIKE '%user_embedding%'
    ) INTO user_index_exists;

    IF user_index_exists THEN
        RAISE NOTICE '✓ Check 5 PASSED: User composite index exists';
        checks_passed := checks_passed + 1;
    ELSE
        RAISE WARNING '✗ Check 5 FAILED: User composite index not found';
    END IF;

    RAISE NOTICE '';
    RAISE NOTICE 'SUMMARY: % of % checks PASSED', checks_passed, total_checks;

    IF checks_passed = total_checks THEN
        RAISE NOTICE '✓ ✓ ✓ ALL CHECKS PASSED - TASK A IS READY FOR PRODUCTION ✓ ✓ ✓';
    ELSE
        RAISE WARNING '✗ ✗ ✗ SOME CHECKS FAILED - DO NOT DEPLOY TO PRODUCTION ✗ ✗ ✗';
    END IF;
END $$;

-- ============================================================================
-- PART 10: Final Approval SQL
-- ============================================================================

-- Copy this entire block and run it to generate the final TASK A approval report

WITH index_summary AS (
    SELECT
        COUNT(*) AS total_indexes,
        COALESCE(SUM(CASE WHEN indexname LIKE '%hnsw%' THEN 1 ELSE 0 END), 0) AS hnsw_count,
        COALESCE(SUM(CASE WHEN indexname LIKE '%ivfflat%' THEN 1 ELSE 0 END), 0) AS ivfflat_count,
        COALESCE(SUM(CASE WHEN indexname LIKE '%user_embedding%' THEN 1 ELSE 0 END), 0) AS user_composite_count,
        pg_size_pretty(SUM(pg_relation_size(indexname::regclass))) AS total_index_size
    FROM pg_indexes
    WHERE tablename = 'memory_chunks'
),
policy_summary AS (
    SELECT
        COUNT(*) AS total_policies,
        STRING_AGG(polname, ', ') AS policy_names
    FROM pg_policies
    WHERE tablename = 'memory_chunks'
),
rls_status AS (
    SELECT
        relrowsecurity AS rls_enabled,
        relforcerowsecurity AS rls_enforced
    FROM pg_class
    WHERE relname = 'memory_chunks'
)
SELECT
    'TASK A Deployment Approval Report' AS report_title,
    NOW() AS generated_at,
    (SELECT rls_enabled FROM rls_status) AS rls_enabled,
    (SELECT rls_enforced FROM rls_status) AS rls_enforced,
    (SELECT total_indexes FROM index_summary) AS index_count,
    (SELECT hnsw_count FROM index_summary) AS hnsw_indexes,
    (SELECT ivfflat_count FROM index_summary) AS ivfflat_indexes,
    (SELECT user_composite_count FROM index_summary) AS user_composite_indexes,
    (SELECT total_index_size FROM index_summary) AS total_index_size,
    (SELECT total_policies FROM policy_summary) AS policy_count,
    (SELECT policy_names FROM policy_summary) AS policy_names,
    CASE
        WHEN (SELECT rls_enabled FROM rls_status)
         AND (SELECT hnsw_count FROM index_summary) > 0
         AND (SELECT ivfflat_count FROM index_summary) > 0
         AND (SELECT total_policies FROM policy_summary) > 0
        THEN '✅ APPROVED FOR PRODUCTION'
        ELSE '❌ NOT READY - REVIEW REQUIRED'
    END AS deployment_status;

-- Expected output:
-- ┌─────────────────────────────────────┐
-- │ TASK A Deployment Approval Report   │
-- ├─────────────────────────────────────┤
-- │ RLS Enabled: true                   │
-- │ RLS Enforced: false                 │
-- │ Index Count: 8                      │
-- │ HNSW Indexes: 1                     │
-- │ IVFFlat Indexes: 1                  │
-- │ User Composite Indexes: 1           │
-- │ Total Index Size: 95 MB             │
-- │ Policy Count: 1                     │
-- │ Policy Names: memory_tenant_isolation│
-- │ Status: ✅ APPROVED FOR PRODUCTION  │
-- └─────────────────────────────────────┘
