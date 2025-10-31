# Infrastructure Validation Checklist — R1 Task D Phase 4

**Date**: 2025-10-31
**Status**: Ready for staging deployment validation
**Model**: Full infrastructure mode (Postgres, Redis, Prometheus, Grafana)

---

## Pre-Deployment Verification

### ✅ Code Quality Gate (Local)

- [x] All tests pass: 44/44 (21 Phase 2 scaffold + 23 Phase 1 envelope)
- [x] Linting clean: ruff, black
- [x] Type hints: Pydantic v2, AsyncPG, Redis client all correct
- [x] Imports: All crypto, RLS, metrics imports verified
- [x] Git history: d5d156c (Phase 1) → c3365f8 (Phase 2) → d262666 (Phase 3)

### ✅ Artifacts Generated (Local)

- [x] `requirements.lock`: 287 packages pinned
- [x] `SBOM_CYCLONEDX.dev.json`: 288 components, no CVE scan performed
- [x] `openapi.v1.json`: 4 endpoints, 11 schemas
- [x] `PROMETHEUS_METRICS_SCHEMA.yaml`: 21 metrics + 7 alert rules
- [x] `TASK_D_PHASE3_AGENT_GATES_REPORT.md`: All 7 gates PASS

---

## Staging Infrastructure Validation (Must Verify)

### Phase 4A: PostgreSQL Validation

**Prerequisites**:
- PostgreSQL 17+ running
- `memory_chunks` table migrated (via alembic)
- `app_user` role created (non-superuser)
- RLS policies enforced

**Checklist**:

| Item | Command | Expected | Status |
|------|---------|----------|--------|
| **DB Connection** | `psql -U postgres -d railway -c "SELECT version();"` | PostgreSQL 17.x connected | [ ] |
| **memory_chunks table** | `SELECT COUNT(*) FROM pg_tables WHERE tablename='memory_chunks';` | 1 (table exists) | [ ] |
| **RLS Enabled** | `SELECT relrowsecurity FROM pg_class WHERE relname='memory_chunks';` | true | [ ] |
| **RLS Policies** | `SELECT COUNT(*) FROM pg_policies WHERE tablename='memory_chunks';` | ≥4 (select, insert, update, delete) | [ ] |
| **Policy Details** | `SELECT policyname, cmd FROM pg_policies WHERE tablename='memory_chunks';` | Show all 4 policies | [ ] |
| **app_user role** | `SELECT rolname FROM pg_roles WHERE rolname='app_user';` | app_user (not superuser) | [ ] |
| **User hash index** | `SELECT COUNT(*) FROM pg_indexes WHERE indexname LIKE 'idx_memory%user_hash%';` | ≥2 | [ ] |
| **Vector extension** | `SELECT extname FROM pg_extension WHERE extname='vector';` | vector | [ ] |
| **Connection pool** | `SELECT count(*) FROM pg_stat_activity WHERE usename='app_user';` | 0-5 (idle or in-use) | [ ] |

**Validation Script**:
```bash
python scripts/test_db_rls.py
# Expected output: All [PASS] statements
```

**Rollback Plan** (if RLS validation fails):
```sql
-- Disable RLS temporarily
ALTER TABLE memory_chunks DISABLE ROW LEVEL SECURITY;

-- Or rollback migration
alembic downgrade 20251019_memory_schema_rls
```

---

### Phase 4B: Redis Rate Limiting Validation

**Prerequisites**:
- Redis running (localhost:6379 or configured URL)
- `REDIS_URL` environment variable set
- No existing rate-limit keys from previous runs

**Checklist**:

| Item | Command | Expected | Status |
|------|---------|----------|--------|
| **Redis Connection** | `redis-cli PING` | PONG | [ ] |
| **Key Space** | `redis-cli DBSIZE` | > 0 or empty (clean state) | [ ] |
| **Rate Limit Test** | `python scripts/test_redis_rate_limit.py` | See rate limiting in action | [ ] |
| **X-RateLimit Headers** | Test request to `/api/v1/memory/index` with 100 reqs/s | X-RateLimit-Remaining decreases | [ ] |
| **429 Response** | Send 101st request when limit=100 | HTTP 429 + Retry-After header | [ ] |
| **Key Expiration** | Wait 3600s or check TTL | `PTTL rate_limit:user_123` shows < 3600000 | [ ] |

**Rate Limit Test Script** (to create):
```bash
# Generate 150 requests in 10 seconds
for i in {1..150}; do
  curl -H "Authorization: Bearer $JWT" \
       -H "X-Client-IP: 127.0.0.1" \
       http://localhost:8000/api/v1/memory/index \
       -d '{"text":"test"}' &
done
wait

# Check for 429 responses and headers
# Expected: Last ~50 requests get 429 with Retry-After
```

**Rollback Plan**:
```bash
redis-cli FLUSHALL  # Clear all rate limit keys
```

---

### Phase 4C: Prometheus Metrics Validation

