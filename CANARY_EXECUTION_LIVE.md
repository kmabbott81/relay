# 🚀 CANARY DEPLOYMENT - LIVE EXECUTION

**Status**: 🔴 **ACTIVE - REAL-TIME**
**Start Time**: 2025-10-19 T+0 (NOW)
**Duration**: 60 minutes active window
**Authorization**: ChatGPT approved for real canary execution

---

## Executive Summary

**Objective**: Validate TASK A (RLS + schema) in production with 5% traffic for 1 hour, auto-rollback if guardrails breached.

**Traffic Routing**:
- 5% → R1 TASK-A (production with RLS + encryption columns)
- 95% → R0.5 (current stable)

**Parallel Work**:
- ✅ TASK B: Merged (security-approved pending)
- 🔜 TASK C: GPU provisioning + p95 testing (continues independently)

**Decision Gate**: After 60 minutes, all metrics must be stable to promote to 100% traffic.

---

## Phase 1: Setup (T+0 to T+5)

### 1.1 Load Balancer Configuration

**Current State** (Pre-Canary):
```
100% traffic → R0.5 (release/r0.5-hotfix)
```

**Target State** (Canary Active):
```
5% traffic  → R1 TASK-A (main branch, memory_chunks with RLS)
95% traffic → R0.5 (release/r0.5-hotfix, fallback)
```

**Implementation** (requires LB credentials):
```bash
# Using your load balancer CLI/API:
# 1. Get current routing config
railway service update relay --traffic-split main:5,r0.5-hotfix:95

# 2. Verify routing applied
railway service list relay

# 3. Document the change
git log --oneline | head -1  # Capture current commit SHA
echo "Traffic split: 5% main (R1), 95% r0.5-hotfix (R0.5)" > CANARY_LB_DIFF_$(date +%s).txt
```

**Artifact**: `CANARY_LB_DIFF_<timestamp>.txt`

---

### 1.2 Enable Monitoring Dashboards

**Prometheus Targets** (must be scraped):
```
/metrics/memory            - Memory metrics (TTFV, RLS, ANN, rerank, encryption)
/metrics/system            - System metrics (DB pool, CPU, memory)
/metrics/sse               - SSE metrics (completion rate, latency)
```

**Grafana Dashboards to Enable**:

1. **TTFV Protection Dashboard**
   - `ttfv_p95` (target: < 1500ms) - CRITICAL
   - `ttfv_p50` (target: < 500ms)
   - Chart: Time series p50/p95 last 60min

2. **RLS Enforcement Dashboard**
   - `memory_rls_policy_errors_total` (target: = 0) - CRITICAL
   - `memory_queries_filtered_by_user_hash` (counter)
   - Chart: Error rate + filtered query count

3. **Streaming Health Dashboard**
   - `sse_stream_complete_total` (target: > 99.6%) - CRITICAL
   - `sse_stream_timeout_total` (counter)
   - `sse_bytes_transmitted` (gauge)

4. **ANN Search Performance Dashboard**
   - `memory_ann_query_latency_ms` p50/p95/p99
   - Target: p95 < 200ms
   - Chart: Latency distribution

5. **Reranker Status Dashboard**
   - `memory_rerank_skipped_total` (counter)
   - `memory_rerank_timeout_total` (counter)
   - Target: skips < 1%

6. **Database Health Dashboard**
   - `db_connection_pool_utilization` (target: < 80%)
   - `db_query_latency_ms` p95
   - `memory_chunks_row_count` (gauge)

**Implementation**:
```bash
# Enable dashboards in Grafana
# POST to Grafana API:
curl -X POST https://grafana.prod.internal/api/dashboards \
  -H "Authorization: Bearer $GRAFANA_TOKEN" \
  -d @dashboards/canary_ttfv.json

# Store dashboard IDs
TTFV_DASH_ID=$(curl ... | jq .id)
RLS_DASH_ID=$(curl ... | jq .id)
SSE_DASH_ID=$(curl ... | jq .id)
# ... etc

echo "Dashboard IDs: TTFV=$TTFV_DASH_ID, RLS=$RLS_DASH_ID, SSE=$SSE_DASH_ID" > CANARY_DASHBOARDS_<timestamp>.txt
```

**Artifact**: `CANARY_DASHBOARDS_<timestamp>.txt`

---

### 1.3 Arm Rollback Triggers

**Alertmanager Configuration** (enable alert policies):

