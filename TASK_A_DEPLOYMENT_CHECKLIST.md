# TASK A: Schema + RLS + Encryption — Pre-Deployment Checklist

**Sprint**: 62 / R1 Phase 1
**Task**: A (Blocker)
**Type**: Database schema migration with Row-Level Security
**Estimated Deployment Time**: 15 minutes (staging), 20 minutes (production)
**Risk Level**: MEDIUM (RLS + encryption foundations)
**Rollback Time**: < 5 minutes

---

## ✅ Pre-Deployment Checklist

Use this checklist before deploying TASK A to any environment. Each item must be verified and signed off.

### Phase 1: Code Review & Testing

- [ ] **Code Review Complete**
  - [ ] Migration file reviewed (alembic/versions/20251019_memory_schema_rls.py)
  - [ ] RLS plumbing reviewed (src/memory/rls.py)
  - [ ] All LGTM from security team
  - Reviewed by: _________________ Date: _______

- [ ] **Unit Tests Passing**
  ```bash
  pytest tests/memory/test_rls_isolation.py -v
  ```
  - [ ] All 30+ test cases PASSED
  - [ ] Test coverage > 90%
  - [ ] No skipped tests
  - Test run date: _________________ Duration: _______ seconds

- [ ] **Linting & Format**
  ```bash
  ruff check src/memory/ tests/memory/
  black --check src/memory/ tests/memory/
  ```
  - [ ] No linting errors
  - [ ] Code formatted correctly
  - Verified by: _________________ Date: _______

### Phase 2: Staging Deployment

- [ ] **Staging Environment Ready**
  - [ ] Database backups enabled
  - [ ] Application servers healthy
  - [ ] Monitoring dashboards accessible
  - [ ] Low traffic window confirmed
  - Verified by: _________________ Date: _______

- [ ] **Pre-Migration Database State**
  ```bash
  psql $STAGING_DATABASE_URL -c "\d memory_chunks"
  psql $STAGING_DATABASE_URL -c "SELECT version FROM alembic_version;"
  ```
  - [ ] memory_chunks table does NOT exist
  - [ ] Migration history correct
  - [ ] Database connectivity confirmed
  - Verified by: _________________ Date: _______

- [ ] **Run Migration on Staging**
  ```bash
  cd /path/to/repo
  alembic upgrade +1 --db-url $STAGING_DATABASE_URL
  ```
  - [ ] Migration completed (exit code 0)
  - [ ] Duration: _________________ seconds
  - [ ] No errors in logs
  - Deployed by: _________________ Date: _______

- [ ] **Post-Migration Validation**
  ```bash
  # Verify table exists
  psql $STAGING_DATABASE_URL -c "\d memory_chunks"

  # Verify RLS enabled
  psql $STAGING_DATABASE_URL -c "SELECT relrowsecurity FROM pg_class WHERE relname='memory_chunks';"

  # Verify indexes created
  psql $STAGING_DATABASE_URL -c "SELECT indexname FROM pg_indexes WHERE tablename='memory_chunks';"
  ```
  - [ ] memory_chunks table created with all columns
  - [ ] RLS enabled: relrowsecurity = true
  - [ ] All 8 indexes created (HNSW, IVFFlat, user composite, B-tree)
  - [ ] No errors in application logs
  - Verified by: _________________ Date: _______

- [ ] **EXPLAIN Plan Verification**
  ```bash
  psql $STAGING_DATABASE_URL < scripts/verify_task_a_indexes.sql
  ```
  - [ ] All 10 EXPLAIN plans generated successfully
  - [ ] No query performance regressions
  - [ ] RLS policy enforced in query plans
  - [ ] Partial indexes used for ANN queries
  - [ ] Report shows: ✅ APPROVED FOR PRODUCTION
  - Verified by: _________________ Date: _______

- [ ] **RLS Isolation Testing**
  ```bash
  pytest tests/memory/test_rls_isolation.py::TestRLSTenantIsolation -v -m integration
  ```
  - [ ] Cross-tenant isolation blocked
  - [ ] RLS policy working correctly
  - [ ] User A cannot see User B's data
  - Test run date: _________________ Duration: _______ seconds

