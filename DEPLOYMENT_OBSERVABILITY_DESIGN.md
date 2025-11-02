# Deployment Observability Design
## Relay AI - Automated Deployment Pipeline Monitoring

**Status:** Design Ready
**Target Implementation:** Immediate (leverage existing metrics infrastructure)
**Prometheus Endpoints:**
- Grafana: relay-grafana-production.up.railway.app
- Prometheus: relay-prometheus-production.up.railway.app
- Pushgateway: (configure for CI/CD)

---

## Executive Summary

Your deployment pipeline already has excellent metrics collection via `DeploymentMetricsCollector`. This design adds:

1. **5 Critical Metrics** for complete visibility
2. **Implementation patterns** for existing GitHub Actions workflows
3. **Grafana dashboards** with drill-down capabilities
4. **Alert rules** tuned to minimize false positives
5. **Cost tracking** for deployment infrastructure

All recommendations leverage your existing Prometheus/Grafana on Railway and can be implemented in **< 2 hours**.

---

## Core Metrics Framework

### The 5 Golden Deployment Metrics

```
1. DEPLOYMENT SUCCESS RATE (%) - "Are deployments working?"
2. TIME TO DEPLOY (TTD) - "How fast are we deploying?"
3. API HEALTH POST-DEPLOY (%) - "Is the new version healthy?"
4. DATABASE MIGRATION SUCCESS (%) - "Did schema changes apply?"
5. SMOKE TEST PASS RATE (%) - "Does the app work end-to-end?"

SLA Target: 99% success rate, <10min TTD, 100% health after 5min
```

---

## Metric Definitions & Implementation

### 1. Deployment Success Rate (Overall)

**What it measures:** % of deployments that complete without rollback

**Why it matters:**
- Reliability of CI/CD process
- Velocity signal (failed deployments block productivity)
- Error budget consumption

**Implementation:**

```yaml
# In your GitHub Actions workflow, add these lines after deploy completes:

    - name: Record deployment metrics
      if: always()
      env:
        DEPLOYMENT_ID: ${{ github.run_id }}
        ENVIRONMENT: production
        STATUS: ${{ job.status }}
      run: |
        python3 -c "
        from relay_ai.platform.observability.deployment_metrics import get_deployment_metrics
        import os

        collector = get_deployment_metrics()

        # Record completion with status
        collector.record_deployment_complete(
            environment=os.getenv('ENVIRONMENT'),
            deployment_id=os.getenv('DEPLOYMENT_ID'),
            total_duration_seconds=int('${{ job.duration_seconds }}' or 600),
            success=(os.getenv('STATUS') == 'success')
        )
        "
```

**Prometheus Query:**
```promql
# Success rate (last hour)
sum(increase(deployment_total{status="success"}[1h]))
/
sum(increase(deployment_total[1h]))

# Trend over time
rate(deployment_total{status="success"}[5m])
/
rate(deployment_total[5m])
```

**SLO Alert:**
```yaml
- alert: DeploymentSuccessRateLow
  expr: |
    (sum(rate(deployment_total{status="success"}[1h])) by (environment)
    / sum(rate(deployment_total[1h])) by (environment)) < 0.95
  for: 30m
  labels:
    severity: high
  annotations:
    summary: "Deployment success rate < 95% (target: 99%)"
```

---

### 2. Time to Deploy (TTD)

**What it measures:** Minutes from git push to production stabilization

**Why it matters:**
- Velocity metric (how fast can we ship fixes?)
- Resource utilization (slow deploys = blocked engineers)
- Deployment pipeline health

**Target SLO:** p95 < 10 minutes

**Implementation:**

