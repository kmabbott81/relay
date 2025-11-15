# Observability Quick Reference
## Session 2025-11-11

### Key Metrics to Track

**The Four Golden Signals**:
1. **Latency** (p95 < 200ms): How fast are requests?
2. **Traffic** (RPS): How much load?
3. **Errors** (< 0.1%): What's failing?
4. **Saturation** (CPU/Memory): How full?

### Alert Thresholds

| Alert | Threshold | Severity | Response |
|-------|-----------|----------|----------|
| API Down | 0% success for 1m | CRITICAL | Page on-call now |
| High Error Rate | > 5% for 5m | HIGH | Page on-call in 5m |
| High Latency p95 | > 200ms for 10m | HIGH | Page on-call in 5m |
| Memory High | > 85% for 5m | HIGH | Create ticket |
| Memory Critical | > 95% for 2m | CRITICAL | Page on-call now |
| DB Connection Pool | > 80% for 5m | HIGH | Page on-call in 5m |
| Deployment Failure | Success rate < 95% | HIGH | Page on-call in 5m |
| Smoke Test Failure | Any failure | CRITICAL | Investigate rollback |

### SLO Targets

```
Availability:    99.5% (Beta) | 99.9% (Prod)
Latency p95:     < 200ms (Beta) | < 150ms (Prod)
Error Budget:    43 min/month (Beta)
Deploy Success:  > 95%
```

### Error Budget Tracking

Current Month (November 2025):
```
Budget: 43 minutes of downtime allowed
Used: 15 minutes (1 incident)
Remaining: 28 minutes ← Proceed with caution
```

If remaining < 15 min: STOP risky deployments

### Dashboards

| Dashboard | URL | Refresh | Purpose |
|-----------|-----|---------|---------|
| System Health | `/d/system-health` | 10s | Overall status |
| API Performance | `/d/api-performance` | 30s | Debugging APIs |
| User Activity | `/d/user-activity` | 1m | User metrics |
| Deployment Health | `/d/deployment-health` | 1m | CI/CD status |
| Cost Metrics | `/d/cost-metrics` | 5m | Financial tracking |

### Quick Access

**Prometheus**: http://localhost:9090
**Grafana**: http://localhost:3000 (admin/admin)
**AlertManager**: http://localhost:9093

### Common Commands

```bash
# Start Prometheus + Grafana
docker-compose -f observability/docker-compose.yml up -d

# View recent alerts
curl http://localhost:9090/api/v1/alerts | jq '.data.alerts'

# Check Prometheus targets
curl http://localhost:9090/api/v1/targets | jq '.data.activeTargets'

# Query a metric
curl 'http://localhost:9090/api/v1/query?query=http_requests_total'

# Test alert rule syntax
promtool check rules observability/ALERT_RULES.yml
```

### Incident Response Flow

```
1. Alert fires
   ↓
2. Check dashboard (which component failing?)
   ↓
3. Follow runbook
   ↓
4. Resolve (deploy fix, scale resource, or rollback)
   ↓
5. Post-incident review
```

### Runbooks (First Steps)

**API Down** → Check DB connectivity, recent deployments, LLM API status
**High Error Rate** → Check error logs, identify failing endpoint, check dependencies
**High Latency** → Check database slow queries, cache hit rate, scale resources
**Memory High** → Check for memory leak, monitor GC pauses, restart if > 95%
**DB Connection Pool** → Check for connection leaks, scale pool, restart connections

### Team Contacts

- Platform Team: `@platform` on Slack
- Database Team: `@data` on Slack
- DevOps Team: `@devops` on Slack
- On-Call: Check PagerDuty rotation

### Key Files

```
Main Docs:
  - OBSERVABILITY_2025-11-11.md (comprehensive design)
  - OBSERVABILITY_IMPLEMENTATION_GUIDE.md (step-by-step)

Config Files:
  - observability/PROMETHEUS_CONFIG.yml
  - observability/ALERT_RULES.yml
  - config/alertmanager/alertmanager.yml

Dashboards:
  - observability/dashboards/system-health.json
  - observability/dashboards/api-performance.json
  - observability/dashboards/user-activity.json
  - observability/dashboards/deployment-health.json
  - observability/dashboards/cost-metrics.json

Code:
  - relay_ai/api/main.py (metrics middleware)
  - relay_ai/api/db/metrics.py (database metrics)
  - relay_ai/product/web/lib/metrics.ts (web metrics)
  - relay_ai/api/services/cost_tracker.py (cost events)
```

### Implementation Timeline

**Week 1**: Prometheus + API metrics + Grafana dashboards
**Week 2**: Alerting + AlertManager routing
**Week 3**: Logging + Distributed tracing (optional)
**Week 4**: Cost tracking + Runbooks + Team training

### Critical Metrics to Check Every Day

- [ ] API Success Rate (target > 99.5%)
- [ ] P95 Latency (target < 200ms)
- [ ] Error Rate (target < 0.1%)
- [ ] Memory Usage (target < 75%)
- [ ] Database Connections (target < 80% of pool)
- [ ] Daily Cost (track vs budget)
- [ ] Deployment Success Rate (target > 95%)

### Definition of Done (Observability Complete)

- [ ] All metrics being collected
- [ ] Dashboards updated daily
- [ ] Alerts firing with < 5% false positive rate
- [ ] SLOs being tracked and reported
- [ ] Cost being tracked per operation
- [ ] Team trained on dashboards
- [ ] On-call runbooks updated
- [ ] Incident reviews happening weekly

---

**Version**: 1.0
**Last Updated**: 2025-11-15
**Next Review**: 2025-11-22
