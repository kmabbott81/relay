# Audit Tickets Index - 2025-10-07

**Total Tickets:** 2 created, ~8 additional recommended
**Priority Distribution:** P0 (1), P1 (1), P2 (TBD), P3 (TBD)

---

## P0 - Critical Blockers (Sprint 52 Week 0)

### P0-001: Merge Sprint 51 Phase 2/3 to Main
**Status:** Open
**Owner:** TBD
**Size:** S (2-4 hours)
**Risk:** Medium
**Sprint:** 52 (Week 0, Pre-Sprint)

**Summary:** Merge PRs #29 and #30 to activate CI/CD, backups, rate limiting, security headers, and SLO monitoring.

**Impact:** Blocks automated operations, backups, and alerting. High risk of data loss and undetected outages.

**Actions:**
- Merge Phase 2 PR (#29)
- Merge Phase 3 PR (#30)
- Configure GitHub Secrets
- Import Grafana dashboards
- Import Prometheus alert rules
- Verify production deployment

**File:** `P0-001-merge-phase2-phase3.md`

---

## P1 - High Priority (Sprint 52 Week 1)

### P1-002: Run Database Restore Drill
**Status:** Open
**Owner:** TBD
**Size:** M (4-6 hours)
**Risk:** Medium
**Sprint:** 52 (Week 1)

**Summary:** Execute first manual restore drill to validate backup integrity and establish RTO/RPO baselines.

**Impact:** Untested backups = unknown recovery capability. False sense of security.

**Actions:**
- Run manual backup test
- Execute restore drill script
- Generate restore drill report
- Verify RTO < 10 minutes
- Schedule monthly drills

**File:** `P1-002-run-restore-drill.md`

---

## P1 - Recommended (To Be Created)

### P1-003: Complete Rollback Automation
**Summary:** Implement Railway API integration in rollback script (currently only generates markdown notes)
**Size:** M (6-8 hours)
**Sprint:** 52 (Week 2)

### P1-004: Add E2E Webhook Signing Test
**Summary:** Create end-to-end test with real webhook receiver to validate HMAC signing flow
**Size:** S (3-4 hours)
**Sprint:** 52 (Week 1)

---

## P2 - Medium Priority (Sprint 52 Week 2-3)

### P2-001: Deploy OTel Tracing
**Summary:** Deploy existing OpenTelemetry tracing code, configure collector
**Size:** M (4-6 hours)
**Sprint:** 52 (Week 2)

### P2-002: Add OPTIONS Smoke Test
**Summary:** Verify CORS preflight responses in CI/CD pipeline
**Size:** S (1-2 hours)
**Sprint:** 52 (Week 1)

### P2-003: Add Rate Limit Metrics
**Summary:** Export `rate_limit_breaches_total` metric from rate limiter
**Size:** S (2-3 hours)
**Sprint:** 52 (Week 2)

### P2-004: Add DB Connection Pool Metrics
**Summary:** Export `db_connection_pool_*` metrics for pool exhaustion alerts
**Size:** S (2-3 hours)
**Sprint:** 52 (Week 2)

---

## P3 - Nice to Have (Sprint 52 Week 4 or Sprint 53)

### P3-001: Automate Error Budget Tracking
**Summary:** Create weekly SLO compliance report script
**Size:** M (4-6 hours)
**Sprint:** 52 (Week 4) or 53

### P3-002: Add Incident Runbooks
**Summary:** Document runbooks for common incidents (outage, DB connection issues, rate limit breaches)
**Size:** M (6-8 hours)
**Sprint:** 53

### P3-003: Configure Long-Term Backup Storage
**Summary:** Move from 30-day GitHub artifacts to S3 or Railway persistent storage
**Size:** M (4-6 hours)
**Sprint:** 53

---

## Priority Guidance

**P0:** Must complete before Sprint 52 starts
**P1:** Complete in Sprint 52 Week 1 (foundation)
**P2:** Complete in Sprint 52 Week 2-3 (alongside Chat MVP)
**P3:** Complete in Sprint 52 Week 4 or defer to Sprint 53

---

## Categories

| Category | Count | Tickets |
|----------|-------|---------|
| Operational Excellence | 3 | P0-001, P1-002, P1-003 |
| Security | 2 | P1-004, P2-002 |
| Observability | 4 | P2-001, P2-003, P2-004, P3-001 |
| Docs | 1 | P3-002 |
| Reliability | 1 | P3-003 |

---

## Effort Summary

| Size | Hours | Count | Tickets |
|------|-------|-------|---------|
| S | 1-4 | 4 | P0-001, P2-002, P2-003, P2-004 |
| M | 4-12 | 6 | P1-002, P1-003, P2-001, P3-001, P3-002, P3-003 |
| L | 12-24 | 0 | - |
| Total | ~60h | 10 | - |

**Sprint 52 Total:** ~30-40 hours (P0, P1, P2 tickets)

---

## Next Actions

1. Create remaining P1/P2/P3 tickets
2. Assign owners
3. Add to Sprint 52 backlog
4. Prioritize in sprint planning
5. Track completion in weekly standups

---

Generated: 2025-10-07
Source: Audit findings, gap analysis, risk assessment