```bash
#!/bin/bash
# Add this to your deploy.yml workflow

DEPLOYMENT_START=$(date +%s%N)

# ... your deployment steps ...

DEPLOYMENT_END=$(date +%s%N)
TTD_SECONDS=$(( (DEPLOYMENT_END - DEPLOYMENT_START) / 1000000000 ))

python3 -c "
from relay_ai.platform.observability.deployment_metrics import get_deployment_metrics
collector = get_deployment_metrics()
collector.time_to_deploy_seconds.labels(environment='production').observe($TTD_SECONDS)
collector._push_metrics()
"
```

**Prometheus Query:**
```promql
# P95 TTD (last 24 hours)
histogram_quantile(0.95, rate(time_to_deploy_seconds_bucket{environment="production"}[24h]))

# Track over time
histogram_quantile(0.95, rate(time_to_deploy_seconds_bucket{environment="production"}[1h]))

# Individual stage breakdown
deployment_stage_duration_seconds{environment="production", service="api"}
```

**Grafana Panel:**
```json
{
  "title": "Time to Deploy (TTD)",
  "targets": [
    {
      "expr": "histogram_quantile(0.95, rate(time_to_deploy_seconds_bucket{environment=\"production\"}[1h]))"
    }
  ],
  "thresholds": [300, 600],  // 5min, 10min
  "alert": "when above 600"
}
```

---

### 3. API Health Post-Deployment

**What it measures:** % of health checks passing in first 5 minutes after deploy

**Why it matters:**
- Early signal for deployment issues
- Automatic rollback trigger
- User impact prevention

**Implementation:**

```python
# In your deployment workflow health check section

def check_api_health(api_url, deployment_id, max_attempts=30):
    from relay_ai.platform.observability.deployment_metrics import get_deployment_metrics
    import requests
    import time

    collector = get_deployment_metrics()
    health_checks_passed = 0
    health_checks_total = 0

    for attempt in range(max_attempts):
        start_ms = time.time() * 1000
        try:
            response = requests.get(f"{api_url}/health", timeout=5)
            latency_ms = time.time() * 1000 - start_ms

            if response.status_code == 200:
                health_checks_passed += 1
                collector.record_health_check(
                    environment="production",
                    deployment_id=deployment_id,
                    latency_ms=latency_ms,
                    status="healthy"
                )
            else:
                collector.record_health_check(
                    environment="production",
                    deployment_id=deployment_id,
                    latency_ms=latency_ms,
                    status="unhealthy"
                )
        except Exception as e:
            collector.record_health_check(
                environment="production",
                deployment_id=deployment_id,
                latency_ms=5000,
                status="unhealthy"
            )

        health_checks_total += 1
        if health_checks_passed == max_attempts:
            break
        time.sleep(5)

    health_rate = health_checks_passed / health_checks_total

    # Record post-deployment error rate for first 5 minutes
    collector.record_post_deployment_error_rate(
        environment="production",
        deployment_id=deployment_id,
        service="api",
        error_rate=1.0 - health_rate
    )

    return health_rate >= 0.95

check_api_health("https://relay-production-f2a6.up.railway.app", "${{ github.run_id }}")
```

**Prometheus Query:**
```promql
# API health success rate
(sum(increase(api_health_check_latency_ms_count{status="healthy"}[5m]))
/ sum(increase(api_health_check_latency_ms_count[5m]))) * 100

# Health check latency (p95)
histogram_quantile(0.95, rate(api_health_check_latency_ms_bucket[5m]))
```

**Alert:**
```yaml
- alert: PostDeploymentHealthChecksFailing
  expr: |
    (sum(increase(api_health_check_latency_ms_count{status="healthy"}[5m]))
    / sum(increase(api_health_check_latency_ms_count[5m]))) < 0.90
  for: 2m
  labels:
    severity: critical
  annotations:
    summary: "API health checks < 90% (trigger rollback)"
```

---

### 4. Database Migration Success Rate

**What it measures:** % of Alembic migrations that apply successfully

**Why it matters:**
- Schema correctness (data integrity)
- Deployment cannot proceed without successful migrations
- Rollback complexity (cannot downgrade during deploy)

**Implementation:**

