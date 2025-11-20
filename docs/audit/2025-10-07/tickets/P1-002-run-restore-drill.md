# P1-002: Run Database Restore Drill

**Priority:** P1 - High
**Sprint:** 52 (Week 1)
**Owner:** TBD
**Size:** M (4-6 hours)
**Risk:** Medium

---

## Problem

Database backup workflow exists (`.github/workflows/backup.yml`) but has never been executed. Restore drill script (`scripts/db_restore_check.py`) has never been run. **Untested backups = unrecoverable data loss risk.**

**Evidence:**
- Backup workflow on sprint/51-phase3-ops branch (not merged)
- No backup artifacts in GitHub Actions
- No restore drill reports in `docs/evidence/sprint-51/phase3/`
- No historical restore drill execution

---

## Impact

**Current Risk:**
- Database corruption → no verified recovery method
- Accidental data deletion → no tested restore process
- Unknown backup validity (may be corrupted/incomplete)
- Unknown restore time (RTO unknown)

**Compliance Risk:** HIGH (no disaster recovery validation)

---

## Proposed Fix

### Step 1: Manual Backup Test
```bash
# Prerequisites
pip install psycopg2-binary

# Set environment
export DATABASE_PUBLIC_URL="<postgres-url>"

# Create test backup directory
mkdir -p /tmp/audit-backup-test

# Run backup script
python scripts/db_backup.py --output-dir /tmp/audit-backup-test

# Verify backup created
ls -lh /tmp/audit-backup-test/$(date +%Y-%m-%d)/
# Expected: relay_backup_YYYYMMDD_HHMMSS.sql.gz (>1MB)
```

### Step 2: Manual Restore Drill
```bash
# Run restore drill (creates ephemeral DB)
python scripts/db_restore_check.py --backup-dir /tmp/audit-backup-test

# Expected output:
# - Ephemeral database created
# - Backup restored
# - Sanity checks passed:
#   ✅ Tables: workspaces, api_keys, audit_logs, sessions
#   ✅ Row counts validated
# - Ephemeral database dropped
# - Report generated: docs/evidence/sprint-51/phase3/RESTORE-DRILL-REPORT.md
```

### Step 3: Review Report
```bash
cat docs/evidence/sprint-51/phase3/RESTORE-DRILL-REPORT.md

# Verify:
# - Duration < 5 minutes
# - All expected tables present
# - Row counts match production
# - No checksum errors
```

### Step 4: Schedule Regular Drills
After Phase 3 merge:
```bash
# Verify backup cron scheduled
gh workflow list | grep backup

# Manually trigger restore drill
gh workflow run backup.yml
```

---

## Acceptance Criteria

- [ ] Manual backup executed successfully
- [ ] Backup file created and validated (>1MB, gzipped)
- [ ] Manual restore drill completed
- [ ] Ephemeral database restored without errors
- [ ] Sanity checks passed (tables, row counts)
- [ ] Restore drill report generated
- [ ] Duration < 10 minutes (acceptable RTO)
- [ ] Monthly drill scheduled (after Phase 3 merge)

---

## Rollback Plan

N/A - Non-destructive operation (uses ephemeral database)

---

## Dependencies

- Phase 3 merge (for automated scheduling)
- Railway Postgres access
- `psycopg2-binary` installed
- `pg_dump` and `psql` tools installed

---

## Notes

**Restore Drill Frequency:**
- Manual: After Phase 3 merge (first time)
- Automated: Monthly (1st of month via GitHub Actions)

**RTO/RPO Targets:**
- RTO (Recovery Time Objective): < 10 minutes
- RPO (Recovery Point Objective): < 24 hours (nightly backups)

**Evidence Location:**
- `docs/evidence/sprint-51/phase3/RESTORE-DRILL-REPORT.md`

---

Created: 2025-10-07
Category: Reliability
