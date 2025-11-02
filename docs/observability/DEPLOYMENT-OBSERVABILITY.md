# Deployment Observability Architecture

**Document Version:** 1.0
**Date:** 2025-01-15
**Status:** Design - Ready for Implementation
**Target SLO:** <15 minutes Time-to-Deploy (TTD)

---

## Executive Summary

This document outlines a comprehensive observability framework for the automated deployment pipeline. The system will track deployments from GitHub Actions trigger through production stabilization, providing real-time visibility into success/failure rates, deployment stages, and post-deployment health.

### Key Objectives

1. **Deployment Success Visibility:** Know immediately when deployments succeed or fail
2. **Root Cause Attribution:** Identify exactly which deployment stage failed (API build → DB migration → Web deploy → smoke tests)
3. **Performance Tracking:** Monitor Time-to-Deploy (TTD) and individual stage latencies
4. **Health Verification:** Confirm API/Web/DB health post-deployment via automated checks
5. **Cost Impact:** Track deployment-related infrastructure costs and scaling events
6. **Incident Response:** Enable rapid detection of deployment-induced incidents

---

## Core Metrics Framework

### 1. Deployment Pipeline Metrics

All metrics use Prometheus format with standard tags: `environment`, `deployment_id`, `stage`, `service`

#### Counter: `deployment_total`
Incremented when deployment completes (success or failure)

```
deployment_total{
  environment="production",
  deployment_id="<github_run_id>",
  service="api|web|database",
  stage="<stage_name>",
  status="success|failure"
}
```

**Stages (API):**
- `build` → Docker image built
- `push` → Image pushed to registry
- `deploy_railway` → Railway deployment triggered
- `health_check` → Health endpoint verified
- `migration` → Database migrations applied
- `smoke_test` → Smoke tests executed
- `rollback` → Rollback triggered (if needed)

**Stages (Web):**
- `install` → Dependencies installed
- `build` → Next.js build completed
- `deploy_vercel` → Vercel deployment triggered
- `verification` → Web app loads successfully

**Stages (Database):**
- `migration_check` → Migration validation
- `migration_apply` → Migrations applied to DB
- `verification` → Schema verified

---

#### Gauge: `deployment_stage_duration_seconds`
Records latency of each deployment stage

```
deployment_stage_duration_seconds{
  environment="production",
  deployment_id="<github_run_id>",
  service="api|web|database",
  stage="health_check|migration|deploy_vercel|...",
  status="success|failure"
} = 45.2
```

**Thresholds (healthy deployment):**
- Docker build: < 120s
- Health check: < 30s (each attempt, should retry 3-5x)
- Database migration: < 60s
- Vercel deploy: < 180s
- Smoke tests: < 90s
- **Total deployment: < 15 minutes**

---

#### Counter: `deployment_errors_total`
Incremented when stage fails

```
deployment_errors_total{
  environment="production",
  deployment_id="<github_run_id>",
  service="api|web|database",
  stage="<stage_name>",
  error_type="timeout|health_check_failed|migration_failed|test_failed|rollback_triggered"
}
```

**Error Types:**
- `timeout` → Stage took too long
- `health_check_failed` → API/Web not responding
- `migration_failed` → Alembic migration error
- `test_failed` → Smoke test assertion failed
- `rollback_triggered` → Automatic rollback executed
- `api_unreachable` → Cannot connect to API endpoint
- `database_connection_error` → DB not accessible

---

#### Gauge: `deployment_in_progress`
1 when deployment running, 0 when complete

```
deployment_in_progress{
  environment="production",
  deployment_id="<github_run_id>",
  branch="main|beta|...",
  triggered_by="github_actions|manual|webhook"
} = 1|0
```

---

#### Counter: `deployment_rollback_total`
Tracks rollbacks

```
deployment_rollback_total{
  environment="production",
  deployment_id="<github_run_id>",
  reason="health_check_failed|test_failed|manual",
  status="success|failure"
}
```

---

### 2. Post-Deployment Health Metrics

#### Gauge: `api_health_check_latency_ms`
Health endpoint response time (collected every 30s post-deploy)

```
api_health_check_latency_ms{
  environment="production",
  deployment_id="<github_run_id>",
  status="healthy|degraded|unhealthy"
} = 42
```

---

#### Gauge: `post_deployment_error_rate`
Error rate in 5-minute window after deployment completes

```
post_deployment_error_rate{
  environment="production",
  deployment_id="<github_run_id>",
  service="api|web"
} = 0.02
```

**Baseline:** <1% error rate indicates healthy deployment

---

#### Gauge: `database_migration_lag_seconds`
Tracks how long migrations take

```
database_migration_lag_seconds{
  environment="production",
  deployment_id="<github_run_id>",
  migration_count="5"
} = 23.4
```

---

### 3. Git & GitHub Actions Metrics

#### Gauge: `github_action_duration_seconds`
Workflow duration from trigger to completion

```
github_action_duration_seconds{
  workflow="deploy-full-stack|deploy|ci",
  repository="relay-ai",
  branch="main",
  conclusion="success|failure|cancelled"
} = 892.5
```

---

#### Counter: `github_workflow_runs_total`
Total workflow executions

```
github_workflow_runs_total{
  workflow="deploy-full-stack",
  repository="relay-ai",
  branch="main",
  conclusion="success|failure"
}
```

---

### 4. Deployment Frequency Metrics

#### Counter: `deployment_frequency`
Deployments per time period (used for dora metrics)

```
deployment_frequency{
  environment="production",
  service="api|web|all",
  period="1h|1d"
}
```

---

#### Histogram: `time_to_deploy_seconds`
Distribution of deployment times (enables percentile calculation)

```
time_to_deploy_seconds_bucket{
  le="60",
  environment="production"
} = 2
time_to_deploy_seconds_bucket{
  le="300",
  environment="production"
} = 8
time_to_deploy_seconds_bucket{
  le="+Inf",
  environment="production"
} = 10
```

**Percentile Targets:**
- p50 (median): < 8 minutes
- p95: < 12 minutes
- p99: < 15 minutes

---

### 5. Cost & Infrastructure Metrics

#### Gauge: `deployment_infrastructure_cost`
Cost incurred during deployment (scaling, compute)

```
deployment_infrastructure_cost{
  environment="production",
  deployment_id="<github_run_id>",
  resource="railway_compute|vercel_build|database_migration"
} = 2.50
```

---

#### Gauge: `railway_deployment_memory_mb`
Peak memory during deployment

```
railway_deployment_memory_mb{
  environment="production",
  deployment_id="<github_run_id>"
} = 512
```

---

#### Gauge: `railway_deployment_cpu_percent`
Peak CPU during deployment

