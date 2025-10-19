# R1 Phase 1 - Final Phase Execution Guide

**Date**: 2025-10-19
**Status**: 🟢 **AUTHORIZED FOR EXECUTION**
**Strategy**: Canary Deployment + Parallel B&C Execution

---

## Executive Summary

**Optimal Strategy**: Execute canary deployment (5% traffic validation) while TASK B and TASK C teams work in parallel.

**Rationale**:
- Canary validates RLS and streaming guardrails under real load
- Auto-rollback active for safety
- TASK B+C teams work on isolated branches behind feature flags
- If canary passes: teams merge immediately into production
- If canary fails: auto-rollback, teams continue isolated

**Timeline**:
- **Canary**: 1 hour (active window)
- **TASK B**: 3-4 days parallel
- **TASK C**: 2-3 days parallel
- **Total**: Days 5-10 for full R1 Phase 1 rollout

---

## Phase 1: Canary Deployment (1 Hour Active Window)

### Setup (5 minutes)

```bash
# 1. Verify production app_user connection
export PROD_DATABASE_URL="postgresql://app_user:app_secure_password_r1_2025@switchyard.proxy.rlwy.net:39963/railway"

# 2. Verify RLS policy is active
psql $PROD_DATABASE_URL -c "SELECT * FROM pg_policies WHERE tablename='memory_chunks';"
# Expected: 4 policies (SELECT, INSERT, UPDATE, DELETE)

# 3. Verify metrics endpoint is responding
curl https://relay.production.com/metrics/memory
# Expected: Prometheus metrics format
```

### Deployment (10 minutes)

**Step 1: Route 5% Traffic to Production**

```bash
# Current routing (pre-canary)
# 100% → R0.5 (production)

# Canary setup
# 5% → TASK A (R1 with RLS)
# 95% → R0.5 (current stable)

# Implementation:
# 1. Update load balancer configuration
# 2. Set canary % to 5
# 3. Monitor error rate (should be < 0.5%)
```

**Step 2: Activate Monitoring**

```bash
# Open real-time dashboards
# - TTFV p95 (target: < 1.5s, baseline: 1.1s)
# - RLS policy errors (target: 0)
# - ANN query latency (target: p95 < 200ms)
# - SSE stream success (target: > 99.6%)
# - Database connection pool (target: < 80%)
```

**Step 3: Execute Production Queries**

```bash
# Simulate user traffic
for i in {1..100}; do
  curl -X POST https://relay.production.com/api/v1/memory/query \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"query": "test query", "user_id": "user_'$i'"}'
done

# Monitor metrics in real-time
```

### Monitoring (50 minutes - Active Window)

**Metrics to Watch:**

| Metric | Target | Alert | Action |
|--------|--------|-------|--------|
| TTFV p95 | < 1.5s | > 1500ms | AUTO-ROLLBACK |
| RLS errors | 0 | > 0 in 5m | AUTO-ROLLBACK |
| SSE success | > 99.6% | < 99.5% | AUTO-ROLLBACK |
| ANN latency p95 | < 200ms | > 250ms | WARNING → investigate |
| DB pool | < 80% | > 85% | WARNING → scale if needed |
| Cross-tenant attempts | 0 | > 0 | AUTO-ROLLBACK (security) |

**Real-Time Validation:**

```bash
# Every 5 minutes during 1-hour window:
1. Check TTFV p95 < 1500ms
2. Check RLS policy errors = 0
3. Check SSE completion > 99.6%
4. Check no cross-tenant access attempts
5. Check connection pool < 80%
```

**Auto-Rollback Triggers** (Immediate):

```
IF TTFV p95 > 1500ms
  → Execute TASK_A_ROLLBACK_PROCEDURE.md
  → Revert to R0.5
  → Alert on-call engineering

IF RLS policy errors > 0
  → Execute TASK_A_ROLLBACK_PROCEDURE.md
  → Investigate policy violation
  → Alert security team

IF SSE success < 99.6%
  → Execute TASK_A_ROLLBACK_PROCEDURE.md
  → Investigate streaming issue
  → Alert ops team

IF Cross-tenant access attempts > 0
  → CRITICAL: Execute immediate rollback
  → Alert security team
  → Investigate breach
```

### Decision Gate (End of Hour)

**After 1 hour of canary monitoring:**

**✅ PASS Criteria** (All must be true):
- [ ] TTFV p95 < 1500ms (maintained R0.5 baseline)
- [ ] RLS policy errors = 0
- [ ] SSE success >= 99.6%
- [ ] No cross-tenant access attempts
- [ ] Connection pool < 80%
- [ ] No auto-rollback triggered

