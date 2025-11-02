# Deployment Observability - Team Cheat Sheet

## For Your Team: Quick Reference Card

---

## The 5 Metrics At a Glance

```
┌─────────────────────────────────────────────────────────┐
│ METRIC 1: Success Rate                                  │
│ Question: "Are deployments working?"                    │
│ Target: ≥99%                                            │
│ Alert: <95% = HIGH                                      │
│ Query: deployment_total{status="success"}              │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│ METRIC 2: Time to Deploy (p95)                          │
│ Question: "How fast are we deploying?"                  │
│ Target: ≤10 minutes                                     │
│ Alert: >15 min = HIGH                                   │
│ Query: time_to_deploy_seconds (p95)                    │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│ METRIC 3: API Health (post-deploy)                      │
│ Question: "Is the new version healthy?"                 │
│ Target: ≥99% health checks passing                      │
│ Alert: <90% = CRITICAL (auto-rollback)                 │
│ Query: api_health_check_latency_ms{status="healthy"}   │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│ METRIC 4: Migration Success                             │
│ Question: "Did database changes apply?"                 │
│ Target: 100% success                                    │
│ Alert: Any failure = CRITICAL                           │
│ Query: migration_total{status="success"}               │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│ METRIC 5: Smoke Tests (pass rate)                       │
│ Question: "Does the app work end-to-end?"               │
│ Target: ≥99%                                            │
│ Alert: <90% = HIGH                                      │
│ Query: smoke_test_total{status="success"}              │
└─────────────────────────────────────────────────────────┘
```

---

## During a Deployment

### What to Watch (in order)

1. **Build Stage** (0-2 min)
   - Should complete in <3 min
   - If >5 min: Check Docker build logs

2. **Deploy Stage** (2-5 min)
   - Watch for Railway deployment progress
   - If >5 min: May be slow rolling out new version

3. **Health Checks** (5-7 min)
   - Must pass ≥90% (auto-rollback if <90%)
   - If failing: Check API logs for startup errors

4. **Database Migration** (7-9 min)
   - Must complete without error
   - If fails: Deployment blocked (no auto-rollback)

5. **Smoke Tests** (9-10+ min)
   - Tests API endpoints and web app
   - If any fail: Triggers rollback

### Success Indicators
- ✅ All stages complete (green)
- ✅ No alerts firing
- ✅ Health checks: 100% passing
- ✅ Smoke tests: All pass
- ✅ TTD: Within 10 minutes

### Failure Indicators
- ❌ Stage times out (red)
- ❌ Critical alert fires
- ❌ Health checks <90%
- ❌ Smoke test fails
- ❌ Any stage fails

---

## Dashboard Quick Links

### Main Dashboard (Command Center)
View success rate, TTD, health, recent deployments
```
http://relay-grafana-production.up.railway.app/d/deployment-pipeline-overview
```

### Stage Breakdown (Where's the bottleneck?)
See which stages are slow
```promql
avg(deployment_stage_duration_seconds) by (stage)
```

### Rollback History (Deployment quality)
See why we rolled back
```promql
deployment_rollback_total by (reason)
```

### Error Log (Debugging failures)
Check why deployment failed
```
GitHub Actions: github.com/[org]/[repo]/actions
Logs: Filter by deployment_id from Grafana
```

---

## Common Scenarios

### Scenario 1: Deployment is slow (>15 min)

**Troubleshoot:**
1. Check which stage is slow
2. Check stage duration graph
3. If build: Check Docker dependencies
4. If deploy: Check Railway resources
5. If migration: Check database load

**Action:**
- If >20 min: Consider canceling to unblock team
- After stabilizes: Review stage breakdown

---

### Scenario 2: Health checks failing

**Troubleshoot:**
1. Check API logs in Railway
2. Check database connectivity
3. Check external service status (Supabase, embeddings)
4. Check resource usage (CPU, memory)

**Action:**
- If <2 min: May auto-rollback
- Check error logs for root cause
- Manual rollback if auto-rollback fails

---

### Scenario 3: Smoke tests failing

**Troubleshoot:**
1. See which test is failing (in Grafana)
2. Check test output in GitHub Actions
3. Verify test expectations match new code
4. Check if external API changed

**Action:**
- If test issue: Fix test + redeploy
- If real issue: Manual rollback + investigation
- Update test if expectations changed

---

### Scenario 4: Database migration failed

**Troubleshoot:**
1. Check migration error message
2. Review migration SQL
3. Check if schema already exists
4. Check database locks

**Action:**
- If simple fix: Run migration manually
- Otherwise: Manual schema rollback needed
- Contact DBA if complex

---

### Scenario 5: Auto-rollback triggered

**Troubleshoot:**
1. Check what triggered rollback (alert name)
2. Review new code changes
3. Check if rollback succeeded
4. Analyze difference between old/new version

**Action:**
- Check if rollback worked (green health again)
- Document issue
- File bug for follow-up investigation
- Re-deploy after fix

---

## Key Prometheus Queries (Copy-Paste)

### Success Rate (Last 24h)
```promql
sum(increase(deployment_total{status="success"}[24h]))
/ sum(increase(deployment_total[24h])) * 100
```

### TTD Distribution (Last 7 days)
```promql
histogram_quantile(0.50, rate(time_to_deploy_seconds_bucket[7d]))  # p50
histogram_quantile(0.95, rate(time_to_deploy_seconds_bucket[7d]))  # p95
histogram_quantile(0.99, rate(time_to_deploy_seconds_bucket[7d]))  # p99
```

### Stage Slowdown Detection
```promql
avg(deployment_stage_duration_seconds{stage="build"}) / 300  # if >5min
```