```
railway_deployment_cpu_percent{
  environment="production",
  deployment_id="<github_run_id>"
} = 75.2
```

---

## SLIs, SLOs & SLAs

### Service Level Indicators (SLIs)

| SLI | Definition | Measurement |
|-----|-----------|-------------|
| **Deployment Success Rate** | % of deployments that complete without rollback | `deployment_total{status="success"} / deployment_total` |
| **Time to Deploy (TTD)** | Duration from trigger to prod stabilization | `histogram_quantile(0.95, deployment_duration_seconds)` |
| **Post-Deployment Error Rate** | % of requests failing in 5min after deploy | `post_deployment_error_rate < 1%` |
| **Health Check Pass Rate** | % of health checks passing post-deploy | `1 - (api_health_check_failures / api_health_check_total)` |
| **Migration Success Rate** | % of database migrations completing | `migration_success_total / migration_total` |
| **Smoke Test Pass Rate** | % of smoke test suites passing | `smoke_test_success_total / smoke_test_total` |

### Service Level Objectives (SLOs)

| Objective | Target | Window | Error Budget |
|-----------|--------|--------|--------------|
| **Deployment Success** | 99.5% | Monthly | 1.5% = ~1 failed deploy/month |
| **TTD (p95)** | <12 minutes | Weekly | Tracks deployment velocity |
| **Post-Deploy Errors** | <1% | Per-deployment | If exceeded, rollback triggered |
| **Health Checks** | 99.9% | Per-deployment | Must verify before prod traffic |
| **Migrations** | 100% | Per-deployment | Rollback if migration fails |
| **Smoke Tests** | 99% | Per-deployment | >1% failure = rollback |

### Service Level Agreements (SLAs)

#### External SLA (Customer-Facing)
- Deployments should not cause > 5 minutes of unavailability
- System remains available during deployments (blue-green or canary)
- No data loss during migrations
- Feature rollout within 1 hour

#### Internal SLA (Operations)
- Page on-call if deployment fails
- Rollback within 2 minutes of failure detection
- Post-deployment validation within 15 minutes
- Root cause analysis within 1 hour

---

## Error Budget Allocation

**Monthly Error Budget: 0.5% of deployments can fail (2-3 failures)**

### Allocation Strategy
```
Total: 0.5% monthly budget = ~1.5 failed deployments

Breakdown:
- Deployment infrastructure failures: 0.2% (0.6 deployments)
  → Railway downtime, API timeout, health check failures

- Migration failures: 0.1% (0.3 deployments)
  → Database schema conflicts, migration bugs

- Post-deployment quality: 0.1% (0.3 deployments)
  → Smoke tests fail, high error rates detected

- Unclassified: 0.1% (0.3 deployments)
  → Rollback triggered by incident
```

### Actions When Budget Depleted
- Freeze risky deployments (feature flags only)
- Focus on stability and testing
- No major refactoring or infrastructure changes
- Resume risky deployments next month

---

## Alert & Escalation Rules

### Alert Levels

#### CRITICAL (Page immediately)
```
1. Deployment Failure
   Condition: deployment_total{status="failure"} for > 2 minutes
   Action: Page on-call engineer
   Runbook: "Deployment Failed - Check logs for stage failure"

2. Health Check Failure
   Condition: api_health_check failures for > 5 minutes post-deploy
   Action: Trigger automatic rollback

3. Migration Failure
   Condition: database_migration_lag_seconds > 120s OR error detected
   Action: Block further deployments, page DBA

4. Post-Deploy Error Spike
   Condition: post_deployment_error_rate > 5% for 2 minutes
   Action: Trigger automatic rollback
```

#### HIGH (Alert ops team)
```
1. Deployment Slow
   Condition: deployment_duration_seconds > 900s (15 min)
   Action: Send to ops Slack channel

2. Stage Timeout
   Condition: Any stage taking > 2x expected time
   Action: Alert with stage details

3. Smoke Test Failures
   Condition: > 50% smoke test failures
   Action: Alert, block production traffic
```

#### MEDIUM (Create ticket)
```
1. Health Check Latency High
   Condition: api_health_check_latency_ms > 1000ms
   Action: Create ops ticket

2. Deployment Frequency Anomaly
   Condition: < 1 deployment per day when expected > 2
   Action: Investigate delays
```

#### LOW (Log for analysis)
```
1. Minor Stage Delays
   Condition: Stage taking 1-2x expected time

2. Rollback Executed (non-critical)
   Condition: Rollback completed successfully
```

---

### Alert Rules (Prometheus)

```yaml
groups:
- name: deployment_alerts
  rules:

  - alert: DeploymentFailed
    expr: increase(deployment_total{status="failure"}[5m]) > 0
    for: 2m
    labels:
      severity: critical
      component: deployment_pipeline
    annotations:
      summary: "Deployment failed - {{ $labels.service }}"
      description: "Service {{ $labels.service }} failed at stage {{ $labels.stage }}"
      runbook: "docs/runbooks/DEPLOYMENT_FAILED.md"

  - alert: HealthCheckFailuresPostDeploy
    expr: increase(api_health_check_failures_total[5m]) > 5
    for: 3m
    labels:
      severity: critical
      component: deployment_health_check
    annotations:
      summary: "Health checks failing after deployment"
      description: "{{ $value }} health check failures in last 5m"
      runbook: "docs/runbooks/HEALTH_CHECK_FAILED.md"

  - alert: DatabaseMigrationSlow
    expr: deployment_stage_duration_seconds{stage="migration",status="success"} > 120
    for: 5m
    labels:
      severity: high
      component: database_migration
    annotations:
      summary: "Database migration taking > 2 minutes"
      description: "Migration duration: {{ $value }}s (threshold: 120s)"
      runbook: "docs/runbooks/MIGRATION_SLOW.md"

  - alert: DeploymentTakingTooLong
    expr: deployment_in_progress > 0 and time() - deployment_start_time > 900
    for: 2m
    labels:
      severity: high
      component: deployment_pipeline
    annotations:
      summary: "Deployment in progress for > 15 minutes"
      description: "Check deployment logs"

  - alert: PostDeploymentErrorRateHigh
    expr: post_deployment_error_rate > 0.05
    for: 2m
    labels:
      severity: critical
      component: post_deployment_health
    annotations:
      summary: "Error rate > 5% after deployment"
      description: "Error rate: {{ $value | humanizePercentage }}"
      runbook: "docs/runbooks/POST_DEPLOY_ERRORS.md"

  - alert: SmokeTestsFailingPostDeploy
    expr: increase(smoke_test_failures_total[5m]) > 5
    for: 2m
    labels:
      severity: high
      component: smoke_tests
    annotations:
      summary: "Smoke tests failing after deployment"
      description: "{{ $value }} test failures"

  - alert: RollbackTriggered
    expr: increase(deployment_rollback_total{status="success"}[1h]) > 0
    for: 1m
    labels:
      severity: high
      component: deployment_pipeline
    annotations:
      summary: "Deployment rollback executed"
      description: "Deployment {{ $labels.deployment_id }} was rolled back"
```