- [ ] **Performance Benchmarking**
  - [ ] Query latency baseline < 100ms for ANN (top 24)
  - [ ] No index bloat detected
  - [ ] Index sizes reasonable (< 100 MB total)
  - Baseline latency: _________________ ms
  - Verified by: _________________ Date: _______

- [ ] **Staging Sign-Off**
  - [ ] All checks PASSED ✓
  - [ ] Ready for production deployment
  - Approved by: _________________ Title: _____________ Date: _______

### Phase 3: Production Deployment

- [ ] **Production Environment Ready**
  - [ ] Database backups running
  - [ ] Backup verified to be restorable
  - [ ] Application servers healthy
  - [ ] Monitoring alerts configured
  - [ ] On-call engineer notified
  - [ ] Deployment window approved (low traffic)
  - Verified by: _________________ Date: _______

- [ ] **Production Pre-Migration State**
  ```bash
  psql $PRODUCTION_DATABASE_URL -c "\d memory_chunks" || true
  psql $PRODUCTION_DATABASE_URL -c "SELECT version FROM alembic_version;"
  ```
  - [ ] memory_chunks table does NOT exist
  - [ ] Current migration version recorded: _______________
  - [ ] Database connectivity confirmed
  - Verified by: _________________ Date: _______

- [ ] **Production Database Backup**
  ```bash
  # Create full backup
  pg_dump $PRODUCTION_DATABASE_URL > memory_task_a_backup_$(date +%s).sql

  # Verify backup
  file memory_task_a_backup_*.sql
  ls -lh memory_task_a_backup_*.sql
  ```
  - [ ] Full database backup created
  - [ ] Backup file size > 100 MB (realistic)
  - [ ] Backup file location: ___________________________
  - [ ] Backup verified restorable
  - Backup created by: _________________ Date: _______

- [ ] **Run Migration on Production**
  ```bash
  cd /path/to/repo
  alembic upgrade +1
  ```
  - [ ] Migration started at: _________________ (UTC)
  - [ ] Migration completed at: _________________ (UTC)
  - [ ] Duration: _________________ seconds
  - [ ] Exit code: 0 (success)
  - [ ] No errors in PostgreSQL logs
  - Deployed by: _________________ Date: _______

- [ ] **Immediate Post-Migration Checks**
  ```bash
  # Verify table exists
  psql $PRODUCTION_DATABASE_URL -c "\d memory_chunks"

  # Verify structure
  psql $PRODUCTION_DATABASE_URL -c "SELECT column_name, data_type FROM information_schema.columns WHERE table_name='memory_chunks' ORDER BY ordinal_position;"
  ```
  - [ ] memory_chunks table exists
  - [ ] All 11 columns present
  - [ ] Column types correct (UUID, String, LargeBinary, vector, etc.)
  - [ ] No constraint violations
  - Verified by: _________________ Date: _______

- [ ] **RLS Policy Verification**
  ```bash
  psql $PRODUCTION_DATABASE_URL -c "SELECT polname, poltype FROM pg_policies WHERE tablename='memory_chunks';"
  psql $PRODUCTION_DATABASE_URL -c "SELECT relrowsecurity FROM pg_class WHERE relname='memory_chunks';"
  ```
  - [ ] memory_tenant_isolation policy exists
  - [ ] RLS is enabled (relrowsecurity = true)
  - [ ] No policy errors in logs
  - Verified by: _________________ Date: _______

- [ ] **Index Creation Verification**
  ```bash
  psql $PRODUCTION_DATABASE_URL -c "SELECT indexname, idx_scan FROM pg_stat_user_indexes WHERE relname='memory_chunks' ORDER BY indexname;"
  ```
  - [ ] idx_memory_chunks_embedding_hnsw created
  - [ ] idx_memory_chunks_embedding_ivfflat created
  - [ ] idx_memory_chunks_user_embedding created
  - [ ] All 8 indexes present and ready
  - [ ] Index sizes reported: Total _________________ MB
  - Verified by: _________________ Date: _______

- [ ] **EXPLAIN Plan Verification (Production)**
  ```bash
  psql $PRODUCTION_DATABASE_URL < scripts/verify_task_a_indexes.sql > task_a_explain_report.txt 2>&1
  ```
  - [ ] All EXPLAIN plans generated successfully
  - [ ] Report shows: ✅ APPROVED FOR PRODUCTION
  - [ ] No missing indexes detected
  - [ ] RLS policy correctly integrated
  - Report location: ___________________________
  - Verified by: _________________ Date: _______

