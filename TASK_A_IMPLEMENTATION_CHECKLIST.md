# TASK A IMPLEMENTATION CHECKLIST
## Row-Level Security Tenant Isolation - Remediation Steps

**Status:** READY FOR IMPLEMENTATION
**Estimated Duration:** 3.5-4 hours
**Owner:** Backend Engineering Lead
**Reviewer:** Architecture Lead
**Approver:** Tech Lead

---

## PHASE 1: PRE-IMPLEMENTATION (0.5 hours)

### Setup

- [ ] **Clone repository**
  ```bash
  cd /path/to/openai-agents-workflows-2025.09.28-v1
  git branch -b fix/task-a-rls-isolation
  ```

- [ ] **Review documents**
  - [ ] Read: `TASK_A_QUICK_REFERENCE.md` (10 min)
  - [ ] Read: `TASK_A_EXECUTIVE_SUMMARY.md` (15 min)
  - [ ] Skim: `TENANT_ISOLATION_VERIFICATION_REPORT.md` (10 min)

- [ ] **Gather credentials**
  ```bash
  # Set environment variables for testing
  export STAGING_DATABASE_URL="postgresql://..."
  export APP_USER_PASSWORD="strong_password_from_secrets_manager"
  export MEMORY_TENANT_HMAC_KEY="32_byte_base64_key_here"
  ```

- [ ] **Verify current state**
  ```bash
  # Run current (broken) validation to confirm issue
  python staging_validate_artifacts.py 2>&1 | grep "LEAK TEST"
  # Expected output: "RESULT: LEAK TEST FAILED"
  ```

### Approvals

- [ ] **Get approval from Tech Lead** to proceed
  - [ ] Review risk assessment
  - [ ] Confirm timeline
  - [ ] Review rollback plan

- [ ] **Schedule code review** (for after implementation)
  - [ ] Calendar: 30 min review window
  - [ ] Reviewer: Architecture Lead

---

## PHASE 2: IMPLEMENTATION (2.5 hours)

### Part 1: Create app_user Role Migration (0.5 hours)

- [ ] **Create migration file**
  ```bash
  # File path
  alembic/versions/20251019_create_app_user_role.py

  # Copy from RLS_REMEDIATION_GUIDE.md "FIX #1" section
  # Update timestamp if needed (keep 20251019 prefix)
  ```

- [ ] **Review migration code**
  ```bash
  # Check for:
  # ✓ app_user role created with LOGIN
  # ✓ Password set (to be overridden in CI/CD)
  # ✓ Minimal permissions granted
  # ✓ Superuser check included
  # ✓ Downgrade function defined
  ```

- [ ] **Syntax check**
  ```bash
  python -m py_compile alembic/versions/20251019_create_app_user_role.py
  # Expected: No output (success)
  ```

### Part 2: Update Validation Script (1 hour)

- [ ] **Backup current script**
  ```bash
  cp staging_validate_artifacts.py staging_validate_artifacts.py.backup
  ```

- [ ] **Update connection code**
  - [ ] Add `connect_as_app_user()` function
  - [ ] Create two app_user connections (not superuser)
  - [ ] Keep superuser connection for schema checks only

- [ ] **Update leak test**
  - [ ] Use `conn_a` and `conn_b` (two app_user connections)
  - [ ] Set `app.user_hash` before each query
  - [ ] Verify isolation with (1, 0) result

- [ ] **Update sanity checks**
  - [ ] Add check for app_user role existence
  - [ ] Verify app_user is NOT superuser
  - [ ] Keep RLS and index checks

- [ ] **Code review**
  ```bash
  # Review for:
  # ✓ No superuser connection for leak test
  # ✓ Two separate connections for users A and B
  # ✓ app.user_hash set before queries
  # ✓ Expected (1, 0) result
  # ✓ Cleanup in finally block
  ```

### Part 3: Update Application Connection Code (0.5 hours)

- [ ] **Find connection file**
  ```bash
  # Likely: src/db/connection.py
  ls -la src/db/connection.py
  ```