---

## Dashboard Design

### 1. Deployment Pipeline Dashboard
**Purpose:** Real-time deployment status overview
**URL:** `/d/deployment-pipeline`
**Target Audience:** DevOps, Platform Team

**Panels:**

```
Row 1: Deployment Status (Large Status Card)
┌─────────────────────────────────────────────┐
│ Current Deployment Status                   │
│ ─────────────────────────────────────────── │
│ Status: IN PROGRESS (8/12 min elapsed)      │
│ Deployment ID: run-12345                    │
│ Branch: main                                │
│ Triggered by: GitHub Actions                │
│ ─────────────────────────────────────────── │
│ Current Stage: Smoke Tests (5/10 min)       │
│ Progress: 67% ████████░                     │
└─────────────────────────────────────────────┘

Row 2: Deployment Timeline
┌─────────────────────────────────────────────────────┐
│ Stage Timeline                                      │
│ ───────────────────────────────────────────────── │
│ ✅ Docker Build (120s)           [████░░░░]        │
│ ✅ Push to Registry (45s)         [████░░░░]        │
│ ✅ Deploy to Railway (180s)       [████░░░░]        │
│ ✅ Health Check (15s, 1/5 ok)    [████░░░░]        │
│ ✅ Migrations (45s)               [████░░░░]        │
│ ⏳ Smoke Tests (5s / 10s)         [███░░░░░]        │
│ ⏸️  Waiting: Deploy Web (pending)  [░░░░░░░░]       │
└─────────────────────────────────────────────────────┘

Row 3: Stage Durations
┌─────────────────────────────────────────────┐
│ Stage Duration Comparison (last 10 deploys) │
│ ─────────────────────────────────────────── │
│ Build:     avg 98s   p95 120s   max 145s    │
│ Deploy:    avg 155s  p95 180s   max 210s    │
│ Health:    avg 8s    p95 15s    max 22s     │
│ Migration: avg 32s   p95 60s    max 89s     │
│ Smoke:     avg 45s   p95 78s    max 120s    │
│ WEB Deploy: avg 162s p95 210s   max 280s    │
│ ─────────────────────────────────────────── │
│ TOTAL:     avg 500s  p95 663s   max 816s    │
│            ~8.3min   ~11min     ~13.6min    │
└─────────────────────────────────────────────┘

Row 4: Error Details (if deployment failed)
┌─────────────────────────────────────────────┐
│ Failure Details                             │
│ ─────────────────────────────────────────── │
│ Stage: Smoke Tests                          │
│ Error: Test Failed - /health endpoint       │
│ Response Code: 503                          │
│ Error Message: API not responding           │
│ Timestamp: 2025-01-15 14:32:15 UTC         │
│ Action: Rollback triggered (RTB: 2m 15s)  │
└─────────────────────────────────────────────┘

Row 5: Deployment Metrics (Time Series)
┌────────────────────────────────────────┐
│ TTD Distribution (Last 7 Days)        │
│ Count: 42 deployments                  │
│ ├─ 300-600s:   2  (4%)    ▂           │
│ ├─ 600-900s:   8  (19%)   ▄           │
│ ├─ 900-1200s:  18 (43%)   ████        │
│ ├─ 1200-1500s: 10 (24%)   ██          │
│ ├─ 1500-1800s: 3  (7%)    ▁           │
│ └─ >1800s:     1  (2%)    ▁           │
│                                        │
│ p50: 985s (16.4 min)                  │
│ p95: 1345s (22.4 min)  ⚠️ Over SLO    │
│ p99: 1680s (28 min)    ⚠️ Over SLO    │
└────────────────────────────────────────┘
```

### 2. Deployment Success Rate Dashboard
**Purpose:** Track deployment reliability
**URL:** `/d/deployment-success-rate`

```
Row 1: Success Metrics (Stat Cards)
┌─────────────┬──────────────┬──────────────┐
│ Success     │ Rollbacks    │ Error Budget │
│ Rate        │ This Month   │ Remaining    │
│ ─────────── │ ──────────── │ ──────────── │
│ 98.5%       │ 1            │ 50% used     │
│ (66/67)     │ (1 rollback) │ 0.25% avail  │
│ ↑ +2.3%     │ ↓ -50%       │              │
│ w/o/w       │ w/o/w        │              │
└─────────────┴──────────────┴──────────────┘

Row 2: Deployment Status Pie Chart
┌──────────────────────────────────────┐
│ Deployments: Success / Failure       │
│                                      │
│   Success: 66 (98.5%) ███████████    │
│   Failure: 1  (1.5%)  █              │
│                                      │
│ Failure Details:                     │
│ • 1x Smoke test failure → Rollback   │
└──────────────────────────────────────┘

Row 3: Failure Root Causes (This Month)
┌─────────────────────────────────────┐
│ Failure Category | Count | %         │
│ ─────────────────┼───────┼──────     │
│ Timeout         | 2     | 50%       │
│ Health Check    | 1     | 25%       │
│ Migration       | 0     | 0%        │
│ Smoke Test      | 1     | 25%       │
│ Rollback        | 1     | 25%       │
└─────────────────────────────────────┘

Row 4: Error Budget Burndown
┌─────────────────────────────────────┐
│ Monthly Error Budget: 0.5% (1.5     │
│ deployments)                         │
│                                      │
│ Week 1: 1 failure (67% used)        │
│ Week 2: 0 failures                  │
│ Week 3: 0 failures                  │
│ Week 4: 0 failures (pending)        │
│                                      │
│ Budget Used:  0.25% (0.75 deps)     │
│ Budget Left:  0.25% (0.75 deps)     │
└─────────────────────────────────────┘
```

### 3. Post-Deployment Health Dashboard
**Purpose:** Monitor API/Web health after deployment
**URL:** `/d/post-deployment-health`

