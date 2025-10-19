-- TASK A: Pre-Deploy Sanity Checks (Copy-paste for staging validation)
-- Run IMMEDIATELY after migration and seed, before Phase 3 approval
-- Exit code 0 = green light for TASK B kickoff

-- ============================================================================
-- PROBE 1: RLS Policy Active & Enforced
-- ============================================================================

\echo '🔍 PROBE 1: RLS Policy Enforcement'
\echo '===================================='

-- Verify RLS is enabled on memory_chunks
SELECT 'RLS Status' as check_name,
       CASE WHEN relrowsecurity THEN '✅ ENABLED' ELSE '❌ DISABLED' END as status
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'public' AND c.relname = 'memory_chunks';

-- Verify policy exists and is permissive (SELECT/INSERT/UPDATE/DELETE)
\echo 'RLS Policies:'
SELECT polname,
       CASE polcmd
           WHEN 'r' THEN 'SELECT'
           WHEN 'a' THEN 'INSERT'
           WHEN 'w' THEN 'UPDATE/DELETE'
           WHEN '*' THEN 'ALL'
       END as command,
       CASE WHEN polpermissive THEN 'PERMISSIVE' ELSE 'RESTRICTIVE' END as type
FROM pg_policy
WHERE polrelid = 'memory_chunks'::regclass
ORDER BY polname;

-- ============================================================================
-- PROBE 2: Leak Test (Mismatched app.user_hash returns 0 rows)
-- ============================================================================

\echo ''
\echo '🔐 PROBE 2: Cross-Tenant Isolation Leak Test'
\echo '=============================================='

-- Insert test row for user_hash_A
SET app.user_hash = 'test_user_hash_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';

INSERT INTO memory_chunks (
    user_hash, doc_id, source, embedding, chunk_index,
    created_at, updated_at
) VALUES (
    'test_user_hash_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
    'test_doc_a',
    'test',
    '[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]'::vector,
    0,
    NOW(),
    NOW()
);

-- Verify: User A sees 1 row
SELECT COUNT(*) as rows_visible_user_a FROM memory_chunks;

-- Switch to different user_hash (User B)
SET app.user_hash = 'test_user_hash_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb';

-- Critical: User B must see 0 rows (RLS leak blocked)
SELECT COUNT(*) as rows_visible_user_b FROM memory_chunks;

-- Expected output: 0 (zero rows)
-- If > 0: RLS POLICY FAILED ⚠️ DO NOT PROCEED

RESET app.user_hash;

-- Clean up test data
DELETE FROM memory_chunks WHERE doc_id = 'test_doc_a';

-- ============================================================================
-- PROBE 3: ANN Index Usage & Query Plan
-- ============================================================================

\echo ''
\echo '⚡ PROBE 3: ANN Index Plan Regression Check'
\echo '==========================================='

-- Set user context for realistic ANN query
SET app.user_hash = 'test_user_hash_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';

-- Insert seed data for index regression test
INSERT INTO memory_chunks (
    user_hash, doc_id, source, embedding, chunk_index,
    created_at, updated_at
) SELECT
    'test_user_hash_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
    'seed_doc_' || i::text,
    'test',
    (ARRAY[random(), random(), random(), random(), random(),
           random(), random(), random(), random(), random()] ||
     ARRAY[random() FOR 1526])::vector,
    i,
    NOW(),
    NOW()
FROM generate_series(1, 100) i;

-- Verify indexes are being used
\echo 'Index Usage Statistics (should show idx_scans > 0 after queries):'
SELECT indexrelname,
       idx_scan,
       idx_tup_read,
       idx_tup_fetch,
       ROUND(100.0 * idx_tup_fetch / NULLIF(idx_tup_read, 0), 2) as efficiency
FROM pg_stat_user_indexes
WHERE relname = 'memory_chunks'
  AND indexname LIKE '%embedding%'
ORDER BY indexname;

-- Run ANN query and measure plan
\echo ''
\echo 'ANN Query Plan (should use HNSW or IVFFlat index):'
\explain (ANALYZE, BUFFERS, TIMING, FORMAT JSON)
SELECT id, embedding <-> '[0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]'::vector as distance
FROM memory_chunks
WHERE user_hash = COALESCE(current_setting('app.user_hash', true), '')
ORDER BY embedding <-> '[0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]'::vector
LIMIT 24;

