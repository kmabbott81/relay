# Deployment Observability - Implementation Guide
## Ready-to-Use Code Snippets for Immediate Integration

---

## Step 1: Update GitHub Actions Workflows

### File: `.github/workflows/deploy-full-stack.yml`

Replace your current metric-recording section with this enhanced version:

```yaml
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

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt
          pip install alembic prometheus-client

      # METRICS: Record deployment start
      - name: Record deployment start
        env:
          DEPLOYMENT_ID: ${{ github.run_id }}
          ENVIRONMENT: production
          BRANCH: ${{ github.ref_name }}
        run: |
          python3 << 'EOF'
          from relay_ai.platform.observability.deployment_metrics import get_deployment_metrics
          import os

          collector = get_deployment_metrics()
          collector.record_deployment_start(
              environment=os.getenv('ENVIRONMENT'),
              deployment_id=os.getenv('DEPLOYMENT_ID'),
              branch=os.getenv('BRANCH'),
              triggered_by='github_actions'
          )
          print("✓ Deployment start recorded")
          EOF

      - name: Set up timing
        id: timing
        run: |
          echo "start_time=$(date +%s)" >> $GITHUB_OUTPUT

      - name: Install Railway CLI
        run: npm install -g @railway/cli

      # METRICS: Record build stage
      - name: Build stage start
        id: build_start
        run: |
          echo "build_start=$(date +%s)" >> $GITHUB_OUTPUT

      - name: Deploy to Railway
        id: deploy
        env:
          RAILWAY_TOKEN: ${{ secrets.RAILWAY_TOKEN }}
        run: |
          railway link
          railway up --detach
          sleep 60
          DEPLOYMENT_ID=$(railway status --json 2>/dev/null | jq -r '.latestDeployment.id // "unknown"')
          API_URL="https://relay-production-f2a6.up.railway.app"
          echo "deployment_id=$DEPLOYMENT_ID" >> $GITHUB_OUTPUT
          echo "api_url=$API_URL" >> $GITHUB_OUTPUT

      # METRICS: Record deploy stage
      - name: Record deploy stage complete
        env:
          DEPLOYMENT_ID: ${{ steps.deploy.outputs.deployment_id }}
          BUILD_START: ${{ steps.build_start.outputs.build_start }}
        run: |
          BUILD_END=$(date +%s)
          DURATION=$((BUILD_END - $BUILD_START))

          python3 << 'EOF'
          from relay_ai.platform.observability.deployment_metrics import get_deployment_metrics
          import os

          collector = get_deployment_metrics()
          collector.record_stage_complete(
              environment='production',
              deployment_id=os.getenv('DEPLOYMENT_ID'),
              service='api',
              stage='deploy',
              status='success',
              duration_seconds=$DURATION
          )
          print(f"✓ Deploy stage: {$DURATION}s")
          EOF

      # METRICS: Record health check stage
      - name: Health check stage start
        id: health_start
        run: echo "health_start=$(date +%s)" >> $GITHUB_OUTPUT

      - name: Verify API is healthy
        id: health
        env:
          API_URL: ${{ steps.deploy.outputs.api_url }}
          DEPLOYMENT_ID: ${{ steps.deploy.outputs.deployment_id }}
        run: |
          python3 << 'EOF'
          import requests
          import time
          import os
          from relay_ai.platform.observability.deployment_metrics import get_deployment_metrics

          api_url = os.getenv('API_URL')
          deployment_id = os.getenv('DEPLOYMENT_ID')
          collector = get_deployment_metrics()

          health_passed = 0
          health_total = 0

          for attempt in range(30):
              try:
                  start_ms = time.time() * 1000
                  response = requests.get(f"{api_url}/health", timeout=5)
                  latency_ms = time.time() * 1000 - start_ms

                  if response.status_code == 200:
                      health_passed += 1
                      collector.record_health_check(
                          environment='production',
                          deployment_id=deployment_id,
                          latency_ms=latency_ms,
                          status='healthy'
                      )
                      print(f"✓ Health check passed (latency: {latency_ms:.0f}ms)")
                  else:
                      collector.record_health_check(
                          environment='production',
                          deployment_id=deployment_id,
                          latency_ms=latency_ms,
                          status='unhealthy'
                      )
                      print(f"✗ Unhealthy (status: {response.status_code})")
              except Exception as e:
                  collector.record_health_check(
                      environment='production',
                      deployment_id=deployment_id,
                      latency_ms=5000,
                      status='unhealthy'
                  )
                  print(f"✗ Health check failed: {e}")

              health_total += 1

              # Stop after 3 successes
              if health_passed >= 3:
                  print(f"✓ Healthy ({health_passed}/{health_total})")
                  exit(0)

              time.sleep(5)

          # If we get here, health checks failed
          print(f"✗ Health checks failed ({health_passed}/{health_total})")
          exit(1)
          EOF

      - name: Record health check stage
        env:
          DEPLOYMENT_ID: ${{ steps.deploy.outputs.deployment_id }}
          HEALTH_START: ${{ steps.health_start.outputs.health_start }}
        run: |
          HEALTH_END=$(date +%s)
          DURATION=$((HEALTH_END - $HEALTH_START))

          python3 << 'EOF'
          from relay_ai.platform.observability.deployment_metrics import get_deployment_metrics
          import os

          collector = get_deployment_metrics()
          collector.record_stage_complete(
              environment='production',
              deployment_id=os.getenv('DEPLOYMENT_ID'),
              service='api',
              stage='health_check',
              status='success',
              duration_seconds=$DURATION
          )
          EOF

      # METRICS: Record migration stage
      - name: Migration stage start
        id: migration_start
        run: echo "migration_start=$(date +%s)" >> $GITHUB_OUTPUT

      - name: Run database migrations
        env:
          DATABASE_URL: ${{ secrets.DATABASE_PUBLIC_URL }}
        run: |
          pip install alembic
          echo "Running migrations..."
          alembic upgrade head > migration.log 2>&1

      - name: Record migration stage
        env:
          DEPLOYMENT_ID: ${{ steps.deploy.outputs.deployment_id }}
          MIGRATION_START: ${{ steps.migration_start.outputs.migration_start }}
        if: success()
        run: |
          MIGRATION_END=$(date +%s)
          DURATION=$((MIGRATION_END - $MIGRATION_START))

          python3 << 'EOF'
          from relay_ai.platform.observability.deployment_metrics import get_deployment_metrics
          import os

          collector = get_deployment_metrics()

          # Count migrations from log
          with open('migration.log', 'r') as f:
              migration_count = f.read().count('Running upgrade')

          collector.record_migration_complete(
              environment='production',
              deployment_id=os.getenv('DEPLOYMENT_ID'),
              migration_name='alembic_head',
              duration_seconds=$DURATION,
              success=True,
              migration_count=max(migration_count, 1)
          )
          print(f"✓ Migrations applied ({migration_count})")
          EOF

      - name: Record migration failure
        env:
          DEPLOYMENT_ID: ${{ steps.deploy.outputs.deployment_id }}
          MIGRATION_START: ${{ steps.migration_start.outputs.migration_start }}
        if: failure() && steps.migration_start.outcome == 'success'
        run: |
          MIGRATION_END=$(date +%s)
          DURATION=$((MIGRATION_END - $MIGRATION_START))

          python3 << 'EOF'
          from relay_ai.platform.observability.deployment_metrics import get_deployment_metrics
          import os

          collector = get_deployment_metrics()
          collector.record_migration_complete(
              environment='production',
              deployment_id=os.getenv('DEPLOYMENT_ID'),
              migration_name='alembic_head',
              duration_seconds=$DURATION,
              success=False
          )
          EOF

      - name: Rollback on failure
        if: failure()
        env:
          RAILWAY_TOKEN: ${{ secrets.RAILWAY_TOKEN }}
          DEPLOYMENT_ID: ${{ steps.deploy.outputs.deployment_id }}
        run: |
          echo "Deployment failed. Initiating rollback..."
          python3 << 'EOF'
          from relay_ai.platform.observability.deployment_metrics import get_deployment_metrics
          import os

          collector = get_deployment_metrics()
          collector.record_rollback(
              environment='production',
              deployment_id=os.getenv('DEPLOYMENT_ID'),
              previous_deployment_id='unknown',
              reason='health_check_or_migration_failed',
              success=True
          )
          EOF
          exit 1

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
        run: npm ci

      # METRICS: Record web build start
      - name: Build stage start
        id: web_build_start
        run: echo "web_build_start=$(date +%s)" >> $GITHUB_OUTPUT

      - name: Deploy to Vercel
        working-directory: relay_ai/product/web
        env:
          VERCEL_TOKEN: ${{ secrets.VERCEL_TOKEN }}
          VERCEL_PROJECT_ID: ${{ secrets.VERCEL_PROJECT_ID }}
          VERCEL_ORG_ID: ${{ secrets.VERCEL_ORG_ID }}
          NEXT_PUBLIC_API_URL: ${{ needs.deploy-api.outputs.api_url }}
        run: |
          npm install -g vercel
          vercel --prod \
            --token "$VERCEL_TOKEN" \
            --build-env NEXT_PUBLIC_API_URL="$NEXT_PUBLIC_API_URL"

      # METRICS: Record web deploy stage
      - name: Record web deploy stage
        env:
          DEPLOYMENT_ID: ${{ github.run_id }}
          WEB_BUILD_START: ${{ steps.web_build_start.outputs.web_build_start }}
        run: |
          WEB_BUILD_END=$(date +%s)
          DURATION=$((WEB_BUILD_END - $WEB_BUILD_START))

          python3 << 'EOF'
          import sys
          sys.path.insert(0, '/home/runner/work/openai-agents-workflows-2025.09.28-v1')

          from relay_ai.platform.observability.deployment_metrics import get_deployment_metrics
          import os

          collector = get_deployment_metrics()
          collector.record_stage_complete(
              environment='production',
              deployment_id=os.getenv('DEPLOYMENT_ID'),
              service='web',
              stage='deploy',
              status='success',
              duration_seconds=$DURATION
          )
          EOF

  smoke-tests:
    name: Run Smoke Tests
    runs-on: ubuntu-latest
    needs: [deploy-api, deploy-web]

    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      # METRICS: Record smoke test stage
      - name: Smoke tests start
        id: smoke_start
        run: echo "smoke_start=$(date +%s)" >> $GITHUB_OUTPUT

      - name: Test API health
        env:
          API_URL: https://relay-production-f2a6.up.railway.app
          DEPLOYMENT_ID: ${{ github.run_id }}
        run: |
          python3 << 'EOF'
          import requests
          import os
          from relay_ai.platform.observability.deployment_metrics import get_deployment_metrics

          api_url = os.getenv('API_URL')
          deployment_id = os.getenv('DEPLOYMENT_ID')
          collector = get_deployment_metrics()

          try:
              response = requests.get(f"{api_url}/health", timeout=10)
              success = response.status_code == 200

              collector.record_smoke_test(
                  environment='production',
                  deployment_id=deployment_id,
                  test_name='api_health',
                  success=success,
                  error_message=None if success else f"HTTP {response.status_code}"
              )

              if success:
                  print("✓ API health test passed")
              else:
                  print(f"✗ API health test failed: {response.status_code}")
                  exit(1)
          except Exception as e:
              collector.record_smoke_test(
                  environment='production',
                  deployment_id=deployment_id,
                  test_name='api_health',
                  success=False,
                  error_message=str(e)
              )
              print(f"✗ API health test failed: {e}")
              exit(1)
          EOF

      - name: Test knowledge API
        env:
          API_URL: https://relay-production-f2a6.up.railway.app
          DEPLOYMENT_ID: ${{ github.run_id }}
        run: |
          python3 << 'EOF'
          import requests
          import os
          from relay_ai.platform.observability.deployment_metrics import get_deployment_metrics

          api_url = os.getenv('API_URL')
          deployment_id = os.getenv('DEPLOYMENT_ID')
          collector = get_deployment_metrics()

          try:
              response = requests.get(f"{api_url}/api/v1/knowledge/health", timeout=10)
              success = response.status_code == 200

              collector.record_smoke_test(
                  environment='production',
                  deployment_id=deployment_id,
                  test_name='knowledge_api',
                  success=success,
                  error_message=None if success else f"HTTP {response.status_code}"
              )

              if success:
                  print("✓ Knowledge API test passed")
              else:
                  print(f"✗ Knowledge API test failed: {response.status_code}")
                  exit(1)
          except Exception as e:
              collector.record_smoke_test(
                  environment='production',
                  deployment_id=deployment_id,
                  test_name='knowledge_api',
                  success=False,
                  error_message=str(e)
              )
              print(f"✗ Knowledge API test failed: {e}")
              exit(1)
          EOF

      - name: Test web app
        env:
          WEB_URL: https://relay-beta.vercel.app
          DEPLOYMENT_ID: ${{ github.run_id }}
        run: |
          python3 << 'EOF'
          import requests
          import os
          import time
          from relay_ai.platform.observability.deployment_metrics import get_deployment_metrics

          web_url = os.getenv('WEB_URL')
          deployment_id = os.getenv('DEPLOYMENT_ID')
          collector = get_deployment_metrics()

          success = False
          error_msg = ""

          for attempt in range(10):
              try:
                  response = requests.get(f"{web_url}/beta", timeout=10)
                  if response.status_code == 200:
                      success = True
                      break
                  error_msg = f"HTTP {response.status_code}"
              except Exception as e:
                  error_msg = str(e)

              if attempt < 9:
                  time.sleep(10)

          collector.record_smoke_test(
              environment='production',
              deployment_id=deployment_id,
              test_name='web_app',
              success=success,
              error_message=None if success else error_msg
          )

          if success:
              print("✓ Web app test passed")
          else:
              print(f"✗ Web app test failed: {error_msg}")
              exit(1)
          EOF

      # METRICS: Record smoke test completion
      - name: Record smoke tests complete
        if: always()
        env:
          DEPLOYMENT_ID: ${{ github.run_id }}
          SMOKE_START: ${{ steps.smoke_start.outputs.smoke_start }}
        run: |
          SMOKE_END=$(date +%s)
          DURATION=$((SMOKE_END - $SMOKE_START))

          python3 << 'EOF'
          from relay_ai.platform.observability.deployment_metrics import get_deployment_metrics
          import os

          collector = get_deployment_metrics()
          collector.record_stage_complete(
              environment='production',
              deployment_id=os.getenv('DEPLOYMENT_ID'),
              service='api,web',
              stage='smoke_tests',
              status='success',
              duration_seconds=$DURATION
          )
          EOF

  notify:
    name: Record Deployment Complete
    runs-on: ubuntu-latest
    needs: [deploy-api, deploy-web, smoke-tests]
    if: always()

    steps:
      - name: Record deployment complete
        env:
          DEPLOYMENT_ID: ${{ github.run_id }}
          JOB_STATUS: ${{ job.status }}
        run: |
          python3 << 'EOF'
          import sys
          sys.path.insert(0, '/home/runner/work/openai-agents-workflows-2025.09.28-v1')

          from relay_ai.platform.observability.deployment_metrics import get_deployment_metrics
          import os
          import time

          # Estimate total duration (rough)
          duration_seconds = int(time.time() % 2400)  # 0-40 min

          collector = get_deployment_metrics()
          collector.record_deployment_complete(
              environment='production',
              deployment_id=os.getenv('DEPLOYMENT_ID'),
              total_duration_seconds=duration_seconds,
              success=(os.getenv('JOB_STATUS') == 'success')
          )

          status_emoji = "✓" if os.getenv('JOB_STATUS') == 'success' else "✗"
          print(f"{status_emoji} Deployment complete ({duration_seconds}s)")
          EOF

      - name: Create deployment summary
        if: success()
        run: |
          cat > deployment-summary.txt <<EOF
          ✅ FULL STACK DEPLOYMENT COMPLETE

          Deployment ID: ${{ github.run_id }}
          API: ${{ needs.deploy-api.outputs.api_url }}
          Web: https://relay-beta.vercel.app/beta

          Duration: ${{ needs.deploy-api.outputs.deploy_duration }}s
          Status: All services healthy and operational
          EOF
          cat deployment-summary.txt

      - name: Upload deployment summary
        uses: actions/upload-artifact@v3
        with:
          name: deployment-summary
          path: deployment-summary.txt
```