```
Row 1: Health Status (Current Deployment)
┌────────────────────────────────────┐
│ API Health:    ✅ HEALTHY (42ms)   │
│ Web Health:    ✅ HEALTHY (156ms)  │
│ Database:      ✅ CONNECTED        │
│ Error Rate:    ✅ 0.3% (<1%)       │
│ P95 Latency:   ✅ 245ms (<500ms)   │
└────────────────────────────────────┘

Row 2: Error Rate Trend (5min window)
┌─────────────────────────────────────┐
│ Error Rate After Deploy             │
│ 1.5%│                               │
│ 1.0%│    ╱╲    ╱╲                   │
│ 0.5%│───╱  ╲──╱  ╲───                │
│ 0.0%│_______________________         │
│     │ -5m  -2.5m  0m  +2.5m +5m     │
│     Deploy point: now →              │
│     Target: < 1%  ✅ OK              │
└─────────────────────────────────────┘

Row 3: Request Latency Distribution
┌─────────────────────────────────────┐
│ P50:  125ms ████░░░░░░░░░░░░░       │
│ P75:  245ms ████████░░░░░░░░░░       │
│ P95:  456ms ██████████░░░░░░░░░░     │
│ P99:  892ms ███████████░░░░░░░░░░    │
│                                      │
│ Median +30ms vs pre-deploy baseline  │
│ But normalizing after 2min ✅       │
└─────────────────────────────────────┘

Row 4: Service Dependencies
┌──────────────────────────────────────┐
│ Dependency | Status | Latency | +/-  │
│ ─────────────────────────────────────│
│ API        | 🟢 OK  | 42ms    | -5%  │
│ Database   | 🟢 OK  | 12ms    | +2%  │
│ Redis      | 🟢 OK  | 8ms     | -1%  │
│ Supabase   | 🟢 OK  | 78ms    | +15% │
│ Embedding  | 🟢 OK  | 234ms   | +8%  │
└──────────────────────────────────────┘
```

### 4. Database Migration Dashboard
**Purpose:** Track migration performance and success
**URL:** `/d/database-migrations`

```
Row 1: Current Migration Status
┌─────────────────────────────────────┐
│ Current Migration: v004_add_indexes  │
│ Status: IN PROGRESS (28s / 60s)     │
│ Duration: ███████░░░░░░░░░░░░░ 47%  │
│ Direction: UP ↑                      │
│ Estimated Time Remaining: 32s       │
└─────────────────────────────────────┘

Row 2: Migration History (Last 10)
┌─────────────────────────────────────┐
│ Migration | Duration | Status| Notes │
│ ─────────────────────────────────────│
│ v004      │ 28s      │ ⏳ Run │ 47%  │
│ v003      │ 45s      │ ✅ OK │ Done │
│ v002      │ 52s      │ ✅ OK │ Done │
│ v001      │ 38s      │ ✅ OK │ Done │
└─────────────────────────────────────┘

Row 3: Migration Duration Trend
┌─────────────────────────────────────┐
│ Duration (seconds) over time        │
│ 60s│     ╱╲                         │
│ 50s│────╱  ╲                        │
│ 40s│_______╲_____                   │
│     │ v001 v002 v003 v004           │
│ Avg: 40.75s (target: <60s) ✅      │
│ Max: 52s                            │
└─────────────────────────────────────┘

Row 4: Migration Success Rate
┌─────────────────────────────────────┐
│ Last 30 Days: 100% (45/45) ✅       │
│ Last 90 Days: 99.5% (134/135)       │
│                                      │
│ 1 failure: v087_schema_conflict     │
│ Resolved: Rollback, fixed, re-run   │
│                                      │
│ Error Budget: 0% used               │
└─────────────────────────────────────┘
```

### 5. Deployment Cost Dashboard
**Purpose:** Track infrastructure costs from deployments
**URL:** `/d/deployment-costs`

```
Row 1: Cost Summary
┌─────────────────────────────────┐
│ Total Deployment Cost (This Mo) │
│ ─────────────────────────────── │
│ Railway Compute:    $185.50     │
│ Vercel Builds:      $42.30      │
│ Database Resources: $28.50      │
│ Total:              $256.30     │
│ ─────────────────────────────── │
│ Avg Cost/Deploy:    $3.82       │
│ (67 deployments)                │
└─────────────────────────────────┘

Row 2: Cost by Service
┌─────────────────────────────────┐
│ Railway: $185.50 (72%)   ███████ │
│ Vercel:  $42.30  (17%)   ██      │
│ Database: $28.50 (11%)   █       │
└─────────────────────────────────┘

Row 3: Cost Trends
┌─────────────────────────────────┐
│ Daily Cost Average                │
│ $12│      ╱╲      ╱╲             │
│ $10│────╱  ╲────╱  ╲───          │
│ $8 │________________╲___          │
│    │ Week1 Week2 Week3 Week4      │
│ Trend: Stable, no anomalies ✅    │
└─────────────────────────────────┘

Row 4: Cost Breakdown by Component
┌──────────────────────────────────┐
│ Component      | Cost  | Per-Dep │
│ ────────────────────────────────  │
│ Railway CPU    | $120  | $1.79   │
│ Railway Memory | $65.5 | $0.98   │
│ Build Compute  | $42.3 | $0.63   │
│ Database Ops   | $28.5 | $0.43   │
│ Total          | $256.3| $3.83   │
└──────────────────────────────────┘
```

---

## Implementation Guide

### Phase 1: Instrumentation (Week 1)

#### Step 1: Create Metrics Collector Module
**File:** `/relay_ai/platform/observability/deployment_metrics.py`

