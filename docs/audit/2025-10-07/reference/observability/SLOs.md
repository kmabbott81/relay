# Service Level Objectives (SLOs)

**Purpose:** Define quantitative reliability targets for Relay Actions API.

## Overview

SLOs represent our reliability commitments to users. They drive alerting, incident response priorities, and engineering decisions. Each SLO has an associated **error budget** — the amount of unreliability we can tolerate before impacting user experience.

---

## SLO Definitions

### 1. Light Endpoints (List/Preview) - Latency

**Endpoints:** `/actions`, `/actions/preview`, `/audit`

**Target:** p99 latency ≤ 50ms

**Measurement Window:** 30 days

**Error Budget:**
- Tolerate: 1% of requests > 50ms
- At 1M requests/month: 10,000 slow requests allowed

**Why this matters:**
- List and preview are "fast path" operations used in Studio UI
- Users expect sub-100ms response times for interactive workflows
- p99 ensures tail latency doesn't degrade user experience

**PromQL Query:**
```promql
histogram_quantile(
  0.99,
  rate(http_request_duration_seconds_bucket{path=~"/actions|/audit"}[5m])
)
```

---

### 2. Webhook Execute - Latency

**Endpoint:** `/actions/execute` (webhook adapter)

**Target:** p95 latency ≤ 1.2s

**Measurement Window:** 30 days

**Error Budget:**
- Tolerate: 5% of requests > 1.2s
- At 100K executions/month: 5,000 slow webhooks allowed

**Why this matters:**
- Execute involves external webhook calls (network + remote processing)
- p95 (not p99) balances user experience with webhook variability
- 1.2s threshold leaves room for 500ms webhook latency + 200ms overhead

**PromQL Query:**
```promql
histogram_quantile(
  0.95,
  rate(http_request_duration_seconds_bucket{path="/actions/execute"}[5m])
)
```

---

### 3. Error Rate

**Endpoints:** All `/actions` endpoints

**Target:** Error rate ≤ 1%

**Measurement Window:** 7 days

**Error Budget:**
- Tolerate: 1% of requests return 5xx errors
- At 1M requests/week: 10,000 failed requests allowed

**Excludes:**
- 4xx client errors (user mistakes, not system failures)
- Rate limit 429s (intentional throttling)

**Why this matters:**
- High error rates indicate system instability
- 1% threshold balances reliability with operational complexity
- 7-day window smooths out temporary spikes

**PromQL Query:**
```promql
sum(rate(http_requests_total{status=~"5.."}[5m]))
/
sum(rate(http_requests_total[5m]))
```

---

### 4. Availability

**Target:** ≥ 99.9% uptime (monthly)

**Measurement Window:** 30 days

**Error Budget:**
- Tolerate: 43.2 minutes downtime per month
- At 720 hours/month: 43.2 minutes unavailable allowed

**Definition of "Down":**
- Health endpoint (`/_stcore/health`) returns non-200
- Sustained 5xx error rate > 50% for > 1 minute

**Why this matters:**
- 99.9% is industry standard for SaaS APIs
- Monthly window aligns with billing cycles
- Excludes planned maintenance windows (announced 48h in advance)

**PromQL Query:**
```promql
avg_over_time(
  up{job="relay-backend"}[30d]
)
```

---

## Error Budget Consumption

**Formula:**
```
Error Budget Consumed = (Total Requests - Good Requests) / Total Requests
```

**Example (Latency SLO):**
- Total requests: 1,000,000
- Requests > 50ms: 8,000
- Error budget: 1% = 10,000 requests
- Consumed: 8,000 / 10,000 = **80% of budget**
- Remaining: **20%** (2,000 requests)

**Actions based on consumption:**
- **< 50% consumed:** Normal operations. Focus on features.
- **50-80% consumed:** Warning. Review incidents. Pause risky deploys.
- **80-100% consumed:** Critical. Freeze features. Focus on reliability.
- **> 100% consumed:** SLO breach. Incident. Postmortem required.

---

## SLO Review Schedule

**Weekly:**
- Review error budget consumption
- Identify trends (degrading latency, error spikes)
- Update PromQL queries if needed

**Monthly:**
- Generate SLO compliance report
- Review breaches and postmortems
- Adjust targets if consistently under/over budget

**Quarterly:**
- Re-evaluate SLO targets based on user feedback
- Update measurement windows if needed
- Align SLOs with business goals

---

## Alert Thresholds

Alerts fire **before** SLOs are breached, allowing proactive response.

### Latency Alerts

**Light endpoints p99 > 50ms:**
- Threshold: p99 > 50ms for 5 minutes
- Severity: Warning
- Action: Investigate slow queries, check DB load

**Webhook p95 > 1.2s:**
- Threshold: p95 > 1.2s for 5 minutes
- Severity: Warning
- Action: Check webhook receiver latency, review timeouts

### Error Rate Alerts

**5xx error rate > 1%:**
- Threshold: Error rate > 1% for 5 minutes
- Severity: Critical
- Action: Check logs, rollback recent deploy if needed

**Sustained 5xx streak:**
- Threshold: Error rate > 10% for 3 minutes
- Severity: Page
- Action: Immediate incident response

### Rate Limit Alerts

**Rate limit breaches sustained:**
- Threshold: Rate limit hits > 0 for 10 minutes
- Severity: Info
- Action: Review workspace usage, consider limit increase

---

## Metrics Collection

**Prometheus Metrics:**
- `http_request_duration_seconds` (histogram) - Request latency
- `http_requests_total` (counter) - Request counts by status code
- `rate_limit_breaches_total` (counter) - Rate limit hits
- `webhook_duration_seconds` (histogram) - Webhook latency
- `up` (gauge) - Service availability

**Scrape Interval:** 15s

**Retention:** 30 days (local Prometheus), 1 year (remote storage)

---

## Grafana Dashboard

Golden signals dashboard: `observability/dashboards/golden-signals.json`

**Panels:**
1. **Request Rate (RPM)** - Line graph of requests/minute
2. **Error Rate (%)** - Line graph of 5xx errors vs total
3. **Latency (p50/p95/p99)** - Multi-line graph by endpoint
4. **Rate Limit Hits** - Counter of 429 responses
5. **SLO Compliance** - Gauge showing error budget remaining

**Time Range:** Last 24 hours (default), adjustable to 7/30 days

---

## References

- [Google SRE Book: Implementing SLOs](https://sre.google/workbook/implementing-slos/)
- [Prometheus Query Best Practices](https://prometheus.io/docs/practices/histograms/)
- [Grafana Dashboard Design](https://grafana.com/docs/grafana/latest/dashboards/)

---

🤖 Generated with [Claude Code](https://claude.com/claude-code)

*Document version: Sprint 51 Phase 3 (2025-10-07)*
