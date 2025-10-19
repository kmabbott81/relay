# 📦 TASK A Staging Evidence Package

**Date**: 2025-10-19
**Task**: TASK A (Schema + RLS + Encryption)
**Environment**: Staging
**Goal**: Capture 3 critical artifacts to unlock production migration

---

## 📋 Three Critical Artifacts

### Artifact 1: Sanity Checks (RLS + Policies + Indexes)

**File**: `staging_artifacts_*/03_sanity_checks.log`

**Expected Output**:
```
✅ Check 1: RLS is ENABLED
✅ Check 2: RLS policy exists and is active
✅ Check 3: ANN indexes (HNSW/IVFFlat) exist
RESULT: 3 of 3 sanity checks PASSED
🟢 🟢 🟢 APPROVED: Proceed to staging Phase 3
```

**What It Validates**:
- ✅ RLS enabled on memory_chunks table
- ✅ memory_tenant_isolation policy active
- ✅ HNSW and IVFFlat indexes created

**Acceptance Criteria**: All 3 checks must PASS

---

### Artifact 2: EXPLAIN Plans (ANN Performance)

**File**: `staging_artifacts_*/04_explain_plans.log`

**Key Metrics to Extract**:

```
-- Query 1: Simple SELECT with RLS
Planning Time: < 1ms
Execution Time: < 50ms (for 100 test rows)
Rows: matching only user's rows

-- Query 2: ANN Search (CRITICAL)
Index Scan using idx_memory_chunks_embedding_hnsw
Planning Time: < 1ms
Execution Time: < 150ms (for 100 test rows, top 24)
Rows: 24 (or fewer)
Filter: (user_hash = <current value>) AND (user_hash IS NOT NULL)

-- Query 3: Composite Index
Backward Index Scan using idx_memory_chunks_user_hash_created
Planning Time: < 1ms
Execution Time: < 50ms
```

**What It Validates**:
- ✅ ANN queries use HNSW/IVFFlat index
- ✅ RLS filter applied in query plan
- ✅ Performance within budget (< 150ms for 24 candidates)
- ✅ Partial indexes scoped to user_hash IS NOT NULL

**Acceptance Criteria**:
- ANN query execution time < 150ms
- All queries show RLS filter in plan
- Index scans used (not sequential scans)

---

### Artifact 3: Leak Test (Cross-Tenant Isolation)

**File**: `staging_artifacts_*/05_leak_test.log`

**Expected Output**:
```
USER_A_SEES: 1 row (their own data)
USER_B_SEES: 0 rows (RLS blocked access)

LEAK TEST PASSED - RLS is blocking cross-tenant access
```

**What It Validates**:
- ✅ User A inserts 1 row with user_hash_a
- ✅ User A can query and sees 1 row
- ✅ User B with different app.user_hash sees 0 rows
- ✅ RLS policy is enforcing tenant isolation

**Acceptance Criteria**:
- User A sees exactly 1 row
- User B sees exactly 0 rows
- No cross-tenant data leakage

---

## 🚀 Execution Flow

### Step 1: Run Staging Deployment

```bash
# Set environment
export STAGING_DATABASE_URL="postgresql://user:pass@host/db"

# Run execution guide
bash scripts/staging_execution_guide.sh

# Captures all 6 artifacts automatically
```

### Step 2: Review Artifacts

```bash
# List generated artifacts
ls -lh staging_artifacts_20251019_*/

# Expected files:
# 00_pre_migration_state.log
# 01_migration_output.log
# 02_table_structure.log
# 03_sanity_checks.log           <- CRITICAL 1
# 04_explain_plans.log            <- CRITICAL 2
# 05_leak_test.log               <- CRITICAL 3
```

### Step 3: Validate Results

| Artifact | Check | Status |
|----------|-------|--------|
| Sanity | 3/3 checks PASS | ✅ or ❌ |
| EXPLAIN | ANN < 150ms | ✅ or ❌ |
| Leak Test | User B sees 0 | ✅ or ❌ |

### Step 4: Approval Decision

```
If ALL artifacts ✅:
  → Upload to deployment ticket
  → Unlock production migration

If ANY artifact ❌:
  → Analyze failure in artifact logs
  → Fix issue
  → Re-run staging execution
  → Recapture artifacts
```

---

## 📊 Sanity Check Details

The sanity checks script (Probe 4 & 5) provides automated validation:

### Probe 4: Final Approval Gate