```python
from prometheus_client import Counter, Gauge, Histogram, start_http_server
from datetime import datetime
from typing import Optional, Dict
import os

class DeploymentMetricsCollector:
    """Prometheus metrics for deployment pipeline"""

    def __init__(self, port: int = 8001):
        # Counters
        self.deployment_total = Counter(
            'deployment_total',
            'Total deployments',
            ['environment', 'deployment_id', 'service', 'stage', 'status']
        )

        self.deployment_errors_total = Counter(
            'deployment_errors_total',
            'Total deployment errors',
            ['environment', 'deployment_id', 'service', 'stage', 'error_type']
        )

        self.deployment_rollback_total = Counter(
            'deployment_rollback_total',
            'Total rollbacks',
            ['environment', 'deployment_id', 'reason', 'status']
        )

        self.smoke_test_failures_total = Counter(
            'smoke_test_failures_total',
            'Smoke test failures',
            ['environment', 'deployment_id', 'test_name']
        )

        self.migration_success_total = Counter(
            'migration_success_total',
            'Successful migrations',
            ['environment', 'deployment_id']
        )

        self.migration_failure_total = Counter(
            'migration_failure_total',
            'Failed migrations',
            ['environment', 'deployment_id']
        )

        # Gauges
        self.deployment_in_progress = Gauge(
            'deployment_in_progress',
            'Deployment in progress',
            ['environment', 'deployment_id', 'branch', 'triggered_by']
        )

        self.deployment_stage_duration_seconds = Gauge(
            'deployment_stage_duration_seconds',
            'Stage duration in seconds',
            ['environment', 'deployment_id', 'service', 'stage', 'status']
        )

        self.api_health_check_latency_ms = Gauge(
            'api_health_check_latency_ms',
            'Health check latency',
            ['environment', 'deployment_id', 'status']
        )

        self.post_deployment_error_rate = Gauge(
            'post_deployment_error_rate',
            'Error rate after deployment',
            ['environment', 'deployment_id', 'service']
        )

        self.database_migration_lag_seconds = Gauge(
            'database_migration_lag_seconds',
            'Migration duration',
            ['environment', 'deployment_id', 'migration_count']
        )

        # Histograms
        self.time_to_deploy_seconds = Histogram(
            'time_to_deploy_seconds',
            'Time to deploy',
            ['environment'],
            buckets=(60, 300, 600, 900, 1200, 1500, 1800)
        )

        # Start metrics server
        if port:
            start_http_server(port)

    def record_stage_start(self, environment: str, deployment_id: str,
                          service: str, stage: str):
        """Record stage start time"""
        self.deployment_in_progress.labels(
            environment=environment,
            deployment_id=deployment_id,
            branch=os.getenv('GITHUB_REF_NAME', 'unknown'),
            triggered_by='github_actions'
        ).set(1)

        # Store start time in environment for later duration calculation
        os.environ[f"STAGE_START_{stage}"] = str(datetime.utcnow().timestamp())

    def record_stage_complete(self, environment: str, deployment_id: str,
                             service: str, stage: str, status: str = 'success',
                             error_type: Optional[str] = None):
        """Record stage completion"""
        start_time_str = os.environ.get(f"STAGE_START_{stage}")
        if start_time_str:
            duration = datetime.utcnow().timestamp() - float(start_time_str)
            self.deployment_stage_duration_seconds.labels(
                environment=environment,
                deployment_id=deployment_id,
                service=service,
                stage=stage,
                status=status
            ).set(duration)

        # Record counter
        self.deployment_total.labels(
            environment=environment,
            deployment_id=deployment_id,
            service=service,
            stage=stage,
            status=status
        ).inc()

        # Record error if present
        if error_type:
            self.deployment_errors_total.labels(
                environment=environment,
                deployment_id=deployment_id,
                service=service,
                stage=stage,
                error_type=error_type
            ).inc()

    def record_health_check(self, environment: str, deployment_id: str,
                           latency_ms: float, status: str):
        """Record health check result"""
        self.api_health_check_latency_ms.labels(
            environment=environment,
            deployment_id=deployment_id,
            status=status
        ).set(latency_ms)

    def record_migration_complete(self, environment: str, deployment_id: str,
                                 duration_seconds: float, success: bool,
                                 migration_count: int):
        """Record migration completion"""
        self.database_migration_lag_seconds.labels(
            environment=environment,
            deployment_id=deployment_id,
            migration_count=str(migration_count)
        ).set(duration_seconds)

        if success:
            self.migration_success_total.labels(
                environment=environment,
                deployment_id=deployment_id
            ).inc()
        else:
            self.migration_failure_total.labels(
                environment=environment,
                deployment_id=deployment_id
            ).inc()

    def record_deployment_complete(self, environment: str, deployment_id: str,
                                  total_duration_seconds: float):
        """Record total deployment duration"""
        self.time_to_deploy_seconds.labels(
            environment=environment
        ).observe(total_duration_seconds)

        self.deployment_in_progress.labels(
            environment=environment,
            deployment_id=deployment_id,
            branch=os.getenv('GITHUB_REF_NAME', 'unknown'),
            triggered_by='github_actions'
        ).set(0)

    def record_rollback(self, environment: str, deployment_id: str,
                       reason: str, success: bool):
        """Record rollback event"""
        self.deployment_rollback_total.labels(
            environment=environment,
            deployment_id=deployment_id,
            reason=reason,
            status='success' if success else 'failure'
        ).inc()

# Global instance
_collector = None

def get_collector() -> DeploymentMetricsCollector:
    global _collector
    if _collector is None:
        _collector = DeploymentMetricsCollector(
            port=int(os.getenv('METRICS_PORT', 8001))
        )
    return _collector
```

#### Step 2: Update GitHub Actions Workflows
**File:** `/.github/workflows/deploy-full-stack.yml` (instrumentation additions)

```yaml
env:
  DEPLOYMENT_ID: ${{ github.run_id }}
  ENVIRONMENT: production
  METRICS_ENDPOINT: https://relay-prometheus-production.up.railway.app

jobs:
  deploy-api:
    steps:
      - name: Record deployment start
        run: |
          cat > /tmp/metrics.sh <<'EOF'
          #!/bin/bash
          export DEPLOYMENT_ID="${{ env.DEPLOYMENT_ID }}"
          export ENVIRONMENT="production"
          export SERVICE="api"
          export STAGE="$1"
          export STATUS="$2"
          export ERROR_TYPE="${3:-}"

          # Push metrics to Prometheus pushgateway
          cat <<METRICS | curl --data-binary @- http://pushgateway:9091/metrics/job/deployment
          # HELP deployment_stage_duration_seconds Deployment stage duration
          # TYPE deployment_stage_duration_seconds gauge
          deployment_stage_duration_seconds{environment="${ENVIRONMENT}",deployment_id="${DEPLOYMENT_ID}",service="${SERVICE}",stage="${STAGE}",status="${STATUS}"} ${DURATION}
          METRICS
          EOF
          chmod +x /tmp/metrics.sh

      - name: Deploy to Railway
        id: deploy
        env:
          RAILWAY_TOKEN: ${{ secrets.RAILWAY_TOKEN }}
        run: |
          export DEPLOY_START=$(date +%s%N | cut -b1-13)

          # Deployment logic
          railway link
          railway up --detach
          sleep 60
          DEPLOYMENT_ID=$(railway status --json 2>/dev/null | jq -r '.latestDeployment.id // "unknown"')

          export DEPLOY_END=$(date +%s%N | cut -b1-13)
          export DEPLOY_DURATION=$(( ($DEPLOY_END - $DEPLOY_START) / 1000 ))

          # Record metric
          echo "Deployment took ${DEPLOY_DURATION}ms"
          echo "deployment_id=$DEPLOYMENT_ID" >> $GITHUB_OUTPUT
```

#### Step 3: Instrument Deployment Script
**File:** `/scripts/deploy-all.sh` (add metrics collection)