```bash
# In your deploy.yml, wrap Alembic migration

echo "Recording migration start..."
MIGRATION_START=$(date +%s)

# Run migrations with output capture
if alembic upgrade head > migration.log 2>&1; then
    MIGRATION_END=$(date +%s)
    DURATION=$((MIGRATION_END - MIGRATION_START))

    # Count applied migrations
    MIGRATION_COUNT=$(grep -c "Running upgrade" migration.log || echo "1")

    python3 -c "
from relay_ai.platform.observability.deployment_metrics import get_deployment_metrics
collector = get_deployment_metrics()
collector.record_migration_complete(
    environment='production',
    deployment_id='${{ github.run_id }}',
    migration_name='alembic_head',
    duration_seconds=$DURATION,
    success=True,
    migration_count=$MIGRATION_COUNT
)
    "
else
    MIGRATION_END=$(date +%s)
    DURATION=$((MIGRATION_END - MIGRATION_START))

    python3 -c "
from relay_ai.platform.observability.deployment_metrics import get_deployment_metrics
collector = get_deployment_metrics()
collector.record_migration_complete(
    environment='production',
    deployment_id='${{ github.run_id }}',
    migration_name='alembic_head',
    duration_seconds=$DURATION,
    success=False
)
    "
    exit 1
fi
```

**Prometheus Query:**
```promql
# Migration success rate
sum(increase(migration_total{status="success"}[30d]))
/
sum(increase(migration_total[30d]))

# Migration duration
deployment_stage_duration_seconds{stage="migration"}
```

---

### 5. Smoke Test Pass Rate

**What it measures:** % of smoke tests passing post-deployment

**Why it matters:**
- Real end-to-end validation
- Earlier signal than production traffic
- Test coverage indicator

**Implementation:**

```bash
# In your ci_smoke_tests.sh, instrument each test

run_smoke_test() {
    local test_name=$1
    local test_cmd=$2
    local deployment_id="$DEPLOYMENT_ID"

    echo "Running smoke test: $test_name..."

    if eval "$test_cmd"; then
        python3 -c "
from relay_ai.platform.observability.deployment_metrics import get_deployment_metrics
collector = get_deployment_metrics()
collector.record_smoke_test(
    environment='production',
    deployment_id='$deployment_id',
    test_name='$test_name',
    success=True
)
        "
    else
        python3 -c "
from relay_ai.platform.observability.deployment_metrics import get_deployment_metrics
collector = get_deployment_metrics()
collector.record_smoke_test(
    environment='production',
    deployment_id='$deployment_id',
    test_name='$test_name',
    success=False,
    error_message='Test command failed'
)
        "
        return 1
    fi
}

# Usage
run_smoke_test "api_health" "curl -f $BACKEND_URL/health"
run_smoke_test "knowledge_api" "curl -f $BACKEND_URL/api/v1/knowledge/health"
run_smoke_test "web_app" "curl -f $WEB_URL/beta"
```

**Prometheus Query:**
```promql
# Pass rate by test
sum(increase(smoke_test_total{status="success"}[1h])) by (test_name)
/
sum(increase(smoke_test_total[1h])) by (test_name)

# Overall pass rate
sum(increase(smoke_test_total{status="success"}[1h]))
/
sum(increase(smoke_test_total[1h]))
```

---

## Two Additional Critical Metrics

### 6. Rollback Events & Frequency

**What it measures:** How often we need to rollback, and if rollbacks succeed

**Why it matters:**
- Deployment quality indicator
- Safety net reliability
- Troubleshooting capability

**Implementation (already in your code):**

```python
collector.record_rollback(
    environment="production",
    deployment_id="run-12345",
    previous_deployment_id="run-12344",
    reason="health_check_failed",  # or 'test_failed', 'manual'
    success=True
)
```

**Prometheus Query:**
```promql
# Rollback rate (per hour)
rate(deployment_rollback_total{status="success"}[1h])

# Rollback reasons (last 7 days)
sum(increase(deployment_rollback_total[7d])) by (reason)
```

