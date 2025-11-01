# R2 Phase 3 Knowledge API - Canary Deployment Plan

**Date:** 2025-11-01
**Stage:** Pre-Canary (Smoke Tests Passing)
**Target:** Production Canary with Progressive Rollout

---

## Deployment Summary

The Knowledge API (R2 Phase 3) is a new set of 5 endpoints for PDF/document ingestion, vector embedding, and semantic search with enterprise-grade security:

- **JWT Authentication** (bearer token validation)
- **Row-Level Security (RLS)** (PostgreSQL policies per user)
- **Per-User Rate Limiting** (Redis-backed, 100 requests/hour free tier)
- **Advanced Encryption** (AES-256-GCM with AAD binding)
- **Comprehensive Telemetry** (request tracing, latency percentiles, error budgeting)

All endpoints deployed at: `/api/v1/knowledge/*`

---

## Guardrails

### Success Rate
- **Target:** ≥99%
- **Measured (Staging):** 100% (all endpoints responding)
- **Error Budget:** 1 request per 100 can fail before rollback

### Latency (p95)
- **Target:** ≤400ms
- **Baseline (local testing):** <50ms (no DB yet)
- **Expected (with PostgreSQL):** 50-150ms for search
- **Rollback threshold:** >800ms p95

### Security
- **RLS Violations:** 0 (must be zero)
  - If any cross-tenant data leak detected → immediate rollback
- **Rate Limit Precision:** Per-user keyed (must not affect other users)
- **JWT Validation:** 100% - all unauthenticated requests must return 401

### Availability
- **Target SLO:** 99.9% uptime
- **Deployment window:** Off-peak (23:00-04:00 UTC) to minimize impact
- **Rollback capability:** < 5 minutes (revert to previous commit)

---

## Canary Traffic Ramp

### Phase 1: Canary (5% Traffic)
**Duration:** 15 minutes
**Traffic:** ~50 requests (if baseline 1000 req/min)
**Error Budget:** 1 error max

**Success Criteria:**
- ✓ All 4 smoke test suites pass
- ✓ No 5xx errors in canary traffic
- ✓ RLS isolation verified (User A/B cross-tenant test)
- ✓ Rate limiting enforced per-user
- ✓ JWT validation blocks unauthenticated
- ✓ All headers present (X-Request-ID, X-RateLimit-*)

**On Failure:**
- Automatic rollback to R2 Phase 2
- PagerDuty alert to on-call team
- Post-incident review (RCA) required

---

### Phase 2: Gradual Rollout (25% Traffic)
**Duration:** 30 minutes
**Traffic:** ~250 requests
**Error Budget:** 5 errors max

**Metrics to Monitor:**
- Error rate stays ≤1%
- p95 latency ≤400ms
- Rate limit headers correct (per-user keyed)
- Zero RLS violations

**On Failure:**
- Stage back to Phase 1 (5% traffic)
- Investigate metrics in CloudWatch
- Delay Phase 3 until root cause resolved

---

### Phase 3: Full Rollout (100% Traffic)
**Duration:** 12 hours (continuous monitoring)
**Traffic:** All production traffic
**Error Budget:** Based on 99% SLO

**Metrics to Monitor:**
- Error rate ≤1%
- p95 latency ≤400ms
- RLS enforced on all requests
- Rate limit precision maintained
- Query latency distribution stable

**Success Criteria:**
- ✓ Zero security violations
- ✓ No anomalies in error patterns
- ✓ Latency stable at baseline

**On Failure:**
- Immediate rollback via git revert
- Contact DRI (Deployment Risk Identifier)
- Schedule post-incident review

---

## Rollback Decision Tree

