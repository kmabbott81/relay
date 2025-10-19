# TASK A QUICK REFERENCE
## Row-Level Security Tenant Isolation - Status & Action Items

**Last Updated:** 2025-10-19 10:21 UTC
**Status:** CRITICAL - PRODUCTION BLOCKED
**Priority:** P0 - Must fix before go-live

---

## ONE SENTENCE SUMMARY

RLS policy is correctly designed but wasn't tested properly (test used superuser which bypasses RLS) - needs app_user role + corrected validation.

---

## THE THREE-PART PROBLEM

```
1. Schema Setup       ✓ CORRECT
   └─ memory_chunks table with 7 indexes

2. RLS Policy        ✓ CORRECT
   └─ Tenant isolation enforced at DB level

3. Test Validation   ✗ WRONG
   └─ Used superuser connection (bypasses RLS)
   └─ Never actually tested RLS works

Result:
   RLS might work in production...
   OR might not (unknown - never tested correctly)
   = BLOCKED until proven with app_user role
```

---

## WHAT THE TEST SHOWED

```
Current Test (INVALID):
  User A inserts:  1 row  ✓
  User B queries:  1 row  ✗ (should be 0, but superuser sees all)

After Fix (VALID):
  User A inserts:  1 row
  User B queries:  0 rows ← RLS blocks User B from seeing User A's rows
```

---

## THE FIX (3 PARTS)

### Part 1: Create app_user Role
```bash
# In migration: 20251019_create_app_user_role.py
CREATE ROLE app_user WITH LOGIN;
GRANT SELECT, INSERT, UPDATE, DELETE ON memory_chunks TO app_user;
```

### Part 2: Update Validation
```python
# staging_validate_artifacts.py
# OLD: conn = psycopg2.connect(db_url)  # Superuser - WRONG

# NEW:
conn = psycopg2.connect(user='app_user', password='...')  # Non-superuser - RIGHT
```

### Part 3: Update App Connection
```python
# src/db/connection.py
# OLD: postgresql://postgres:pass@host/railway  # Superuser - WRONG
# NEW: postgresql://app_user:pass@host/railway   # Non-superuser - RIGHT
```

---

## FILES TO CHANGE

| File | Action | Why |
|------|--------|-----|
| `alembic/versions/20251019_create_app_user_role.py` | CREATE | Add app_user role |
| `staging_validate_artifacts.py` | UPDATE | Use app_user not superuser |
| `src/db/connection.py` | UPDATE | Use app_user not superuser |
| `src/memory/rls.py` | NO CHANGE | Already correct |

---

## SUCCESS CRITERIA

```
✓ Create app_user migration
✓ staging_validate_artifacts.py passes with app_user connections
✓ Leak test result: Expected (1, 0) and got (1, 0)
✓ DATABASE_URL uses app_user role
✓ Production approved label applied
```

---

## RISK CHECKLIST

### If You Deploy Without Fixes:

- ✗ All users can see all other users' memory chunks
- ✗ Cross-tenant data breach
- ✗ User A can delete User B's data
- ✗ User C can read User D's embeddings
- ✗ Complete multi-tenancy failure

**This is a showstopper.**

---

## QUICK COMMANDS

### Verify Current Status
```bash
# Check RLS enabled
psql -U postgres -d railway << 'EOF'
SELECT relrowsecurity FROM pg_class WHERE relname='memory_chunks';
EOF
# Expected: t (true)

# Check policy exists
psql -U postgres -d railway << 'EOF'
SELECT polname FROM pg_policies WHERE tablename='memory_chunks';
EOF
# Expected: memory_tenant_isolation
```

### Test After Fixes
```bash
# Set environment
export STAGING_DATABASE_URL="postgresql://..."
export APP_USER_PASSWORD="strong_password"

# Run corrected validation
python staging_validate_artifacts.py

# Expected output at end:
# RESULT: LEAK TEST PASSED
# Status: GREEN - Ready for production migration
```

---

## TIMELINE

```
Today (30 min):
  └─ Approve remediation approach

Today (1.5 hours):
  └─ Create app_user migration
  └─ Update validation script
  └─ Update connection code

Today (1 hour):
  └─ Test on staging database
  └─ Verify leak test passes

Before Merge (30 min):
  └─ Code review
  └─ Merge to main

Before Production (48 hours):
  └─ Deploy to production
  └─ Monitor audit logs
  └─ Verify zero cross-tenant access
```

**Total:** ~3.5 hours to fix, 48 hours to validate production

---

## DONT'S (CRITICAL)

- ✗ Don't deploy with current code
- ✗ Don't use superuser role for app
- ✗ Don't skip the corrected leak test
- ✗ Don't change the RLS policy (it's correct)
- ✗ Don't manually test RLS (use automated test)

---

## DO'S (CRITICAL)