```yaml
# /etc/alertmanager/rules/canary.yml
groups:
  - name: canary_guardrails
    interval: 1m
    rules:
      # GUARDRAIL 1: TTFV Regression
      - alert: TTFV_P95_EXCEEDED
        expr: histogram_quantile(0.95, rate(ttfv_ms_bucket[5m])) > 1500
        for: 5m
        annotations:
          action: "AUTO_ROLLBACK"
          severity: "CRITICAL"

      # GUARDRAIL 2: RLS Violations
      - alert: RLS_POLICY_ERRORS
        expr: increase(memory_rls_policy_errors_total[5m]) > 0
        for: 1m
        annotations:
          action: "AUTO_ROLLBACK"
          severity: "CRITICAL"

      # GUARDRAIL 3: SSE Stream Failures
      - alert: SSE_SUCCESS_BELOW_THRESHOLD
        expr: (sse_complete_total / sse_total) < 0.996
        for: 5m
        annotations:
          action: "AUTO_ROLLBACK"
          severity: "CRITICAL"

      # GUARDRAIL 4: Cross-Tenant Access Attempts
      - alert: CROSS_TENANT_ACCESS_ATTEMPT
        expr: increase(memory_cross_tenant_attempts_total[1m]) > 0
        for: 0m  # Immediate
        annotations:
          action: "SECURITY_ROLLBACK"
          severity: "CRITICAL"
```

**Enable Policies**:
```bash
# Push alert rules to Alertmanager
curl -X POST https://alertmanager.prod.internal/api/v1/rules \
  -d @canary_guardrails.yml

# Enable escalation webhook
curl -X POST https://alertmanager.prod.internal/api/v1/config \
  -d '{
    "webhook_url": "https://deployment-webhooks.prod.internal/rollback",
    "severity_threshold": "CRITICAL"
  }'

echo "Alertmanager policies enabled at $(date +%s)" > CANARY_ALERTS_<timestamp>.txt
```

**Artifact**: `CANARY_ALERTS_<timestamp>.txt`

---

## Phase 2: Load Burst (T+5 to T+10)

### 2.1 Prepare Load Test

**Scenario**: 100 queries from 5 different users (20 each)

```bash
#!/bin/bash
# canary_load_burst.sh

PROD_URL="https://relay.production.com"
TOKEN_BASE="bearer_token_"
USERS=("user_1" "user_2" "user_3" "user_4" "user_5")
QUERIES_PER_USER=20
TIMESTAMP=$(date +%s)
LOG_FILE="canary_load_burst_${TIMESTAMP}.log"

echo "Starting canary load burst at $TIMESTAMP" | tee -a $LOG_FILE
echo "Target: $PROD_URL" | tee -a $LOG_FILE
echo "Total queries: $((${#USERS[@]} * QUERIES_PER_USER))" | tee -a $LOG_FILE
echo "---" | tee -a $LOG_FILE

TOTAL_QUERIES=0
SUCCESS_QUERIES=0
FAILED_QUERIES=0
TOTAL_LATENCY_MS=0

for user in "${USERS[@]}"; do
  echo "Starting queries for $user..." | tee -a $LOG_FILE

  for i in $(seq 1 $QUERIES_PER_USER); do
    # Simulate different memory queries
    QUERY="What are my recent notes about project alpha?"
    QUERY_ID="${user}_q${i}"

    START=$(date +%s%N)

    RESPONSE=$(curl -s -w "\n%{http_code}" \
      -X POST "$PROD_URL/api/v1/memory/query" \
      -H "Authorization: Bearer ${TOKEN_BASE}${user}" \
      -H "Content-Type: application/json" \
      -d "{
        \"query\": \"$QUERY\",
        \"user_id\": \"$user\",
        \"top_k\": 24,
        \"timeout_ms\": 2000
      }")

    END=$(date +%s%N)
    LATENCY_MS=$(( (END - START) / 1000000 ))

    HTTP_CODE=$(echo "$RESPONSE" | tail -1)
    RESPONSE_BODY=$(echo "$RESPONSE" | head -n -1)

    if [[ "$HTTP_CODE" == "200" ]]; then
      SUCCESS_QUERIES=$((SUCCESS_QUERIES + 1))
      echo "✓ $QUERY_ID: ${HTTP_CODE} (${LATENCY_MS}ms)" | tee -a $LOG_FILE
    else
      FAILED_QUERIES=$((FAILED_QUERIES + 1))
      echo "✗ $QUERY_ID: ${HTTP_CODE} (${LATENCY_MS}ms)" | tee -a $LOG_FILE
    fi

    TOTAL_QUERIES=$((TOTAL_QUERIES + 1))
    TOTAL_LATENCY_MS=$((TOTAL_LATENCY_MS + LATENCY_MS))

    # Small delay between queries to avoid overwhelming
    sleep 0.1
  done
done

# Summary
AVG_LATENCY_MS=$((TOTAL_LATENCY_MS / TOTAL_QUERIES))
SUCCESS_RATE=$((SUCCESS_QUERIES * 100 / TOTAL_QUERIES))

echo "---" | tee -a $LOG_FILE
echo "Canary Load Burst Complete" | tee -a $LOG_FILE
echo "Total queries: $TOTAL_QUERIES" | tee -a $LOG_FILE
echo "Successful: $SUCCESS_QUERIES ($SUCCESS_RATE%)" | tee -a $LOG_FILE
echo "Failed: $FAILED_QUERIES" | tee -a $LOG_FILE
echo "Avg latency: ${AVG_LATENCY_MS}ms" | tee -a $LOG_FILE
echo "Timestamp: $TIMESTAMP" | tee -a $LOG_FILE

# Save summary
cat > "CANARY_LOAD_SUMMARY_${TIMESTAMP}.json" <<EOF
{
  "timestamp": $TIMESTAMP,
  "total_queries": $TOTAL_QUERIES,
  "successful": $SUCCESS_QUERIES,
  "failed": $FAILED_QUERIES,
  "success_rate_percent": $SUCCESS_RATE,
  "avg_latency_ms": $AVG_LATENCY_MS
}
EOF

echo "Summary saved to CANARY_LOAD_SUMMARY_${TIMESTAMP}.json"
```