```
┌─ Error Rate > 5%?
│  YES → Rollback (Phase 1/2/3)
│  NO  → Continue
│
├─ p95 Latency > 800ms?
│  YES → Rollback
│  NO  → Continue
│
├─ RLS Violations Detected?
│  YES → Immediate Rollback + Security Incident
│  NO  → Continue
│
├─ Rate Limit State Leak (User A affects User B)?
│  YES → Immediate Rollback
│  NO  → Continue
│
└─ JWT Validation Bypassed?
   YES → Immediate Rollback + Security Patch
   NO  → Continue to Full Rollout
```

---

## Rollback Instructions

### 1. Revert Deployment
```bash
# If on main branch
git revert HEAD --no-edit
git push origin main

# Railway will auto-rebuild with previous stable commit
# Monitor /ready endpoint for health
```

### 2. Notify Team
- Post in #deployments: "R2 Phase 3 rollback initiated - reason: [error_rate|latency|security]"
- Page on-call SRE if security incident

### 3. Post-Incident Review
- Collect metrics from CloudWatch
- Review error logs and exceptions
- Identify root cause
- Add regression test to prevent recurrence

---

## Monitoring Dashboard

**CloudWatch Metrics to Observe:**

| Metric | Threshold | Action |
|--------|-----------|--------|
| `api_requests_total` | Any | Baseline |
| `api_errors_total` | >1% | Investigate |
| `api_latency_p95_ms` | >400 | Investigate; >800 → Rollback |
| `rls_violations_total` | >0 | Immediate Rollback |
| `rate_limit_precision` | Not per-user | Investigate |
| `jwt_rejections_total` | >0 (normal) | Baseline |

**Request-Level Traces:**

Each request includes `X-Request-ID` header for end-to-end tracing. Correlate with:
- Datadog/Honeycomb trace ID
- PostgreSQL slow query log
- Redis latency histogram

---

## Communication Template

### Pre-Deployment (Slack #deployments)
```
:rocket: R2 Phase 3 Canary Deployment Starting
- Staging: SMOKE TESTS PASS (4/4)
- Staging URLs verified working
- ETA: [time] (UTC)
- Rollback available < 5 minutes
- Follow: [link-to-canary-plan]
```

### Phase 1 Passed (Slack #deployments)
```
:green_circle: Phase 1 Canary (5%) PASS
- 15 minutes, 0 errors
- RLS isolation: ✓
- Rate limiting: ✓
- JWT enforcement: ✓
- Proceeding to Phase 2 (25%)
```

### Phase 2 Passed (Slack #deployments)
```
:green_circle: Phase 2 Gradual Rollout (25%) PASS
- 30 minutes, error rate 0%
- p95 latency: 120ms (target: 400ms)
- Proceeding to Phase 3 (100%)
```

### Phase 3 Complete (Slack #announcements)
```
:tada: R2 Phase 3 Knowledge API LIVE
- Full production rollout complete
- Status: HEALTHY
- Metrics: [link to dashboard]
- Docs: [link to API docs]
```

---

## Success Definition

**R2 Phase 3 canary deployment is successful when:**

1. ✅ Phase 1 (5% traffic, 15 min): 0 errors, all guards pass
2. ✅ Phase 2 (25% traffic, 30 min): <1% error rate, guards pass
3. ✅ Phase 3 (100% traffic, 12 hrs): <1% error rate, guards pass
4. ✅ All smoke test suites verified on production
5. ✅ RLS isolation confirmed in production
6. ✅ Rate limiting enforced per-user in production
7. ✅ Zero security violations (no JWT bypasses, no cross-tenant leaks)

**Then:** Knowledge API is production-ready for general availability

---

## Contacts

- **DRI (Deployment Risk Identifier):** [On-Call SRE]
- **Product Owner:** Knowledge API team
- **Security Contact:** [Security team]
- **Escalation:** [VP Engineering]

---

## Appendix: R1 vs R2 API Compatibility

**R1 Endpoints:** All preserved (memory API, streaming, actions)
**R2 New Endpoints:** Knowledge API (5 new routes)

**Backward Compatibility:** ✅ 100% - R1 routes unaffected

No users experience service interruption from R2 Phase 3 deployment.