**❌ FAIL Criteria** (If any triggered):
- [ ] Auto-rollback was triggered
- [ ] Metrics breached thresholds
- [ ] User errors reported

**Decision**:
```
IF canary PASSED:
  → Proceed to 100% traffic (production promotion)
  → Teams continue TASK B+C in parallel
  → Deploy TASK B+C when ready (no additional canary)

IF canary FAILED:
  → Automatic rollback to R0.5 (already triggered)
  → Teams continue TASK B+C on isolated branches
  → Investigate failure before next canary attempt
  → Schedule retry after fix
```

---

## Phase 2: Parallel B+C Execution

### Execution Timeline

**During Canary (Day 1, Hour 2-25):**

| Time | TASK B | TASK C | Notes |
|------|--------|--------|-------|
| Hour 0 | Kick off | Kick off | While canary runs |
| Hour 1 | Canary monitoring | Canary monitoring | Active window |
| Hour 2-6 | Implement functions | GPU provisioning | First half-day |
| Hour 24-30 | Tests passing | Service working | After canary decision |
| Day 2-3 | Write path integration | Performance tuning | Full day execution |
| Day 4 | Code review | Code review | Final day checkpoint |
| Day 5 | Deliver security-approved | Deliver perf-approved | Ready to merge |

### TASK B Execution (Parallel)

**Start**: Day 1, Hour 2 (immediately after canary starts)
**Timeline**: 3-4 days
**End**: Day 4-5 (deliver with `security-approved`)

**Day 1: Core Functions**
- Implement `seal()`, `open_sealed()`, `hmac_user()`
- Basic unit tests framework
- Checkpoint: All 3 functions working

**Day 2: Full Test Suite**
- 20+ unit tests
- AAD binding verification (CRITICAL)
- Throughput measurement
- Checkpoint: All tests passing, >= 5k ops/sec

**Day 3: Integration**
- Write path encryption
- End-to-end testing
- Checkpoint: Integration complete

**Day 4: Review & Approval**
- Code review
- Security team sign-off
- `security-approved` label applied
- Checkpoint: Ready to merge

### TASK C Execution (Parallel)

**Start**: Day 1, Hour 2 (immediately after canary starts)
**Timeline**: 2-3 days
**End**: Day 3-4 (deliver with `perf-approved`)

**Day 0-1: GPU Setup**
- Provision L40 or A100
- Verify CUDA available
- Download cross-encoder model
- Checkpoint: GPU ready

**Day 1-2: Service Implementation**
- Implement `rerank()`, `get_cross_encoder()`, `maybe_rerank()`
- Unit tests framework
- Initial latency measurement
- Checkpoint: Service working

**Day 2-3: Performance Tuning**
- Load test (100 queries)
- Verify p95 < 150ms
- Metrics collection
- Checkpoint: p95 validated

**Day 3: Review & Approval**
- Code review
- ML Ops team sign-off
- `perf-approved` label applied
- Checkpoint: Ready to merge

### Coordination Points

**Daily Standup (3 PM UTC)**:
- TASK B: Report seal/open/hmac_user checkpoint
- TASK C: Report GPU/model/latency checkpoint
- Canary: Report metrics status
- Escalate blockers

**Merge Gate (Day 5)**:
- TASK B: `security-approved` label required
- TASK C: `perf-approved` label required
- Both must merge before TASK D starts

**Decision Point (End of Canary)**:
- If canary PASSED: Teams can merge immediately
- If canary FAILED: Teams continue on isolated branches, retry canary after fix

---

## Phase 3: Integration (Day 6+)

### After Canary Passes + TASK B+C Deliver

**Day 6: TASK D Starts**
- Integrate `seal()`/`open_sealed()` functions
- Integrate `rerank()` service
- Memory query endpoint with RLS + encryption + reranking
- Timeline: 2-3 days

**Day 8: TASK E Non-Regression**
- Full regression test suite
- Performance baseline validation
- Cross-tenant isolation regression tests
- Timeline: 1-2 days

**Day 10: TASK F Full Rollout**
- Canary promotion from 5% → 50% → 100%
- 24-hour monitoring window per stage
- Production confirmed stable
- Timeline: 1-2 hours per stage

---

## Success Criteria

### Canary (Hour 1)

✅ **PASS**:
- TTFV p95 < 1500ms
- RLS errors = 0
- SSE success >= 99.6%
- No security incidents

### TASK B (Day 5)

✅ **PASS**:
- AAD binding test PASSING
- All 20+ tests PASSING
- Throughput >= 5k ops/sec
- `security-approved` label
- Ready to merge

### TASK C (Day 4)

✅ **PASS**:
- GPU available
- p95 latency < 150ms (100 query test)
- All 40+ tests PASSING
- `perf-approved` label
- Ready to merge

