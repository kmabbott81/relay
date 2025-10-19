# 📋 CANARY EXECUTION - DEVOPS/SRE COORDINATION

**Status**: Ready for infrastructure handoff
**Timeline**: ~75 minutes total (5 min setup + 60 min active + 10 min cleanup)
**Authority**: ChatGPT-approved real canary execution

---

## Pre-Canary Checklist (DevOps/SRE)

### Required Infrastructure Access

**1. Load Balancer**
- [ ] LB provider credentials (Railway, AWS, GCP, etc.)
- [ ] Authority to modify traffic split
- [ ] Ability to route 5% to `main` branch, 95% to `release/r0.5-hotfix`
- [ ] **Credential**: Store as `LB_API_KEY` or `LB_CREDENTIALS`

**2. Prometheus**
- [ ] Prometheus endpoint: `https://prometheus.prod.internal/api/v1`
- [ ] API token for authenticated queries
- [ ] Memory metrics available (ttfv_ms, sse_complete, rls_errors, etc.)
- [ ] **Credential**: Store as `PROMETHEUS_TOKEN`

**3. Grafana**
- [ ] Grafana instance: `https://grafana.prod.internal`
- [ ] API token for dashboard creation
- [ ] Authority to create/edit dashboards
- [ ] Authority to enable alert rules
- [ ] **Credential**: Store as `GRAFANA_TOKEN`

**4. Alertmanager**
- [ ] Alertmanager endpoint: `https://alertmanager.prod.internal`
- [ ] Authority to push alert policies
- [ ] Webhook URL configured for escalation (e.g., Slack, PagerDuty)
- [ ] **Credential**: Store as `ALERTMANAGER_TOKEN`

**5. Production API**
- [ ] Production API endpoint: `https://relay.production.com`
- [ ] 5 test user Bearer tokens (different users for load test)
- [ ] `/api/v1/memory/query` endpoint available
- [ ] **Credential**: Store as `API_TOKEN_USER_1` through `API_TOKEN_USER_5`

### Credential Staging

```bash
# Create .env file with all credentials
cat > .env.canary << 'EOF'
# Load Balancer
LB_PROVIDER=railway
LB_API_KEY=your_lb_token_here
LB_SERVICE=relay

# Prometheus
PROMETHEUS_URL=https://prometheus.prod.internal/api/v1
PROMETHEUS_TOKEN=your_prometheus_token_here

# Grafana
GRAFANA_URL=https://grafana.prod.internal
GRAFANA_TOKEN=your_grafana_token_here

# Alertmanager
ALERTMANAGER_URL=https://alertmanager.prod.internal
ALERTMANAGER_TOKEN=your_alertmanager_token_here
ALERT_WEBHOOK_URL=https://your-webhook-endpoint.com/alerts

# Production API
PROD_API_URL=https://relay.production.com
API_TOKEN_USER_1=bearer_token_user_1
API_TOKEN_USER_2=bearer_token_user_2
API_TOKEN_USER_3=bearer_token_user_3
API_TOKEN_USER_4=bearer_token_user_4
API_TOKEN_USER_5=bearer_token_user_5

# Canary Configuration
CANARY_TRAFFIC_NEW=5
CANARY_TRAFFIC_OLD=95
CANARY_DURATION_MINUTES=60
CANARY_ROLLBACK_THRESHOLD_TTFV_MS=1500
CANARY_ROLLBACK_THRESHOLD_SSE_PERCENT=99.6

EOF

# Verify all credentials present
grep -c "=" .env.canary  # Should show 14+ variables

# DO NOT COMMIT THIS FILE
echo ".env.canary" >> .gitignore
```

---

## Canary Execution Steps

### Step 1: Source Credentials (T+0 to T+1)

```bash
# Load all credentials
source .env.canary

# Verify all present
[[ -z "$LB_API_KEY" ]] && echo "ERROR: LB_API_KEY missing" && exit 1
[[ -z "$PROMETHEUS_TOKEN" ]] && echo "ERROR: PROMETHEUS_TOKEN missing" && exit 1
[[ -z "$GRAFANA_TOKEN" ]] && echo "ERROR: GRAFANA_TOKEN missing" && exit 1
[[ -z "$ALERTMANAGER_TOKEN" ]] && echo "ERROR: ALERTMANAGER_TOKEN missing" && exit 1
[[ -z "$API_TOKEN_USER_1" ]] && echo "ERROR: API tokens missing" && exit 1

echo "OK: All credentials sourced"
```

### Step 2: Execute Canary (Follow CANARY_EXECUTION_LIVE.md)

**Key sections**:
1. **Phase 1 (T+0-5)**: Traffic routing + monitoring setup
2. **Phase 2 (T+5-10)**: Load burst (100 queries)
3. **Phase 3 (T+10-60)**: Active monitoring
4. **Phase 4 (T+60)**: Decision gate

**See**: `/CANARY_EXECUTION_LIVE.md` for detailed instructions

### Step 3: Monitoring During Canary

**Real-time dashboards** (enable in Grafana):
- TTFV Protection (p95 < 1500ms)
- RLS Enforcement (errors = 0)
- SSE Health (success > 99.6%)
- ANN Performance (p95 < 200ms)
- Reranker Status (skips < 1%)
- Database Health (pool < 80%)

**Auto-escalation** (Alertmanager):
- TTFV breach → immediate rollback
- RLS errors → immediate rollback
- SSE failures → immediate rollback
- Cross-tenant attempts → security rollback

