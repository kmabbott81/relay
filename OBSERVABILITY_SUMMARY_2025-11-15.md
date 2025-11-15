# Observability Architecture Summary
## Session 2025-11-11 Infrastructure Changes

**Date**: 2025-11-15
**Project**: Relay AI
**Infrastructure**: Railway API + Vercel Web + Supabase DB + GitHub Actions

---

## Overview

Comprehensive observability architecture designed for monitoring the 2025-11-11 infrastructure changes:
- Rally API rename: `relay-beta-api`, `relay-prod-api` (Railway)
- Unified web app: `relay-studio-one` (Vercel)
- Stage-specific databases: `relay-beta-db`, `relay-prod-db` (Supabase)
- Stage-specific CI/CD: `deploy-beta.yml`, `deploy-prod.yml` (GitHub Actions)

---

## Deliverables Created

### 1. Main Documentation (3 files)

**`OBSERVABILITY_2025-11-11.md`** (23 KB)
- Comprehensive observability architecture
- All 4 golden signals defined with metrics
- SLI/SLO/SLA definitions and targets
- Alert severity levels and thresholds
- 5 dashboard specifications
- 5-phase implementation roadmap
- 80+ specific metrics with definitions

**`OBSERVABILITY_IMPLEMENTATION_GUIDE.md`** (18 KB)
- Day-1 quick start setup (Prometheus + Grafana)
- Phase 1-5 implementation steps
- Python/FastAPI metrics code examples
- Next.js web metrics code examples
- SQLAlchemy database metrics examples
- AlertManager configuration
- Cost tracking implementation
- Testing and validation procedures

**`OBSERVABILITY_SESSION_2025-11-11.md`** (15 KB)
- Infrastructure-specific monitoring
- Environment-specific metrics (Beta vs Prod)
- Railway, Vercel, Supabase monitoring details
- GitHub Actions workflow monitoring
- Zero-downtime validation checklist
- Migration validation procedures
- First week post-launch monitoring plan

### 2. Configuration Files (2 files)

**`observability/PROMETHEUS_CONFIG.yml`** (4 KB)
- Prometheus scrape targets for all environments
- Recording rules for latency percentiles
- Error rate aggregations
- Resource utilization calculations
- 6 scrape jobs configured (Beta API, Prod API, Web, Database, GitHub, Self)

**`observability/ALERT_RULES.yml`** (12 KB)
- 40+ alert rules across 9 categories
- Environment-specific thresholds (Beta vs Prod)
- Severity levels: critical, high, medium, low
- Runbook references for each alert
- Annotations with debugging guidance

### 3. Quick Reference (1 file)

**`OBSERVABILITY_QUICKREF.md`** (4 KB)
- Quick lookup for key metrics
- Alert thresholds summary table
- SLO targets reference
- Dashboard URLs
- Common commands
- Incident response flow
- Team contacts

---

## Architecture at a Glance

### The Four Golden Signals

```
1. LATENCY (p95 < 200ms)
   Metrics: http_request_duration_seconds
   Alerts: High latency > 2s for 10m
   SLO: 99.5% of requests < 200ms

2. TRAFFIC (10-500 RPS)
   Metrics: http_requests_total
   Alerts: RPS drops 50% suddenly
   Tracks: Request rate per endpoint

3. ERRORS (< 0.1%)
   Metrics: http_requests_total{status_code="5.."}
   Alerts: Error rate > 5% for 5 minutes
   SLO: 99.9% availability (0.1% error budget)

4. SATURATION (CPU < 70%, Memory < 75%)
   Metrics: process_resident_memory_bytes, db_connections
   Alerts: Memory > 85%, DB pool > 80%
   Predicts: Capacity to handle spikes
```

### Dashboard Structure