- [ ] **Application Startup**
  ```bash
  # Monitor application logs during startup
  tail -f /var/log/app/api.log | grep -E "ERROR|WARN|memory"
  ```
  - [ ] Application servers started successfully
  - [ ] No errors related to memory_chunks or RLS
  - [ ] Health checks passing
  - [ ] No database connection issues
  - Verified by: _________________ Date: _______

- [ ] **Health Check Endpoints**
  ```bash
  curl -s https://relay-production-f2a6.up.railway.app/health | jq .
  ```
  - [ ] API responding with 200 status
  - [ ] Database health check: OK
  - [ ] No elevated error rates
  - [ ] Response time < 2 seconds
  - Verified by: _________________ Date: _______

### Phase 4: Post-Deployment Monitoring

- [ ] **Error Rate Monitoring (24 hours)**
  - [ ] Error rate baseline < 0.1%
  - [ ] No spike in 4xx/5xx errors
  - [ ] No RLS-related errors in logs
  - [ ] No "permission denied" errors
  - Monitoring period: _________________ to _________________
  - Verified by: _________________ Date: _______

- [ ] **Database Performance Monitoring**
  - [ ] Query latency baseline maintained (< 1.5s for TTFV)
  - [ ] No connection pool exhaustion
  - [ ] No CPU/memory spike on database server
  - [ ] Replication lag (if applicable) < 100ms
  - Baseline query latency: _________________ ms
  - Verified by: _________________ Date: _______

- [ ] **RLS Behavior Verification**
  - [ ] Users can only see their own memory chunks
  - [ ] No cross-tenant data leakage detected
  - [ ] No "permission denied" errors in normal operation
  - [ ] Session variable correctly set/cleared
  - Verified by: _________________ Date: _______

- [ ] **Index Usage Monitoring**
  - [ ] HNSW index being used (idx_scan > 0)
  - [ ] IVFFlat index available as backup
  - [ ] No sequential scans on memory_chunks without RLS filter
  - [ ] Index efficiency ratio > 90%
  - Verified by: _________________ Date: _______

- [ ] **Monitoring Dashboard Setup**
  - [ ] Memory query latency dashboard created
  - [ ] RLS policy enforcement metrics visible
  - [ ] Index usage metrics visible
  - [ ] Alerts configured for errors/performance
  - Dashboard URL: ___________________________
  - Configured by: _________________ Date: _______

### Phase 5: Final Sign-Off & Approval

- [ ] **All Checks Passed**
  - [ ] Code review ✓
  - [ ] Unit tests ✓
  - [ ] Staging deployment ✓
  - [ ] Production deployment ✓
  - [ ] 24-hour monitoring ✓
  - [ ] RLS isolation verified ✓
  - [ ] Performance baseline maintained ✓

- [ ] **Sign-Off Authority**
  - [ ] DBA Sign-Off: _________________ Date: _______
  - [ ] DevOps Lead: _________________ Date: _______
  - [ ] Security Team: _________________ Date: _______
  - [ ] Architecture Team: _________________ Date: _______

- [ ] **Documentation Updated**
  - [ ] API docs updated with RLS requirements
  - [ ] Runbook updated with memory_chunks operations
  - [ ] Incident response guide updated
  - [ ] Architecture diagram updated
  - Documentation updated by: _________________ Date: _______

- [ ] **Notification & Communication**
  - [ ] Team Slack notification posted
  - [ ] Stakeholders notified of completion
  - [ ] Release notes created
  - [ ] Changelog entry added
  - Notification sent by: _________________ Date: _______

---

## 🚨 Rollback Decision Criteria

Execute **IMMEDIATE ROLLBACK** if any of these occur:

```
❌ ROLLBACK IF:
[ ] Error rate jumps above 0.5% for > 5 minutes
[ ] Memory_chunks table corrupted or inaccessible
[ ] RLS policy blocks legitimate queries
[ ] Query latency > 3 seconds (sustained)
[ ] Database connection pool exhausted
[ ] Replication lag > 1 second (if multi-node)
[ ] "permission denied" errors for normal users
[ ] Cross-tenant data leakage detected
```

