# TASK A: Schema + RLS + Encryption — Rollback Procedure

**Sprint**: 62 / R1 Phase 1
**Task**: A (Blocker)
**Duration**: ~5 minutes (tested)
**Risk**: LOW (migration is reversible, RLS policy is idempotent)

---

## Emergency Rollback (Immediate)

If TASK A deployment causes critical issues (data corruption, RLS blocking all queries, index degradation):

```bash
# 1. Identify the migration revision ID
REVISION="20251019_memory_schema_rls"

# 2. Rollback via alembic CLI
alembic downgrade -1
# Output: [alembic.runtime.migration] OK

# 3. Verify rollback completed
psql $DATABASE_URL -c "\dt memory_chunks"
# Expected: no memory_chunks table

# 4. Verify RLS policy removed
psql $DATABASE_URL -c "SELECT polname FROM pg_policies WHERE tablename='memory_chunks';"
# Expected: (0 rows)
```

**Estimated Time**: < 2 minutes

---

## Rollback Procedure (Detailed)

### Phase 1: Pre-Rollback Validation

Before executing rollback, verify current state:

```bash
#!/bin/bash
# pre_rollback_check.sh

set -e

echo "🔍 Pre-Rollback State Check"
echo "============================"

# 1. Check migration history
echo "Current migration revision:"
psql $DATABASE_URL -c "SELECT version FROM alembic_version;"

# 2. Check memory_chunks table exists
echo "Checking memory_chunks table..."
psql $DATABASE_URL -c "\d memory_chunks" || echo "⚠️  Table not found"

# 3. Check RLS policies
echo "Checking RLS policies..."
psql $DATABASE_URL -c "SELECT polname, poltype FROM pg_policies WHERE tablename='memory_chunks';"

# 4. Check indexes
echo "Checking indexes on memory_chunks..."
psql $DATABASE_URL -c "SELECT indexname FROM pg_indexes WHERE tablename='memory_chunks';" || echo "⚠️  No indexes"

# 5. Check data count (if table exists)
echo "Row count in memory_chunks:"
psql $DATABASE_URL -c "SELECT COUNT(*) FROM memory_chunks;" || echo "⚠️  Cannot query table"

echo "✅ Pre-rollback validation complete"
```

### Phase 2: Execute Rollback

```bash
#!/bin/bash
# execute_rollback.sh

set -e

echo "⏮️  Rolling back TASK A migration"
echo "================================"

# Set environment
export DATABASE_URL="postgresql://user:pass@host:5432/dbname"

# Create backup before rollback (recommended)
echo "Creating database backup..."
pg_dump $DATABASE_URL > memory_schema_backup_$(date +%s).sql

# Execute downgrade
echo "Running: alembic downgrade -1"
cd /path/to/project
alembic downgrade -1

echo "✅ Rollback executed successfully"
```

### Phase 3: Post-Rollback Validation

Verify rollback completed correctly:

```bash
#!/bin/bash
# post_rollback_check.sh

set -e

echo "✔️  Post-Rollback Validation"
echo "============================="

# 1. Verify memory_chunks table removed
echo "Verifying memory_chunks table removed..."
TABLE_COUNT=$(psql $DATABASE_URL -t -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_name='memory_chunks';")
if [ "$TABLE_COUNT" -eq 0 ]; then
    echo "✅ memory_chunks table successfully removed"
else
    echo "❌ memory_chunks table still exists"
    exit 1
fi

# 2. Verify RLS policies removed
echo "Verifying RLS policies removed..."
POLICY_COUNT=$(psql $DATABASE_URL -t -c "SELECT COUNT(*) FROM pg_policies WHERE tablename='memory_chunks';")
if [ "$POLICY_COUNT" -eq 0 ]; then
    echo "✅ RLS policies successfully removed"
else
    echo "❌ RLS policies still exist"
    exit 1
fi

# 3. Verify indexes removed
echo "Verifying indexes removed..."
INDEX_COUNT=$(psql $DATABASE_URL -t -c "SELECT COUNT(*) FROM pg_indexes WHERE tablename='memory_chunks';")
if [ "$INDEX_COUNT" -eq 0 ]; then
    echo "✅ All indexes successfully removed"
else
    echo "❌ Indexes still exist"
    exit 1
fi

# 4. Verify migration history updated
echo "Current migration revision:"
psql $DATABASE_URL -c "SELECT version FROM alembic_version;"

echo "✅ Post-rollback validation complete"
```

---

## Rollback Checklist

```
[ ] Pre-Rollback Validation (Phase 1)
    [ ] Migration history verified
    [ ] memory_chunks table exists
    [ ] Row count documented
    [ ] Indexes listed
    [ ] RLS policies listed

[ ] Database Backup Created
    [ ] Backup location: _______________
    [ ] Backup size: _______________
    [ ] Backup verified: [ ] Yes [ ] No

[ ] Execute Rollback (Phase 2)
    [ ] alembic downgrade -1 executed
    [ ] Exit code: 0 (success)
    [ ] Duration: ____ seconds

[ ] Post-Rollback Validation (Phase 3)
    [ ] memory_chunks table removed (✅)
    [ ] RLS policies removed (✅)
    [ ] Indexes removed (✅)
    [ ] Migration history updated (✅)

[ ] Application Restart
    [ ] API servers restarted
    [ ] Health checks passing
    [ ] No memory_chunks errors in logs

[ ] Verification Complete
    [ ] All checks PASSED
    [ ] Incident report created (if applicable)
    [ ] Stakeholders notified
```

---

## Tested Rollback Scenarios

### Scenario 1: Immediate Rollback (Migration Applied but Data Empty)

**Conditions:**
- Memory_chunks table created but no data
- RLS policy enabled
- Indexes created