```bash
# Add at top of script
METRICS_ENDPOINT="${METRICS_ENDPOINT:-http://localhost:9091}"
DEPLOYMENT_ID="${DEPLOYMENT_ID:-$(date +%s)}"
ENVIRONMENT="${ENVIRONMENT:-production}"

record_metric() {
    local stage="$1"
    local status="$2"
    local duration="$3"
    local service="$4"

    # Push to Prometheus Pushgateway
    cat <<METRICS | curl --data-binary @- "${METRICS_ENDPOINT}/metrics/job/deployment/instance/${DEPLOYMENT_ID}"
deployment_stage_duration_seconds{stage="${stage}",status="${status}",service="${service}",environment="${ENVIRONMENT}"} ${duration}
METRICS
}

# Modify deploy_railway function
deploy_railway() {
    log_info "Deploying to Railway..."

    STAGE_START=$(date +%s%N | cut -b1-13)

    # ... existing deployment logic ...

    STAGE_END=$(date +%s%N | cut -b1-13)
    STAGE_DURATION=$(echo "scale=3; ($STAGE_END - $STAGE_START) / 1000" | bc)

    record_metric "deploy_railway" "success" "$STAGE_DURATION" "api"
}
```

#### Step 4: Smoke Test Metrics
**File:** `/scripts/ci_smoke_tests.sh` (add test metrics)

```bash
# Add metrics recording for each test
run_test() {
    local test_name="$1"
    local test_cmd="$2"

    TEST_START=$(date +%s%N | cut -b1-13)

    if eval "$test_cmd"; then
        TEST_END=$(date +%s%N | cut -b1-13)
        TEST_DURATION=$(echo "scale=3; ($TEST_END - $TEST_START) / 1000" | bc)

        echo "✓ Test $test_name passed (${TEST_DURATION}ms)"

        # Record success metric
        curl -X POST "${METRICS_ENDPOINT}/metrics/job/smoke_tests" \
            --data "smoke_test_result{test=\"${test_name}\",status=\"pass\"} 1"
    else
        TEST_END=$(date +%s%N | cut -b1-13)
        TEST_DURATION=$(echo "scale=3; ($TEST_END - $TEST_START) / 1000" | bc)

        echo "✗ Test $test_name failed (${TEST_DURATION}ms)"

        # Record failure metric
        curl -X POST "${METRICS_ENDPOINT}/metrics/job/smoke_tests" \
            --data "smoke_test_failures_total{test=\"${test_name}\"} 1"

        return 1
    fi
}
```

---

### Phase 2: Prometheus Configuration (Week 2)

#### File: `/config/prometheus/prometheus-deployment-alerts.yml`

```yaml
groups:
- name: deployment_alerts
  interval: 30s

  rules:
  # ========================================
  # CRITICAL ALERTS
  # ========================================

  - alert: DeploymentFailed
    expr: increase(deployment_total{status="failure"}[5m]) > 0
    for: 2m
    labels:
      severity: critical
      component: deployment_pipeline
      oncall: yes
    annotations:
      summary: "CRITICAL: Deployment failed - {{ $labels.service }}"
      description: |
        Service: {{ $labels.service }}
        Stage: {{ $labels.stage }}
        Deployment ID: {{ $labels.deployment_id }}
        Error Type: {{ $labels.error_type }}

        Action:
        1. Check deployment logs: github.com/relay-ai/actions/runs/{{ $labels.deployment_id }}
        2. Identify failure reason (build/deploy/test/rollback)
        3. If available, check rollback status
        4. If rollback failed, perform manual rollback
      runbook_url: "https://docs.relay.ai/runbooks/DEPLOYMENT_FAILED"
      dashboard_url: "https://grafana/d/deployment-pipeline"

  - alert: HealthCheckFailuresPostDeploy
    expr: increase(api_health_check_failures_total[5m]) > 5
    for: 3m
    labels:
      severity: critical
      component: deployment_health_check
      oncall: yes
    annotations:
      summary: "CRITICAL: API health checks failing after deployment"
      description: |
        Deployment ID: {{ $labels.deployment_id }}
        Failed Checks: {{ $value }} in last 5m
        Last Status: {{ $labels.status }}

        Action:
        1. Check API logs for errors
        2. Verify database connectivity
        3. Check external dependencies (Supabase, Redis)
        4. Trigger automatic rollback if health not restored in 2min
      runbook_url: "https://docs.relay.ai/runbooks/HEALTH_CHECK_FAILED"

  - alert: PostDeploymentErrorRateHigh
    expr: post_deployment_error_rate > 0.05
    for: 2m
    labels:
      severity: critical
      component: post_deployment_health
      oncall: yes
    annotations:
      summary: "CRITICAL: Error rate > 5% after deployment"
      description: |
        Deployment ID: {{ $labels.deployment_id }}
        Error Rate: {{ $value | humanizePercentage }}
        Service: {{ $labels.service }}

        Action:
        1. Check error logs for common pattern
        2. Identify affected endpoints
        3. Trigger rollback if error rate doesn't drop below 1% in 3min
        4. Post-incident review required
      runbook_url: "https://docs.relay.ai/runbooks/POST_DEPLOY_HIGH_ERROR"

  - alert: DatabaseMigrationFailed
    expr: increase(migration_failure_total[5m]) > 0
    for: 2m
    labels:
      severity: critical
      component: database_migration
      oncall: yes
    annotations:
      summary: "CRITICAL: Database migration failed"
      description: |
        Deployment ID: {{ $labels.deployment_id }}
        Environment: {{ $labels.environment }}

        Action:
        1. Check migration error logs
        2. Verify database state
        3. Trigger rollback
        4. Contact DBA for manual recovery if needed
      runbook_url: "https://docs.relay.ai/runbooks/MIGRATION_FAILED"

  # ========================================
  # HIGH ALERTS
  # ========================================

  - alert: DeploymentTakingTooLong
    expr: (time() - deployment_start_time) > 900 and deployment_in_progress > 0
    for: 2m
    labels:
      severity: high
      component: deployment_pipeline
    annotations:
      summary: "HIGH: Deployment in progress for > 15 minutes"
      description: |
        Deployment ID: {{ $labels.deployment_id }}
        Elapsed: {{ (time() - deployment_start_time) | humanizeDuration }}

        Action:
        1. Check which stage is running
        2. Review logs for hangs or timeouts
        3. Consider manual intervention if timeout persists
      runbook_url: "https://docs.relay.ai/runbooks/DEPLOYMENT_TIMEOUT"

  - alert: DatabaseMigrationSlow
    expr: deployment_stage_duration_seconds{stage="migration"} > 120
    for: 2m
    labels:
      severity: high
      component: database_migration
    annotations:
      summary: "HIGH: Database migration taking > 2 minutes"
      description: |
        Duration: {{ $value }}s (threshold: 120s)
        Deployment: {{ $labels.deployment_id }}

        Possible causes:
        - Large schema changes with data transformation
        - Database under heavy load
        - Lock contention on tables

        Action:
        1. Check current queries: SELECT * FROM pg_stat_activity
        2. Identify blocking locks
        3. If > 5min, consider killing transaction and manual recovery
      runbook_url: "https://docs.relay.ai/runbooks/MIGRATION_SLOW"

  - alert: SmokeTestsFailingPostDeploy
    expr: increase(smoke_test_failures_total[5m]) > 5
    for: 2m
    labels:
      severity: high
      component: smoke_tests
    annotations:
      summary: "HIGH: {{ $value }} smoke tests failing after deployment"
      description: |
        Deployment ID: {{ $labels.deployment_id }}
        Failed Tests: {{ $value }}

        Action:
        1. Review test failures
        2. Determine if deployment caused or pre-existing
        3. If deployment caused, trigger rollback
      runbook_url: "https://docs.relay.ai/runbooks/SMOKE_TESTS_FAILED"

  # ========================================
  # MEDIUM ALERTS
  # ========================================

  - alert: DeploymentSlightlyBehindSchedule
    expr: (time() - deployment_start_time) > 600 and deployment_in_progress > 0
    for: 1m
    labels:
      severity: medium
      component: deployment_pipeline
    annotations:
      summary: "MEDIUM: Deployment in progress for > 10 minutes"
      description: |
        Deployment ID: {{ $labels.deployment_id }}
        Elapsed: {{ (time() - deployment_start_time) | humanizeDuration }}

        This is within acceptable range but worth monitoring.
      runbook_url: "https://docs.relay.ai/runbooks/DEPLOYMENT_SLOW"

  - alert: HealthCheckLatencyHigh
    expr: api_health_check_latency_ms > 1000
    for: 3m
    labels:
      severity: medium
      component: deployment_health_check
    annotations:
      summary: "MEDIUM: API health check latency > 1000ms"
      description: |
        Current Latency: {{ $value }}ms
        Deployment: {{ $labels.deployment_id }}
      runbook_url: "https://docs.relay.ai/runbooks/HEALTH_CHECK_SLOW"

# Recording rules for pre-aggregation
- name: deployment_recording
  interval: 30s
  rules:

  - record: deployment:success_rate:5m
    expr: |
      count(increase(deployment_total{status="success"}[5m]))
      /
      count(increase(deployment_total[5m]))

  - record: deployment:avg_duration:1h
    expr: |
      avg(deployment_stage_duration_seconds) by (stage, service)

  - record: deployment:error_budget:used
    expr: |
      count(increase(deployment_total{status="failure"}[30d]))
      /
      count(increase(deployment_total[30d]))
```

