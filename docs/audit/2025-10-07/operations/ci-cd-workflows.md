# CI/CD Workflows Audit - 2025-10-07

## Deployed Workflows

### 1. Deploy Workflow (Phase 3)
**File:** `.github/workflows/deploy.yml` (on sprint/51-phase3-ops branch, NOT YET MERGED)

**Status:** ⏸️ **NOT ACTIVE** (branch not merged to main)

**Steps:**
1. Unit tests (`pytest`)
2. Deploy to Railway (`railway up --detach`)
3. Wait 60s for stabilization
4. Run Alembic migrations (`alembic upgrade head`)
5. Production smoke tests (`scripts/ci_smoke_tests.sh`)
6. Rollback on failure (`scripts/rollback_release.py`)
7. Generate evidence report

**Triggers:**
- Push to `sprint/51-phase3-ops`
- PR to `main`

**Required Secrets:**
- ✅ `RAILWAY_TOKEN`
- ✅ `DATABASE_PUBLIC_URL`
- ✅ `ADMIN_KEY`
- ✅ `DEV_KEY`

**Smoke Tests:**
- Health check
- /actions list
- /actions preview
- /audit read
- Security headers
- Rate limit headers

**Issues:**
- ⚠️ **P0:** Workflow not yet merged - no automated deployments
- ⚠️ **P1:** Railway CLI integration not tested in CI
- ⚠️ **P2:** Rollback script untested (generates notes only, no API call)

---

### 2. Backup Workflow (Phase 3)
**File:** `.github/workflows/backup.yml` (on sprint/51-phase3-ops branch, NOT YET MERGED)

**Status:** ⏸️ **NOT ACTIVE** (branch not merged to main)

**Nightly Backup:**
- Schedule: `0 9 * * *` (09:00 UTC)
- Script: `scripts/db_backup.py`
- Retention: 30 days (GitHub artifacts)

**Monthly Restore Drill:**
- Runs on 1st of month
- Script: `scripts/db_restore_check.py`
- Validates backup integrity

**Issues:**
- ⚠️ **P0:** Backup cron not active - no automated backups
- ⚠️ **P1:** Restore drill never executed - backups untested
- ⚠️ **P2:** No S3/long-term storage - 30-day artifact limit

---

### 3. Existing Workflows (Main Branch)

**CI Workflow**
- File: `.github/workflows/ci.yml`
- Status: ✅ Active
- Runs on: PR to main
- Steps: Linting, unit tests
- Issues: None

**Nightly Performance Baseline**
- File: `.github/workflows/nightly.yml`
- Status: ✅ Active
- Runs: Daily
- Purpose: Update perf baseline
- Issues: None

**Docker Build**
- File: `.github/workflows/docker-build.yml`
- Status: ✅ Active
- Purpose: Build and push Docker images
- Issues: None

---

## Gaps & Recommendations

### Critical (P0)
1. **No Automated Deployments**
   - Deploy workflow exists but not merged
   - Manual deploys via Railway dashboard only
   - **Action:** Merge Phase 3 PR, configure secrets

2. **No Automated Backups**
   - Backup workflow exists but not merged
   - Database unprotected
   - **Action:** Merge Phase 3 PR, verify cron runs

### High Priority (P1)
3. **Rollback Script Incomplete**
   - Only generates markdown notes
   - No actual rollback via Railway API
   - **Action:** Implement Railway API integration

4. **Backups Untested**
   - Restore drill never executed
   - Unknown if backups are valid
   - **Action:** Run manual restore drill

### Medium Priority (P2)
5. **No Long-Term Backup Storage**
   - 30-day GitHub artifacts only
   - Insufficient for compliance
   - **Action:** Configure S3 or Railway persistent storage

6. **Smoke Tests Not E2E**
   - Tests curl endpoints only
   - No full workflow validation
   - **Action:** Add preview→execute E2E test

---

## Deployment Gate

**Current State:** ❌ No automated gate

**Phase 3 Design:** ✅ Smoke tests gate deployment

**When Active:**
- Tests must pass before deploy marked successful
- Failures trigger automatic rollback
- Evidence report generated on success

**Status:** Ready to activate after Phase 3 merge

---

Generated: 2025-10-07