- [ ] **Update DATABASE_URL validation**
  ```python
  # Add check to prevent superuser connection
  if "postgres:postgres@" in DATABASE_URL or "postgres:password@" in DATABASE_URL:
      raise ValueError("ERROR: Must use app_user role, not superuser")
  ```

- [ ] **Add documentation**
  ```python
  """Database connection pooling with app_user (non-superuser) role.

  Production must use:
      postgresql://app_user:password@host/railway

  NOT:
      postgresql://postgres:password@host/railway
  """
  ```

- [ ] **Verify no hardcoded superuser**
  ```bash
  grep -r "postgres:postgres" . --include="*.py" | grep -v ".backup" | grep -v ".pyc"
  # Expected: No matches in production code
  ```

### Part 4: Verify Middleware Uses RLS Context (0.5 hours)

- [ ] **Check RLS middleware integration**
  ```bash
  # Find middleware files
  find . -name "*.py" -path "*/middleware*" -o -name "*middleware*.py" | head -5
  ```

- [ ] **Verify usage**
  ```bash
  # Search for usage of set_rls_context
  grep -r "set_rls_context" . --include="*.py" | grep -v "def set_rls_context" | head -10
  ```

- [ ] **Add if missing**
  ```python
  # In FastAPI middleware:
  @app.middleware("http")
  async def rls_context_middleware(request, call_next):
      user_id = request.state.user_id
      async with set_rls_context(conn, user_id):
          request.state.db = conn
          response = await call_next(request)
      return response
  ```

- [ ] **Add documentation comment**
  ```python
  # TASK A: RLS context automatically set for each request
  # This ensures tenant isolation at DB level
  ```

---

## PHASE 3: TESTING ON STAGING (1 hour)

### Pre-Test Checks

- [ ] **Verify migration file exists and is valid**
  ```bash
  ls -la alembic/versions/20251019_create_app_user_role.py
  python -m py_compile alembic/versions/20251019_create_app_user_role.py
  ```

- [ ] **Verify validation script updated**
  ```bash
  grep -n "connect_as_app_user" staging_validate_artifacts.py
  # Expected: Function definition and usage
  ```

- [ ] **Set environment variables**
  ```bash
  export STAGING_DATABASE_URL="postgresql://user:pass@host:port/railway"
  export APP_USER_PASSWORD="strong_password_from_secrets"
  export MEMORY_TENANT_HMAC_KEY="base64_encoded_32_byte_key"
  ```

### Run Tests

- [ ] **Apply migration to staging**
  ```bash
  alembic upgrade head
  # Expected: "Done" with no errors
  ```

- [ ] **Verify app_user role created**
  ```bash
  psql -U postgres -d railway << 'EOF'
  SELECT rolname, usesuper, usecreatedb FROM pg_roles WHERE rolname = 'app_user';
  EOF
  # Expected output: app_user | f | f
  ```

- [ ] **Run corrected validation script**
  ```bash
  python staging_validate_artifacts.py
  # Expected: GREEN status and PASS on leak test
  ```

- [ ] **Check artifact logs**
  ```bash
  # Check sanity checks
  tail -5 staging_artifacts_*/03_sanity_checks.log
  # Expected: 4 of 4 checks PASSED

  # Check leak test result (CRITICAL)
  tail -10 staging_artifacts_*/05_leak_test.log
  # Expected: "RESULT: LEAK TEST PASSED"
  # Expected: "Expected (1, 0) and got (1, 0)"
  ```

### Verify RLS Enforcement

- [ ] **Manual verification - RLS blocks cross-tenant**
  ```bash
  # Terminal 1 - Create as app_user
  PGPASSWORD=<password> psql -U app_user -d railway << 'EOF'
  SET app.user_hash = 'user_a_hash_1111111111111111111111111111';
  INSERT INTO memory_chunks (user_hash, doc_id, source, embedding, chunk_index)
  VALUES ('user_a_hash_1111111111111111111111111111', 'doc1', 'test',
          ARRAY[0.1,0.2,0.3]::vector, 0);
  SELECT COUNT(*) FROM memory_chunks;  -- Should show 1
  EOF

  # Terminal 2 - Query as different user
  PGPASSWORD=<password> psql -U app_user -d railway << 'EOF'
  SET app.user_hash = 'user_b_hash_2222222222222222222222222222';
  SELECT COUNT(*) FROM memory_chunks;  -- Should show 0 (RLS blocks)
  EOF
  ```

