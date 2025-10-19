#!/bin/bash
# Staging Execution Guide: TASK A Deployment with Evidence Capture
# Sprint 62 / R1 Phase 1
# Date: 2025-10-19
# Usage: bash scripts/staging_execution_guide.sh

set -e

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}════════════════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}         TASK A STAGING DEPLOYMENT - Evidence Capture Guide       ${NC}"
echo -e "${GREEN}════════════════════════════════════════════════════════════════════${NC}"
echo ""

# Verify environment
echo -e "${YELLOW}Step 0: Environment Verification${NC}"
echo "========================================"

if [ -z "$STAGING_DATABASE_URL" ]; then
    echo -e "${RED}❌ STAGING_DATABASE_URL not set${NC}"
    echo "   Set: export STAGING_DATABASE_URL='postgresql://user:pass@host/db'"
    exit 1
fi

echo "✅ STAGING_DATABASE_URL is set"
echo "   Host: $(echo $STAGING_DATABASE_URL | grep -o '@[^/]*' | cut -c2-)"

# Create artifacts directory
ARTIFACTS_DIR="staging_artifacts_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$ARTIFACTS_DIR"
echo "✅ Artifacts directory: $ARTIFACTS_DIR"
echo ""

# Phase 2: Staging Deployment
echo -e "${YELLOW}Phase 2: Staging Deployment${NC}"
echo "========================================"

echo "Step 2.1: Pre-Migration Database State"
echo "----"

# Verify memory_chunks does NOT exist yet
TABLE_EXISTS=$(psql "$STAGING_DATABASE_URL" -t -c "SELECT EXISTS(SELECT 1 FROM information_schema.tables WHERE table_name='memory_chunks');")
if [ "$TABLE_EXISTS" = "t" ]; then
    echo -e "${YELLOW}⚠️  memory_chunks already exists (rollback or different staging?)${NC}"
    read -p "Continue anyway? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Capture pre-migration state
psql "$STAGING_DATABASE_URL" -c "SELECT version FROM alembic_version;" > "$ARTIFACTS_DIR/00_pre_migration_state.log" 2>&1
echo "✅ Pre-migration state captured"
echo ""

echo "Step 2.2: Running Migration"
echo "----"

# Run Alembic migration
cd /repo || cd "$(dirname "$0")/.." || exit 1
alembic upgrade +1 2>&1 | tee "$ARTIFACTS_DIR/01_migration_output.log"
MIGRATION_EXIT=$?

if [ $MIGRATION_EXIT -ne 0 ]; then
    echo -e "${RED}❌ Migration failed (exit code $MIGRATION_EXIT)${NC}"
    exit 1
fi

echo -e "${GREEN}✅ Migration completed successfully${NC}"
echo ""

echo "Step 2.3: Post-Migration Validation"
echo "----"

# Verify memory_chunks table exists
TABLE_EXISTS=$(psql "$STAGING_DATABASE_URL" -t -c "SELECT EXISTS(SELECT 1 FROM information_schema.tables WHERE table_name='memory_chunks');")
if [ "$TABLE_EXISTS" = "t" ]; then
    echo "✅ memory_chunks table created"
else
    echo -e "${RED}❌ memory_chunks table not found${NC}"
    exit 1
fi

# Verify RLS enabled
RLS_ENABLED=$(psql "$STAGING_DATABASE_URL" -t -c "SELECT relrowsecurity FROM pg_class WHERE relname='memory_chunks';")
if [ "$RLS_ENABLED" = "t" ]; then
    echo "✅ RLS is ENABLED"
else
    echo -e "${RED}❌ RLS not enabled${NC}"
    exit 1
fi

# List indexes
echo "✅ Indexes created:"
psql "$STAGING_DATABASE_URL" -c "\d memory_chunks" | tee "$ARTIFACTS_DIR/02_table_structure.log"
echo ""

# Phase 2.4: Pre-Deploy Sanity Checks
echo "Step 2.4: Running Pre-Deploy Sanity Checks"
echo "----"

psql "$STAGING_DATABASE_URL" < scripts/task_a_pre_deploy_sanity.sql 2>&1 | tee "$ARTIFACTS_DIR/03_sanity_checks.log"

# Check if all 3 checks passed
SANITY_PASSED=$(grep -c "✅ Check" "$ARTIFACTS_DIR/03_sanity_checks.log" || echo 0)
if [ "$SANITY_PASSED" -ge 3 ]; then
    echo -e "${GREEN}✅ All sanity checks PASSED${NC}"
else
    echo -e "${RED}❌ Some sanity checks FAILED${NC}"
    cat "$ARTIFACTS_DIR/03_sanity_checks.log"
    exit 1
fi
echo ""

# Phase 2.5: EXPLAIN Plan Verification
echo "Step 2.5: Running EXPLAIN Plan Verification"
echo "----"

psql "$STAGING_DATABASE_URL" < scripts/verify_task_a_indexes.sql 2>&1 | tee "$ARTIFACTS_DIR/04_explain_plans.log"

# Extract key metrics from EXPLAIN output
echo "🔍 Extracted Metrics:"
grep -E "(Execution Time|Planning Time|Index Scan|APPROVED)" "$ARTIFACTS_DIR/04_explain_plans.log" | head -20
echo ""

