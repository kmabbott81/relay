# Observability Monitoring: Session 2025-11-11 Changes
## Infrastructure Rename & Stage-Specific Deployment

**Date**: 2025-11-15
**Infrastructure**: Railway (API), Vercel (Web), Supabase (DB), GitHub Actions (CI/CD)
**Scope**: Monitoring the 2025-11-11 infrastructure changes

---

## Executive Summary

The 2025-11-11 session involved critical infrastructure changes:
- Renaming Railway service from `relay-production` to `relay-beta-api` (Beta) / `relay-prod-api` (Prod)
- Vercel web app unified as `relay-studio-one`
- Supabase databases: `relay-beta-db` and `relay-prod-db`
- Stage-specific GitHub Actions workflows created

**Observability Goals**:
1. Monitor both environments independently (Beta & Prod)
2. Track deployment health for stage-specific workflows
3. Verify zero service disruption during infrastructure changes
4. Establish baseline metrics for new environment names

---

## Part 1: Environment-Specific Metrics

### 1.1 Railroad API Monitoring

#### Beta API: relay-beta-api.railway.app

```yaml
Job Name: relay-beta-api
Target: relay-beta-api.railway.app
Metrics Path: /metrics
Scrape Interval: 15s
Labels:
  environment: beta
  service: relay-api
  region: railway
```

**Key Metrics to Baseline**:
```
http_requests_total{environment="beta"}
  - Baseline RPS: 10-50 (during beta testing)
  - Target: Stable within 20% daily variance

http_request_duration_seconds{environment="beta"}
  - p50: 50ms
  - p95: 150-200ms
  - p99: 300-400ms

http_requests_total{environment="beta",status_code="5.."}
  - Baseline: 0-1 per minute
  - Alert threshold: > 5 per minute (0.1% error rate)

process_resident_memory_bytes{environment="beta"}
  - Baseline: 200-300MB (Python API)
  - Alert: > 450MB (85% of 512MB limit)

railway_container_restarts_total{environment="beta"}
  - Baseline: 0
  - Alert: > 3 in 24 hours (indicates crashes)
```

#### Production API: relay-prod-api.railway.app

```yaml
Job Name: relay-prod-api
Target: relay-prod-api.railway.app
Metrics Path: /metrics
Scrape Interval: 15s
Labels:
  environment: prod
  service: relay-api
  region: railway
```

**Key Metrics to Baseline**:
```
http_requests_total{environment="prod"}
  - Baseline RPS: 100-500 (production load)
  - Alert: RPS drops > 50% suddenly

http_request_duration_seconds{environment="prod"}
  - p50: 40ms
  - p95: 100-150ms
  - p99: 200-300ms

Error Rate {environment="prod"}
  - Baseline: 0.01% (SLO: 99.9%)
  - Alert: > 0.05%

database_connections_active{environment="prod"}
  - Baseline: 5-20
  - Alert: > 40 (80% of 50)
```

---

### 1.2 Vercel Web App Monitoring

#### Web: relay-studio-one.vercel.app

```yaml
Job Name: relay-web-app
Target: relay-studio-one.vercel.app
Metrics Path: /_next/metrics
Scrape Interval: 30s
Labels:
  environment: web
  service: relay-web
  platform: vercel
```

**Key Metrics**:
```
vercel_build_duration_seconds
  - Baseline: 45-60 seconds
  - Alert: > 120 seconds (2x normal)

vercel_build_success_rate
  - Baseline: 98-99%
  - Alert: < 90%

web_page_load_time_seconds
  - FCP (First Contentful Paint): < 1s
  - LCP (Largest Contentful Paint): < 2.5s
  - TTFB (Time to First Byte): < 100ms

vercel_function_cold_start_duration_ms
  - Baseline: 200-500ms
  - Alert: > 1000ms

vercel_cache_hit_rate
  - Baseline: 80-90%
  - Alert: < 60% (indicates cache problems)
```

---

### 1.3 Supabase Database Monitoring

#### Beta Database: relay-beta-db

```yaml
Job Name: supabase-metrics-beta
Database: relay-beta-db
Labels:
  environment: beta
  service: database
  provider: supabase
```

