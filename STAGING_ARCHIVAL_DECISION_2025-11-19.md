# Staging Environment Archival Decision
**Date**: 2025-11-19
**Status**: APPROVED (Tech-Lead + Repo-Guardian)
**Decision Owner**: Kyle (with Tech-Lead + Repo-Guardian consensus)

---

## Executive Summary

**Decision**: Archive the staging environment in Railway and consolidate to a **single production runtime** only.

The staging environment (previously at `relay-staging-api.railway.app`) is no longer used for QA/testing. Production (`relay-production-f2a6.up.railway.app`) is the only active runtime.

**Effective Date**: 2025-11-19
**Reversibility**: Full (all configurations preserved in code for future rebuild)

---

## Rationale

### Current State
- Staging deployment workflow already disabled (`.github/workflows/deploy-staging.yml.disabled`)
- Railway staging environment renamed to "staging ARCHIVED DO NOT DEPLOY"
- Production database (pgvector-pg17) is stable and handles all workloads
- No active staging QA or testing pipeline

### Cost & Complexity Reduction
- Eliminate maintenance overhead of dual environments
- Reduce GitHub Actions secret management
- Simplify monitoring/observability configuration
- Eliminate confusion between "what goes to staging vs production"

### Production Consolidation
- All MVP features deployed and tested in production
- File upload feature (Option B) live in production
- No "pre-production staging" needed for current dev pace

---

## What Is Being Archived

### 1. **CI/CD Pipeline for Staging**
- Workflow: `.github/workflows/deploy-staging.yml.disabled` ← Already disabled
- Status: Remains disabled with explicit archival comments

### 2. **Monitoring / Observability**
- Prometheus job: `relay-staging` job removed from active scraping
- Alert labels: Staging labels retained for rebuild reference (with archival comment)

### 3. **Environment Variables**
- GitHub Secrets: `RELAY_STAGING_*` (10 secrets total) - Not rotated, access locked by disabled CI
- `.env` configuration: Archival notice added to staging section

### 4. **Railway Services**
- Railway environment: Already renamed by Kyle to "staging ARCHIVED DO NOT DEPLOY"
- Status: Cannot be deployed to without manual re-creation

---

## What Is Preserved for Future Rebuild

### 1. **Application Code**
- `Stage.STAGING` enum remains in `relay_ai/config/stage.py` (with archival docstring)
- Stage configuration logic preserved for rebuild when needed
- No code archaeology required - rebuild path is clear

### 2. **Configuration Templates**
- `.env.example` - Staging variables commented out but preserved as examples
- Prometheus config - `relay-staging` job commented but remains in template
- Deployment workflow - Still in `.disabled` file (can be re-enabled if needed)

### 3. **Documentation**
- This decision file: Explains **why** staging was archived and **how** to rebuild
- NAMING_CONVENTION.md: Updated with explicit archival state handling
- Inline code comments: Mark archival date and reference this decision

---

## Rebuild Process (If Needed Later)

**If staging needs to be restored**, follow these steps:

1. **Create Staging Environment in Railway**
   - Create new Railway environment: `staging`
   - Create new database following pgvector-pg17 pattern
   - Allocate new Railway services: `relay-staging-api`, `relay-staging-web`

2. **Enable Deployment Workflow**
   - Re-enable `.github/workflows/deploy-staging.yml.disabled`
   - Uncomment `relay-staging` job in prometheus configs
   - Update GitHub secrets with new environment credentials

3. **Deploy**
   - Push to `main` branch → triggers deployment to staging
   - Run smoke tests
   - Verify staging functionality

**Estimated rebuild time**: 2-3 hours (new services + data setup)

---

## Implementation Details

### Files Modified (Minimal, Reversible Changes)

| File | Change | Rationale |
|------|--------|-----------|
| `.github/workflows/deploy-staging.yml.disabled` | Add archival header comment | Clear signal to future developers |
| `observability/templates/prometheus.yml` | Comment out `relay-staging` job | Prevent scrape errors |
| `.env.example` | Add "ARCHIVED" notice to staging section | Document for reference |
| `relay_ai/config/stage.py` | Add archival docstring to `Stage.STAGING` | Preserve rebuild path |
| `NAMING_CONVENTION.md` | Add "Archived Stages" section | Explain git-to-staging mapping |
| `STAGING_ARCHIVAL_DECISION_2025-11-19.md` | Create this file | Single source of truth |

### Files NOT Modified
- `docs/deployment/README.md` - Will reference this decision in future updates
- GitHub Secrets - **Not rotated** (disabled CI = sufficient access control)
- `Stage.STAGING` enum - Preserved intentionally for rebuild

---

## Verification Checklist

- [x] Tech-Lead approval received
- [x] Repo-Guardian governance validation passed
- [x] No architectural conflicts detected
- [x] Rebuild path documented and reversible
- [x] Prometheus won't error on commented job
- [x] Deployment workflow remains disabled
- [x] GitHub secrets access controlled by disabled CI

---

## Timeline & Notifications

**2025-11-19**: Archival decision formalized
**2025-11-19**: Config changes committed to main
**2025-12-19** (30-day review): Assess GitHub secret rotation need

---

## Questions / Future Decisions

**Q: When should staging be rebuilt?**
A: When QA testing workflow is needed again (estimated Q1 2026 or later)

**Q: Who can approve re-enabling staging?**
A: Tech-Lead + Repo-Guardian (same approval level as this archival)

**Q: What if we need testing before that?**
A: Use production with feature flags; no separate staging environment needed

---

## References

- **Tech-Lead Review**: Approved Option A++ with enhancements
- **Repo-Guardian Governance Check**: All architectural decisions aligned
- **Prior Decision**: Staging workflow already disabled (commits b8525eb, 8a09d82)
- **Naming Convention**: See NAMING_CONVENTION.md "Archived Stages" section

---

**This decision is locked. Changes require Tech-Lead + Repo-Guardian re-approval.**
