# Deployment Observability - Implementation Guide

**Document Version:** 1.0
**Status:** Ready for Implementation
**Estimated Effort:** 5-10 days (3 developers)
**Target Completion:** End of Sprint

---

## Quick Start

### For Impatient Readers (5 min)

1. **What's being added?** → Full observability of the deployment pipeline (CI/CD to prod)
2. **Why?** → Know instantly when deployments fail, at which stage, and why
3. **How?** → Add metrics collection to workflows, push to Prometheus Pushgateway, visualize in Grafana
4. **Cost?** → < 5% of deployment infrastructure cost for observability
5. **Timeline?** → 1-2 weeks to full implementation

**Next Action:** Read "Phase 1: Quick Win" section below

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│ GitHub Actions Workflow (Main Entry Point)                      │
│ ├─ Triggered by: git push origin main                           │
│ ├─ File: .github/workflows/deploy-full-stack.yml               │
│ └─ Duration: ~10-15 minutes total                              │
└────────────────┬──────────────────────────────────────────────┘
                 │
        ┌────────┴──────────────────────┐
        │                               │
   ┌────▼──────────┐             ┌─────▼──────────┐
   │ Deploy API    │             │ Deploy Web     │
   │ (Railway)     │             │ (Vercel)       │
   │ Time: 5-10m   │             │ Time: 3-8m     │
   │               │             │                │
   │ ├─ Build      │             │ ├─ Install     │
   │ ├─ Deploy     │             │ ├─ Build       │
   │ ├─ Health     │             │ ├─ Deploy      │
   │ └─ Migrate    │             │ └─ Verify      │
   └────┬──────────┘             └─────┬──────────┘
        │                               │
        └───────────────┬───────────────┘
                        │
            ┌───────────▼──────────┐
            │ Smoke Tests          │
            │ (Parallel after both)│
            │ Time: 2-5 min        │
            └───────────┬──────────┘
                        │
        ┌───────────────▼──────────────┐
        │ Metrics Export              │
        ├─ Stage duration            │
        ├─ Success/failure status    │
        ├─ Error types               │
        ├─ Health check results      │
        └─ Post-deploy validation    │
                        │
        ┌───────────────▼──────────────┐
        │ Prometheus Pushgateway       │
        │ (Temporary storage)          │
        │ TTL: 5 minutes               │
        └───────────────┬──────────────┘
                        │
        ┌───────────────▼──────────────┐
        │ Prometheus Server (Railway)  │
        │ (Scrapes every 15s)          │
        │ url: relay-prometheus...     │
        └───────────────┬──────────────┘
                        │
        ┌───────────────▼──────────────┐
        │ Grafana Dashboards (Railway) │
        │ url: relay-grafana...        │
        │                              │
        │ Shows:                       │
        │ - Current deployment status  │
        │ - Stage timeline             │
        │ - Error details (if failed)  │
        │ - Health trends              │
        └──────────────────────────────┘
```

---

## Phase 1: Quick Win (Day 1)

**Goal:** Get metrics flowing to Prometheus in < 1 day

### Step 1a: Create Bash Metrics Helper

**File:** `/scripts/metrics_utils.sh`

```bash
#!/bin/bash
# Metrics utilities for deployment pipeline

set -e

# Configuration
PUSHGATEWAY_URL="${PUSHGATEWAY_URL:-http://localhost:9091}"
DEPLOYMENT_ID="${DEPLOYMENT_ID:-$(date +%s)}"
ENVIRONMENT="${ENVIRONMENT:-production}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# ===== METRIC RECORDING FUNCTIONS =====