**Rollback Command**:
```bash
alembic downgrade -1
# Then validate post-rollback state
bash /path/to/TASK_A_ROLLBACK_PROCEDURE.md  (Phase 3)
```

---

## 📋 Deployment Team Roles

| Role | Name | Contact | Escalation |
|------|------|---------|------------|
| **Deployment Lead** | __________ | __________ | VP Engineering |
| **DBA** | __________ | __________ | CTO |
| **DevOps** | __________ | __________ | VP Infrastructure |
| **Security** | __________ | __________ | Chief Security Officer |
| **On-Call** | __________ | __________ | [PagerDuty] |

---

## 📊 Deployment Timeline

```
Phase 1: Code Review & Testing      [ 4 hours ]
  ├─ Code review                    [ 1 hour  ]
  ├─ Unit tests                     [ 1 hour  ]
  ├─ Linting & formatting           [ 0.5 hour]
  └─ Sign-off                       [ 1.5 hours]

Phase 2: Staging Deployment         [ 2 hours ]
  ├─ Pre-migration checks           [ 0.25 hour]
  ├─ Run migration                  [ 0.5 hour]
  ├─ Post-migration validation      [ 0.5 hour]
  ├─ EXPLAIN plans & benchmarks    [ 0.5 hour]
  └─ Sign-off                       [ 0.25 hour]

Phase 3: Production Deployment      [ 1 hour  ]
  ├─ Pre-deployment checks          [ 0.1 hour ]
  ├─ Database backup                [ 0.2 hour ]
  ├─ Run migration                  [ 0.5 hour ]
  ├─ Validation & sign-off          [ 0.1 hour ]

Phase 4: Post-Deployment Monitoring [ 24 hours ]
  ├─ Error rate monitoring          [ Continuous ]
  ├─ Performance monitoring         [ Continuous ]
  ├─ RLS behavior verification      [ 1 hour  ]
  └─ Final approval                 [ 0.5 hour ]

Total Elapsed Time: 30 hours (from code review to production approval)
Active Deployment Time: ~2.5 hours
```

---

## 📞 Escalation Path

```
Issue Detected
    ↓
On-Call Engineer Notified
    ↓
[If < 5 min to fix?]
  ├─ YES → Attempt quick fix
  └─ NO → Execute Rollback
```

**Escalation Contacts**:
- **Database Issues**: DBA → CTO
- **Performance Issues**: DevOps → VP Infrastructure
- **Security Issues**: Security Team → Chief Security Officer
- **Data Loss**: CTO + VP Engineering → Executive Team

---

## ✅ Final Verification

Run this command one final time before declaring TASK A complete:

```bash
# Final approval script
psql $PRODUCTION_DATABASE_URL << 'EOF'
DO $$
BEGIN
    IF (SELECT COUNT(*) FROM pg_policies WHERE tablename='memory_chunks') > 0
       AND (SELECT relrowsecurity FROM pg_class WHERE relname='memory_chunks')
       AND (SELECT COUNT(*) FROM pg_indexes WHERE tablename='memory_chunks' AND indexdef LIKE '%hnsw%') > 0
    THEN
        RAISE NOTICE '✅ ✅ ✅ TASK A APPROVED FOR PRODUCTION ✅ ✅ ✅';
    ELSE
        RAISE WARNING '❌ TASK A NOT READY';
    END IF;
END $$;
EOF
```

**Expected Output**: `✅ ✅ ✅ TASK A APPROVED FOR PRODUCTION ✅ ✅ ✅`

---

## 🎯 Success Criteria (Gate Condition)

✅ **TASK A Complete when:**

- [ ] Migration reversible (rollback tested)
- [ ] RLS policy blocks cross-tenant reads (verified)
- [ ] Partial ANN indexes scoped to user_hash (EXPLAIN verified)
- [ ] repo-guardian: `security-approved` label applied
- [ ] All team sign-offs collected
- [ ] 24-hour monitoring window passed
- [ ] No critical issues detected
- [ ] Runbook updated

**Status: 🔓 UNLOCKED → TASK B (Encryption Helpers)**

---

**Checklist Last Updated**: 2025-10-19
**Checklist Version**: 1.0
**Approved By**: Architecture Team