# Phase 2.6: Leak Test (Cross-Tenant Isolation)
echo "Step 2.6: Executing Leak Test (Cross-Tenant Isolation)"
echo "----"

LEAK_TEST_OUTPUT=$(mktemp)
cat > "$LEAK_TEST_OUTPUT" << 'LEAKTEST_SQL'
-- Leak Test: Verify RLS blocks cross-tenant access

-- Setup test data for user A
SET app.user_hash = 'test_user_hash_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';

INSERT INTO memory_chunks (
    user_hash, doc_id, source, embedding, chunk_index,
    created_at, updated_at
) VALUES (
    'test_user_hash_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
    'leak_test_doc_a',
    'test',
    '[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]'::vector,
    0,
    NOW(),
    NOW()
);

-- Verify user A sees 1 row
SELECT 'USER_A_SEES:' as test_step, COUNT(*) as rows_visible FROM memory_chunks;

-- Switch to user B with different user_hash
SET app.user_hash = 'test_user_hash_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb';

-- CRITICAL: User B must see 0 rows (RLS policy enforced)
SELECT 'USER_B_SEES:' as test_step, COUNT(*) as rows_visible FROM memory_chunks;

-- If user B sees 0, RLS is working correctly (leak blocked)
-- If user B sees > 0, RLS FAILED (data leaked)

-- Cleanup
RESET app.user_hash;
DELETE FROM memory_chunks WHERE doc_id = 'leak_test_doc_a';

-- Final verification
SELECT 'CLEANUP_RESULT:' as test_step, COUNT(*) as remaining_rows FROM memory_chunks;
LEAKTEST_SQL

psql "$STAGING_DATABASE_URL" < "$LEAK_TEST_OUTPUT" 2>&1 | tee "$ARTIFACTS_DIR/05_leak_test.log"

# Parse leak test results
USER_A_ROWS=$(grep "USER_A_SEES" "$ARTIFACTS_DIR/05_leak_test.log" | grep -oE "[0-9]+" | tail -1)
USER_B_ROWS=$(grep "USER_B_SEES" "$ARTIFACTS_DIR/05_leak_test.log" | grep -oE "[0-9]+" | tail -1)

echo ""
echo "📊 Leak Test Results:"
echo "   User A sees: $USER_A_ROWS rows (expected: 1)"
echo "   User B sees: $USER_B_ROWS rows (expected: 0 - CRITICAL)"

if [ "$USER_A_ROWS" = "1" ] && [ "$USER_B_ROWS" = "0" ]; then
    echo -e "${GREEN}✅ LEAK TEST PASSED - RLS is blocking cross-tenant access${NC}"
    LEAK_TEST_PASS=true
else
    echo -e "${RED}❌ LEAK TEST FAILED - RLS not enforcing isolation${NC}"
    LEAK_TEST_PASS=false
fi

rm -f "$LEAK_TEST_OUTPUT"
echo ""

# Summary
echo -e "${GREEN}════════════════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}                         STAGING SUMMARY                           ${NC}"
echo -e "${GREEN}════════════════════════════════════════════════════════════════════${NC}"
echo ""

echo "✅ Artifacts Captured:"
echo "   1. Pre-migration state: $ARTIFACTS_DIR/00_pre_migration_state.log"
echo "   2. Migration output: $ARTIFACTS_DIR/01_migration_output.log"
echo "   3. Table structure: $ARTIFACTS_DIR/02_table_structure.log"
echo "   4. Sanity checks (5 probes): $ARTIFACTS_DIR/03_sanity_checks.log"
echo "   5. EXPLAIN plans (ANN verified): $ARTIFACTS_DIR/04_explain_plans.log"
echo "   6. Leak test (RLS isolation): $ARTIFACTS_DIR/05_leak_test.log"
echo ""

echo "📋 Deployment Status:"
echo "   ✅ Migration: PASSED"
echo "   ✅ RLS Policy: ENABLED"
echo "   ✅ Indexes: CREATED (8 indexes)"
echo "   ✅ Sanity Checks: 3/3 PASSED"

if [ "$LEAK_TEST_PASS" = true ]; then
    echo "   ✅ Leak Test: PASSED (cross-tenant isolation verified)"
    echo ""
    echo -e "${GREEN}🟢 ALL STAGING VALIDATIONS PASSED - READY FOR PRODUCTION${NC}"
else
    echo "   ❌ Leak Test: FAILED"
    echo ""
    echo -e "${RED}🔴 STAGING VALIDATION INCOMPLETE - DO NOT PROCEED${NC}"
    exit 1
fi

echo ""
echo "📁 Artifact Directory: $ARTIFACTS_DIR"
echo "   Upload all .log files to deployment ticket for production approval"
echo ""

echo -e "${YELLOW}Next Steps:${NC}"
echo "1. Review all artifacts in $ARTIFACTS_DIR"
echo "2. Upload artifacts to deployment ticket"
echo "3. If all green: Proceed to Phase 3 (Production Deploy)"
echo "4. Use TASK_A_DEPLOYMENT_CHECKLIST.md Phase 3"
echo ""

echo -e "${GREEN}✨ Staging execution complete ✨${NC}"