# Record a metric to Prometheus Pushgateway
# Usage: push_metric "metric_name" "value" "labels"
push_metric() {
    local metric_name="$1"
    local metric_value="$2"
    local labels="$3"

    if [ -z "$PUSHGATEWAY_URL" ] || [ "$PUSHGATEWAY_URL" = "disabled" ]; then
        echo -e "${YELLOW}[METRICS]${NC} Metrics disabled, skipping push"
        return 0
    fi

    local job_name="deployment-pipeline"
    local instance="$DEPLOYMENT_ID"

    cat <<METRICS | curl --data-binary @- \
        "${PUSHGATEWAY_URL}/metrics/job/${job_name}/instance/${instance}" \
        2>/dev/null || echo "Warning: Failed to push metric $metric_name"

# HELP ${metric_name} Deployment metric
# TYPE ${metric_name} gauge
${metric_name}${labels} ${metric_value}
METRICS
}

# Record stage completion with duration
# Usage: record_stage "build" "api" "success" "95.4"
record_stage() {
    local stage="$1"
    local service="$2"
    local status="$3"
    local duration="$4"

    local labels="{stage=\"${stage}\",service=\"${service}\",status=\"${status}\",environment=\"${ENVIRONMENT}\",deployment_id=\"${DEPLOYMENT_ID}\"}"

    push_metric "deployment_stage_duration_seconds" "$duration" "$labels"
    echo -e "${GREEN}[METRICS]${NC} Stage: $stage - $status ($duration s)"
}

# Record error
# Usage: record_error "build" "api" "timeout"
record_error() {
    local stage="$1"
    local service="$2"
    local error_type="$3"

    local labels="{stage=\"${stage}\",service=\"${service}\",error_type=\"${error_type}\",environment=\"${ENVIRONMENT}\",deployment_id=\"${DEPLOYMENT_ID}\"}"

    push_metric "deployment_errors_total" "1" "$labels"
    echo -e "${RED}[METRICS]${NC} Error: $stage - $error_type"
}

# Record health check
# Usage: record_health_check "42" "healthy"
record_health_check() {
    local latency_ms="$1"
    local status="$2"

    local labels="{status=\"${status}\",environment=\"${ENVIRONMENT}\",deployment_id=\"${DEPLOYMENT_ID}\"}"

    push_metric "api_health_check_latency_ms" "$latency_ms" "$labels"
    echo -e "${GREEN}[METRICS]${NC} Health: $status ($latency_ms ms)"
}

# Record deployment start
# Usage: record_deployment_start "main"
record_deployment_start() {
    local branch="$1"

    local labels="{environment=\"${ENVIRONMENT}\",deployment_id=\"${DEPLOYMENT_ID}\",branch=\"${branch}\",triggered_by=\"github_actions\"}"

    push_metric "deployment_in_progress" "1" "$labels"
    echo -e "${GREEN}[METRICS]${NC} Deployment started: $DEPLOYMENT_ID"
}

# Record deployment complete
# Usage: record_deployment_complete "456.2"
record_deployment_complete() {
    local total_duration="$1"

    local labels="{environment=\"${ENVIRONMENT}\",deployment_id=\"${DEPLOYMENT_ID}\"}"

    push_metric "deployment_in_progress" "0" "$labels"
    push_metric "time_to_deploy_seconds" "$total_duration" "{environment=\"${ENVIRONMENT}\"}"

    echo -e "${GREEN}[METRICS]${NC} Deployment complete: $total_duration s"
}

# Record rollback
# Usage: record_rollback "health_check_failed" "success"
record_rollback() {
    local reason="$1"
    local status="$2"

    local labels="{deployment_id=\"${DEPLOYMENT_ID}\",reason=\"${reason}\",status=\"${status}\",environment=\"${ENVIRONMENT}\"}"

    push_metric "deployment_rollback_total" "1" "$labels"
    echo -e "${YELLOW}[METRICS]${NC} Rollback: $reason ($status)"
}

export -f push_metric record_stage record_error record_health_check
export -f record_deployment_start record_deployment_complete record_rollback
```

### Step 1b: Update Deploy Script

**File:** `/scripts/deploy-all.sh`

Add at the top (after color definitions):

```bash
# Load metrics utilities
source "$(dirname "$0")/metrics_utils.sh"