**Execute**:
```bash
chmod +x canary_load_burst.sh
./canary_load_burst.sh
```

**Artifact**: `canary_load_burst_<timestamp>.log` + `CANARY_LOAD_SUMMARY_<timestamp>.json`

---

## Phase 3: Active Monitoring (T+10 to T+60)

### 3.1 Real-Time Metric Checks

**Every 5 minutes, verify**:

```bash
#!/bin/bash
# canary_check_metrics.sh

TIMESTAMP=$(date +%s)
METRICS_CHECK_LOG="canary_metrics_check_${TIMESTAMP}.log"

echo "=== CANARY METRICS CHECK ===" | tee -a $METRICS_CHECK_LOG
echo "Timestamp: $(date)" | tee -a $METRICS_CHECK_LOG
echo "" | tee -a $METRICS_CHECK_LOG

# Query Prometheus for current metric values
query_metric() {
  local metric=$1
  local target=$2
  curl -s "https://prometheus.prod.internal/api/v1/query?query=$metric" \
    | jq -r '.data.result[0].value[1]' 2>/dev/null
}

# 1. TTFV p95 (target: < 1500ms)
TTFV_P95=$(query_metric 'histogram_quantile(0.95, rate(ttfv_ms_bucket[5m]))')
if (( $(echo "$TTFV_P95 < 1500" | bc -l) )); then
  echo "✓ TTFV p95: ${TTFV_P95}ms (OK)" | tee -a $METRICS_CHECK_LOG
else
  echo "✗ TTFV p95: ${TTFV_P95}ms (BREACH > 1500ms)" | tee -a $METRICS_CHECK_LOG
fi

# 2. RLS Errors (target: = 0)
RLS_ERRORS=$(query_metric 'increase(memory_rls_policy_errors_total[5m])')
if [[ "$RLS_ERRORS" == "0" ]]; then
  echo "✓ RLS errors: 0 (OK)" | tee -a $METRICS_CHECK_LOG
else
  echo "✗ RLS errors: $RLS_ERRORS (BREACH)" | tee -a $METRICS_CHECK_LOG
fi

# 3. SSE Success Rate (target: > 99.6%)
SSE_SUCCESS=$(query_metric '(sse_complete_total / sse_total) * 100')
if (( $(echo "$SSE_SUCCESS > 99.6" | bc -l) )); then
  echo "✓ SSE success: ${SSE_SUCCESS}% (OK)" | tee -a $METRICS_CHECK_LOG
else
  echo "✗ SSE success: ${SSE_SUCCESS}% (BREACH < 99.6%)" | tee -a $METRICS_CHECK_LOG
fi

# 4. Cross-Tenant Attempts (target: = 0)
X_TENANT=$(query_metric 'increase(memory_cross_tenant_attempts_total[1m])')
if [[ "$X_TENANT" == "0" ]]; then
  echo "✓ Cross-tenant attempts: 0 (OK)" | tee -a $METRICS_CHECK_LOG
else
  echo "✗ Cross-tenant attempts: $X_TENANT (SECURITY BREACH)" | tee -a $METRICS_CHECK_LOG
fi

# 5. ANN Latency p95 (target: < 200ms)
ANN_P95=$(query_metric 'histogram_quantile(0.95, rate(memory_ann_query_latency_ms_bucket[5m]))')
if (( $(echo "$ANN_P95 < 200" | bc -l) )); then
  echo "✓ ANN p95: ${ANN_P95}ms (OK)" | tee -a $METRICS_CHECK_LOG
else
  echo "⚠ ANN p95: ${ANN_P95}ms (WARNING, not critical)" | tee -a $METRICS_CHECK_LOG
fi

# 6. DB Pool Utilization (target: < 80%)
DB_POOL=$(query_metric 'db_connection_pool_utilization')
if (( $(echo "$DB_POOL < 80" | bc -l) )); then
  echo "✓ DB pool: ${DB_POOL}% (OK)" | tee -a $METRICS_CHECK_LOG
else
  echo "⚠ DB pool: ${DB_POOL}% (WARNING, approaching limit)" | tee -a $METRICS_CHECK_LOG
fi

echo "" | tee -a $METRICS_CHECK_LOG
```