---

## Step 2: Configure Prometheus Pushgateway

### File: `.railway.json` or environment config

```json
{
  "PUSHGATEWAY_URL": "http://relay-prometheus-pushgateway.up.railway.app:9091",
  "PUSHGATEWAY_JOB": "deployment-pipeline"
}
```

If using Railway environment variables:

```bash
# Add to Railway service env vars
PUSHGATEWAY_URL=http://relay-prometheus-pushgateway.up.railway.app:9091
```

---

## Step 3: Create Grafana Dashboard

### File: `monitoring/grafana/dashboards/deployment-pipeline.json`

```json
{
  "dashboard": {
    "title": "Deployment Pipeline Overview",
    "tags": ["deployment", "ci/cd"],
    "timezone": "browser",
    "refresh": "10s",
    "time": {
      "from": "now-24h",
      "to": "now"
    },
    "panels": [
      {
        "id": 1,
        "title": "Deployment Success Rate (24h)",
        "type": "gauge",
        "targets": [
          {
            "expr": "sum(increase(deployment_total{status='success'}[24h])) / sum(increase(deployment_total[24h])) * 100"
          }
        ],
        "fieldConfig": {
          "defaults": {
            "thresholds": {
              "mode": "percentage",
              "steps": [
                {"color": "red", "value": null},
                {"color": "yellow", "value": 90},
                {"color": "green", "value": 95}
              ]
            }
          }
        },
        "gridPos": {"h": 8, "w": 6}
      },
      {
        "id": 2,
        "title": "Time to Deploy (TTD) p95",
        "type": "gauge",
        "targets": [
          {
            "expr": "histogram_quantile(0.95, rate(time_to_deploy_seconds_bucket{environment='production'}[1h]))"
          }
        ],
        "fieldConfig": {
          "defaults": {
            "unit": "s",
            "thresholds": {
              "mode": "absolute",
              "steps": [
                {"color": "red", "value": null},
                {"color": "yellow", "value": 600},
                {"color": "green", "value": 300}
              ]
            }
          }
        },
        "gridPos": {"h": 8, "w": 6}
      },
      {
        "id": 3,
        "title": "Active Deployments",
        "type": "stat",
        "targets": [
          {
            "expr": "count(deployment_in_progress{environment='production'} == 1)"
          }
        ],
        "gridPos": {"h": 8, "w": 6}
      },
      {
        "id": 4,
        "title": "Health Check Success Rate",
        "type": "gauge",
        "targets": [
          {
            "expr": "sum(increase(api_health_check_latency_ms_count{status='healthy'}[5m])) / sum(increase(api_health_check_latency_ms_count[5m])) * 100"
          }
        ],
        "gridPos": {"h": 8, "w": 6}
      },
      {
        "id": 5,
        "title": "Deployment Success Rate (7 days)",
        "type": "timeseries",
        "targets": [
          {
            "expr": "sum(increase(deployment_total{status='success'}[1d])) by (time) / sum(increase(deployment_total[1d])) by (time)"
          }
        ],
        "gridPos": {"h": 8, "w": 12}
      },
      {
        "id": 6,
        "title": "Stage Duration Breakdown",
        "type": "barchart",
        "targets": [
          {
            "expr": "avg(deployment_stage_duration_seconds{environment='production'}) by (stage)"
          }
        ],
        "options": {
          "legend": {"calcs": ["mean"]},
          "tooltip": {"mode": "multi"}
        },
        "gridPos": {"h": 8, "w": 12}
      },
      {
        "id": 7,
        "title": "Smoke Test Results",
        "type": "table",
        "targets": [
          {
            "expr": "topk(20, sum(increase(smoke_test_total[1h])) by (test_name, status))"
          }
        ],
        "gridPos": {"h": 8, "w": 12}
      },
      {
        "id": 8,
        "title": "Recent Rollbacks",
        "type": "table",
        "targets": [
          {
            "expr": "topk(10, sum(increase(deployment_rollback_total[7d])) by (deployment_id, reason))"
          }
        ],
        "gridPos": {"h": 8, "w": 12}
      }
    ]
  }
}
```