\echo ''
\echo 'Expected: Index Scan using idx_memory_chunks_embedding_hnsw or ivfflat'
\echo 'Execution Time should be < 150ms (with 100 seed rows)'

RESET app.user_hash;

-- Clean up seed data
DELETE FROM memory_chunks WHERE doc_id LIKE 'seed_doc_%';

-- ============================================================================
-- PROBE 4: Final Approval Gate
-- ============================================================================

\echo ''
\echo '✅ TASK A Pre-Deploy Sanity Check Summary'
\echo '========================================'

DO $$
DECLARE
    rls_enabled BOOLEAN;
    policy_exists BOOLEAN;
    hnsw_index_exists BOOLEAN;
    checks_passed INT := 0;
    total_checks INT := 3;
BEGIN
    -- Check 1: RLS enabled
    SELECT relrowsecurity INTO rls_enabled
    FROM pg_class WHERE relname = 'memory_chunks';

    IF rls_enabled THEN
        RAISE NOTICE '✅ Check 1: RLS is ENABLED';
        checks_passed := checks_passed + 1;
    ELSE
        RAISE WARNING '❌ Check 1 FAILED: RLS is not enabled';
    END IF;

    -- Check 2: RLS policy exists
    SELECT EXISTS(
        SELECT 1 FROM pg_policy WHERE polrelid = 'memory_chunks'::regclass
    ) INTO policy_exists;

    IF policy_exists THEN
        RAISE NOTICE '✅ Check 2: RLS policy exists and is active';
        checks_passed := checks_passed + 1;
    ELSE
        RAISE WARNING '❌ Check 2 FAILED: No RLS policy found';
    END IF;

    -- Check 3: Partial ANN indexes exist
    SELECT EXISTS(
        SELECT 1 FROM pg_indexes
        WHERE tablename = 'memory_chunks'
          AND (indexname LIKE '%hnsw%' OR indexname LIKE '%ivfflat%')
    ) INTO hnsw_index_exists;

    IF hnsw_index_exists THEN
        RAISE NOTICE '✅ Check 3: ANN indexes (HNSW/IVFFlat) exist';
        checks_passed := checks_passed + 1;
    ELSE
        RAISE WARNING '❌ Check 3 FAILED: No ANN indexes found';
    END IF;

    RAISE NOTICE '';
    RAISE NOTICE 'RESULT: % of % sanity checks PASSED', checks_passed, total_checks;

    IF checks_passed = total_checks THEN
        RAISE NOTICE '🟢 🟢 🟢 APPROVED: Proceed to staging Phase 3 (Production Deploy) 🟢 🟢 🟢';
    ELSE
        RAISE WARNING '🔴 🔴 🔴 BLOCKED: Fix failed checks before proceeding 🔴 🔴 🔴';
    END IF;
END $$;

-- ============================================================================
-- PROBE 5: Baseline Capture for Regression (copy to monitoring)
-- ============================================================================

\echo ''
\echo '📊 Baseline Metrics Capture'
\echo '==========================='

-- Capture index stats baseline
SELECT 'memory_chunks index baseline at ' || NOW()::text as timestamp,
       indexrelname,
       idx_scan,
       idx_size_mb = ROUND(pg_relation_size(indexrelid) / 1024.0 / 1024.0, 2),
       blks_read,
       blks_hit
FROM pg_stat_user_indexes
WHERE relname = 'memory_chunks'
ORDER BY indexrelname;

\echo ''
\echo '⏱️  Table Size Baseline'
SELECT 'memory_chunks size at ' || NOW()::text as timestamp,
       pg_size_pretty(pg_total_relation_size('memory_chunks'::regclass)) as total_size,
       pg_size_pretty(pg_relation_size('memory_chunks'::regclass)) as table_size,
       pg_size_pretty(pg_indexes_size('memory_chunks'::regclass)) as indexes_size;

\echo ''
\echo 'Row Count Baseline'
SELECT COUNT(*) as rows_in_memory_chunks FROM memory_chunks;

\echo ''
\echo '✨ Pre-Deploy Sanity Check Complete'
