# P0-001: Merge Sprint 51 Phase 2/3 to Main

**Priority:** P0 - Critical Blocker
**Sprint:** 52 (Week 1)
**Owner:** TBD
**Size:** S (2-4 hours)
**Risk:** Medium

---

## Problem

Sprint 51 Phase 2 and Phase 3 PRs (#29, #30) are complete but not merged to `main`. This blocks:
- Automated CI/CD pipeline
- Automated database backups
- Alert rules and dashboards
- SLO monitoring

**Evidence:**
- PR #29: sprint/51-phase2-harden (rate limiting, security headers, webhook docs)
- PR #30: sprint/51-phase3-ops (CI/CD, backups, SLOs, alerts)
- Current main branch: Sprint 46 observability (no Phase 2/3 features)

---

## Impact

**Without merge:**
- ❌ No automated deployments (manual Railway dashboard only)
- ❌ No automated backups (database unprotected)
- ❌ No SLO monitoring (no alerts for outages/latency)
- ❌ Rate limiting not active in production
- ❌ Security headers not deployed

**Production Risk:** HIGH

---

## Proposed Fix

### Step 1: Merge Phase 2 (#29)
```bash
# Review PR
gh pr view 29

# Merge
gh pr merge 29 --squash --delete-branch

# Deploy to Railway
railway up --detach

# Verify production
curl -I https://relay-production-f2a6.up.railway.app/_stcore/health
# Check for: Strict-Transport-Security, Content-Security-Policy, X-RateLimit-*
```

### Step 2: Merge Phase 3 (#30)
```bash
# Review PR
gh pr view 30

# Merge
gh pr merge 30 --squash --delete-branch

# Configure GitHub Secrets (if not already set)
gh secret set RAILWAY_TOKEN --body="..."
gh secret set DATABASE_PUBLIC_URL --body="..."
gh secret set ADMIN_KEY --body="..."
gh secret set DEV_KEY --body="..."

# Import Grafana dashboards
# 1. Open Grafana UI
# 2. Import observability/dashboards/alerts.json
# 3. Import observability/dashboards/golden-signals.json

# Import Prometheus alert rules
# Copy observability/dashboards/alerts.json to Prometheus config
# Reload Prometheus
```

### Step 3: Verify
- ✅ Nightly backup cron scheduled (check GitHub Actions next day 09:00 UTC)
- ✅ Deploy workflow active (check .github/workflows/deploy.yml triggers)
- ✅ Grafana dashboard showing metrics
- ✅ Alert rules loaded in Prometheus

---

## Acceptance Criteria

- [ ] Phase 2 PR merged
- [ ] Phase 3 PR merged
- [ ] Production security headers verified (HSTS, CSP)
- [ ] Rate limiting active (burst test returns 429s)
- [ ] GitHub secrets configured
- [ ] Grafana dashboards imported
- [ ] Prometheus alert rules loaded
- [ ] Nightly backup cron verified (after 24h)
- [ ] Deploy workflow smoke tests pass

---

## Rollback Plan

If issues after merge:
```bash
# Revert Phase 3
git revert <phase3-merge-commit>
git push origin main

# Revert Phase 2
git revert <phase2-merge-commit>
git push origin main

# Redeploy
railway up --detach
```

---

## Dependencies

- Railway access
- Grafana access (for dashboard import)
- Prometheus config access (for alert rules)
- GitHub admin (for secrets configuration)

---

## Notes

- Phase 2/3 have full unit tests (27 passing)
- No breaking changes
- All features backward-compatible
- Evidence packages complete

---

Created: 2025-10-07
Category: Operational Excellence
