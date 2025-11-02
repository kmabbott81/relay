# Deployment Observability - Complete Guide

**Last Updated:** 2025-01-15
**Status:** Ready for Implementation
**Documentation Version:** 1.0

---

## Quick Navigation

### For Decision Makers
Start here to understand the value and cost:
- **[Executive Summary](DEPLOYMENT-OBSERVABILITY-SUMMARY.md)** ← Start here
  - Problem statement
  - Solution overview
  - ROI analysis
  - Implementation timeline
  - Risk mitigation

### For Implementation Team
Step-by-step implementation guide:
- **[Implementation Guide](DEPLOYMENT-OBSERVABILITY-IMPLEMENTATION.md)** ← Then read this
  - Phase-by-phase breakdown
  - Code examples
  - Testing procedures
  - Troubleshooting

### For Operators/On-Call
Complete technical reference:
- **[Architecture & Design](DEPLOYMENT-OBSERVABILITY.md)** ← Reference during implementation
  - Metrics definitions
  - SLI/SLO/SLA definitions
  - Alert rules
  - Dashboard designs
  - Runbooks

### For Incident Response
When deployments go wrong:
- **[Runbooks](../runbooks/DEPLOYMENT_*.md)** ← Use during incidents
  - DEPLOYMENT_FAILED.md
  - HEALTH_CHECK_FAILED.md
  - MIGRATION_FAILED.md
  - POST_DEPLOY_ERROR_SPIKE.md
  - etc.

---

## What's Being Built

### Overview Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                   GitHub Actions Workflow                   │
│              (Triggered on: git push origin main)           │
└──────────────┬────────────────────────────────┬─────────────┘
               │                                │
        ┌──────▼──────┐                  ┌─────▼────────┐
        │  Deploy API │                  │  Deploy Web  │
        │  (Railway)  │                  │  (Vercel)    │
        │             │                  │              │
        │ Stages:     │                  │ Stages:      │
        │ • Build     │                  │ • Install    │
        │ • Push      │                  │ • Build      │
        │ • Deploy    │                  │ • Deploy     │
        │ • Health ✓  │                  │ • Verify     │
        │ • Migrate ✓ │                  │              │
        │             │                  │              │
        │ Metrics: ↓  │                  │ Metrics: ↓   │
        │ • Duration  │                  │ • Duration   │
        │ • Status    │                  │ • Status     │
        │ • Errors    │                  │ • Errors     │
        └──────┬──────┘                  └─────┬────────┘
               │                               │
               └───────────────┬───────────────┘
                               │
                    ┌──────────▼─────────────┐
                    │   Smoke Tests         │
                    │                       │
                    │ Stages:               │
                    │ • API health check    │
                    │ • Knowledge API       │
                    │ • Web app loads       │
                    │                       │
                    │ Metrics: ↓            │
                    │ • Test duration       │
                    │ • Pass/fail count     │
                    │ • Error details       │
                    └──────────┬────────────┘
                               │
                ┌──────────────▼──────────────┐
                │  Prometheus Pushgateway     │
                │  (Temporary metrics buffer) │
                │  TTL: 5 minutes             │
                └──────────────┬──────────────┘
                               │
                ┌──────────────▼──────────────┐
                │  Prometheus Server          │
                │  (Railway deployment)       │
                │  Scrapes: Every 15 seconds  │
                │  Retains: 15 days           │
                └──────────────┬──────────────┘
                               │
                ┌──────────────▼──────────────┐
                │  Alertmanager               │
                │                            │
                │ Routes alerts to:          │
                │ • Slack #incidents         │
                │ • PagerDuty (on-call)      │
                │ • Email (summary)          │
                │ • GitHub issues            │
                └──────────────┬──────────────┘
                               │
                ┌──────────────▼──────────────┐
                │  Grafana Dashboards        │
                │                            │
                │ Real-time visibility:      │
                │ • Deployment status        │
                │ • Stage timeline           │
                │ • Error details            │
                │ • Health metrics           │
                │ • Success rates            │
                │ • Cost tracking            │
                └────────────────────────────┘