**Key Metrics**:
```
database_connections_active{environment="beta"}
  - Baseline: 2-8 connections
  - Max pool: 10
  - Alert: > 8 (80% of pool)

database_query_duration_seconds{operation="SELECT",environment="beta"}
  - p50: 5-10ms
  - p95: 20-30ms
  - p99: 50-100ms

database_query_duration_seconds{operation="INSERT",environment="beta"}
  - p50: 10-15ms
  - p95: 25-40ms
  - p99: 100-150ms

database_slow_queries_total{environment="beta"}
  - Baseline: 0 per hour
  - Alert: > 5 per hour

db_autovacuum_runs_total{environment="beta"}
  - Expected: 1-2 per day
  - Tracks: VACUUM maintenance

database_backup_duration_seconds{environment="beta"}
  - Baseline: 60-120 seconds
  - Alert: > 300 seconds (backup taking too long)
```

#### Production Database: relay-prod-db

```yaml
Database: relay-prod-db
Labels:
  environment: prod
  service: database
  provider: supabase
```

**Key Metrics**:
```
database_connections_active{environment="prod"}
  - Baseline: 15-40 connections
  - Max pool: 50
  - Alert: > 40 (80% of pool)
  - Critical: > 45 (90% of pool)

database_replication_lag_seconds{environment="prod"}
  - Baseline: 0-1 second
  - Alert: > 5 seconds

database_slow_queries_total{environment="prod"}
  - Baseline: 0-2 per hour
  - Alert: > 10 per hour

query_errors_total{environment="prod"}
  - Baseline: 0
  - Alert: Any errors logged
```

---

## Part 2: Deployment Pipeline Monitoring

### 2.1 GitHub Actions Workflows

#### Stage-Specific Workflows Created

```yaml
Workflows:
  1. deploy-beta.yml
     Trigger: Push to 'beta' branch
     Services: relay-beta-api, relay-web
     Database: relay-beta-db
     Target: relay-beta-api.railway.app

  2. deploy-prod.yml
     Trigger: Push to 'prod' branch
     Services: relay-prod-api, relay-web
     Database: relay-prod-db
     Target: relay-prod-api.railway.app

  3. deploy-staging.yml.disabled
     Status: Currently disabled
     Reason: Infrastructure not ready

  4. ci.yml
     Trigger: Push to any branch
     Jobs: Lint, Test, Build
     Purpose: Quality gates before deployment
```

#### Deployment Health Metrics

```
github_workflow_status{workflow="deploy-beta",status="success"}
  - Baseline: 95%+ success rate
  - Alert: < 90% success in last 10 runs

github_workflow_status{workflow="deploy-prod",status="success"}
  - Baseline: 95%+ success rate
  - Target SLO: > 95%
  - Alert: < 90% success

github_workflow_duration_seconds{workflow="deploy-beta",job="migrate-db"}
  - Baseline: 60-120 seconds
  - Alert: > 300 seconds

github_workflow_duration_seconds{workflow="deploy-beta",job="deploy-api"}
  - Baseline: 2-4 minutes
  - Alert: > 10 minutes

github_workflow_duration_seconds{workflow="deploy-beta",job="smoke-tests"}
  - Baseline: 30-60 seconds
  - Alert: > 120 seconds

deployment_smoke_test_status{test="api_health_check"}
  - Expected: 100% pass rate
  - Alert: Any failure

deployment_smoke_test_status{test="web_page_load"}
  - Expected: < 3 seconds load time
  - Alert: > 5 seconds

deployment_smoke_test_status{test="db_connectivity"}
  - Expected: 100% success
  - Alert: Any failure
```

---

### 2.2 Monitoring Deployment Rollouts

**Beta Deployment Sequence**:
```
1. Database Migrations (migrate-db job)
   ↓ Success? Continue
2. API Deploy (deploy-api job)
   ↓ Success? Continue
3. Web Deploy (deploy-web job)
   ↓ Success? Continue
4. Smoke Tests (smoke-tests job)
   ↓ All Pass? Deployment complete
   ↓ Failure? Auto-rollback initiated
```

**Metrics to Track During Deployment**:

```
Pre-Deployment (T-5 min):
  - Current error rate: < 1%
  - Memory usage: < 70%
  - Database connections: < 80% of pool

During Deployment (T0 to T+5 min):
  - Deploy job status: running
  - Request rate: watch for drops
  - Error rate: should stay < 2% (test traffic)
  - New requests routing to new version

Post-Deployment (T+5 to T+30 min):
  - All smoke tests: PASS
  - Error rate: return to < 1%
  - Latency: p95 < 200ms
  - Memory stable: < 75%
  - Database connections: recovering
```

**Rollback Triggers**:
```
Automatic:
  - Smoke tests fail: Immediate rollback
  - Health check fails: Immediate rollback

Manual:
  - Error rate > 10% for 2 minutes
  - Latency p95 > 2 seconds for 5 minutes
  - Database errors > 10 per minute
```

---