### Health Check Failures (Last hour)
```promql
sum(increase(api_health_check_latency_ms_count{status="unhealthy"}[1h]))
/ sum(increase(api_health_check_latency_ms_count[1h])) * 100
```

### Smoke Test Coverage
```promql
sum(increase(smoke_test_total{status="success"}[1h])) by (test_name)
/ sum(increase(smoke_test_total[1h])) by (test_name) * 100
```

### Rollback Rate (per week)
```promql
rate(deployment_rollback_total{status="success"}[7d])
```

---

## Alert Severity Legend

| Level | What | Action | Escalation |
|-------|------|--------|------------|
| 🔴 CRITICAL | Service down / health failing | Immediate | Page on-call |
| 🟠 HIGH | Major issue / test failing | Within 5 min | Alert ops |
| 🟡 MEDIUM | Issue trending / slow | Within 30 min | Create ticket |
| 🟢 INFO | FYI / informational | Async | Log for review |

---

## SLO Error Budget

### Monthly Error Budget: 1%

```
Total deployments: ~30/month
Allowed failures: ~1 (budget: 1%)

If you use the budget:
- Freeze risky deployments
- Only hotfixes + critical bug fixes
- Resume next month
```

---

## Glossary (2-min read)

**Metric:** A number you measure (success rate, TTD, health)
**Alert:** Notification when metric crosses threshold
**Auto-rollback:** Automatically deploy previous version if new one fails
**SLO:** Service Level Objective (99% success target)
**Error Budget:** How much failure you can tolerate (1% / month)
**TTD:** Time to Deploy (minutes from push to stable)
**p95:** 95th percentile (95% of deployments are this fast)
**Smoke test:** Quick end-to-end test to verify app works
**Pushgateway:** Prometheus component for batch metrics

---

## Slack Bot Commands (if configured)

```
/deployment-status          → Show current deployment metrics
/deployment-history         → Show last 10 deployments
/deployment-health          → Show health check status
/deployment-alert <type>    → Configure alert routing
```

*(Commands must be configured in Slack integration)*

---

## Runbook Quick Links

**If X happens, do Y:**

| Alert | What to Check | Action |
|-------|---------------|--------|
| Deployment Failed | Which stage? | Review stage logs |
| Health Check Failed | API logs | Check error message |
| Migration Failed | Database logs | Contact DBA |
| Smoke Test Failed | Test output | Fix test or code |
| TTD High | Stage duration | Profile slow stage |
| Rollback Triggered | Previous version | Verify working |

---

## Phone Tree (if deployment fails)

1. **First 2 minutes:** Check Grafana dashboard
2. **If still failing:** Slack #engineering
3. **If ongoing:** Page on-call lead
4. **If critical:** Page engineering manager

---

## Weekly Review Checklist

Every Monday morning:
- [ ] Check success rate (target: >95%)
- [ ] Review TTD trend (target: <10 min p95)
- [ ] Count rollbacks (target: <1 per week)
- [ ] Check stage durations (identify bottleneck)
- [ ] Review any alerts fired
- [ ] Discuss improvements

---

## Monthly Review Checklist

Every 1st of month:
- [ ] Calculate error budget (used vs. remaining)
- [ ] Review SLO compliance (all 5 metrics)
- [ ] Analyze top failure reasons
- [ ] Identify 1-2 improvements
- [ ] Plan optimizations for next month
- [ ] Update runbooks if needed

---

## Common Commands

### Check if deployment is in progress
```bash
curl -s http://relay-prometheus:9090/api/v1/query?query=deployment_in_progress | jq
```

### Find deployment by ID
```promql
deployment_total{deployment_id="12345"}
```

### Export metrics to CSV
```promql
# In Prometheus UI: Graph tab → Export
histogram_quantile(0.95, rate(time_to_deploy_seconds_bucket[1d]))
```

---

## Dashboard Tips & Tricks

**Tip 1: Time Range**
- Last hour: Shows current deployment in real-time
- Last 24h: Shows daily patterns
- Last 7d: Shows trends and outliers

**Tip 2: Auto-Refresh**
- During deploy: Set to 10 seconds
- After deploy: Set to 1 minute
- Normal: Set to 5 minutes

**Tip 3: Drill-Down**
- Click on metric → see related alerts
- Click on stage → see logs
- Click on deployment ID → see GitHub Actions job

**Tip 4: Create Custom Panels**
- Add query: Click "+" → Add panel
- Common queries above
- Save dashboard after changes

---

## Debugging Checklist

- [ ] Is Prometheus scraping metrics? (check targets page)
- [ ] Is Pushgateway configured? (check env var)
- [ ] Is Grafana connected to Prometheus? (test query)
- [ ] Are alert rules configured? (check Prometheus alerts page)
- [ ] Did workflow record metrics? (check workflow logs)
- [ ] Is there data in time range? (check Prometheus)

---

## Emergency Contacts

| Role | Contact | Purpose |
|------|---------|---------|
| On-Call Lead | Slack #on-call | Page for critical issues |
| DevOps | Slack #devops | Infrastructure questions |
| DBA | Slack #database | Migration issues |
| Platform | Slack #platform | Observability questions |

---

## Resources

- **Full Design:** `DEPLOYMENT_OBSERVABILITY_DESIGN.md`
- **Implementation:** `DEPLOYMENT_OBSERVABILITY_IMPLEMENTATION.md`
- **Quick Start:** `DEPLOYMENT_OBSERVABILITY_QUICKSTART.md`
- **Summary:** `DEPLOYMENT_OBSERVABILITY_SUMMARY.md`
- **Prometheus Docs:** prometheus.io/docs
- **Grafana Docs:** grafana.com/docs

---

**Last Updated:** 2025-11-02
**Next Review:** 2025-12-02