---

### Phase 3: Grafana Dashboards (Week 2-3)

Create dashboard JSON files in `/config/grafana/dashboards/`:

#### File: `/config/grafana/dashboards/deployment-pipeline.json`

```json
{
  "dashboard": {
    "title": "Deployment Pipeline",
    "tags": ["deployment", "pipeline"],
    "timezone": "browser",
    "panels": [
      {
        "title": "Current Deployment Status",
        "type": "stat",
        "targets": [
          {
            "expr": "deployment_in_progress{environment='production'}"
          }
        ],
        "fieldConfig": {
          "defaults": {
            "custom": {},
            "color": {
              "mode": "thresholds"
            },
            "thresholds": {
              "steps": [
                {"color": "green", "value": 0},
                {"color": "blue", "value": 0.5},
                {"color": "red", "value": 1}
              ]
            }
          }
        }
      },
      {
        "title": "Deployment Duration (Last 10)",
        "type": "graph",
        "targets": [
          {
            "expr": "time_to_deploy_seconds_sum / time_to_deploy_seconds_count"
          }
        ]
      },
      {
        "title": "Stage Duration Heatmap",
        "type": "heatmap",
        "targets": [
          {
            "expr": "deployment_stage_duration_seconds"
          }
        ]
      }
    ]
  }
}
```

---

### Phase 4: Integration with Existing Systems (Week 3)

#### Connect to Prometheus on Railway

Update `/config/prometheus/prometheus.yml`:

```yaml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

alerting:
  alertmanagers:
    - static_configs:
        - targets:
            - relay-alertmanager-production.up.railway.app:9093

rule_files:
  - /etc/prometheus/deployment-alerts.yml
  - /etc/prometheus/existing-alerts.yml

scrape_configs:
  # Existing scrapers...

  # Deployment metrics (from CI/CD)
  - job_name: 'deployment-pipeline'
    static_configs:
      - targets: ['localhost:8001']
    relabel_configs:
      - source_labels: [__address__]
        target_label: instance
        regex: '([^:]+)(?::\d+)?'
        replacement: '${1}'

  # Pushgateway for CI/CD metrics
  - job_name: 'pushgateway'
    static_configs:
      - targets: ['pushgateway:9091']
    honor_labels: true
    metric_relabel_configs:
      - source_labels: [__name__]
        regex: 'deployment_.*'
        action: keep
```

---

### Phase 5: Runbook Documentation (Week 3-4)

Create incident response runbooks:

#### File: `/docs/runbooks/DEPLOYMENT_FAILED.md`

```markdown
# Runbook: Deployment Failed

## Summary
A deployment has failed at one of the pipeline stages (build, deploy, health check, migration, or smoke test).

## Severity
CRITICAL - Page on-call engineer immediately

## Detection
Alert: `DeploymentFailed`
- Condition: `deployment_total{status="failure"}` triggered
- Window: 2 minutes

## Root Cause Analysis

### Step 1: Identify Failure Stage
```bash
# Check which stage failed
curl https://relay-prometheus-production.up.railway.app/api/v1/query \
  'deployment_total{status="failure"}' | jq '.data.result[0].metric.stage'
```

Expected stages:
- `build` → Docker image build failed
- `push` → Registry push failed
- `deploy_railway` → Railway deployment rejected
- `health_check` → API not responding
- `migration` → Database schema error
- `smoke_test` → Test assertion failed
- `deploy_web` → Vercel build failed
- `rollback` → Rollback itself failed (CRITICAL)

### Step 2: Check Logs
```bash
# GitHub Actions logs
https://github.com/relay-ai/openai-agents-workflows-2025.09.28-v1/actions/runs/<DEPLOYMENT_ID>

# Railway logs
railway logs --follow

# Database logs (if migration failed)
SELECT * FROM pg_stat_activity WHERE state != 'idle';
```

### Step 3: Determine Action

**If health check failed:**
```bash
# Test manually
curl -v https://relay-production-f2a6.up.railway.app/health
curl -v https://relay-production-f2a6.up.railway.app/api/v1/knowledge/health

# Check API status
docker ps | grep relay  # or check Railway dashboard
```

**If migration failed:**
```bash
# Check migration status
alembic current
alembic history -r20  # Show last 20 migrations