# Set metrics environment
export DEPLOYMENT_ID="${DEPLOYMENT_ID:-$GITHUB_RUN_ID}"
export ENVIRONMENT="${ENVIRONMENT:-production}"
export PUSHGATEWAY_URL="${PUSHGATEWAY_URL:-http://localhost:9091}"

DEPLOY_START=$(date +%s%N | cut -b1-13)
record_deployment_start "$(git rev-parse --abbrev-ref HEAD)"
```

Modify `deploy_railway()`:

```bash
deploy_railway() {
    log_info "Deploying to Railway..."

    STAGE_START=$(date +%s%N | cut -b1-13)

    cd "$PROJECT_ROOT"

    # ... existing deployment logic ...

    STAGE_END=$(date +%s%N | cut -b1-13)
    STAGE_DURATION=$(echo "scale=3; ($STAGE_END - $STAGE_START) / 1000" | bc)

    record_stage "deploy_railway" "api" "success" "$STAGE_DURATION"
}
```

Modify `deploy_vercel()`:

```bash
deploy_vercel() {
    log_info "Deploying web app to Vercel..."

    STAGE_START=$(date +%s%N | cut -b1-13)

    cd "$PROJECT_ROOT/relay_ai/product/web"

    # ... existing deployment logic ...

    STAGE_END=$(date +%s%N | cut -b1-13)
    STAGE_DURATION=$(echo "scale=3; ($STAGE_END - $STAGE_START) / 1000" | bc)

    record_stage "deploy_vercel" "web" "success" "$STAGE_DURATION"
}
```

Update end of main script:

```bash
# At very end of script, record total duration
DEPLOY_END=$(date +%s%N | cut -b1-13)
TOTAL_DURATION=$(echo "scale=3; ($DEPLOY_END - $DEPLOY_START) / 1000" | bc)
record_deployment_complete "$TOTAL_DURATION"

log_success "Deployment script completed (${TOTAL_DURATION}s total)"
```

### Step 1c: Test Locally

```bash
# Set environment
export PUSHGATEWAY_URL="http://localhost:9091"
export DEPLOYMENT_ID="local-test-001"
export ENVIRONMENT="staging"

# Run with --smoke mode to test metrics
bash scripts/deploy-all.sh --smoke

# Check metrics were pushed
curl http://localhost:9091/api/v1/metrics/job/deployment-pipeline
```

**Expected Output:**
```
deployment_stage_duration_seconds{...} 45.2
deployment_in_progress{...} 0
time_to_deploy_seconds{...} 450
```

---

## Phase 2: GitHub Actions Integration (Day 2)

### Step 2a: Create GitHub Actions Wrapper Script

**File:** `scripts/deployment_metrics_wrapper.sh`

```bash
#!/bin/bash
# Wrapper script for GitHub Actions to collect deployment metrics

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# GitHub Actions environment variables
export DEPLOYMENT_ID="${GITHUB_RUN_ID}"
export GITHUB_REF_NAME="${GITHUB_REF_NAME:-main}"
export GITHUB_SHA="${GITHUB_SHA}"
export GITHUB_ACTOR="${GITHUB_ACTOR}"

# Pushgateway URL (from secrets)
export PUSHGATEWAY_URL="${PUSHGATEWAY_URL:-http://localhost:9091}"

# Source metrics utilities
source "${SCRIPT_DIR}/metrics_utils.sh"

echo "=========================================="
echo "Deployment Metrics Wrapper"
echo "=========================================="
echo "Deployment ID: $DEPLOYMENT_ID"
echo "Branch: $GITHUB_REF_NAME"
echo "Commit: $GITHUB_SHA"
echo "Actor: $GITHUB_ACTOR"
echo "Pushgateway: $PUSHGATEWAY_URL"
echo ""

# Run the actual deployment script
"${SCRIPT_DIR}/deploy-all.sh" "$@"

# Capture exit code
EXIT_CODE=$?

if [ $EXIT_CODE -eq 0 ]; then
    echo "Deployment succeeded"
else
    echo "Deployment failed with code $EXIT_CODE"
fi