- [ ] **Verify result**
  ```
  Terminal 1: 1
  Terminal 2: 0  ← RLS WORKING
  ```

### Verify Backward Compatibility

- [ ] **Check RLS doesn't break existing queries**
  ```bash
  # Run existing test suite
  pytest tests/ -v -k "memory" --tb=short
  # Expected: All tests pass
  ```

- [ ] **Check no schema changes**
  ```bash
  # Verify only app_user role was added
  git diff alembic/versions/20251019_memory_schema_rls.py
  # Expected: No output (no changes to RLS schema)
  ```

---

## PHASE 4: CODE REVIEW & MERGE (0.5 hours)

### Prepare for Review

- [ ] **Create git commits**
  ```bash
  git add alembic/versions/20251019_create_app_user_role.py
  git commit -m "feat: add app_user role for RLS enforcement (TASK A)"

  git add staging_validate_artifacts.py
  git commit -m "fix: test RLS with app_user role, not superuser (TASK A)"

  git add src/db/connection.py
  git commit -m "fix: use app_user role in production, validate against superuser (TASK A)"

  git add src/middleware/rls.py  # If changes
  git commit -m "docs: document RLS context middleware integration (TASK A)"
  ```

- [ ] **Push to review branch**
  ```bash
  git push origin fix/task-a-rls-isolation
  ```

- [ ] **Create pull request**
  ```bash
  # Title: "TASK A: Fix RLS tenant isolation by using app_user role"

  # Description:
  # - Create app_user (non-superuser) role
  # - Update validation to test RLS with app_user
  # - Fix: leak test now shows (1, 0) isolation
  # - Update app connection to use app_user
  # - Blocks: CRITICAL tenant isolation vulnerability
  #
  # Fixes: #task-a-rls-isolation
  ```

### Review Checklist

- [ ] **Architecture Lead Reviews**
  - [ ] Verifies app_user role has minimal permissions
  - [ ] Verifies RLS policy not changed (only test fixed)
  - [ ] Confirms isolation test valid (1, 0 result)

- [ ] **Tech Lead Reviews**
  - [ ] Approves remediation approach
  - [ ] Verifies production impact is minimal
  - [ ] Signs off on deployment plan

- [ ] **Reviewer Signs Off**
  ```bash
  # After approval comments resolved:
  git log --oneline fix/task-a-rls-isolation
  # Expected: 4 commits with clear messages
  ```

### Merge

- [ ] **Merge to main**
  ```bash
  git checkout main
  git pull origin main
  git merge --no-ff fix/task-a-rls-isolation -m "Merge TASK A RLS remediation"
  git push origin main
  ```

- [ ] **Delete branch**
  ```bash
  git branch -d fix/task-a-rls-isolation
  git push origin --delete fix/task-a-rls-isolation
  ```

- [ ] **Tag release candidate**
  ```bash
  git tag -a task-a-rls-v1 -m "TASK A: RLS tenant isolation fix"
  git push origin task-a-rls-v1
  ```

---

## PHASE 5: PRODUCTION DEPLOYMENT PREP (0.5 hours)

### Pre-Deployment

- [ ] **Document app_user password**
  - [ ] Add to secrets manager (AWS Secrets Manager / Vault)
  - [ ] Generate strong password (32+ chars, mixed case, numbers, symbols)
  - [ ] Store: `DATABASE_APP_USER_PASSWORD`