## Part 3: Migration Validation (For 2025-11-11 Changes)

### 3.1 Service Name Verification

**Validate Scrape Targets**:
```
Old Name              New Name                  Status
relay-production     relay-beta-api.railway    ✓ Being monitored
(staging - removed)  relay-prod-api.railway    ✓ Ready for prod
N/A                  relay-studio-one.vercel   ✓ Unified web app
N/A                  relay-beta-db             ✓ Beta database
N/A                  relay-prod-db             ✓ Prod database
```

**Prometheus Config Verification**:
```bash
# Check scrape config has new targets
cat observability/PROMETHEUS_CONFIG.yml | grep relay-beta-api
cat observability/PROMETHEUS_CONFIG.yml | grep relay-prod-api
cat observability/PROMETHEUS_CONFIG.yml | grep relay-studio-one

# Verify targets are healthy
curl http://localhost:9090/api/v1/targets | jq '.data.activeTargets[] | select(.labels.instance | contains("relay-")'
```

---

### 3.2 Zero-Downtime Validation

**During Infrastructure Rename**:

```
Validation Checklist:
☐ Old service (if any) still online during transition
☐ New service DNS resolving correctly
☐ New service responding to /health check
☐ New service /metrics endpoint reachable
☐ Prometheus scraping new targets
☐ Grafana dashboards updated with new labels
☐ Alert rules updated with new environment names
☐ Zero requests dropped (request count continuous)
☐ Zero increase in error rate
☐ Zero latency spike

Success Criteria:
  - Request success rate remains > 99.5%
  - Error rate remains < 0.1%
  - Latency p95 remains < 200ms
  - Database connection count remains stable
```

**Monitoring During Transition**:

```
Timeline:
T-1 hour:  Deploy new infrastructure alongside old
T0:        Start routing 1% traffic to new
T+15 min:  Increase to 10% traffic (monitor metrics)
T+30 min:  Increase to 50% traffic (canary deployment)
T+45 min:  Increase to 100% traffic (full cutover)
T+60 min:  Decommission old infrastructure (if old exists)

Metrics to Watch:
- Request rate per service
- Error rate per service
- Latency per service
- Error budget consumption
```

---

## Part 4: Alert Rules for Session 2025-11-11

### 4.1 Environment-Specific Alerts

**Beta API Alerts** (development-focused, lower thresholds):
```yaml
- alert: BetaAPIDown
  expr: api:success_rate:5m{environment="beta"} < 0.5
  for: 1m
  severity: critical

- alert: BetaHighErrorRate
  expr: api:error_rate:5m{environment="beta"} > 0.05
  for: 5m
  severity: high

- alert: BetaBuildFailure
  expr: deployment_smoke_test_status{environment="beta"} > 0
  for: 0m
  severity: critical
```

**Production API Alerts** (stricter thresholds):
```yaml
- alert: ProdAPIDown
  expr: api:success_rate:5m{environment="prod"} < 0.999
  for: 1m
  severity: critical
  annotations:
    escalate: "true"  # Immediate page on-call

- alert: ProdHighErrorRate
  expr: api:error_rate:5m{environment="prod"} > 0.001
  for: 2m
  severity: critical
```

---

### 4.2 Database Alerts by Environment

**Beta Database**:
```yaml
- alert: BetaDBConnectionPoolHigh
  expr: |
    (database_connections_active{environment="beta"} / 10) > 0.8
  for: 5m
  severity: medium
```

**Production Database**:
```yaml
- alert: ProdDBConnectionPoolHigh
  expr: |
    (database_connections_active{environment="prod"} / 50) > 0.8
  for: 5m
  severity: high
  annotations:
    escalate: "true"

- alert: ProdDBReplicationLag
  expr: database_replication_lag_seconds{environment="prod"} > 5
  for: 2m
  severity: high
```

---

## Part 5: Dashboard Updates

### 5.1 New Dashboard: Infrastructure Status

**Purpose**: Track both environments side-by-side

```json
{
  "dashboard": {
    "title": "Infrastructure Status - Beta vs Prod",
    "panels": [
      {
        "title": "Request Rate Comparison",
        "type": "graph",
        "targets": [
          {
            "expr": "rate(http_requests_total{environment=~'beta|prod'}[5m])",
            "legendFormat": "{{environment}}"
          }
        ]
      },
      {
        "title": "Error Rate Comparison",
        "targets": [
          {
            "expr": "api:error_rate:5m{environment=~'beta|prod'}",
            "legendFormat": "{{environment}}"
          }
        ]
      },
      {
        "title": "Latency P95 Comparison",
        "targets": [
          {
            "expr": "api:request_duration:p95:5m{environment=~'beta|prod'}",
            "legendFormat": "{{environment}}"
          }
        ]
      },
      {
        "title": "Deployment Status",
        "type": "table",
        "targets": [
          {
            "expr": "github_workflow_status",
            "format": "table"
          }
        ]
      }
    ]
  }
}
```