```
System Health                (Real-time status overview)
├── API Status (🟢 99.94%)
├── Error Rate (0.2%)
├── P95 Latency (180ms)
├── Uptime % (99.94%)
├── Request Rate graph
├── Error Rate graph
└── Database Health

API Performance              (Debugging & optimization)
├── Request rate by endpoint
├── Error rate by status
├── Latency percentiles
├── Top slow endpoints
├── Error details table
└── Dependency health

User Activity                (Business metrics)
├── Active users (234)
├── Active sessions (412)
├── New signups (18)
├── Page views breakdown
├── Feature usage
└── Retention rates

Deployment Health            (CI/CD pipeline)
├── Success rate (94%)
├── Build metrics
├── Recent deployments
├── Smoke test results
└── Error budget tracking

Cost Metrics                 (Financial tracking)
├── Daily cost ($234.56)
├── Monthly projection ($7,200)
├── Cost by component (API 65%)
├── Cost per user ($2.40)
└── Budget utilization (87%)
```

### Alert Routing

```
CRITICAL (0 min SLA)              → PagerDuty + Slack + SMS
  - API unavailable
  - Database down
  - Smoke tests failing
  - Data loss detected

HIGH (5 min SLA)                  → PagerDuty + Slack
  - Error rate > 5% for 5m
  - Latency p95 > 2s for 10m
  - Memory > 85% for 5m
  - DB pool > 80% for 5m

MEDIUM (4 hour SLA)               → Slack #ops-alerts
  - Error rate 1-5% for 15m
  - Memory 70-85% for 10m
  - Disk usage > 80%
  - Build time > 120s

LOW (Logged)                      → No notification
  - Error rate 0.1-1% for 30m
  - Latency p99 > 2s
  - Build time 60-120s
```

### SLO Framework

```
SLI (Measure)               SLO (Target)         SLA (Commitment)
├─ Availability            ├─ 99.5% (Beta)      ├─ 99.5% uptime
│  (% success)             │  99.9% (Prod)      │  10% credit if < 99.5%
│
├─ Latency                 ├─ p95 < 200ms       ├─ p95 < 300ms
│  (p95, p99)              │  p99 < 500ms       │  5% credit if > 500ms
│
└─ Deployment Success      └─ > 95%             └─ Automatic rollback

Error Budget:
  99.5% SLO → 0.5% = 43 min/month failure allowed
  Used: 15 min (1 incident)
  Remaining: 28 min ← Proceed carefully
```

---

## Implementation Timeline

### Week 1: Foundation
- [ ] Deploy Prometheus (15 min)
- [ ] Deploy Grafana (15 min)
- [ ] Add API metrics middleware (2 hours)
- [ ] Create 5 dashboards (4 hours)
- **Deliverable**: Metrics flowing, dashboards visible

### Week 2: Alerting
- [ ] Configure AlertManager (1 hour)
- [ ] Create alert rules (2 hours)
- [ ] Test alert routing (1 hour)
- [ ] Slack + PagerDuty integration (1 hour)
- **Deliverable**: Alerts firing with < 5% false positives

### Week 3: Logging & Tracing
- [ ] Structured JSON logging (2 hours)
- [ ] OpenTelemetry setup (3 hours)
- [ ] Deploy Jaeger or Tempo (2 hours)
- **Deliverable**: End-to-end tracing working

### Week 4: Cost & Documentation
- [ ] Cost event logging (2 hours)
- [ ] Cost forecasting (2 hours)
- [ ] Runbook creation (3 hours)
- [ ] Team training (2 hours)
- **Deliverable**: Cost tracking + trained team

---

## Key Metrics at a Glance

### API Metrics (50+ metrics)
```
Request: http_requests_total, http_request_duration_seconds, http_requests_in_flight
Errors: http_requests_total{status_code="5.."}, error_rate_percent
Database: database_query_duration_seconds, database_connections_active, database_slow_queries_total
Business: chat_messages_total, llm_tokens_total, api_cost_usd_total
Cache: cache_hits_total, cache_hit_rate
Auth: auth_attempts_total, auth_failure_rate, api_key_validation_failures
Jobs: async_jobs_queued, async_job_duration_seconds
```