- [ ] **Create deployment runbook**
  ```
  1. Notify on-call team
  2. Run migration: alembic upgrade head
  3. Verify app_user role: SELECT * FROM pg_roles WHERE rolname='app_user'
  4. Update DATABASE_URL environment variable
  5. Restart application instances
  6. Monitor for 48 hours
  7. Audit zero cross-tenant access
  ```

- [ ] **Prepare rollback plan**
  ```
  If issue detected:
  1. STOP application (kill connections)
  2. Rollback: alembic downgrade 20251019_memory_schema_rls
  3. Switch DATABASE_URL back to superuser (temporary)
  4. Restart application
  5. Investigate with team
  ```

- [ ] **Set up monitoring alerts**
  - [ ] Alert: RLS policy error rate > 0.1%
  - [ ] Alert: Cross-tenant row access detected (audit query)
  - [ ] Alert: app_user connection failures

### Documentation

- [ ] **Update deployment guide**
  ```
  Add to: docs/deployment/database.md

  ## TASK A: RLS Tenant Isolation (Oct 2025)

  Applications must use app_user role:
  - DATABASE_URL: postgresql://app_user:password@host/railway
  - NOT: postgresql://postgres:password@host/railway

  This ensures Row-Level Security policies are enforced.
  ```

- [ ] **Update runbook**
  ```
  Add troubleshooting section:
  - Check app_user role exists: SELECT * FROM pg_roles WHERE rolname='app_user'
  - Check app_user is not superuser: usesuper should be false
  - Check RLS policy active: SELECT * FROM pg_policies WHERE tablename='memory_chunks'
  ```

---

## PHASE 6: POST-DEPLOYMENT VALIDATION (48 hours)

### Hour 1: Immediate Checks

- [ ] **Monitor application logs**
  ```bash
  # Check for RLS errors
  grep -i "rls\|permission denied" logs/*.log | wc -l
  # Expected: 0 or very low count
  ```

- [ ] **Verify RLS enforcement**
  ```bash
  # Run audit query
  SELECT user_hash, COUNT(*) FROM memory_chunks GROUP BY user_hash;
  # Expected: Each user_hash has its own rows
  ```

- [ ] **Check performance**
  ```bash
  # Monitor query latency
  SELECT query, mean_time FROM pg_stat_statements WHERE query LIKE '%memory_chunks%'
  # Expected: No significant degradation
  ```

### Hours 2-24: Continuous Monitoring

- [ ] **Every 4 hours: Check audit logs**
  ```bash
  # Query: Have any users accessed other users' rows?
  SELECT DISTINCT user_hash FROM memory_chunks
  HAVING COUNT(*) > threshold_for_user;
  # Expected: No anomalies
  ```

- [ ] **Every 8 hours: Check application logs**
  ```bash
  # Grep for RLS-related errors
  grep -c "permission denied\|RLS\|isolation" logs/*.log
  # Expected: Count remains stable/low
  ```

- [ ] **Daily: Run manual verification**
  ```bash
  # Re-run corrected leak test on production
  python staging_validate_artifacts.py --database production
  # Expected: PASS with (1, 0) isolation
  ```

### Hours 24-48: Comprehensive Audit

- [ ] **Audit trail review**
  ```sql
  SELECT * FROM audit_logs WHERE action LIKE '%permission%' OR action LIKE '%RLS%'
  ORDER BY created_at DESC LIMIT 100;
  -- Expected: No cross-tenant violations
  ```

- [ ] **Query pattern analysis**
  ```sql
  SELECT user_id, resource_id, COUNT(*) FROM access_log
  GROUP BY user_id, resource_id
  HAVING COUNT(*) > THRESHOLD;
  -- Expected: No suspicious patterns
  ```

- [ ] **Performance report**
  ```bash
  # Generate before/after comparison
  | Metric | Before | After | Impact |
  |--------|--------|-------|--------|
  | Avg Query Time | 10ms | 11ms | +10% (acceptable) |
  | P95 Latency | 50ms | 52ms | +4% (acceptable) |
  | RLS Bypass Errors | 0 | 0 | ✓ |
  ```

### Approval & Sign-Off