exit $EXIT_CODE
```

### Step 2b: Update GitHub Actions Workflow

**File:** `.github/workflows/deploy-full-stack.yml`

```yaml
name: Deploy Full Stack (API + Web + DB)

on:
  push:
    branches: [ main ]
    paths:
      - 'relay_ai/**'
      - 'scripts/**'
      - 'Dockerfile'
      - 'requirements.txt'
      - 'pyproject.toml'
  workflow_dispatch:

env:
  REGISTRY: ghcr.io
  # Prometheus Pushgateway URL
  PUSHGATEWAY_URL: http://pushgateway:9091
  ENVIRONMENT: production

jobs:
  deploy-api:
    name: Deploy API to Railway
    runs-on: ubuntu-latest
    outputs:
      api_url: ${{ steps.deploy.outputs.api_url }}
      deployment_id: ${{ steps.deploy.outputs.deployment_id }}
      deploy_duration: ${{ steps.deploy.outputs.deploy_duration }}

    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Record deployment start
        run: |
          mkdir -p /tmp/metrics
          echo "DEPLOY_START=$(date +%s)" > /tmp/metrics/deploy_start.env
          echo "API deployment stage starting"

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install Railway CLI
        run: npm install -g @railway/cli

      - name: Deploy to Railway
        id: deploy
        env:
          RAILWAY_TOKEN: ${{ secrets.RAILWAY_TOKEN }}
        run: |
          export DEPLOY_STAGE_START=$(date +%s%N | cut -b1-13)

          railway link
          railway up --detach
          sleep 60

          DEPLOYMENT_ID=$(railway status --json 2>/dev/null | jq -r '.latestDeployment.id // "unknown"')
          API_URL="https://relay-production-f2a6.up.railway.app"

          export DEPLOY_STAGE_END=$(date +%s%N | cut -b1-13)
          export DEPLOY_STAGE_DURATION=$(echo "scale=3; ($DEPLOY_STAGE_END - $DEPLOY_STAGE_START) / 1000" | bc)

          echo "deployment_id=$DEPLOYMENT_ID" >> $GITHUB_OUTPUT
          echo "api_url=$API_URL" >> $GITHUB_OUTPUT
          echo "deploy_duration=$DEPLOY_STAGE_DURATION" >> $GITHUB_OUTPUT

          # Push metrics
          cat <<METRICS | curl --data-binary @- http://pushgateway:9091/metrics/job/deployment-pipeline/instance/${GITHUB_RUN_ID}
deployment_stage_duration_seconds{stage="deploy",service="api",status="success",environment="production"} ${DEPLOY_STAGE_DURATION}
METRICS
        continue-on-error: false

      - name: Verify API is healthy
        id: health_check
        run: |
          for i in {1..30}; do
            HEALTH_START=$(date +%s%N | cut -b1-13)

            if curl -f https://relay-production-f2a6.up.railway.app/health; then
              HEALTH_END=$(date +%s%N | cut -b1-13)
              HEALTH_LATENCY=$(echo "scale=3; ($HEALTH_END - $HEALTH_START) / 1000" | bc)

              echo "API is healthy! Latency: ${HEALTH_LATENCY}ms"

              # Push health metric
              cat <<METRICS | curl --data-binary @- http://pushgateway:9091/metrics/job/deployment-pipeline/instance/${GITHUB_RUN_ID}
api_health_check_latency_ms{status="healthy",environment="production"} ${HEALTH_LATENCY}
METRICS

              exit 0
            fi
            echo "Attempt $i: Waiting for API to be ready..."
            sleep 5
          done
          echo "API failed to become healthy"
          exit 1

      - name: Run database migrations
        env:
          DATABASE_URL: ${{ secrets.DATABASE_PUBLIC_URL }}
        run: |
          MIGRATION_START=$(date +%s%N | cut -b1-13)

          pip install alembic
          echo "Running migrations..."
          alembic upgrade head

          MIGRATION_END=$(date +%s%N | cut -b1-13)
          MIGRATION_DURATION=$(echo "scale=3; ($MIGRATION_END - $MIGRATION_START) / 1000" | bc)

          # Push metric
          cat <<METRICS | curl --data-binary @- http://pushgateway:9091/metrics/job/deployment-pipeline/instance/${GITHUB_RUN_ID}