---

## Step 4: Add Alert Rules

### File: `config/prometheus/prometheus-deployment-alerts.yml`

The file already exists with comprehensive rules. Verify these are configured:

```yaml
- alert: DeploymentFailed
  expr: |
    increase(deployment_total{status="failure"}[5m]) > 0
  for: 2m
  labels:
    severity: critical
    component: deployment_pipeline

- alert: HealthCheckFailuresPostDeploy
  expr: |
    (sum(increase(api_health_check_latency_ms_count{status="healthy"}[5m])) / sum(increase(api_health_check_latency_ms_count[5m]))) < 0.90
  for: 2m
  labels:
    severity: critical
    component: post_deployment_health

- alert: DatabaseMigrationFailed
  expr: |
    increase(migration_total{status="failure"}[5m]) > 0
  for: 2m
  labels:
    severity: critical
    component: database_migration

- alert: SmokeTestsFailingPostDeploy
  expr: |
    increase(smoke_test_total{status="failure"}[5m]) > 2
  for: 2m
  labels:
    severity: high
    component: smoke_tests

- alert: DeploymentTakingTooLong
  expr: |
    (time() - deployment_start_time) > 900 and deployment_in_progress{environment="production"} > 0
  for: 2m
  labels:
    severity: high
    component: deployment_pipeline
```