# Manual rollback
alembic downgrade -1

# Verify rollback
alembic current
```

**If smoke test failed:**
```bash
# Re-run specific test
bash scripts/ci_smoke_tests.sh

# Debug failed endpoint
curl -v -X POST https://relay-production-f2a6.up.railway.app/api/v1/test \
  -H "Content-Type: application/json" \
  -d '{"test": "value"}'
```

## Resolution Steps

### Option 1: Automatic Rollback (Recommended)
The system should auto-rollback, but if not:

```bash
# Trigger rollback script
DEPLOYMENT_ID=<failed_id> \
PREVIOUS_DEPLOYMENT_ID=<last_good_id> \
  python scripts/rollback_release.py --deployment-id "$DEPLOYMENT_ID"

# Verify rollback
curl https://relay-production-f2a6.up.railway.app/health
```

### Option 2: Manual Rollback (If Auto-Rollback Fails)
```bash
# On Railway dashboard:
# 1. Go to relay-api service
# 2. Select "Deployments" tab
# 3. Click last known-good deployment
# 4. Click "Redeploy"

# Verify
curl https://relay-production-f2a6.up.railway.app/health
```

### Option 3: Fix & Retry
If the issue is external (API dependency down, schema conflict resolved):

```bash
# Fix the issue in code/config
git commit -am "fix: deployment issue"
git push origin main

# Manually trigger workflow
gh workflow run deploy-full-stack.yml --ref main

# Monitor
gh run watch
```

## Post-Incident

1. **Communication**
   - Update status page
   - Notify affected users via Slack
   - Document resolution in incident ticket

2. **Analysis**
   - Review logs for root cause
   - Identify if code change or infrastructure issue
   - Document findings in incident review

3. **Prevention**
   - Add test coverage for failed scenario
   - Update documentation if deployment process changed
   - Consider adding pre-deployment validation

4. **Metrics**
   - Review: `deployment_total{status="failure"}`
   - Check error budget consumption
   - If > 0.5% monthly budget used, prepare stability sprint

## Escalation

- **5 minutes:** Page on-call engineer
- **10 minutes:** If not resolved, page on-call lead/manager
- **15 minutes:** If still ongoing, page infrastructure team lead
- **20 minutes+:** Critical incident bridge + VP Engineering

## Related Dashboards
- [Deployment Pipeline](https://grafana/d/deployment-pipeline)
- [Post-Deployment Health](https://grafana/d/post-deployment-health)
- [Error Rate Trend](https://grafana/d/error-trends)
```

---

## Metrics Export Strategy

### Prometheus Pushgateway Setup

For CI/CD systems that cannot run long-lived Prometheus exporters, use Pushgateway:

```yaml
# Docker Compose addition
prometheus-pushgateway:
  image: prom/pushgateway:latest
  ports:
    - "9091:9091"
  volumes:
    - pushgateway_data:/pushgateway
  command:
    - '--persistence.file=/pushgateway/metrics'
    - '--persistence.interval=5m'
```

### Metric Lifecycle
```
1. CI/CD Job Start
   → Export metrics to Pushgateway

2. Pushgateway holds for scrape
   → Default: 5 minutes TTL

3. Prometheus scrapes Pushgateway
   → Every 15-30 seconds

4. Grafana queries Prometheus
   → Instant: metrics available < 1 minute after job complete

5. Alertmanager evaluates
   → Checks rules every 30 seconds
   → Alert fires if threshold exceeded
```

---

## Expected Metrics Output

### Sample Metrics During Deployment

```
# At deployment start
deployment_in_progress{environment="production",deployment_id="run-12345",branch="main",triggered_by="github_actions"} 1
deployment_stage_duration_seconds{environment="production",deployment_id="run-12345",service="api",stage="build",status="in_progress"} 0

# After build completes
deployment_total{environment="production",deployment_id="run-12345",service="api",stage="build",status="success"} 1
deployment_stage_duration_seconds{environment="production",deployment_id="run-12345",service="api",stage="build",status="success"} 95.4

# After health check passes
deployment_total{environment="production",deployment_id="run-12345",service="api",stage="health_check",status="success"} 1
deployment_stage_duration_seconds{environment="production",deployment_id="run-12345",service="api",stage="health_check",status="success"} 8.2
api_health_check_latency_ms{environment="production",deployment_id="run-12345",status="healthy"} 42

# After migration
migration_success_total{environment="production",deployment_id="run-12345"} 1
database_migration_lag_seconds{environment="production",deployment_id="run-12345",migration_count="5"} 23.4

# At deployment end
time_to_deploy_seconds_bucket{le="900",environment="production"} 1
deployment_in_progress{environment="production",deployment_id="run-12345",branch="main",triggered_by="github_actions"} 0
```

---

## Validation Checklist

Before going live:

- [ ] Metrics collector module created and tested
- [ ] GitHub Actions workflows instrumented
- [ ] Deploy script exports metrics to Pushgateway
- [ ] Prometheus scrape config includes new metrics
- [ ] Alert rules configured and tested
- [ ] Grafana dashboards created and validated
- [ ] Runbooks written and reviewed
- [ ] Team trained on dashboard interpretation
- [ ] Alert routing configured (Slack, PagerDuty)
- [ ] Test deployment with metrics collection
- [ ] Verify metrics appear in Grafana within 2 minutes
- [ ] Verify rollback metrics recorded
- [ ] Cost metrics tracked
- [ ] SLO baselines established

---

## Success Criteria

✅ **Implementation Complete When:**

1. **Visibility:** All deployment stages tracked with < 1 minute latency
2. **Reliability:** 95%+ of deployments recorded in Prometheus
3. **Alerting:** Alerts fire correctly for failures within 2 minutes
4. **Dashboards:** Team can diagnose deployment issues in < 5 minutes
5. **Documentation:** Runbooks cover all failure scenarios
6. **Cost:** Observability overhead < 1% of deployment costs
7. **SLOs:** TTD p95 tracked and trending toward <12 minutes
8. **Buy-in:** Team uses dashboards daily for deployment monitoring

---

## Next Steps

1. **Week 1:** Implement metrics collector and basic instrumentation
2. **Week 2:** Deploy Prometheus alerts and Grafana dashboards
3. **Week 3:** Write runbooks and train team
4. **Week 4:** Refine thresholds based on real deployment data
5. **Month 2:** Integrate cost analytics and forecasting
6. **Month 3:** Add automated remediation (auto-rollback on thresholds)

---

**Document Maintained By:** Platform Engineering
**Last Updated:** 2025-01-15
**Review Frequency:** Monthly
**Contact:** @platform-oncall on Slack