deployment_stage_duration_seconds{stage="migration",service="database",status="success",environment="production"} ${MIGRATION_DURATION}
METRICS

  deploy-web:
    name: Deploy Web to Vercel
    runs-on: ubuntu-latest
    needs: deploy-api

    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Set up Node
        uses: actions/setup-node@v4
        with:
          node-version: '18'

      - name: Install dependencies
        working-directory: relay_ai/product/web
        run: |
          WEB_INSTALL_START=$(date +%s%N | cut -b1-13)

          npm ci

          WEB_INSTALL_END=$(date +%s%N | cut -b1-13)
          WEB_INSTALL_DURATION=$(echo "scale=3; ($WEB_INSTALL_END - $WEB_INSTALL_START) / 1000" | bc)

          cat <<METRICS | curl --data-binary @- http://pushgateway:9091/metrics/job/deployment-pipeline/instance/${GITHUB_RUN_ID}
deployment_stage_duration_seconds{stage="install",service="web",status="success",environment="production"} ${WEB_INSTALL_DURATION}
METRICS

      - name: Deploy to Vercel
        working-directory: relay_ai/product/web
        env:
          VERCEL_TOKEN: ${{ secrets.VERCEL_TOKEN }}
          VERCEL_PROJECT_ID: ${{ secrets.VERCEL_PROJECT_ID }}
          VERCEL_ORG_ID: ${{ secrets.VERCEL_ORG_ID }}
          NEXT_PUBLIC_API_URL: ${{ needs.deploy-api.outputs.api_url }}
          NEXT_PUBLIC_SUPABASE_URL: ${{ secrets.NEXT_PUBLIC_SUPABASE_URL }}
          NEXT_PUBLIC_SUPABASE_ANON_KEY: ${{ secrets.NEXT_PUBLIC_SUPABASE_ANON_KEY }}
        run: |
          WEB_DEPLOY_START=$(date +%s%N | cut -b1-13)

          npm install -g vercel
          vercel --prod \
            --token "$VERCEL_TOKEN" \
            --build-env NEXT_PUBLIC_API_URL="$NEXT_PUBLIC_API_URL"

          WEB_DEPLOY_END=$(date +%s%N | cut -b1-13)
          WEB_DEPLOY_DURATION=$(echo "scale=3; ($WEB_DEPLOY_END - $WEB_DEPLOY_START) / 1000" | bc)

          cat <<METRICS | curl --data-binary @- http://pushgateway:9091/metrics/job/deployment-pipeline/instance/${GITHUB_RUN_ID}
deployment_stage_duration_seconds{stage="deploy",service="web",status="success",environment="production"} ${WEB_DEPLOY_DURATION}
METRICS

  smoke-tests:
    name: Run Smoke Tests
    runs-on: ubuntu-latest
    needs: [deploy-api, deploy-web]

    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Run smoke tests
        run: |
          SMOKE_TEST_START=$(date +%s%N | cut -b1-13)

          bash scripts/ci_smoke_tests.sh

          SMOKE_TEST_END=$(date +%s%N | cut -b1-13)
          SMOKE_TEST_DURATION=$(echo "scale=3; ($SMOKE_TEST_END - $SMOKE_TEST_START) / 1000" | bc)

          # Push metric
          cat <<METRICS | curl --data-binary @- http://pushgateway:9091/metrics/job/deployment-pipeline/instance/${GITHUB_RUN_ID}
deployment_stage_duration_seconds{stage="smoke_tests",service="api",status="success",environment="production"} ${SMOKE_TEST_DURATION}
METRICS

      - name: Record deployment complete
        if: success()
        run: |
          # Calculate total duration
          source /tmp/metrics/deploy_start.env || echo "DEPLOY_START=$(date +%s)" > /tmp/metrics/deploy_start.env
          DEPLOY_END=$(date +%s)
          TOTAL_DURATION=$((DEPLOY_END - DEPLOY_START))

          # Push final metrics
          cat <<METRICS | curl --data-binary @- http://pushgateway:9091/metrics/job/deployment-pipeline/instance/${GITHUB_RUN_ID}