### Web Metrics (15+ metrics)
```
Performance: web_page_load_time_seconds, first_contentful_paint_seconds, largest_contentful_paint_seconds
Vitals: cumulative_layout_shift, time_to_first_byte_seconds
Interactions: page_view_total, click_event_total, form_submission_total, session_duration_seconds
Errors: javascript_error_total, api_call_errors_client_total
```

### Database Metrics (20+ metrics)
```
Connections: database_connections_active, database_connections_idle, database_connection_pool_available
Queries: database_query_duration_seconds, database_slow_queries_total, database_query_errors_total
Tables: database_table_row_count, database_table_size_bytes
Replication: database_replication_lag_seconds, database_replication_errors_total
Backups: database_backup_duration_seconds, database_backup_size_bytes
```

### Infrastructure Metrics (15+ metrics)
```
CPU: process_cpu_seconds_total, railway_cpu_utilization_percent
Memory: process_resident_memory_bytes, process_virtual_memory_bytes, railway_memory_utilization_percent
Network: network_bytes_recv_total, network_bytes_sent_total, network_tcp_connections
Disk: disk_read_bytes_total, disk_write_bytes_total, disk_usage_percent
Container: railway_container_restarts_total, railway_container_status
```

### Deployment Metrics (10+ metrics)
```
Workflows: github_workflow_duration_seconds, github_workflow_status, github_build_success_rate
Deployment: deployment_duration_seconds, deployment_frequency, deployment_rollback_count_total
Validation: migration_execution_time_seconds, migration_success_rate, deployment_smoke_test_status
```

---

## File Structure

```
/c/Users/kylem/openai-agents-workflows-2025.09.28-v1/
├── OBSERVABILITY_2025-11-11.md                    (Main architecture: 60+ pages)
├── OBSERVABILITY_IMPLEMENTATION_GUIDE.md          (Step-by-step: 40+ pages)
├── OBSERVABILITY_SESSION_2025-11-11.md            (Session-specific: 30+ pages)
├── OBSERVABILITY_QUICKREF.md                      (Quick lookup: 2 pages)
├── OBSERVABILITY_SUMMARY_2025-11-15.md            (This file: 5 pages)
│
├── observability/
│   ├── PROMETHEUS_CONFIG.yml                      (Scrape targets + recording rules)
│   ├── ALERT_RULES.yml                            (40+ alert rules)
│   ├── dashboards/
│   │   ├── system-health.json                     (To be created)
│   │   ├── api-performance.json                   (To be created)
│   │   ├── user-activity.json                     (To be created)
│   │   ├── deployment-health.json                 (To be created)
│   │   └── cost-metrics.json                      (To be created)
│   └── README.md                                  (Already exists: updated)
│
├── config/
│   ├── alertmanager/
│   │   └── alertmanager.yml                       (Alert routing + notifications)
│   └── prometheus/
│       └── (existing configs + new files)
│
└── relay_ai/
    ├── api/
    │   ├── main.py                                (Add metrics middleware)
    │   ├── db/
    │   │   └── metrics.py                         (Database metrics)
    │   └── services/
    │       └── cost_tracker.py                    (Cost event logging)
    └── product/web/
        └── lib/
            └── metrics.ts                         (Web metrics)
```

---

## Success Criteria

**Week 1 (Foundation)**
- [ ] Prometheus scraping all 5+ targets
- [ ] Grafana dashboards displaying metrics
- [ ] No gaps in metric collection
- [ ] Baseline established for all golden signals

**Week 2 (Alerting)**
- [ ] 40+ alert rules configured
- [ ] Alert false positive rate < 5%
- [ ] Alert response time < 1 minute for critical
- [ ] Team trained on alert handling

**Week 3 (Logging & Tracing)**
- [ ] Structured logging in all services
- [ ] Distributed tracing end-to-end
- [ ] Trace UI showing latency breakdown
- [ ] Can identify slow dependencies