```sql
DO $$
BEGIN
    IF (SELECT COUNT(*) FROM pg_policies WHERE tablename='memory_chunks') > 0
       AND (SELECT relrowsecurity FROM pg_class WHERE relname='memory_chunks')
       AND (SELECT COUNT(*) FROM pg_indexes WHERE tablename='memory_chunks'
            AND (indexname LIKE '%hnsw%' OR indexname LIKE '%ivfflat%')) > 0
    THEN
        RAISE NOTICE '✅ ✅ ✅ TASK A APPROVED FOR PRODUCTION ✅ ✅ ✅';
    ELSE
        RAISE WARNING '❌ TASK A NOT READY';
    END IF;
END $$;
```

**Expected**: Approval message printed

---

## 🔍 EXPLAIN Plan Extraction

Key metrics from `04_explain_plans.log`:

```bash
# Extract execution times
grep "Execution Time" staging_artifacts_*/04_explain_plans.log

# Extract index types used
grep "Index Scan\|Seq Scan" staging_artifacts_*/04_explain_plans.log

# Verify RLS filter present
grep "Filter:" staging_artifacts_*/04_explain_plans.log | grep "user_hash"
```

**Expected**:
- Execution times < 150ms
- Index Scans (not Seq Scans)
- Filter includes user_hash condition

---

## 🧪 Leak Test Breakdown

The leak test verifies RLS enforcement:

```sql
-- Step 1: Set app.user_hash to user A's value
SET app.user_hash = 'test_user_hash_aaaa...';

-- Step 2: Insert 1 row for user A
INSERT INTO memory_chunks (..., user_hash = 'test_user_hash_aaaa...', ...);

-- Step 3: Query as user A
SELECT COUNT(*) FROM memory_chunks;
-- Result: 1 (user A sees their row)

-- Step 4: Switch to user B's hash
SET app.user_hash = 'test_user_hash_bbbb...';

-- Step 5: Query as user B
SELECT COUNT(*) FROM memory_chunks;
-- Result: 0 (RLS blocked access - CRITICAL)

-- If result > 0: RLS FAILED, data leaked
-- If result = 0: RLS working, isolation verified
```

---

## ✅ Sign-Off Checklist

- [ ] Staging migration completed (exit code 0)
- [ ] Sanity check: 3/3 PASS
- [ ] Leak test: User B sees 0 rows
- [ ] EXPLAIN plans: ANN < 150ms
- [ ] All 6 artifacts generated
- [ ] No errors in any artifact logs
- [ ] Ready for production migration

---

## 🚨 Failure Scenarios

### If Sanity Check Fails

```
❌ Check 1 FAILED: RLS is not enabled
→ Action: Run downgrade, check migration
→ Rerun: bash scripts/staging_execution_guide.sh
```

### If Leak Test Fails (User B sees rows)

```
❌ Leak Test: User B sees 1+ rows
→ CRITICAL: RLS policy not enforcing
→ Action: Examine pg_policy, check current_setting('app.user_hash')
→ Possible cause: session variable not set, policy not applied
→ Resolution: Review TASK_A_ROLLBACK_PROCEDURE.md Phase 1
```

### If EXPLAIN Shows Seq Scan

```
Seq Scan on memory_chunks (not Index Scan)
→ Action: Check if indexes were created
→ Verify: SELECT indexname FROM pg_indexes WHERE tablename='memory_chunks';
→ May need ANALYZE: VACUUM (ANALYZE) memory_chunks;
```

---

## 📦 Artifact Package Contents

After successful staging run:

```
staging_artifacts_20251019_153045/
├── 00_pre_migration_state.log
│   └─ Alembic version before migration
├── 01_migration_output.log
│   └─ Alembic output and any warnings
├── 02_table_structure.log
│   └─ \d memory_chunks (full table structure)
├── 03_sanity_checks.log
│   └─ 5 probes: RLS, policies, indexes, approval gate
├── 04_explain_plans.log
│   └─ All EXPLAIN plans with execution times
└── 05_leak_test.log
    └─ Cross-tenant isolation verification
```

**Upload all to deployment ticket → Production approval**

---

## 🎯 Gate to Production

**Unlock production migration when**:

✅ Sanity checks: 3/3 PASS
✅ EXPLAIN plans: ANN < 150ms
✅ Leak test: User B sees 0 rows

**Evidence attached**:
- All 6 artifact logs
- Sanity check approval message
- EXPLAIN plan metrics
- Leak test results

**Approval process**:
1. Deployment team reviews artifacts
2. Security team reviews RLS policy in logs
3. DBA reviews performance metrics
4. Approve and unlock production Phase 3

---

**Staging Complete When**: All 3 critical artifacts ✅ PASS

**Next**: Production migration (Phase 3 of TASK_A_DEPLOYMENT_CHECKLIST.md)