- [ ] **Architecture Lead confirms**
  - [ ] No RLS violations in 48 hours
  - [ ] Performance within acceptable bounds
  - [ ] Audit logs show tenant isolation

- [ ] **Tech Lead approves completion**
  ```
  Status: APPROVED ✓
  Label: multi-tenancy-approved-v2
  Date: 2025-10-21 (example)
  ```

- [ ] **Update project status**
  ```
  TASK A COMPLETION:
  ✓ Schema created (memory_chunks)
  ✓ RLS policy implemented
  ✓ Encryption context bound (HMAC)
  ✓ Tenant isolation verified
  ✓ Production approved

  Status: READY FOR TASK B
  ```

---

## ROLLBACK DECISION TREE

### If Leak Test Fails After Deployment

```
Is leak test showing (1, 1)?
├─ YES: RLS not enforced
│   ├─ Check DATABASE_URL for superuser: grep DATABASE_URL .env
│   ├─ Check app_user exists: psql -c "SELECT * FROM pg_roles WHERE rolname='app_user'"
│   ├─ Check RLS policy: psql -c "SELECT * FROM pg_policies WHERE tablename='memory_chunks'"
│   └─ If all correct: Check PostgreSQL version (RLS added in 9.5)
└─ NO (1, 0): RLS working - proceed

Is there a permission denied error?
├─ YES: app_user role lacks permissions
│   ├─ Rollback migration: alembic downgrade
│   ├─ Fix permissions in migration
│   └─ Re-apply
└─ NO: Continue
```

### If Query Latency Increases >50%

```
Is RLS policy the cause?
├─ Check query plans: EXPLAIN ANALYZE
├─ Check index usage: Check if indexes being used
├─ Check row count: SELECT COUNT(*) FROM memory_chunks
│
If yes:
  ├─ Add partial indexes on user_hash
  ├─ Or upgrade to IVFFLAT indexes
  └─ Retest performance

If no:
  └─ Investigate other causes (not RLS related)
```

---

## SUCCESS METRICS

### Must Have All

- [ ] Leak test result: (1, 0)
- [ ] Zero cross-tenant violations in 48 hours
- [ ] Application latency < 50% increase
- [ ] Deployment completed < 30 minutes
- [ ] Zero connection errors from app
- [ ] RLS policy active in production

### Nice to Have

- [ ] Deployment with zero downtime
- [ ] Performance actually improves due to indexed partitioning
- [ ] Team training on RLS completed
- [ ] Documentation updated for future maintainers

---

## SIGN-OFF

### Checklist Complete

When all checkboxes are ✓:

```
Completed by: _________________ (Engineer)
Date: _______________________
Reviewed by: _________________ (Architect)
Date: _______________________
Approved by: ________________ (Tech Lead)
Date: _______________________

TASK A Status: COMPLETE ✓
Production Ready: YES ✓
Label Applied: multi-tenancy-approved-v2 ✓
```

---

## NOTES & TROUBLESHOOTING

### Common Issues

1. **Migration fails with "role already exists"**
   - That's OK - migration has `DO ... EXCEPTION` handling
   - It's idempotent

2. **Leak test shows (1, 1) after fixes**
   - Check: Is DATABASE_URL using app_user?
   - Check: Is STAGING_DATABASE_URL also using app_user?
   - Check: Did migration run successfully?

3. **Permission denied error on app startup**
   - app_user lacks permissions
   - Run migration again: `alembic upgrade head`
   - Verify grants: `\du` in psql

4. **Query latency spikes after deployment**
   - Check if indexes are being used
   - Check RLS policy isn't filtering everything
   - Check row count hasn't exploded

### Escalation

If stuck: Contact Architecture Lead with:
- [ ] Current step and error message
- [ ] Git branch status: `git status`
- [ ] Migration status: `alembic current`
- [ ] Database status: `SELECT * FROM pg_roles WHERE rolname='app_user'`

---

**Version:** 1.0
**Last Updated:** 2025-10-19
**Status:** Ready for Implementation