### TASK D Integration (Day 8)

✅ **PASS**:
- Memory query endpoint working
- RLS + encryption + reranking integrated
- All tests passing
- Performance maintained

### TASK E Non-Regression (Day 9)

✅ **PASS**:
- R0.5 baseline metrics maintained
- No performance regression
- Cross-tenant isolation verified
- Ready for 100% rollout

---

## Rollback Plan

### Auto-Rollback (Immediate)

**Triggered if any guardrail breached:**

```bash
# Execute rollback script
bash TASK_A_ROLLBACK_PROCEDURE.md

# Steps:
1. Route traffic back to R0.5 (99%)
2. Downgrade memory_chunks schema
3. Remove RLS policies
4. Verify metrics return to baseline
5. Alert engineering team
```

**Time to Rollback**: < 5 minutes
**Data Loss**: None (RLS only, no data changed)

### Investigation & Retry

1. **Understand Failure**
   - Review canary logs
   - Check specific error metrics
   - Determine root cause

2. **Fix Issue**
   - Address RLS, streaming, or performance issue
   - Deploy fix to production app

3. **Retry Canary**
   - Wait 24 hours after rollback
   - Run new canary with fix
   - Verify metrics stable

---

## Final Handoff

### For Canary Team (DevOps/SRE)

1. Monitor real-time dashboards
2. Watch for auto-rollback triggers
3. Execute rollback if needed
4. Report decision (PASS/FAIL)

### For TASK B Team (Security)

1. Start immediately (Day 1, Hour 2)
2. Execute Day 1-4 timeline
3. Merge with `security-approved` label (Day 5)
4. Prepare for TASK D integration (Day 6+)

### For TASK C Team (ML Ops)

1. Start immediately (Day 1, Hour 2)
2. Execute Day 0-3 timeline
3. Merge with `perf-approved` label (Day 3-4)
4. Prepare for TASK D integration (Day 6+)

---

## Go/No-Go Checklist

### Pre-Canary (Ready to Execute)

- [x] TASK A deployed to production
- [x] RLS verified with app_user role
- [x] Leak test PASSED
- [x] Monitoring active
- [x] Auto-rollback configured
- [x] TASK B team prepared
- [x] TASK C team prepared

### During Canary (Monitoring)

- [ ] TTFV p95 < 1500ms
- [ ] RLS errors = 0
- [ ] SSE success >= 99.6%
- [ ] No security incidents
- [ ] No auto-rollback triggered

### Post-Canary Decision

**IF PASS**: Proceed to TASK D integration
**IF FAIL**: Rollback + investigate + retry

---

## Timeline Summary

```
Day 1:
  Hour 0: Canary deployment starts (5% traffic)
  Hour 0-1: TASK B + C teams kick off
  Hour 1: Canary active monitoring window
  Hour 1+: Teams work on TASK B + C (background)

Days 2-3:
  TASK B: Core functions + full tests
  TASK C: GPU + service + performance baseline

Days 4-5:
  TASK B: Write path integration + code review
  TASK C: Performance tuning + code review
  Both teams: Obtain approval labels

Day 5-6:
  Both teams merge with approval labels
  TASK D starts integration

Days 6-8:
  TASK D: API endpoints implementation
  TASK E: Non-regression testing

Days 8-10:
  TASK F: Canary promotion (5% → 50% → 100%)
  Final monitoring window

Total Duration: 10 days
Production Stability: 24-hour window post-deployment
```

---

## What to Execute Now

✅ **Start Immediately**:

1. **Canary Deployment Team**
   - Set up monitoring dashboards
   - Route 5% traffic to R1 (TASK A)
   - Begin 1-hour active monitoring window
   - Watch for auto-rollback triggers

2. **TASK B Crypto Team**
   - Read TASK_B_ENCRYPTION_SPECIFICATION.md
   - Set up development environment
   - Begin Day 1: Core functions implementation
   - Checkpoint: seal/open_sealed/hmac_user working

3. **TASK C Reranker Team**
   - Read TASK_C_RERANKER_SPECIFICATION.md
   - Provision GPU immediately
   - Begin Day 0-1: GPU setup + model download
   - Checkpoint: nvidia-smi + torch.cuda.is_available()

---

## Status: 🟢 GO FOR FINAL PHASE EXECUTION

**All systems ready for parallel execution.**

**Canary deployed, teams authorized, monitoring active.**

**Next: Execute canary decision + complete TASK B+C delivery.**

---

**Generated**: 2025-10-19 12:00 UTC
**Status**: FINAL PHASE EXECUTION GUIDE - READY FOR DEPLOYMENT