**Prerequisites**:
- Prometheus running on localhost:9090
- FastAPI app running on localhost:8000 with `/metrics` endpoint
- Scrape config updated to include memory_api job

**Checklist**:

| Item | Command | Expected | Status |
|------|---------|----------|--------|
| **Metrics Endpoint** | `curl http://localhost:8000/metrics` | 200 OK + Prometheus format | [ ] |
| **Metric Count** | `curl -s http://localhost:8000/metrics \| grep -c "^memory"` | ≥ 18 metric lines | [ ] |
| **Key Metrics Present** | Check for: `memory_query_latency_ms`, `relay_memory_request_latency_ms`, `relay_memory_errors_total` | All 3 present | [ ] |
| **Prom Scrape** | `curl http://localhost:9090/api/v1/targets` | Memory API target up | [ ] |
| **Query p95 Latency** | Prometheus: `histogram_quantile(0.95, memory_query_latency_ms_bucket)` | Numeric value (not NaN) | [ ] |
| **Error Rate** | `rate(relay_memory_errors_total[5m])` | Numeric value | [ ] |
| **Circuit Breaker** | `memory_rerank_skipped_total` | Counter value | [ ] |

**Validation**:
```bash
# Check Prometheus scrape config
curl http://localhost:9090/api/v1/targets | jq '.data.activeTargets[] | select(.labels.job=="memory_api")'

# Query a metric
curl 'http://localhost:9090/api/v1/query?query=memory_query_latency_ms_count'
```

---

### Phase 4D: Grafana Dashboard Validation

**Prerequisites**:
- Grafana running on localhost:3000
- Prometheus data source configured
- Memory API dashboard imported

**Checklist**:

| Item | Action | Expected | Status |
|------|--------|----------|--------|
| **Grafana Connection** | Open http://localhost:3000 | Grafana UI loads | [ ] |
| **Prometheus DS** | Settings → Data Sources | "Prometheus" listed as active | [ ] |
| **Dashboard Import** | Import from `monitoring/grafana_memory_dashboard.json` | Dashboard appears in sidebar | [ ] |
| **Panels Render** | View each dashboard panel | All panels show data (no red errors) | [ ] |
| **Query Latency Panel** | p50, p95, p99 latency graphs | Lines show trend over time | [ ] |
| **Error Rate Panel** | 429 count, 5xx errors | Bars or numbers visible | [ ] |
| **RLS Panel** | memory_rls_blocks_total counter | Value 0 or small integer | [ ] |
| **Refresh Rate** | Set auto-refresh to 5s | Panels update automatically | [ ] |

**Dashboard Import**:
```bash
curl -X POST \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $GRAFANA_API_TOKEN" \
  http://localhost:3000/api/dashboards/db \
  -d @monitoring/grafana_memory_dashboard.json
```

---

### Phase 4E: Alert Rules Validation

**Prerequisites**:
- Alertmanager running
- Alert rules loaded into Prometheus
- Notification channel configured (Slack, PagerDuty, etc.)

**Checklist**:

| Alert | Threshold | Test Method | Expected | Status |
|-------|-----------|------------|----------|--------|
| **MemoryQueryLatencyHigh** | p95 > 400ms for 5m | Simulate slow query | ⚠️ Warning fired | [ ] |
| **MemoryTTFVExceeded** | p95 > 1500ms for 5m | Simulate end-to-end delay | ⚠️ Warning fired | [ ] |
| **MemoryRerankCircuitBreakerHigh** | >10% skips for 10m | Trigger timeout | ⚠️ Warning fired | [ ] |
| **MemoryCrossTenantAccessAttempt** | Count > 0 in 5m | (Should never trigger) | 🔴 Critical (if triggered) | [ ] |
| **MemoryRLSViolationHigh** | > 5 per minute for 5m | Attempt cross-user query | ⚠️ Warning fired | [ ] |
| **MemoryRateLimitExceededHigh** | > 30 per minute for 10m | Flood with requests | ℹ️ Info fired | [ ] |

**Alert Firing Test**:
```bash
# Generate high latency
python scripts/test_alert_latency.py --duration 360 --latency 2000

# Verify alert in Prometheus Alerts UI
curl http://localhost:9090/api/v1/alerts | jq '.data.alerts[] | select(.labels.alertname=="MemoryQueryLatencyHigh")'

# Check Alertmanager received it
curl http://localhost:9093/api/v1/alerts
```

---

### Phase 4F: Load Testing & Performance Baseline

**Objectives**:
- Establish p50, p95, p99 latency baselines
- Verify TTFV < 1500ms target
- Confirm rate limiting kicks in at threshold
- Validate reranker circuit breaker at 250ms timeout

**Load Test Profile**:
```yaml
ramp_up: 30s  # Gradual increase to target RPS
duration: 300s  # 5 minutes steady state
target_rps: 20  # Requests per second
max_concurrent: 50

endpoints:
  - /api/v1/memory/index
  - /api/v1/memory/query
  - /api/v1/memory/summarize
  - /api/v1/memory/entities
```