deployment_in_progress{environment="production",deployment_id="${GITHUB_RUN_ID}"} 0
time_to_deploy_seconds{environment="production"} ${TOTAL_DURATION}
METRICS

          echo "✅ Full stack deployment complete (${TOTAL_DURATION}s)"

      - name: Rollback on failure
        if: failure()
        env:
          RAILWAY_TOKEN: ${{ secrets.RAILWAY_TOKEN }}
          DEPLOYMENT_ID: ${{ needs.deploy-api.outputs.deployment_id }}
        run: |
          echo "Deployment failed, initiating rollback..."

          # Push rollback metric
          cat <<METRICS | curl --data-binary @- http://pushgateway:9091/metrics/job/deployment-pipeline/instance/${GITHUB_RUN_ID}
deployment_rollback_total{deployment_id="${DEPLOYMENT_ID}",reason="test_failed",status="pending"} 1
METRICS

          python scripts/rollback_release.py --deployment-id "$DEPLOYMENT_ID"
          exit 1
```

### Step 2c: Test in GitHub Actions

1. Push a test commit to main:
   ```bash
   git add .
   git commit -m "test: deployment observability metrics"
   git push origin main
   ```

2. Monitor the workflow:
   ```bash
   # Check workflow runs
   gh run list --workflow=deploy-full-stack.yml --limit=1

   # Watch in real time
   gh run watch <RUN_ID>
   ```

3. Verify metrics in Prometheus:
   ```bash
   # Query pushgateway
   curl http://localhost:9091/metrics | grep deployment
   ```

---

## Phase 3: Prometheus & Grafana Setup (Day 3)

### Step 3a: Configure Prometheus Scrape

**File:** `/config/prometheus/prometheus.yml`

Add to `scrape_configs`:

```yaml
  # Deployment metrics from Pushgateway
  - job_name: 'deployment-pipeline'
    honor_labels: true
    static_configs:
      - targets: ['pushgateway:9091']
    scrape_interval: 15s
    scrape_timeout: 10s
```

### Step 3b: Add Alert Rules

**File:** Already created → `/config/prometheus/prometheus-deployment-alerts.yml`

Add to Prometheus configuration:

```yaml
rule_files:
  - '/etc/prometheus/prometheus-deployment-alerts.yml'
```

### Step 3c: Create Grafana Dashboards

**File:** `/config/grafana/provisioning/dashboards/deployment-pipeline.json`

```json
{
  "dashboard": {
    "title": "Deployment Pipeline",
    "tags": ["deployment", "pipeline", "ci-cd"],
    "timezone": "browser",
    "panels": [
      {
        "id": 1,
        "title": "Deployment Status",
        "type": "stat",
        "gridPos": {"h": 8, "w": 24, "x": 0, "y": 0},
        "targets": [
          {
            "expr": "deployment_in_progress{environment=\"production\"}",
            "legendFormat": "In Progress"
          }
        ],
        "fieldConfig": {
          "defaults": {
            "custom": {},
            "color": {
              "mode": "thresholds",
              "thresholds": {
                "mode": "absolute",
                "steps": [
                  {"color": "green", "value": null},
                  {"color": "blue", "value": 0.5},
                  {"color": "red", "value": 1}
                ]
              }
            },
            "mappings": [
              {
                "type": "value",
                "options": {
                  "0": {"text": "Idle", "color": "green"},
                  "1": {"text": "Deploying", "color": "blue"}
                }
              }
            ]
          }
        }
      },
      {
        "id": 2,
        "title": "Stage Durations",
        "type": "graph",
        "gridPos": {"h": 8, "w": 12, "x": 0, "y": 8},
        "targets": [
          {
            "expr": "deployment_stage_duration_seconds{service=\"api\",status=\"success\"}",
            "legendFormat": "{{ stage }}"
          }
        ]
      },
      {
        "id": 3,
        "title": "Deployment Success Rate",
        "type": "stat",
        "gridPos": {"h": 8, "w": 12, "x": 12, "y": 8},
        "targets": [
          {
            "expr": "deployment:success_rate:1h{environment=\"production\"}",
            "legendFormat": "Success Rate"
          }
        ],
        "fieldConfig": {
          "defaults": {
            "unit": "percentunit",
            "min": 0,
            "max": 1
          }
        }
      }
    ]
  }
}
```

### Step 3d: Deploy Changes

```bash
# Commit all changes
git add config/prometheus/ config/grafana/
git commit -m "feat: add deployment observability metrics and dashboards"

