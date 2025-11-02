# Deployment Observability - Quick Start (5-Minute Summary)

## The 5 Critical Metrics You Need

| Metric | What | Why | Alert Threshold |
|--------|------|-----|-----------------|
| **1. Success Rate** | % of deployments without rollback | Reliability signal | < 95% → HIGH alert |
| **2. Time to Deploy** | Minutes from push to stable | Velocity metric | p95 > 10min → HIGH alert |
| **3. API Health** | % health checks passing post-deploy | Early failure detection | < 90% → CRITICAL (auto-rollback) |
| **4. Migration Success** | % Alembic migrations applying | Schema correctness | Any failure → CRITICAL (block deploy) |
| **5. Smoke Test Pass** | % end-to-end tests passing | Real app validation | < 90% → HIGH alert |

---

## Implementation Roadmap

### Minute 1-2: Add to your GitHub Actions workflow

```yaml
# Copy into your deploy.yml workflow

    - name: Record deployment metrics
      if: always()
      run: |
        python3 -c "
from relay_ai.platform.observability.deployment_metrics import get_deployment_metrics
import os, time

collector = get_deployment_metrics()
collector.record_deployment_complete(
    environment='production',
    deployment_id='${{ github.run_id }}',
    total_duration_seconds=600,
    success='${{ job.status }}' == 'success'
)
        "
```

### Minute 3-4: Create Grafana dashboard

Add a new dashboard with these 3 panels:

**Panel 1: Success Rate**
```promql
sum(increase(deployment_total{status="success"}[24h]))
/
sum(increase(deployment_total[24h])) * 100
```

**Panel 2: TTD p95**
```promql
histogram_quantile(0.95, rate(time_to_deploy_seconds_bucket[1h]))
```

**Panel 3: Health Check Pass Rate**
```promql
sum(increase(api_health_check_latency_ms_count{status="healthy"}[5m]))
/
sum(increase(api_health_check_latency_ms_count[5m])) * 100
```

### Minute 5: Add 2 alert rules

```yaml
- alert: DeploymentFailed
  expr: increase(deployment_total{status="failure"}[5m]) > 0
  for: 2m
  severity: critical

- alert: HealthChecksFailing
  expr: (sum(increase(api_health_check_latency_ms_count{status="healthy"}[5m])) / sum(increase(api_health_check_latency_ms_count[5m]))) < 0.90
  for: 2m
  severity: critical
```

---

## Result After 5 Minutes

You can answer:
- "What's our deployment success rate?" ✓
- "How long are deployments taking?" ✓
- "Did the health checks pass?" ✓
- "Will we get alerted if something breaks?" ✓

---

## Full Implementation (Still Only 2 Hours)

| Phase | What | Time | Checklist |
|-------|------|------|-----------|
| 1 | Add metric recording to workflows | 30 min | Update deploy.yml, test locally |
| 2 | Create Grafana dashboards | 45 min | Copy dashboard JSON, verify data flows |
| 3 | Configure alerts | 30 min | Add rules, test alert firing |
| 4 | Train team | 15 min | Show dashboards, explain alerts |

**Total: ~2 hours of focused work**

---

## What Gets Measured

```
GitHub Actions Workflow
├─ Start (record deployment_id, branch)
├─ Build stage (duration)
├─ Deploy to Railway (duration)
├─ Health checks (latency, pass/fail)
├─ Database migrations (duration, success)
├─ Smoke tests (each test pass/fail)
├─ (If failed → Rollback)
└─ End (record total duration, success/failure)

↓ Metrics pushed every step ↓

Prometheus (stores time-series data)

↓ Scraped by ↓

Grafana (displays dashboards)
AlertManager (fires alerts)
```

---

## Key Files

**Existing (No Changes Needed):**
- `relay_ai/platform/observability/deployment_metrics.py` ← Already has all collectors
- `config/prometheus/prometheus-deployment-alerts.yml` ← Already has all alert rules
- `relay-prometheus-production.up.railway.app` ← Prometheus instance running

**You'll Create:**
- Updated `.github/workflows/deploy-full-stack.yml` ← Add metric recording
- `monitoring/grafana/dashboards/deployment-pipeline.json` ← New dashboard
- Environment var: `PUSHGATEWAY_URL=http://pushgateway:9091`

---

## Example Outputs

### Dashboard - Success Rate Gauge
```
┌─────────────────────────────┐
│  Deployment Success Rate    │
│                             │
│          96.2%              │
│     🟢 (target: >95%)      │
└─────────────────────────────┘
```

### Dashboard - Stage Duration
```
Stage              Avg Duration
api-build          2m 30s
api-deploy         1m 45s  ← slowest
web-build          45s
migrations         30s
health-checks      20s
smoke-tests        2m 10s
─────────────────────────────
Total              ~10m
```

### Alert (Example)