**Week 4 (Complete)**
- [ ] Cost tracking per user/operation
- [ ] Monthly forecasting working
- [ ] 10+ runbooks documented
- [ ] Team confident using observability stack

**Ongoing**
- [ ] Error rate < 0.1% (SLO)
- [ ] Latency p95 < 200ms (SLO)
- [ ] Deploy success > 95% (SLO)
- [ ] Weekly incident review happening
- [ ] SLOs on track (error budget > 10%)

---

## Environment Baselines (To Be Established)

### Beta (development)
```
Request Rate:          10-50 RPS
Error Rate:            0.1-1.0%
Latency p95:           150-250ms
Memory Usage:          200-350MB / 512MB max
DB Connections:        2-8 / 10 max
Deploy Frequency:      2-5 per day
Build Time:            45-70 seconds
Uptime:                99%+ (dev tolerance)
```

### Production (stable)
```
Request Rate:          100-500 RPS
Error Rate:            0.01-0.1%
Latency p95:           100-200ms
Memory Usage:          300-450MB / 512MB max
DB Connections:        15-40 / 50 max
Deploy Frequency:      1-3 per day
Build Time:            40-60 seconds
Uptime:                99.9%+ (SLO)
```

---

## Next Steps

1. **This Week**: Review architecture documents and decide on tools
   - Self-hosted Prometheus + Grafana vs Managed (Datadog, New Relic)
   - LocalStorage vs Remote Storage for metrics
   - PagerDuty integration yes/no

2. **Next Week**: Start Phase 1 implementation
   - Deploy Prometheus + Grafana
   - Add API metrics to FastAPI
   - Create first 5 dashboards

3. **Week 3**: Deploy Phase 2
   - Configure AlertManager
   - Create alert rules
   - Test with synthetic data

4. **Week 4+**: Phase 3-5 + ongoing refinement
   - Logging + Tracing
   - Cost tracking
   - Team training

---

## Questions to Answer Before Implementation

1. **Tool Choice**: Prometheus/Grafana vs Managed Service?
2. **Retention**: How long to keep metrics? (30 days vs 1 year)
3. **Alerting**: Email only or PagerDuty required?
4. **Sampling**: Log 100% of requests or sample?
5. **Privacy**: What PII to avoid in metrics/logs?
6. **Budget**: How much to spend on observability?
7. **Team**: Who owns on-call rotation?
8. **Escalation**: Who to page for critical incidents?

---

## References & Resources

**Core Concepts**:
- Google's "Four Golden Signals": https://sre.google/sre-book/monitoring-distributed-systems/
- SRE Book on Monitoring: https://sre.google/sre-book/
- Prometheus Best Practices: https://prometheus.io/docs/practices/

**Tools**:
- Prometheus Docs: https://prometheus.io/docs/
- Grafana Dashboarding: https://grafana.com/docs/grafana/latest/
- AlertManager: https://prometheus.io/docs/alerting/latest/alertmanager/
- OpenTelemetry: https://opentelemetry.io/docs/

**Examples**:
- Prometheus Client Libraries: https://prometheus.io/docs/instrumenting/clientlibs/
- FastAPI Instrumentation: https://opentelemetry.io/docs/instrumentation/python/
- React Web Vitals: https://github.com/GoogleChrome/web-vitals

---

## Contact

**Questions?**
- Observability Lead: Kyle Mahan (@kylem)
- Created: 2025-11-15
- Last Updated: 2025-11-15

**Documents**:
1. `OBSERVABILITY_2025-11-11.md` - Full architecture (START HERE)
2. `OBSERVABILITY_IMPLEMENTATION_GUIDE.md` - Code & setup
3. `OBSERVABILITY_SESSION_2025-11-11.md` - Session-specific
4. `OBSERVABILITY_QUICKREF.md` - Quick lookup
5. `OBSERVABILITY_SUMMARY_2025-11-15.md` - This file

---

**Status**: Design Complete, Ready for Implementation
**Timeline**: 4 weeks to full implementation
**Effort**: 40-60 hours for core setup + ongoing maintenance