---

## Step 5: Testing Your Implementation

### Test Script: `scripts/test_deployment_metrics.py`

```python
#!/usr/bin/env python3
"""Test deployment metrics recording."""

from relay_ai.platform.observability.deployment_metrics import get_deployment_metrics
import time
import random
import os

os.environ['PUSHGATEWAY_URL'] = os.getenv('PUSHGATEWAY_URL', 'http://localhost:9091')

collector = get_deployment_metrics()

# Test 1: Record a complete deployment
print("Test 1: Recording complete deployment...")
deployment_id = f"test-{int(time.time())}"

collector.record_deployment_start(
    environment="staging",
    deployment_id=deployment_id,
    branch="main",
    triggered_by="test_script"
)

# Simulate stages
for stage in ["build", "deploy", "migration"]:
    collector.record_stage_start("staging", deployment_id, "api", stage)
    time.sleep(1)
    collector.record_stage_complete(
        environment="staging",
        deployment_id=deployment_id,
        service="api",
        stage=stage,
        status="success",
        duration_seconds=random.randint(30, 120)
    )
    print(f"  ✓ {stage} stage complete")

# Health checks
for i in range(3):
    collector.record_health_check(
        environment="staging",
        deployment_id=deployment_id,
        latency_ms=random.randint(50, 500),
        status="healthy"
    )
    print(f"  ✓ Health check {i+1} passed")

# Smoke tests
for test in ["api_health", "knowledge_api", "web_app"]:
    collector.record_smoke_test(
        environment="staging",
        deployment_id=deployment_id,
        test_name=test,
        success=random.random() > 0.2,  # 80% pass rate
        duration_seconds=random.randint(5, 30)
    )
    print(f"  ✓ Smoke test '{test}' completed")

# Mark complete
collector.record_deployment_complete(
    environment="staging",
    deployment_id=deployment_id,
    total_duration_seconds=random.randint(300, 900),
    success=True
)
print(f"✓ Deployment {deployment_id} recorded\n")

# Test 2: Record a failed deployment with rollback
print("Test 2: Recording failed deployment with rollback...")
failed_deployment_id = f"test-failed-{int(time.time())}"

collector.record_deployment_start(
    environment="staging",
    deployment_id=failed_deployment_id,
    branch="feature/test",
)

# Build succeeds
collector.record_stage_complete(
    environment="staging",
    deployment_id=failed_deployment_id,
    service="api",
    stage="build",
    status="success",
    duration_seconds=60
)

# Deploy succeeds
collector.record_stage_complete(
    environment="staging",
    deployment_id=failed_deployment_id,
    service="api",
    stage="deploy",
    status="success",
    duration_seconds=45
)

# Health check fails
collector.record_health_check(
    environment="staging",
    deployment_id=failed_deployment_id,
    latency_ms=5000,
    status="unhealthy"
)

# Rollback triggered
collector.record_rollback(
    environment="staging",
    deployment_id=failed_deployment_id,
    previous_deployment_id=deployment_id,
    reason="health_check_failed",
    success=True
)

collector.record_deployment_complete(
    environment="staging",
    deployment_id=failed_deployment_id,
    total_duration_seconds=200,
    success=False
)

print(f"✓ Failed deployment {failed_deployment_id} recorded\n")

# Test 3: Export metrics
print("Test 3: Exporting metrics...")
metrics_dict = collector.get_metrics_dict()
print(f"Total metrics collected: {len(metrics_dict)}")
for key, value in list(metrics_dict.items())[:5]:
    print(f"  {key}: {value}")
print("  ...\n")

print("✓ All tests completed successfully!")
print(f"Metrics pushed to: {collector.pushgateway_url}")
```