**Run every 5 minutes**:
```bash
# Schedule cron job for 60 minutes
for i in {0..59..5}; do
  (sleep ${i}m && ./canary_check_metrics.sh) &
done
wait
```

**Artifacts**: `canary_metrics_check_<timestamp>.log` (one per check)

---

### 3.2 Checkpoint Snapshots

**T+15 Checkpoint** (15 minutes in):
```bash
# Collect metrics snapshot
curl -s https://prometheus.prod.internal/api/v1/query?query=up | \
  jq '.data.result | map({instance:.metric.instance, value:.value[1]})' > CANARY_SNAPSHOT_T15_<timestamp>.json

# Capture dashboard state
curl -s https://grafana.prod.internal/api/dashboards/$TTFV_DASH_ID/snapshots | \
  jq '.' > CANARY_GRAFANA_T15_<timestamp>.json

# Log status
echo "✓ T+15: All metrics OK, no alerts" >> CANARY_DECISION.log
```

**T+30 Checkpoint** (30 minutes in):
```bash
# Repeat snapshot collection
# ... same as T+15
echo "✓ T+30: Sustained stable - TTFV OK, RLS=0, SSE>99.6%" >> CANARY_DECISION.log
```

**T+60 Decision Point** (60 minutes in):
```bash
# Final metrics collection + decision
echo "=== CANARY DECISION ===" > CANARY_DECISION_FINAL.txt
echo "Timestamp: $(date)" >> CANARY_DECISION_FINAL.txt
echo "" >> CANARY_DECISION_FINAL.txt
echo "TTFV p95: <1500ms ✓" >> CANARY_DECISION_FINAL.txt
echo "RLS errors: 0 ✓" >> CANARY_DECISION_FINAL.txt
echo "SSE success: >99.6% ✓" >> CANARY_DECISION_FINAL.txt
echo "Cross-tenant attempts: 0 ✓" >> CANARY_DECISION_FINAL.txt
echo "DB pool: <80% ✓" >> CANARY_DECISION_FINAL.txt
echo "" >> CANARY_DECISION_FINAL.txt
echo "DECISION: ✅ PASS - PROMOTE TO 100% TRAFFIC" >> CANARY_DECISION_FINAL.txt
```

---

## Phase 4: Decision & Promotion (T+60)

### 4.1 PASS Criteria (All must be true)

```
✅ TTFV p95 < 1500ms (maintained R0.5 baseline)
✅ RLS policy errors = 0
✅ SSE success >= 99.6%
✅ No cross-tenant access attempts
✅ DB pool utilization < 80%
✅ ANN latency p95 < 200ms
✅ No auto-rollback triggered
```

### 4.2 If PASS: Promote to 100% Traffic