**Expected Results**:

| Metric | Target | Acceptable | Threshold |
|--------|--------|-----------|-----------|
| Query p50 latency | < 200ms | < 250ms | ❌ > 350ms |
| Query p95 latency | < 350ms | < 400ms | ❌ > 500ms |
| Query p99 latency | < 500ms | < 600ms | ❌ > 750ms |
| TTFV p95 | < 1500ms | < 1600ms | ❌ > 1800ms |
| Rerank p95 | < 150ms | < 200ms | ❌ > 250ms |
| Error rate | < 0.1% | < 0.5% | ❌ > 1% |
| Success rate | > 99.9% | > 99.5% | ❌ < 99% |

**Load Test Script** (using locust or similar):
```bash
locust -f scripts/load_test_memory_api.py \
  --host=http://localhost:8000 \
  --users=50 \
  --spawn-rate=2 \
  --run-time=5m \
  --headless
```

**Pass Criteria**:
- ✅ All p95 latencies < 400ms
- ✅ TTFV p95 < 1500ms
- ✅ Error rate < 1%
- ✅ Rate limiting triggers correctly at 100 req/hour

---

### Phase 4G: Security & Compliance Validation

**Checklist**:

| Check | Method | Expected | Status |
|-------|--------|----------|--------|
| **AAD Validation** | Try decrypt with wrong user_hash | ValueError raised, 403 response | [ ] |
| **RLS Isolation** | User A queries User B's chunks | Empty result set (0 rows) | [ ] |
| **JWT Validation** | Missing/invalid/expired token | 401 response | [ ] |
| **XSS Prevention** | Inject `<script>` in request body | Sanitized or rejected (422) | [ ] |
| **SQL Injection** | Inject SQL syntax in query param | Parameterized query (no injection) | [ ] |
| **CORS Headers** | Cross-origin request | Correct CORS headers or 403 | [ ] |
| **Rate Limit Bypass** | Spoof X-Forwarded-For | Rate limiter still enforced | [ ] |

**Security Test Script**:
```bash
python scripts/test_security_scenarios.py
```

---

## Post-Deployment Monitoring (1st Week)

### Metrics to Watch

- **Query Latency Trend**: Should stabilize within first 24h
- **Error Rate**: Should drop to < 0.1% after warmup
- **Circuit Breaker Trips**: Should be rare (< 1% of queries)
- **RLS Blocks**: Should be 0 (or investigate immediately if > 0)
- **Cross-Tenant Attempts**: Should be 0 (CRITICAL if > 0)
- **Rate Limit Events**: Normal (will increase with traffic)

### Daily Health Checks

```bash
# Check Prometheus targets
curl http://localhost:9090/api/v1/targets | jq '.data.activeTargets[] | .health'

# Query key metrics
curl 'http://localhost:9090/api/v1/query?query=up{job="memory_api"}'

# Check error rate (should be low)
curl 'http://localhost:9090/api/v1/query?query=rate(relay_memory_errors_total[5m])'

# Verify RLS is working
python scripts/test_rls_isolation.py
```

### Rollback Triggers

If ANY of these conditions occur:

1. **Error rate > 5%** → Roll back Phase 3 code to Phase 2 scaffold
2. **RLS violations detected** → Roll back migrations, re-enable without RLS
3. **Cross-tenant access attempt** → Immediate incident, disable API
4. **TTFV > 3000ms** → Investigate, possibly roll back crypto wiring
5. **Rate limit bypass detected** → Investigate Redis configuration
6. **Circuit breaker trips > 50%** → Reduce reranker timeout or disable reranking

**Rollback Command**:
```bash
# Revert to Phase 2 (working scaffold)
git checkout c3365f8 -- src/memory/
python -m pytest tests/memory/test_api_scaffold.py  # Verify tests pass
# Deploy Phase 2 code
```

---

## Sign-Off Checklist

| Role | Check | Signature | Date |
|------|-------|-----------|------|
| **DBA** | RLS policies verified, no data loss | [ ] | [ ] |
| **Infra** | Prometheus/Grafana/Redis operational | [ ] | [ ] |
| **Security** | Encryption working, no data leakage | [ ] | [ ] |
| **Observability** | Alerts configured, dashboards live | [ ] | [ ] |
| **QA** | Load test passed, SLOs met | [ ] | [ ] |
| **Release Lead** | All checks green, ready for prod | [ ] | [ ] |

---

## Next Steps (Phase 5)

After Phase 4 validation passes:

1. **Staging → Production promotion** (1-week canary)
2. **Customer rollout** (gradual, 5%→25%→100%)
3. **24/7 monitoring** (dedicated on-call)
4. **Weekly SLO reviews** (latency, error rate, availability)

---

**Generated**: 2025-10-31 by Sonnet 4.5
**Reference**: TASK_D_PHASE3_AGENT_GATES_REPORT.md