### 5.2 Updated Existing Dashboards

**System Health Dashboard** → Add environment selector:
```
Selector: [All] [Beta] [Prod]
  - Filters all panels by environment
  - Allows switching focus between environments
```

**API Performance Dashboard** → Add environment grouping:
```
Panels grouped by:
  - Beta API Performance (separate row)
  - Prod API Performance (separate row)
  - Comparison charts (side-by-side)
```

---

## Part 6: First Week Post-Launch Monitoring

### Day 1 (Nov 15 - Launch Day)

**Morning Checklist**:
- [ ] All services responding on new endpoints
- [ ] Prometheus scraping all 5 targets
- [ ] Grafana dashboards displaying data
- [ ] No alerts firing (baseline period)
- [ ] Error rate: < 0.1% on both environments

**Actions**:
- Set alert mute period: 8 hours (learning period)
- Collect baseline metrics
- Document any manual interventions

**Evening Review**:
- Error rate trend: Should be flat
- Latency trend: Should be stable
- Database connections: Should be normal
- Build success rate: Should be > 90%

### Days 2-3 (Nov 16-17)

**Validation**:
- [ ] Error rate stable for 48 hours
- [ ] No unplanned restarts
- [ ] Database backup completed successfully
- [ ] Replicate lag (if applicable) < 2 seconds

**Threshold Tuning**:
- Review alert firing patterns
- Adjust thresholds if too noisy
- Document reasons for changes

### Days 4-7 (Nov 18-22)

**Stabilization**:
- [ ] Run full week without critical alerts
- [ ] Complete one full deployment cycle
- [ ] Verify rollback procedure works
- [ ] Team trained on new dashboards

**Metrics Review**:
- Baseline established for all key metrics
- Error budget consumption: Track
- Cost trends: Establish baseline
- Performance profiles: Analyzed

---

## Part 7: SLO Targets for New Infrastructure

### Initial SLOs (November 2025)

```
Beta Environment (Development):
  Availability:     99.0% (target: allow failures for testing)
  Latency p95:      < 300ms
  Error Rate:       < 1.0% (higher tolerance for dev)
  Deploy Success:   > 90%

Production Environment (Stable):
  Availability:     99.9% (SLO: 99.5% with SLA)
  Latency p95:      < 200ms
  Error Rate:       < 0.1%
  Deploy Success:   > 95%
```

### Error Budget Allocation

```
Beta Monthly Error Budget:
  SLO: 99.0% → Budget = 7.2 hours
  Allocation:
    - Feature testing: 3 hours
    - Scheduled maintenance: 2 hours
    - Emergency buffer: 2.2 hours

Production Monthly Error Budget:
  SLO: 99.5% → Budget = 43 minutes
  Allocation:
    - Database migrations: 15 minutes
    - Infrastructure updates: 15 minutes
    - Emergency buffer: 13 minutes
```

---

## Appendix: Key Metrics Reference

### Quick Metric Lookup

**Rate Metrics** (per minute):
```
http_requests_total          → Requests/min per endpoint
database_queries_total       → DB ops/min per table
llm_tokens_total             → Tokens/min per model
deployment_workflow_total    → Deployments/hour
```

**Duration Metrics** (milliseconds):
```
http_request_duration_seconds    → API latency
database_query_duration_seconds  → DB latency
build_time_seconds               → CI build time
deployment_duration_seconds      → Deploy duration
web_page_load_time_seconds       → Page load time
```

**Gauge Metrics** (current value):
```
http_requests_in_flight          → Active requests now
database_connections_active      → DB connections now
process_resident_memory_bytes    → Memory used now
cache_hit_rate                   → Cache hit % now
```

---

## Support

**Questions?**
- Observability Lead: Kyle Mahan (@kylem)
- Documentation: `OBSERVABILITY_2025-11-11.md`
- Quick Ref: `OBSERVABILITY_QUICKREF.md`
- Implementation: `OBSERVABILITY_IMPLEMENTATION_GUIDE.md`

---

**Version**: 1.0
**Created**: 2025-11-15
**Infrastructure**: Railway (relay-beta-api, relay-prod-api), Vercel (relay-studio-one), Supabase (relay-beta-db, relay-prod-db)
**Status**: Ready for Implementation