**Alert:**
```yaml
- alert: RollbacksIncreasing
  expr: |
    increase(deployment_rollback_total{status="success"}[7d]) > 3
  labels:
    severity: high
  annotations:
    summary: "{{ $value }} rollbacks in last 7 days (normal: 0-1)"
```

---

### 7. Deployment Stage Breakdown

**What it measures:** Duration of each deployment stage (build, deploy, test, migrate)

**Why it matters:**
- Identify bottleneck stages
- Resource allocation decisions
- Trend analysis (is build getting slower?)

**Implementation (already supported):**

```python
# At stage start
collector.record_stage_start(
    environment="production",
    deployment_id="run-12345",
    service="api",
    stage="build"
)

# At stage end
collector.record_stage_complete(
    environment="production",
    deployment_id="run-12345",
    service="api",
    stage="build",
    status="success",
    duration_seconds=125.4
)
```

**Prometheus Queries:**

```promql
# Average stage duration
avg(deployment_stage_duration_seconds{environment="production"}) by (stage)

# P95 stage duration trend
histogram_quantile(0.95, rate(deployment_stage_duration_seconds_bucket{environment="production"}[1h])) by (stage)

# Stage duration over time (for Grafana heatmap)
deployment_stage_duration_seconds{environment="production", stage="migration"}
```

---

## Grafana Dashboard Design

### Dashboard 1: Deployment Pipeline Overview (Real-Time)

**Purpose:** Command center view for ops during deployments

**Layout:**

```
ROW 1: Key Metrics (4 Large Numbers)
  - Success Rate (%) ← color-coded: green >95%, yellow 90-95%, red <90%
  - Current TTD (seconds) ← target line at 600s
  - Last Deployment Status (success/failure) ← big green/red
  - Active Deployments (count) ← usually 0

ROW 2: Trend Charts (3 panels)
  - Deployment Success Rate (7-day trend)
  - TTD p95 (7-day trend with target line)
  - Rollback frequency (stacked bar by reason)

ROW 3: Stage Breakdown (2 panels)
  - Stage Duration (average by stage)
  - Stage Failures (count by stage + error type)

ROW 4: Health & Tests (3 panels)
  - API Health Check Success (gauge 0-100%)
  - Smoke Test Results (pass/fail by test name)
  - Migration Duration (gauge with warning 120s, critical 300s)

ROW 5: Details (Table)
  - Recent Deployments (last 10)
  - Columns: deployment_id, timestamp, duration, stages, status, rollback
  - Click to drill into trace/logs
```

**Query Examples:**

```json
{
  "title": "Success Rate (7 days)",
  "expr": "sum(increase(deployment_total{status='success'}[1d])) by (time) / sum(increase(deployment_total[1d])) by (time)",
  "format": "timeseries"
}

{
  "title": "Recent Deployments",
  "expr": "topk(10, deployment_in_progress{environment='production'}) or topk(10, sort_desc(timestamp))",
  "format": "table"
}
```

---

### Dashboard 2: Deployment Troubleshooting (Drill-Down)

**Purpose:** Debug view for when deployments fail

**Layout:**

```
ROW 1: Filter/Context
  - Deployment ID dropdown/search
  - Date range picker
  - Environment filter (prod/staging)

ROW 2: Deployment Timeline (Waterfall)
  - Horizontal bar chart showing:
    - Build stage: start → end
    - Deploy stage: start → end
    - Migration stage: start → end
    - Tests stage: start → end
    - Health checks: dots at 5s intervals
  - Color: green (success), yellow (slow), red (failed)
  - Click each stage to see logs

ROW 3: Error Details (if failed)
  - Error type breakdown
  - Stack traces (from logs)
  - Affected services
  - Correlation with other incidents

ROW 4: Post-Deployment Metrics
  - API latency (p50/p95/p99)
  - Error rate (first 5 minutes vs normal)
  - Database queries (slow query log)
  - External API calls (to Supabase, embeddings)

ROW 5: Comparison (if rollback)
  - Before vs after metrics
  - Old version vs new version performance
```