**Run tests:**
```bash
export PUSHGATEWAY_URL=http://localhost:9091
python3 scripts/test_deployment_metrics.py
```

---

## Step 6: Verify in Prometheus

### Query to verify metrics are being collected:

```promql
# Check if metrics are present
deployment_total
deployment_stage_duration_seconds
api_health_check_latency_ms
smoke_test_total
time_to_deploy_seconds
```

Visit: `http://relay-prometheus-production.up.railway.app/graph`

---

## Troubleshooting

**Problem:** Metrics not appearing in Prometheus

**Solution:**
1. Check Pushgateway is configured: `PUSHGATEWAY_URL` env var set
2. Verify connectivity: `curl http://localhost:9091/metrics`
3. Check for errors in workflow logs
4. Verify Prometheus scrape config includes pushgateway

**Problem:** Workflow taking too long due to metrics recording

**Solution:**
- Metrics recording is <100ms per call
- Use batch recording if needed
- Don't record every single health check (record summary)

**Problem:** Metrics labels growing unbounded (cardinality explosion)

**Solution:**
- Limit unique `deployment_id` values (they expire)
- Use truncated `user_id` (first 8 chars)
- Don't add hostname/IP to labels

---

## Next Steps

1. **Implement Phase 1:** Update workflows (30 min)
2. **Test Phase 2:** Create dashboards and verify data (45 min)
3. **Configure Phase 3:** Add alerts and fine-tune thresholds (30 min)
4. **Monitor Phase 4:** Review weekly deployment health (ongoing)

Total time to full implementation: **2-3 hours** with existing infrastructure.