# Deploy to Railway
git push origin main

# Monitor
gh run watch
```

---

## Phase 4: Testing & Tuning (Days 4-5)

### Step 4a: Test Each Alert

Create a test deployment that triggers each alert:

```bash
# Test 1: Health check failure
curl -X POST https://relay-production.up.railway.app/admin/simulate-health-failure

# Test 2: Slow migration
# Add to alembic script: time.sleep(180)

# Test 3: High error rate
curl -X POST https://relay-production.up.railway.app/admin/simulate-errors?rate=0.1

# Test 4: Smoke test failure
# Modify smoke test to fail: exit 1
```

### Step 4b: Verify Alerts Fire

1. Check Alertmanager: `https://relay-alertmanager-production.up.railway.app`
2. Check notification channels (Slack, PagerDuty)
3. Document which alerts you receive

### Step 4c: Tune Alert Thresholds

After 3-5 real deployments:

```yaml
# Review alert thresholds in prometheus-deployment-alerts.yml
# Adjust based on:
# - False positive rate (should be < 5%)
# - Detection latency (should alert within 2-3 minutes)
# - Relevance (does alert correspond to real issue?)
```

---

## Phase 5: Documentation & Training (Day 5)

### Step 5a: Create Incident Runbooks

Create `/docs/runbooks/DEPLOYMENT_*.md` for each alert:
- DEPLOYMENT_FAILED.md
- HEALTH_CHECK_FAILED.md
- MIGRATION_FAILED.md
- etc.

**Template:**
```markdown
# Runbook: [Alert Name]

## Summary
[What happened and why it matters]

## Detection
Alert: `[AlertName]`
Severity: [CRITICAL|HIGH|MEDIUM]

## Root Cause Analysis
[Steps to diagnose]

## Resolution
[Steps to fix]

## Post-Incident
[Actions to prevent recurrence]
```

### Step 5b: Team Training

Schedule 30-min session covering:
1. Where to find deployment dashboards
2. How to interpret metrics
3. Common failure scenarios
4. How to respond to alerts
5. Q&A

### Step 5c: Create Dashboard Guide

Document for each dashboard:
- What it shows
- When to check it
- How to interpret green/yellow/red states
- What to do if something looks wrong

---

## File Structure

```
relay_ai/
├── platform/
│   └── observability/
│       ├── __init__.py
│       ├── deployment_metrics.py          [NEW] Core metrics collector
│       └── ...

scripts/
├── deploy-all.sh                          [MODIFIED] Add metrics collection
├── metrics_utils.sh                       [NEW] Bash metric helpers
├── deployment_metrics_wrapper.sh          [NEW] GitHub Actions wrapper
└── ci_smoke_tests.sh                      [MODIFIED] Add metrics for tests

.github/workflows/
├── deploy-full-stack.yml                  [MODIFIED] Add metrics export
└── deploy.yml                             [MODIFIED] Add metrics export

config/
├── prometheus/
│   ├── prometheus.yml                     [MODIFIED] Add scrape config
│   └── prometheus-deployment-alerts.yml   [NEW] Alert rules
└── grafana/
    └── dashboards/
        ├── deployment-pipeline.json       [NEW] Main dashboard
        ├── post-deployment-health.json    [NEW] Health dashboard
        ├── deployment-success.json        [NEW] Success metrics
        ├── database-migrations.json       [NEW] Migrations dashboard
        └── deployment-costs.json          [NEW] Cost tracking

docs/
├── observability/
│   ├── DEPLOYMENT-OBSERVABILITY.md                    [NEW] Design doc
│   └── DEPLOYMENT-OBSERVABILITY-IMPLEMENTATION.md     [NEW] This file
└── runbooks/
    ├── DEPLOYMENT_FAILED.md               [NEW]
    ├── HEALTH_CHECK_FAILED.md             [NEW]
    ├── MIGRATION_FAILED.md                [NEW]
    ├── POST_DEPLOY_ERROR_SPIKE.md         [NEW]
    └── ...
```