```
CRITICAL: Deployment Failed
Deployment ID: run-123456
Service: api
Stage: health_check
Status: Unhealthy

Action: Auto-rollback triggered to previous version
View: https://grafana/d/deployment-pipeline
Logs: https://github.com/.../actions/runs/123456
```

---

## Metrics Available to Query

After implementation, you can query:

```promql
# Success rate
sum(increase(deployment_total{status="success"}[1h])) / sum(increase(deployment_total[1h]))

# Time to deploy percentiles
histogram_quantile(0.50, rate(time_to_deploy_seconds_bucket[1h]))  # p50
histogram_quantile(0.95, rate(time_to_deploy_seconds_bucket[1h]))  # p95
histogram_quantile(0.99, rate(time_to_deploy_seconds_bucket[1h]))  # p99

# Health check status
api_health_check_latency_ms{status="healthy"}
api_health_check_latency_ms{status="unhealthy"}

# Database migrations
migration_total{status="success"}
migration_total{status="failure"}
database_migration_lag_seconds

# Smoke tests
smoke_test_total{status="success"}
smoke_test_total{status="failure"}

# Rollbacks
deployment_rollback_total{status="success"}
deployment_rollback_total{reason="health_check_failed"}

# Stage breakdown
deployment_stage_duration_seconds{stage="build"}
deployment_stage_duration_seconds{stage="deploy"}
deployment_stage_duration_seconds{stage="migration"}
```

---

## Common Queries for Grafana

**Query 1: Is deployment healthy?**
```promql
# Returns 1 if any deployment in progress, 0 if idle
deployment_in_progress{environment="production"}
```

**Query 2: Show last 10 deployments**
```promql
# Table showing recent deployments with status
topk(10, sort_desc(timestamp(deployment_total)))
```

**Query 3: Are we rolling back too much?**
```promql
# Shows rollback frequency
rate(deployment_rollback_total{status="success"}[24h])
```

**Query 4: Which stage is the bottleneck?**
```promql
# Average duration per stage
avg(deployment_stage_duration_seconds) by (stage)
```

**Query 5: How's our error budget?**
```promql
# Percentage of deployments failed (cumulative)
sum(increase(deployment_total{status="failure"}[30d]))
/
sum(increase(deployment_total[30d]))
```

---

## SLO Targets

| SLO | Target | Yellow Threshold | Red Threshold |
|-----|--------|------------------|---------------|
| Deployment Success | 99% | 95% | <95% |
| Time to Deploy (p95) | <10 min | 10-15 min | >15 min |
| API Health Post-Deploy | 100% | 95% | <95% |
| Migration Success | 100% | Any failure | Any failure |
| Smoke Test Coverage | 99% | 95% | <95% |

**Error Budget:** If success rate drops below 95%, freeze deployments until next month

---

## How to Use

1. **Before deploying:** Check dashboard - any red? If yes, don't deploy.
2. **During deploy:** Watch TTD - should hit target in 10 min
3. **After deploy:** Check health and smoke tests - should all pass
4. **If alert fires:** Check which stage/test failed, rollback if needed
5. **Weekly review:** Look at 7-day trends, identify improvements

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| Metrics not showing | Check PUSHGATEWAY_URL env var is set |
| Alerts not firing | Verify alert rules are in Prometheus config |
| Dashboard shows no data | Wait 1-2 minutes for first metrics to appear |
| Slow to load | Use time range filter (last 24h instead of 30d) |
| Missing stages | Add `record_stage_complete()` calls to workflow |

---

## Files to Review

1. Read full design: `DEPLOYMENT_OBSERVABILITY_DESIGN.md` (10 min)
2. Copy implementation code: `DEPLOYMENT_OBSERVABILITY_IMPLEMENTATION.md` (reference)
3. Update workflow: `.github/workflows/deploy-full-stack.yml`
4. Create dashboard: Use Grafana UI or import JSON
5. Test: Run `python3 scripts/test_deployment_metrics.py`

---

## Success Criteria

After implementation, you should be able to:

- [ ] Access Grafana dashboard with deployment metrics
- [ ] See success rate for last 24 hours
- [ ] See TTD trends over time
- [ ] See which stages are taking how long
- [ ] Get alerted when deployment fails
- [ ] Get alerted when health checks fail
- [ ] Auto-rollback when needed
- [ ] Answer "Did the last deploy succeed?" in 10 seconds

---

## Next Steps

1. **Today:** Copy code from `DEPLOYMENT_OBSERVABILITY_IMPLEMENTATION.md` into your workflow
2. **Tomorrow:** Create Grafana dashboard and verify data flows
3. **This week:** Tune alert thresholds, document runbooks
4. **Next week:** Team training, weekly metric reviews

**Estimated effort: 2-3 hours total implementation, 15 min per deploy to monitor**