```

---

## Key Metrics Collected

### During Deployment (Every Stage)
```
deployment_stage_duration_seconds
├─ stage: "build" | "deploy" | "health_check" | "migration" | "smoke_tests"
├─ service: "api" | "web" | "database"
├─ status: "success" | "failure"
├─ deployment_id: "github-run-12345"
├─ environment: "production"
└─ value: <seconds>

Example:
  deployment_stage_duration_seconds{
    stage="health_check",
    service="api",
    status="success",
    deployment_id="run-789456",
    environment="production"
  } 8.2
```

### When Deployment Completes
```
time_to_deploy_seconds
├─ environment: "production"
└─ value: <total_seconds>

Example:
  time_to_deploy_seconds_bucket{
    le="900",
    environment="production"
  } 1
  Means: 1 deployment completed in < 900 seconds (15 min)
```

### Post-Deployment Health
```
api_health_check_latency_ms
├─ status: "healthy" | "unhealthy"
├─ deployment_id: "run-789456"
├─ environment: "production"
└─ value: <milliseconds>

post_deployment_error_rate
├─ service: "api" | "web"
├─ deployment_id: "run-789456"
├─ environment: "production"
└─ value: <0.0-1.0>
```

---

## Alert Examples

### CRITICAL - Page immediately
```
Alert: DeploymentFailed
Trigger: deployment_total{status="failure"} > 0
Delay: 2 minutes
Who: On-call engineer (PagerDuty)
What: Check logs to identify which stage failed
Where: GitHub Actions logs + Grafana dashboard
```

### HIGH - Alert ops team
```
Alert: DeploymentTakingTooLong
Trigger: (current_time - deployment_start) > 900 seconds
Delay: 2 minutes
Who: #incidents Slack channel
What: Monitor if deployment is making progress
Action: Manual intervention if > 20 minutes
```

### MEDIUM - Create ticket
```
Alert: HealthCheckLatencyHigh
Trigger: api_health_check_latency_ms > 1000
Delay: 3 minutes
Who: Ops team
What: Investigate if deployment caused slowness
```

---

## Dashboards Available

### 1. Deployment Pipeline (Main Dashboard)
**URL:** `https://relay-grafana-production.up.railway.app/d/deployment-pipeline`

Shows:
- Current deployment status (running / idle)
- Stage timeline with durations
- Success/failure indicators
- Error details (if failed)
- Recent deployment history

**Who uses it:** DevOps, on-call engineers, developers

**Check frequency:** During deployments (real-time)

### 2. Post-Deployment Health
**URL:** `https://relay-grafana-production.up.railway.app/d/post-deployment-health`

Shows:
- API health check latency
- Error rate trends
- Service dependencies
- P50/P95/P99 latency
- Comparison to pre-deployment baseline

**Who uses it:** Operators monitoring stability

**Check frequency:** First 5 minutes after deployment

### 3. Deployment Success Rate
**URL:** `https://relay-grafana-production.up.railway.app/d/deployment-success-rate`

Shows:
- Monthly success rate %
- Rollback count
- Error budget remaining
- Failure root causes
- Trend over time

**Who uses it:** Engineering leads, sprint planning

**Check frequency:** Weekly review

### 4. Database Migrations
**URL:** `https://relay-grafana-production.up.railway.app/d/database-migrations`

Shows:
- Current migration status
- Migration history
- Duration trends
- Success rate
- Potential schema issues

**Who uses it:** Database engineers

**Check frequency:** During migrations

### 5. Deployment Costs
**URL:** `https://relay-grafana-production.up.railway.app/d/deployment-costs`

Shows:
- Total deployment cost
- Cost by service (Railway/Vercel)
- Daily trends
- Cost per deployment
- Cost anomalies