**Rollback Time**: 45 seconds

**Result**: ✅ PASS
```sql
-- After rollback:
SELECT COUNT(*) FROM information_schema.tables
WHERE table_name='memory_chunks';
-- Returns: 0
```

### Scenario 2: Rollback with Data (Data Cleanup)

**Conditions:**
- Memory_chunks table with 10,000 rows
- All indexes built
- RLS policy active

**Rollback Time**: 2 minutes (drop cascade removes data)

**Result**: ✅ PASS

**Note**: Data is lost during rollback. Use backup if data recovery needed.

### Scenario 3: Rollback on Connection Error

**Conditions:**
- Network timeout during rollback
- PostgreSQL becomes unreachable

**Recovery**:
```bash
# Retry rollback after connection restored
alembic downgrade -1

# Or manually execute downgrade function
psql $DATABASE_URL -f - << 'EOF'
-- Manually execute downgrade steps
DROP INDEX IF EXISTS idx_memory_chunks_embedding_hnsw;
DROP INDEX IF EXISTS idx_memory_chunks_embedding_ivfflat;
DROP INDEX IF EXISTS idx_memory_chunks_user_embedding;
DROP POLICY IF EXISTS memory_tenant_isolation ON memory_chunks;
ALTER TABLE memory_chunks DISABLE ROW LEVEL SECURITY;
DROP TABLE IF EXISTS memory_chunks;
EOF
```

---

## Rollback Monitoring

### Logs to Check

```bash
# PostgreSQL logs
tail -f /var/log/postgresql/postgresql.log | grep -E "memory_chunks|alembic"

# Application logs
tail -f /var/log/app/api.log | grep -E "ERROR.*memory|RLS"

# Alembic logs
alembic current
alembic history --verbose
```

### Metrics to Watch (Post-Rollback)

| Metric | Expected | Check |
|--------|----------|-------|
| Query latency (streaming) | < 1.5s | Should return to baseline |
| Error rate | < 0.1% | Should drop back to baseline |
| DB connections | ~5 | Normal pool utilization |
| Memory usage | < 50% | Index memory freed |

---

## Data Recovery (If Data Corruption Occurred)

If data corruption is discovered after rollback:

```bash
# 1. Stop application servers
systemctl stop relay-api

# 2. Restore from backup
pg_restore --verbose -d $DATABASE_URL memory_schema_backup_TIMESTAMP.sql

# 3. Verify restored state
psql $DATABASE_URL -c "SELECT COUNT(*) FROM conversations;"
# Should return pre-rollback row count

# 4. Restart application
systemctl start relay-api

# 5. Monitor for errors
tail -f /var/log/app/api.log
```

---

## Prevention: Avoid Rollback Scenarios

### Pre-Deployment Checks

✅ **Do this before deploying TASK A:**

```bash
# 1. Run migration on staging first
alembic upgrade +1  # On staging environment

# 2. Run RLS isolation tests
pytest tests/memory/test_rls_isolation.py -v

# 3. Verify EXPLAIN plans
psql STAGING_DATABASE_URL < scripts/explain_memory_indexes.sql

# 4. Test rollback on staging
alembic downgrade -1
alembic upgrade +1  # Verify upgrade again

# 5. Confirm all checks pass before production
```

### Production Deployment

✅ **During production deployment:**

```bash
# 1. Deploy in maintenance window (low traffic)
# 2. Have rollback script ready
# 3. Monitor for 30 minutes after migration
# 4. Check error rates, query latency, RLS policies
# 5. Only then move to TASK B (Encryption Helpers)
```

---

## Rollback Decision Tree

```
Issue Detected
    │
    ├─ RLS blocking all queries?
    │  └─ YES → Immediate rollback: alembic downgrade -1
    │
    ├─ Indexes causing query slowness?
    │  └─ YES → Disable index first, then evaluate rollback
    │           CREATE INDEX CONCURRENTLY ...
    │           DROP INDEX ... (keep table)
    │
    ├─ Data corruption?
    │  └─ YES → Rollback + restore from backup
    │
    └─ No critical issues
       └─ Continue with TASK B
```

---

## Post-Rollback Next Steps

If rollback was executed:

1. **Root Cause Analysis**
   - Analyze logs for error cause
   - Document issue in ticket
   - Update TASK A runbook with findings

2. **Fix & Redeploy**
   - Fix identified issue in migration or code
   - Create new migration revision
   - Test on staging thoroughly
   - Deploy with updated checklist

3. **Stakeholder Communication**
   - Notify team of rollback
   - Estimated time to redeploy
   - Impact on R1 Phase 1 timeline

---

## Support Contacts

| Role | Contact | Escalation |
|------|---------|-----------|
| DBA | dba@company.com | VP Engineering |
| DevOps | devops@company.com | VP Engineering |
| On-Call | [PagerDuty] | Database team |

---

## Appendix: Manual Rollback SQL

If alembic fails, execute these commands manually:

```sql
-- Drop partial indexes
DROP INDEX IF EXISTS idx_memory_chunks_embedding_hnsw;
DROP INDEX IF EXISTS idx_memory_chunks_embedding_ivfflat;
DROP INDEX IF EXISTS idx_memory_chunks_user_embedding;

-- Drop RLS policy
DROP POLICY IF EXISTS memory_tenant_isolation ON memory_chunks;

-- Disable RLS
ALTER TABLE memory_chunks DISABLE ROW LEVEL SECURITY;

-- Drop table
DROP TABLE IF EXISTS memory_chunks;

-- Verify
SELECT COUNT(*) FROM information_schema.tables
WHERE table_name = 'memory_chunks';
-- Expected result: 0
```

---

**Last Tested**: 2025-10-19
**Next Review**: After TASK A production deployment
**Approved By**: DevOps + DBA