- ✓ Do create app_user role
- ✓ Do update validation to use app_user
- ✓ Do verify leak test passes (1, 0)
- ✓ Do use app_user in production DATABASE_URL
- ✓ Do run 48-hour audit after deployment

---

## TECHNICAL DETAILS

### RLS Policy (Correct)
```sql
CREATE POLICY memory_tenant_isolation ON memory_chunks
USING (user_hash = COALESCE(current_setting('app.user_hash', true), ''))
WITH CHECK (user_hash = COALESCE(current_setting('app.user_hash', true), ''));
```

**Why it works:**
- USING: Filters SELECT/DELETE by user_hash
- WITH CHECK: Prevents INSERT/UPDATE with wrong user_hash
- COALESCE: Empty string if session var not set
- PostgreSQL enforces at execution time (not bypassed by views)

### User Hash Computation (Correct)
```python
hmac_user = HMAC-SHA256(MEMORY_TENANT_HMAC_KEY, user_id).hexdigest()
```

**Why it works:**
- Deterministic: same user_id → same hash
- Cryptographic: can't reverse (no rainbow tables)
- Tied to MEMORY_TENANT_HMAC_KEY secret
- Used as encryption AAD in TASK B

### Context Manager (Correct)
```python
async with set_rls_context(conn, user_id):
    # SET app.user_hash = 'computed_hash'
    # Execute queries
    # RESET app.user_hash (cleanup)
```

**Why it works:**
- Sets session variable
- Scopes to connection
- Automatic cleanup (even on error)
- Ready for FastAPI middleware

---

## WHO NEEDS TO ACT

| Role | Action | Timeline |
|------|--------|----------|
| **Tech Lead** | Approve fixes | Today |
| **Backend Engineer** | Implement 3 parts | Today (1.5h) |
| **QA Engineer** | Run corrected test | Today (1h) |
| **DevOps** | Deploy to production | Before go-live |
| **Architect** | Verify production audit | 48 hours |

---

## ESCALATION PATH

If something goes wrong:

1. **Test fails after fixes?**
   - Check DATABASE_URL doesn't have postgres user
   - Check app_user role exists: `SELECT * FROM pg_roles WHERE rolname='app_user'`
   - Check MEMORY_TENANT_HMAC_KEY is set consistently

2. **Leak test still shows (1, 1)?**
   - Verify connections are separate: `SELECT * FROM pg_stat_activity`
   - Check session variable is set: `SHOW app.user_hash`
   - Run as non-superuser manually: `SET ROLE app_user; SET app.user_hash = 'test'; SELECT...`

3. **Production shows cross-tenant access?**
   - IMMEDIATE: Disable app (kill DATABASE_URL connections)
   - Rollback to previous schema (RLS still off)
   - Investigate audit logs
   - Switch back to superuser temporarily (not ideal but safe)

---

## RELATED DOCUMENTS

| Document | Purpose |
|----------|---------|
| `TENANT_ISOLATION_VERIFICATION_REPORT.md` | Full technical analysis (12 sections) |
| `RLS_REMEDIATION_GUIDE.md` | Step-by-step fix instructions with code |
| `TASK_A_EXECUTIVE_SUMMARY.md` | Business/risk summary |
| `TASK_A_QUICK_REFERENCE.md` | This document |

**Start with:** This document (quick overview)
**Then read:** TASK_A_EXECUTIVE_SUMMARY.md (full context)
**Implement using:** RLS_REMEDIATION_GUIDE.md (step-by-step)
**Reference:** TENANT_ISOLATION_VERIFICATION_REPORT.md (deep dive)

---

## APPROVAL MATRIX

Current Status:
```
RLS Policy Structure:          ✓ APPROVED
Encryption Context Binding:    ✓ APPROVED
Edge Cases:                    ✓ APPROVED
Production Role Setup:         ✗ BLOCKED (needs app_user role)
Leak Test Validation:          ✗ BLOCKED (needs corrected test)
Go-Live Approval:              ✗ BLOCKED (depends on above)
```

After fixes:
```
RLS Policy Structure:          ✓ APPROVED
Encryption Context Binding:    ✓ APPROVED
Edge Cases:                    ✓ APPROVED
Production Role Setup:         ✓ APPROVED (app_user created)
Leak Test Validation:          ✓ APPROVED (passes with 1,0)
Go-Live Approval:              ✓ APPROVED (multi-tenancy-approved-v2)
```

---

## ONE PAGER SUMMARY

**What:** Row-Level Security test failed
**Why:** Used superuser role (bypasses RLS)
**Fix:** Create app_user role, use it in tests & app
**Time:** 3.5 hours engineering
**Risk:** LOW (standard PostgreSQL pattern)
**Impact if not fixed:** CRITICAL (data breach)
**Status:** BLOCKED until fixes verified

---

**Date:** 2025-10-19
**Prepared by:** Multi-Tenancy Architect
**Status:** Awaiting Approval to Proceed
**Escalation:** Contact Tech Lead if blocked