---

## Implementation Checklist

### Phase 1: Enable Metric Recording (30 min)

- [ ] Update `deploy.yml` to import `DeploymentMetricsCollector`
- [ ] Add `record_deployment_complete()` calls at deploy end
- [ ] Add `record_stage_complete()` around each major step (build, deploy, migrate, test)
- [ ] Add health check recording with latency
- [ ] Add smoke test recording around each test
- [ ] Configure PUSHGATEWAY_URL env var in Railway → Prometheus Pushgateway

**Code Changes Required:**
```yaml
# In .github/workflows/deploy.yml

    - name: Record deployment complete
      if: always()
      env:
        DEPLOYMENT_ID: ${{ github.run_id }}
      run: |
        python3 << 'EOF'
        from relay_ai.platform.observability.deployment_metrics import *
        import os, time

        status = "success" if "${{ job.status }}" == "success" else "failure"
        record_deployment_complete(
            environment="production",
            deployment_id=os.getenv("DEPLOYMENT_ID"),
            total_duration_seconds=int(${{ github.run_number }} * 600),  # rough est
            success=(status == "success")
        )
        EOF
```

---

### Phase 2: Create Grafana Dashboards (45 min)

- [ ] Create "Deployment Pipeline Overview" dashboard
- [ ] Create "Deployment Troubleshooting" dashboard
- [ ] Set dashboard refresh to 10 seconds (auto-refresh during deploys)
- [ ] Configure drill-down links from dashboard to GitHub Actions logs
- [ ] Add alert annotations to dashboards (show active alerts)

---

### Phase 3: Implement Alert Rules (30 min)

**Alerts to add** (leverage existing `prometheus-deployment-alerts.yml`):

```yaml
# Already defined in your config, ensure these fire:

- alert: DeploymentFailed               # CRITICAL
- alert: HealthCheckFailuresPostDeploy  # CRITICAL
- alert: DatabaseMigrationFailed        # CRITICAL
- alert: SmokeTestsFailingPostDeploy    # HIGH
- alert: DeploymentTakingTooLong        # HIGH (>900s)
- alert: DatabaseMigrationSlow          # HIGH (>120s)
```