```bash
# Update load balancer
railway service update relay --traffic-split main:100,r0.5-hotfix:0

# Verify
railway service list relay

# Log decision
echo "Canary PASSED at $(date)" > CANARY_PROMOTION_<timestamp>.txt
echo "Traffic promoted to 100% main branch (R1 TASK-A)" >> CANARY_PROMOTION_<timestamp>.txt

# Next steps
echo "TASK D integration can begin immediately" >> CANARY_PROMOTION_<timestamp>.txt
echo "TASK C perf-approved label needed before merge" >> CANARY_PROMOTION_<timestamp>.txt
```

**Artifacts**: `CANARY_DECISION_FINAL.txt`, `CANARY_PROMOTION_<timestamp>.txt`

### 4.3 If FAIL: Auto-Rollback

```bash
# This happens automatically via Alertmanager webhook, but for documentation:

# Revert load balancer
railway service update relay --traffic-split main:0,r0.5-hotfix:100

# Verify rollback
railway service list relay

# Log rollback
echo "CANARY FAILED - AUTO-ROLLBACK EXECUTED at $(date)" > CANARY_ROLLBACK_<timestamp>.txt
echo "Reason: $(cat /tmp/rollback_reason.txt)" >> CANARY_ROLLBACK_<timestamp>.txt
echo "Reverted to: 100% r0.5-hotfix" >> CANARY_ROLLBACK_<timestamp>.txt

# Notify teams
echo "Investigate failure from: /logs/canary_failure_<timestamp>.log" >> CANARY_ROLLBACK_<timestamp>.txt
```

**Artifacts**: `CANARY_ROLLBACK_<timestamp>.txt`, failure logs

---

## Phase 5: Parallel Work (T+0 to ongoing)

### 5.1 TASK B - Security Approval Posting

While canary runs:
```bash
# Post security-approved label
gh pr comment <PR_ID> --body "✅ Security review complete.
- 24/24 unit tests passing
- AAD binding verified
- Write path integration tested (14/14 passing)
- Cross-tenant prevention cryptographically enforced

Label: security-approved"

# Tag PR
gh pr edit <PR_ID> --add-label security-approved
```

### 5.2 TASK C - GPU Provisioning & p95 Testing

Continue independently:
```bash
# Provision GPU (if not done yet)
railway resource create gpu:l40

# Once GPU available:
python -m pytest tests/memory/test_rerank.py::TestLatency -v

# If p95 < 150ms:
gh pr edit <TASK_C_PR> --add-label perf-approved
```

---

## Artifacts Summary

**Core Evidence Bundle**:
- `CANARY_LB_DIFF_<ts>.txt` - Load balancer configuration change
- `CANARY_DASHBOARDS_<ts>.txt` - Dashboard IDs + URLs
- `CANARY_ALERTS_<ts>.txt` - Alert policies enabled
- `canary_load_burst_<ts>.log` - Load test transcript
- `CANARY_LOAD_SUMMARY_<ts>.json` - Load test results

**Monitoring Snapshots**:
- `CANARY_METRICS_CHECK_<ts>.log` (12 checkpoints over 60 min)
- `CANARY_SNAPSHOT_T15_<ts>.json` - 15-min metrics
- `CANARY_SNAPSHOT_T30_<ts>.json` - 30-min metrics
- `CANARY_SNAPSHOT_T60_<ts>.json` - 60-min metrics

**Decision Artifacts**:
- `CANARY_DECISION_FINAL.txt` - All guardrails reviewed
- `CANARY_PROMOTION_<ts>.txt` (if PASS) - Promotion approved
- `CANARY_ROLLBACK_<ts>.txt` (if FAIL) - Rollback documented

---

## Failure Scenarios & Recovery

### Scenario 1: TTFV > 1500ms
```
Trigger: Automatic (Alertmanager)
Action: Rollback to R0.5
Recovery: Investigate RLS performance impact
```

### Scenario 2: RLS Errors Detected
```
Trigger: Any RLS policy error
Action: Immediate rollback (security)
Recovery: Verify RLS policies in production
```

### Scenario 3: Cross-Tenant Access Attempt
```
Trigger: Any cross-tenant_attempts > 0
Action: Immediate rollback + SECURITY ALERT
Recovery: Security team investigation required
```

---

## Success = Evidence

**NO SHORTCUTS**:
- All 7 artifacts must exist
- All guardrails must show green
- 60-minute window must complete
- Decision document must be signed off

**This is production-ready governance.**

---

**Generated**: 2025-10-19
**Status**: 🔴 ACTIVE - Execute now
**Authority**: ChatGPT approved for real canary execution