**Who uses it:** Finance, cost optimization

**Check frequency:** Weekly

---

## Implementation Checklist

### Phase 1: Metrics Collection (Days 1-2)
- [ ] Read implementation guide
- [ ] Create `relay_ai/platform/observability/deployment_metrics.py`
- [ ] Create `scripts/metrics_utils.sh`
- [ ] Test locally with `bash scripts/deploy-all.sh --smoke`
- [ ] Verify metrics reach Prometheus Pushgateway

### Phase 2: GitHub Actions (Days 3-5)
- [ ] Update `.github/workflows/deploy-full-stack.yml`
- [ ] Add metrics export at each stage
- [ ] Test in GitHub Actions
- [ ] Verify real deployment exports metrics

### Phase 3: Alerts & Dashboards (Week 2, Days 1-3)
- [ ] Deploy `config/prometheus/prometheus-deployment-alerts.yml`
- [ ] Update Prometheus scrape config
- [ ] Create Grafana dashboards
- [ ] Test each alert trigger
- [ ] Tune thresholds based on baseline data

### Phase 4: Documentation (Week 2, Days 4-5)
- [ ] Write runbooks for each alert
- [ ] Create dashboard interpretation guide
- [ ] Team training session
- [ ] Update on-call documentation

### Phase 5: Optimization (Ongoing)
- [ ] Review alert false positive rate
- [ ] Adjust thresholds
- [ ] Add new metrics based on feedback
- [ ] Integrate with incident management

---

## Key Files

### Code Files

**Python Metrics Collector**
- **File:** `relay_ai/platform/observability/deployment_metrics.py`
- **Purpose:** Core metrics collection module
- **Size:** ~500 lines
- **Dependencies:** prometheus_client, json, time
- **Usage:** Can be imported in Python code or used standalone

**Bash Metrics Utilities**
- **File:** `scripts/metrics_utils.sh`
- **Purpose:** Shell functions for GitHub Actions
- **Size:** ~400 lines
- **Dependencies:** bash, curl, bc
- **Usage:** Source in deployment scripts

**Prometheus Alert Rules**
- **File:** `config/prometheus/prometheus-deployment-alerts.yml`
- **Purpose:** 13 alert rules with multiple severity levels
- **Size:** ~400 lines
- **Updates:** Add to prometheus.yml rule_files

### Documentation Files

**Design Document**
- **File:** `docs/observability/DEPLOYMENT-OBSERVABILITY.md`
- **Content:** Complete technical specification
- **Size:** ~500 lines
- **For:** Reference during implementation

**Implementation Guide**
- **File:** `docs/observability/DEPLOYMENT-OBSERVABILITY-IMPLEMENTATION.md`
- **Content:** Phase-by-phase implementation steps
- **Size:** ~800 lines
- **For:** Step-by-step walkthrough

**Executive Summary**
- **File:** `docs/observability/DEPLOYMENT-OBSERVABILITY-SUMMARY.md`
- **Content:** Problem statement, solution, ROI
- **Size:** ~400 lines
- **For:** Decision makers

---

## SLOs (Service Level Objectives)

### What We Commit To

| Objective | Target | Error Budget | Meaning |
|-----------|--------|--------------|---------|
| **Deployment Success** | 99.5% | 1.5 failed/month | Deployments shouldn't fail often |
| **TTD (Time To Deploy)** | <12 min (p95) | Tracked weekly | Deployments should be fast |
| **Post-Deploy Errors** | <1% | Auto-rollback if >5% | New version shouldn't cause errors |
| **Health Checks** | 99.9% | Rollback if failures | Must verify before prod traffic |
| **Migrations** | 100% | Rollback if fails | Schema changes must succeed |
| **Smoke Tests** | 99% | Investigation if >1% fails | Smoke tests are our safety net |

---

## Alert Response Guide

### CRITICAL Alerts - Page immediately