**Tuning for low false positives:**
- Set `for: 2m` (don't alert on transient issues)
- Use `increase()` not absolute counts (immune to restarts)
- Test thresholds against historical data

---

### Phase 4: Cost Tracking (Optional, 15 min)

**Track deployment infrastructure costs:**

```python
# After successful deployment
collector.record_infrastructure_cost(
    environment="production",
    deployment_id="run-12345",
    resource="railway_compute",
    cost_usd=0.15  # estimated build + deploy compute
)

collector.record_infrastructure_cost(
    environment="production",
    deployment_id="run-12345",
    resource="vercel_build",
    cost_usd=0.02  # web build
)
```

**Cost Metrics Query:**
```promql
# Monthly deployment cost
sum(increase(deployment_infrastructure_cost[30d])) by (resource)

# Cost per deployment
sum(deployment_infrastructure_cost) by (deployment_id)
```

---

## SLO Definitions

### SLO 1: Deployment Reliability
```
SLI: % of deployments completing without rollback
SLO: ≥ 99% (one rollback per month acceptable)
SLA: ≥ 98% (monthly credit if missed)
Error Budget: 1% = ~43 minutes failed deploys/month
```

### SLO 2: Time to Deploy
```
SLI: p95 time from push to production stabilization
SLO: ≤ 10 minutes (p95)
SLA: ≤ 12 minutes
Error Budget: If 2+ deploys exceed 20 min/week, escalate
```

### SLO 3: Post-Deployment Health
```
SLI: % of health checks passing in first 5 minutes
SLO: ≥ 99% (auto-rollback if <95%)
SLA: N/A (internal gate)
Error Budget: Tied to deployment reliability SLO
```

### SLO 4: Database Migration Success
```
SLI: % of migrations applying without rollback
SLO: 100% (zero tolerance)
SLA: N/A (blocks deployment)
Error Budget: Any failure prevents deploy
```

### SLO 5: Smoke Test Coverage
```
SLI: % of smoke tests passing post-deploy
SLO: ≥ 99%
SLA: N/A (internal gate)
Error Budget: Failures trigger rollback
```

---

## Error Budget Tracking

```yaml
# Monthly deployment error budget

Total Budget: 1 failed deployment per month (1%)

Used By:
- Failed build/deploy: 100% if failed
- Failed smoke test: 100% if failed
- Failed migration: 100% if failed
- Rollback due to health: 50% (recoverable)
- Rollback due to errors: 100% (new code issue)

When budget depleted:
1. Freeze risky changes (only hotfixes)
2. Increase test coverage / review
3. Reset at start of next month
```

---

## Rollout Plan

**Week 1:** Phase 1 + 2 (metric recording + dashboards)
- Deploy metric recording to workflows
- Create basic Grafana dashboards
- Begin collecting historical data

**Week 2:** Phase 3 + 4 (alerts + costs)
- Tune alert thresholds against Week 1 data
- Test alert firing (don't disable)
- Add cost tracking if budget allows

**Week 3+:** Operational insights
- Review weekly deployment health
- Identify bottleneck stages
- Prioritize performance work

---

## Quick Reference: Minimum Implementation (2 hours)

If short on time, do these 3 things:

1. **Add 3 lines to deploy.yml:**
   ```python
   # After deployment step
   python3 -c "from relay_ai.platform.observability.deployment_metrics import *;
   record_deployment_complete('production', '${{ github.run_id }}', 600, True)"
   ```

2. **Create 1 Grafana dashboard:**
   - Query: `rate(deployment_total{status="success"}[1h])` (success rate)
   - Query: `deployment_stage_duration_seconds` (stage breakdown)
   - Query: `smoke_test_total` (test pass rate)

3. **Add 2 alert rules:**
   ```promql
   DeploymentFailed: increase(deployment_total{status="failure"}[5m]) > 0
   HighErrorRatePostDeploy: post_deployment_error_rate > 0.05 for 2m
   ```

**Result:** Core visibility of deployment health with existing infrastructure.

---

## FAQ

**Q: Where does the data come from?**
A: `DeploymentMetricsCollector` in `relay_ai/platform/observability/deployment_metrics.py` pushes metrics to Prometheus Pushgateway, which scrapes them into your Prometheus instance.

**Q: How do I know if a stage is slow?**
A: Compare `deployment_stage_duration_seconds` for that stage against historical p95 for that service/environment.

**Q: What if a metric doesn't exist?**
A: Add it to the workflow recording section. The collector supports custom gauges/counters/histograms.

**Q: Can I correlate deployment metrics with errors?**
A: Yes! Use `deployment_id` label to join with application error logs/traces.

**Q: What's the cost of this monitoring?**
A: ~1-2 MB metrics data per deployment (negligible). Prometheus retention: configure based on disk budget.

---

## Success Metrics

After implementing this design:

1. You can answer in <30s:
   - "What's the current deployment success rate?"
   - "How long is the build stage taking?"
   - "Did the health checks pass after the last deploy?"

2. You have automatic rollback triggered by:
   - Health checks failing
   - Error rate spiking
   - Smoke tests failing

3. You can debug a failed deployment in <5 min:
   - Which stage failed?
   - What was the error?
   - How long did it take?
   - Did we rollback?

4. Your deployment process improves by:
   - Identifying and eliminating bottleneck stages
   - Catching issues early (health checks vs. production errors)
   - Reducing MTTR (mean time to recovery)