---

## Success Criteria Checklist

- [ ] Metrics collector module created and tested locally
- [ ] Bash helper script works with `--smoke` flag
- [ ] GitHub Actions workflow exports metrics to Pushgateway
- [ ] Prometheus scrapes and displays metrics within 2 minutes of deployment
- [ ] Alerts fire correctly for both success and failure scenarios
- [ ] Grafana dashboards render all panels without errors
- [ ] Dashboard displays current deployment status in real-time
- [ ] Post-deployment error rate tracked automatically
- [ ] Health check latency monitored
- [ ] Migration duration captured
- [ ] Rollback metrics recorded
- [ ] Team trained on dashboard interpretation
- [ ] Runbooks completed for all CRITICAL/HIGH alerts
- [ ] Historical metrics show clean trend (no anomalies)
- [ ] Metrics cost < 5% of infrastructure cost

---

## Troubleshooting

### Metrics not appearing in Prometheus

**Symptoms:**
- Dashboard shows "No data"
- Query returns empty result

**Solution:**
```bash
# Check if metrics are reaching Pushgateway
curl http://localhost:9091/metrics | grep deployment_stage

# Check if Prometheus is scraping
curl http://localhost:9090/api/v1/query?query=deployment_total

# Check Prometheus logs
docker logs prometheus | grep -i error
```

### Alerts not firing

**Symptoms:**
- Deployment fails but no alert received

**Solution:**
```bash
# Verify alerts are loaded
curl http://localhost:9090/api/v1/rules

# Check Alertmanager configuration
curl http://localhost:9093/api/v1/status

# Manually trigger test alert
curl -X POST http://localhost:9093/api/v1/alerts \
  -d '[{"labels":{"alertname":"TestAlert"}}]'
```

### High latency or missing data

**Symptoms:**
- 5+ minute delay in metrics appearing
- Sparse data in graphs

**Solution:**
```bash
# Increase scrape frequency in prometheus.yml
scrape_interval: 5s  # reduced from 15s

# Increase Pushgateway retention
# Command line arg: --persistence.interval=1m
```

---

## Migration from Manual Monitoring

**Before:** Manually checking GitHub Actions > Railway > Vercel dashboards
**After:** Single Grafana dashboard shows all stages

**How to transition:**

1. Week 1: Run metrics in parallel with manual monitoring
2. Week 2: Use metrics dashboard as primary
3. Week 3: Remove manual monitoring

---

## Performance Impact

**Expected overhead:**
- CI/CD pipeline: +5-10 seconds (metrics export)
- Infrastructure cost: +< 5% (Pushgateway, storage)
- Latency impact: 0ms (async metrics collection)

**Optimization opportunities:**
- Batch metrics pushes (currently every stage)
- Use Prometheus client library instead of curl (if using Python wrapper)
- Compress metrics payloads for large batches

---

## Next Steps After Implementation

1. **Week 2:** Add cost attribution metrics
2. **Week 3:** Implement automated remediation (auto-rollback)
3. **Week 4:** Add deployment frequency analysis (DORA metrics)
4. **Month 2:** Integrate with incident management (auto-PagerDuty)

---

**Document Maintained By:** Platform Engineering
**Last Updated:** 2025-01-15
**Questions?** Contact @platform-oncall