**DeploymentFailed** (Alert DEP001)
- Action: Check logs immediately
- Escalation: If unresolved in 5 min, page lead
- Typical fix: Rollback

**HealthCheckFailuresPostDeploy** (Alert DEP002)
- Action: Check API status + logs
- Escalation: If unresolved in 3 min, auto-rollback
- Typical fix: Database connectivity / external service

**PostDeploymentErrorRateSpike** (Alert DEP003)
- Action: Check error logs + deployments
- Escalation: If unresolved in 3 min, auto-rollback
- Typical fix: Revert problematic code

**DatabaseMigrationFailed** (Alert DEP004)
- Action: Check migration logs
- Escalation: Page DBA if schema corrupted
- Typical fix: Rollback migration or fix schema

### HIGH Alerts - Alert ops

**DeploymentTakingTooLong** (Alert DEP006)
- Action: Monitor, check what stage is running
- Escalation: Manual cancel if > 20 min
- Typical fix: Investigate stage slowness

**DatabaseMigrationSlow** (Alert DEP007)
- Action: Check DB locks and load
- Escalation: Kill transaction if > 5 min
- Typical fix: Optimize migration query

**SmokeTestsFailingPostDeploy** (Alert DEP008)
- Action: Review failed tests
- Escalation: Determine if test or deployment issue
- Typical fix: Rollback or fix deployment

---

## Glossary

| Term | Meaning |
|------|---------|
| **TTD** | Time To Deploy - how long from trigger to production |
| **SLI** | Service Level Indicator - what we measure |
| **SLO** | Service Level Objective - target for SLI |
| **MTTD** | Mean Time To Detect - how long until we notice |
| **MTTR** | Mean Time To Resolve - how long to fix |
| **Error Budget** | How much failure we tolerate monthly |
| **Auto-rollback** | Automatically reverting failed deployment |
| **Pushgateway** | Prometheus component for short-lived jobs |
| **Cardinality** | Number of unique metric combinations |
| **Scrape** | Prometheus collecting metrics from exporter |

---

## Resources

### Prometheus Documentation
- [Prometheus Overview](https://prometheus.io/docs/prometheus/latest/overview/)
- [Prometheus Alerting](https://prometheus.io/docs/prometheus/latest/configuration/alerting_rules/)
- [Pushgateway](https://prometheus.io/docs/instrumenting/pushing/)

### Grafana Documentation
- [Grafana Dashboards](https://grafana.com/docs/grafana/latest/dashboards/)
- [Dashboard Design](https://grafana.com/docs/grafana/latest/panels-visualizations/)

### Incident Response
- [Runbook Index](../runbooks/)
- [On-Call Guide](../on-call/)
- [Escalation Procedures](../escalation/)

---

## Support & Questions

### Getting Help

**Questions about implementation?**
→ Check [Implementation Guide](DEPLOYMENT-OBSERVABILITY-IMPLEMENTATION.md)

**Need to understand a metric?**
→ Check [Architecture & Design](DEPLOYMENT-OBSERVABILITY.md)

**Incident response?**
→ Check [Runbooks](../runbooks/DEPLOYMENT_*.md)

**Financial questions?**
→ Check [Executive Summary](DEPLOYMENT-OBSERVABILITY-SUMMARY.md)

**Something not working?**
→ Post to #observability-help Slack channel with:
- What you're trying to do
- What you expected
- What actually happened
- Screenshots if helpful

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2025-01-15 | Initial design and documentation |

---

## Next Steps

1. **This week:** Review documents with team
2. **Next week:** Begin Phase 1 implementation
3. **Week 3:** Deploy to production
4. **Week 4:** Team training and optimization
5. **Ongoing:** Monitor and improve

---

**Questions?** Contact @platform-engineering on Slack

**Documentation Maintained By:** Platform Engineering

**Last Review:** 2025-01-15

**Next Review:** 2025-02-15