### Step 4: Evidence Collection

**Artifacts to capture at T+15, T+30, T+60**:

```
CANARY_LB_DIFF_<timestamp>.txt
├─ Load balancer configuration before/after
└─ Timestamp of change applied

CANARY_DASHBOARDS_<timestamp>.txt
├─ Grafana dashboard IDs
└─ URLs to each dashboard

CANARY_ALERTS_<timestamp>.txt
├─ Alertmanager policy IDs
└─ Alert rule configuration

canary_load_burst_<timestamp>.log
├─ Load test transcript
├─ 100 queries from 5 users
└─ Success rate + average latency

CANARY_SNAPSHOT_T15_<timestamp>.json
├─ Prometheus metrics at T+15
└─ TTFV, RLS, SSE, ANN values

CANARY_SNAPSHOT_T30_<timestamp>.json
├─ Prometheus metrics at T+30
└─ Sustained metric values

CANARY_SNAPSHOT_T60_<timestamp>.json
├─ Prometheus metrics at T+60
├─ Final decision data
└─ All guardrails review

CANARY_DECISION_FINAL.txt
├─ All guardrails status (PASS/FAIL)
├─ Metric summary table
├─ Decision: PROMOTE or ROLLBACK
└─ Authorization signature
```

---

## Decision Criteria

### PASS Conditions (All must be true)
```
✓ TTFV p95 < 1500ms
✓ RLS errors = 0
✓ SSE success >= 99.6%
✓ Cross-tenant attempts = 0
✓ ANN latency p95 < 200ms
✓ DB pool utilization < 80%
✓ No auto-rollback triggered during 60 minutes
```

### FAIL Conditions (Any trigger auto-rollback)
```
✗ TTFV p95 > 1500ms (for 5+ minutes)
✗ RLS policy errors > 0 (any)
✗ SSE success < 99.6% (for 5+ minutes)
✗ Cross-tenant attempts > 0 (SECURITY)
✗ Unrecoverable error in canary service
```

---

## Promotion Decision

### If PASS
```bash
# Traffic promotion to 100%
railway service update relay --traffic-split main:100,r0.5-hotfix:0

# Log promotion
echo "CANARY PASSED - PROMOTED TO 100% TRAFFIC" > CANARY_PROMOTION_FINAL.txt

# Next steps
echo "TASK D integration can begin immediately"
echo "TASK C must have perf-approved label before merge"
```

### If FAIL
```bash
# Auto-rollback (triggered by Alertmanager)
railway service update relay --traffic-split main:0,r0.5-hotfix:100

# Log rollback
echo "CANARY FAILED - AUTO-ROLLBACK EXECUTED" > CANARY_ROLLBACK_FINAL.txt

# Investigate
echo "Reason: $(cat /tmp/rollback_reason.txt)"

# Next: Investigate, fix, retry after 24 hours
```

---

## Timeline & Handoff

| Time | Phase | Owner | Status |
|------|-------|-------|--------|
| T+0 | Credential verification | DevOps | Blocking |
| T+0-5 | Setup (LB, monitoring, alerts) | DevOps | Phase 1 |
| T+5-10 | Load burst execution | DevOps | Phase 2 |
| T+15 | Snapshot + review | DevOps/Claude | Checkpoint |
| T+30 | Snapshot + review | DevOps/Claude | Checkpoint |
| T+10-60 | Active monitoring | DevOps | Ongoing |
| T+60 | Decision gate | DevOps/Engineering | Gate |
| T+65 | Promotion/Rollback | DevOps | Final |

---

## Communication Channels

**During canary** (real-time):
- **Slack** #canary-live (metrics updates every 5 min)
- **PagerDuty** escalation (if any guardrail breached)

**Decision point** (T+60):
- **Email**: deployment-lead@company.com (pass/fail decision)
- **Slack** #engineering (promotion/rollback announcement)

---

## Rollback Procedure (If Needed)

```bash
# 1. Automatic rollback executed by Alertmanager
# 2. Verify rollback successful
railway service list relay  # Should show 100% r0.5-hotfix

# 3. Capture rollback artifacts
git add CANARY_ROLLBACK_FINAL.txt /logs/canary_failure_*.log

# 4. Investigation begins (separate ticket)
# 5. Schedule retry after fix + 24-hour cooldown

# NOTE: TASK B remains merged (no revert)
# NOTE: TASK C continues GPU testing (independent)
```

---

## Next Steps After Canary

**If PASS (100% promoted)**:
1. Celebrate: R1 TASK-A now in full production
2. TASK D integration begins: Uses RLS + encryption + reranker
3. TASK C must deliver perf-approved before TASK D merge
4. Timeline: Days 6-10 for full R1 Phase 1 completion

**If FAIL (auto-rollback)**:
1. Investigation: What guardrail triggered?
2. Root cause: TASK A performance? RLS issue? Streaming?
3. Fix: Resolve the blocker
4. Retry: After 24-hour cooldown + fix validation

---

## Success = Evidence

**No exceptions**:
- ✓ All 7 artifacts present
- ✓ All guardrails documented
- ✓ Decision signed off
- ✓ Evidence bundle committed to repo

**This is production-ready governance.**

---

**Generated**: 2025-10-19
**Status**: Ready for DevOps/SRE handoff
**Authority**: ChatGPT-approved execution
**Expected**: 75 minutes total, p95 < 150ms validation, promotion or documented rollback
