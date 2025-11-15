# Observability Architecture: Session 2025-11-11

**Date**: 2025-11-15
**Version**: 1.0
**Status**: Design Specification
**Applies To**: Beta & Production infrastructure (Railway API, Vercel Web, Supabase)

---

## Executive Summary

This document defines comprehensive monitoring and observability for Relay AI infrastructure following the 2025-11-11 deployment changes:
- **Rail way API**: `relay-beta-api.railway.app` (Beta), `relay-prod-api.railway.app` (Prod)
- **Vercel Web**: `relay-studio-one.vercel.app` (shared across stages)
- **Supabase**: `relay-beta-db`, `relay-prod-db`
- **GitHub Actions**: Stage-specific CI/CD workflows

### Key Goals
1. **Visibility**: Track health across all components (API, Web, Database, Deployments)
2. **Alerting**: Detect real problems (not noise) with <5% false positive rate
3. **Cost Control**: Monitor token usage and request volume for financial tracking
4. **Performance**: Maintain <1% observability overhead
5. **User Experience**: Track real user metrics (Web Vitals, session health)

---

## Part 1: Metrics Framework

### 1.1 The Four Golden Signals

Every alert and dashboard should map to one of these four user-impacting signals:

#### 1. **LATENCY** - How long do requests take?

**Key Metrics**:
```
api_request_duration_seconds:
  - p50 (median): < 100ms (good), > 500ms (alert)
  - p95 (95th percentile): < 200ms (target), > 2s (alert - HIGH)
  - p99 (99th percentile): < 500ms (target), > 5s (alert - HIGH)

web_page_load_time_seconds:
  - TTFB (Time to First Byte): < 100ms
  - FCP (First Contentful Paint): < 1s
  - LCP (Largest Contentful Paint): < 2.5s

database_query_duration_seconds:
  - Read queries: p95 < 50ms
  - Write queries: p95 < 100ms
  - Slow query (> 1s): count and log
```

**Why**: Users directly experience latency. A slow API means poor experience.

---

#### 2. **TRAFFIC** - How much load is the system handling?

**Key Metrics**:
```
api_requests_total:
  - Requests per second (RPS)
  - Target: Beta 10-50 RPS, Prod 100-500 RPS
  - Labels: method (GET/POST), endpoint, status

web_page_views_total:
  - Page views per minute
  - Unique sessions per minute
  - Return visitor %

database_connections_active:
  - Current active connections
  - Target: < 10 for Beta, < 50 for Prod
  - Max pool size alert: > 80%

token_usage_total:
  - Input tokens per minute
  - Output tokens per minute
  - Cost tracking per operation type
```

**Why**: Understand what the system is handling. Helps with capacity planning and cost forecasting.

---

#### 3. **ERRORS** - What % of requests fail?

**Key Metrics**:
```
api_errors_total:
  - 4xx errors (client errors): should be < 1%
  - 5xx errors (server errors): should be 0% during normal operation
  - Target SLO: 99.9% success rate (0.1% error rate)

error_rate_percent:
  - Overall: (total_errors / total_requests) * 100
  - By endpoint: which endpoints are broken?
  - By status code: 500, 502, 503, 504, etc.

exception_count:
  - Unhandled exceptions (count)
  - Database errors (connection, timeout)
  - Third-party API errors

failed_deployments:
  - Deploy success rate: target > 95%
  - Failed builds: alert if 3+ in a row
  - Rollback rate: should be < 2%
```

**Why**: Errors directly impact users. Critical for SLO/SLA tracking.

---

#### 4. **SATURATION** - How full are resources?

**Key Metrics**:
```
cpu_utilization_percent:
  - Railway API: alert if > 70%, critical if > 90%
  - Vercel: auto-scales (monitor cold starts)

memory_utilization_percent:
  - Railway API: alert if > 75%, critical if > 90%
  - Target: GC pause < 100ms

disk_utilization_percent:
  - Database disk: alert if > 80%, critical if > 95%
  - Backup disk: ensure space for backups

connection_pool_utilization:
  - Active / Max connections
  - Alert: > 80%
  - Critical: > 95%

queue_depth:
  - Async job queue length
  - Alert if > 1000 jobs pending
  - Monitor max queue time

request_queue_time:
  - Time waiting in queue before processing
  - p95: < 100ms
  - Alert: > 1s
```

**Why**: Saturation predicts future outages. Allows preventive action.

---

### 1.2 Application Layer Metrics

#### API Metrics (Railway)

```yaml
Category: Request Metrics
  http_requests_total:
    type: counter
    labels:
      - method: GET, POST, PUT, DELETE
      - endpoint: /api/*, /chat/*, /search/*
      - status_code: 200, 400, 401, 404, 500, 502, 503
    example: "http_requests_total{method='POST',endpoint='/chat',status_code='200'} 15234"

  http_request_duration_seconds:
    type: histogram
    labels:
      - method: GET, POST, PUT, DELETE
      - endpoint: /api/*, /chat/*, /search/*
    buckets: [0.01, 0.05, 0.1, 0.2, 0.5, 1.0, 2.0, 5.0]
    example: "http_request_duration_seconds_bucket{method='POST',endpoint='/chat',le='0.5'} 12000"

  http_request_size_bytes:
    type: histogram
    labels:
      - endpoint: /api/*, /chat/*, /search/*
    description: "Track request body size to identify large payloads"

  http_response_size_bytes:
    type: histogram
    labels:
      - endpoint: /api/*, /chat/*, /search/*
    description: "Track response size (important for bandwidth tracking)"

Category: Business Logic
  chat_messages_total:
    type: counter
    labels:
      - user_id: anonymized
      - model: claude-3.5-sonnet, haiku, opus, gpt-4, etc
      - status: success, error
    example: "chat_messages_total{user_id='hash_xyz',model='claude-3.5-sonnet',status='success'} 523"

  search_queries_total:
    type: counter
    labels:
      - search_type: semantic, keyword, hybrid
      - status: success, error

  embedding_requests_total:
    type: counter
    labels:
      - model: text-embedding-3-small, text-embedding-3-large
      - provider: openai, anthropic, cohere
      - status: success, error

Category: Cost Tracking
  llm_tokens_total:
    type: counter
    labels:
      - model: claude-3.5-sonnet, haiku, gpt-4
      - token_type: input, output
      - operation: chat, search, summary
    description: "Input and output tokens for cost calculation"
    example: "llm_tokens_total{model='claude-3.5-sonnet',token_type='input'} 1234567"

  embedding_tokens_total:
    type: counter
    labels:
      - model: text-embedding-3-small
      - status: success, error

  api_cost_usd_total:
    type: gauge
    labels:
      - operation: chat_message, search, embedding
      - time_period: hourly, daily, monthly
    description: "Track actual cost in USD"

Category: Cache Performance
  cache_hits_total:
    type: counter
    labels:
      - cache_type: redis, memory
      - key_type: embedding, search_result, session

  cache_misses_total:
    type: counter
    labels:
      - cache_type: redis, memory
      - key_type: embedding, search_result, session

  cache_hit_rate:
    type: gauge
    labels:
      - cache_type: redis, memory
    description: "hits / (hits + misses)"
    target: "> 70%"

Category: Database Operations
  database_query_duration_seconds:
    type: histogram
    labels:
      - operation: select, insert, update, delete
      - table: messages, sessions, embeddings, documents
    buckets: [0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0]

  database_errors_total:
    type: counter
    labels:
      - error_type: timeout, connection_error, constraint_violation
      - operation: select, insert, update, delete

  database_connections_active:
    type: gauge
    description: "Current active connections to database"
    alert_threshold: "> 40 for Beta, > 400 for Prod"

  database_connection_pool_available:
    type: gauge
    description: "Available connections in pool"
    alert: "< 10%" (pool nearly full)

Category: Authentication & Security
  auth_attempts_total:
    type: counter
    labels:
      - method: password, oauth, api_key
      - status: success, failure
      - failure_reason: invalid_password, invalid_oauth, not_found

  auth_failure_rate:
    type: gauge
    description: "(failures / total attempts) * 100"
    target: "< 1%"

  api_key_validation_failures:
    type: counter
    description: "Invalid/expired API key usage attempts"
    alert: "> 10 in 5 minutes (possible attack)"

Category: Queue & Async Jobs
  async_jobs_queued:
    type: gauge
    labels:
      - job_type: email, background_process, report_generation
    alert: "> 1000 jobs pending"

  async_job_duration_seconds:
    type: histogram
    labels:
      - job_type: email, background_process, report_generation
    target: "p95 < 30 seconds"

  async_job_failures_total:
    type: counter
    labels:
      - job_type: email, background_process, report_generation
      - error_type: timeout, dependency_error, logic_error

  async_job_retry_count:
    type: counter
    labels:
      - job_type: email, background_process, report_generation
    description: "Track how many times jobs are retried"
```

#### Web App Metrics (Vercel/Next.js)

```yaml
Category: Page Performance (Web Vitals)
  web_page_load_time_seconds:
    type: histogram
    labels:
      - page_name: home, chat, search, docs
      - device_type: mobile, desktop, tablet
    buckets: [0.1, 0.5, 1.0, 2.0, 5.0, 10.0]

  first_contentful_paint_seconds:
    type: gauge
    labels:
      - page_name: home, chat, search, docs
      - device_type: mobile, desktop
    target: "< 1 second"

  largest_contentful_paint_seconds:
    type: gauge
    labels:
      - page_name: home, chat, search, docs
      - device_type: mobile, desktop
    target: "< 2.5 seconds"

  cumulative_layout_shift:
    type: gauge
    labels:
      - page_name: home, chat, search, docs
    target: "< 0.1"

  time_to_first_byte_seconds:
    type: gauge
    labels:
      - page_name: home, chat, search, docs
      - device_type: mobile, desktop
    target: "< 100ms"

Category: User Interactions
  page_view_total:
    type: counter
    labels:
      - page_name: home, chat, search, docs
      - referrer: direct, google, twitter, etc

  click_event_total:
    type: counter
    labels:
      - button_name: send_message, search_docs, new_chat
      - outcome: success, error

  form_submission_total:
    type: counter
    labels:
      - form_name: login, signup, feedback
      - status: success, validation_error, submission_error

  session_duration_seconds:
    type: histogram
    labels:
      - user_type: anonymous, authenticated
    buckets: [10, 30, 60, 300, 600, 1800, 3600]

  session_bounce_rate:
    type: gauge
    description: "% of sessions that leave without taking action"
    target: "< 50%"

Category: API Client Errors
  api_call_errors_client_total:
    type: counter
    labels:
      - endpoint: /api/chat, /api/search
      - error_type: timeout, network_error, invalid_response
      - status_code: 400, 401, 403, 404, 408, 429

Category: JavaScript Errors
  javascript_error_total:
    type: counter
    labels:
      - error_type: ReferenceError, TypeError, SyntaxError
      - page_name: home, chat, search
      - severity: error, warning

Category: Build & Deployment
  build_time_seconds:
    type: gauge
    description: "Vercel build duration"
    target: "< 60 seconds"

  build_success_rate:
    type: gauge
    description: "(successful_builds / total_builds) * 100"
    target: "> 95%"
```

#### Database Metrics (Supabase PostgreSQL)

```yaml
Category: Connection Pool
  db_connections_active:
    type: gauge
    labels:
      - database: relay-beta-db, relay-prod-db
      - user: app_user, api_user
    target: "< 80% of pool max"

  db_connections_idle:
    type: gauge
    labels:
      - database: relay-beta-db, relay-prod-db

  db_connections_total:
    type: gauge
    labels:
      - database: relay-beta-db, relay-prod-db
    description: "Max allowed connections"

  db_connection_wait_time_seconds:
    type: histogram
    description: "Time waiting for available connection"
    target: "p95 < 100ms"

Category: Query Performance
  db_query_duration_seconds:
    type: histogram
    labels:
      - operation: SELECT, INSERT, UPDATE, DELETE
      - table: messages, sessions, embeddings, documents
    buckets: [0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0, 5.0]

  db_slow_queries_total:
    type: counter
    labels:
      - table: messages, sessions, embeddings, documents
    description: "Queries taking > 1 second"

  db_query_errors_total:
    type: counter
    labels:
      - error_type: constraint_violation, syntax_error, permission_denied
      - operation: SELECT, INSERT, UPDATE, DELETE

Category: Table Metrics
  db_table_row_count:
    type: gauge
    labels:
      - table: messages, sessions, embeddings, documents
    description: "Number of rows in each table"

  db_table_size_bytes:
    type: gauge
    labels:
      - table: messages, sessions, embeddings, documents
    description: "Size of table in bytes"

  db_index_usage_total:
    type: counter
    labels:
      - index_name: messages_user_id_idx, sessions_active_idx

Category: Replication (if applicable)
  db_replication_lag_seconds:
    type: gauge
    description: "Replica lag behind primary"
    alert: "> 5 seconds"

  db_replication_errors_total:
    type: counter
    description: "Replication failures"

Category: Backup & Maintenance
  db_backup_duration_seconds:
    type: gauge
    description: "Time for backup operation"

  db_backup_size_bytes:
    type: gauge
    labels:
      - backup_type: incremental, full
    description: "Size of backup"

  db_vacuum_duration_seconds:
    type: gauge
    description: "Time for VACUUM maintenance"

  db_autovacuum_runs_total:
    type: counter
    description: "Number of AUTOVACUUM operations"
```

#### Deployment/GitHub Actions Metrics

```yaml
Category: Build Pipeline
  github_workflow_duration_seconds:
    type: histogram
    labels:
      - workflow: deploy-beta, deploy-prod, ci
      - job: migrate-db, deploy-api, deploy-web, smoke-tests
    buckets: [10, 30, 60, 300, 600, 1200]

  github_workflow_status:
    type: counter
    labels:
      - workflow: deploy-beta, deploy-prod, ci
      - status: success, failure, cancelled
      - trigger: push, workflow_dispatch, schedule

  github_build_success_rate:
    type: gauge
    labels:
      - workflow: deploy-beta, deploy-prod, ci
    description: "(successful / total) * 100"
    target: "> 95%"

Category: Deployment
  deployment_duration_seconds:
    type: gauge
    labels:
      - environment: beta, prod
      - component: api, web, database
    description: "Time from workflow trigger to live"

  deployment_frequency:
    type: gauge
    labels:
      - environment: beta, prod
    description: "Deployments per day"

  deployment_rollback_count_total:
    type: counter
    labels:
      - environment: beta, prod
      - reason: high_error_rate, performance_degradation

Category: Infrastructure Validation
  migration_execution_time_seconds:
    type: gauge
    description: "Time to run database migrations"

  migration_success_rate:
    type: gauge
    description: "% of migrations that succeed"
    target: "100%"

  deployment_smoke_test_status:
    type: counter
    labels:
      - test_name: api_health_check, web_page_load, db_connectivity
      - status: pass, fail

  railway_deployment_status:
    type: gauge
    labels:
      - service: relay-beta-api, relay-prod-api
      - status: healthy, degraded, unhealthy

  vercel_deployment_status:
    type: gauge
    labels:
      - project: relay-studio-one
      - status: ready, building, error
```

---

### 1.3 Infrastructure Metrics

#### Railway (API Server)

```yaml
Category: CPU & Memory
  process_cpu_seconds_total:
    type: counter
    description: "Total CPU time used by Python process"

  process_resident_memory_bytes:
    type: gauge
    description: "RSS memory usage"
    alert: "> 512MB for Python API"

  process_virtual_memory_bytes:
    type: gauge
    description: "Virtual memory usage"

  railway_cpu_utilization_percent:
    type: gauge
    target: "< 70% (alert), < 90% (critical)"

  railway_memory_utilization_percent:
    type: gauge
    target: "< 75% (alert), < 90% (critical)"

Category: Network
  network_bytes_recv_total:
    type: counter
    description: "Bytes received from network"

  network_bytes_sent_total:
    type: counter
    description: "Bytes sent to network"

  network_tcp_connections:
    type: gauge
    labels:
      - state: ESTABLISHED, TIME_WAIT, CLOSE_WAIT

Category: Disk I/O
  disk_read_bytes_total:
    type: counter
    description: "Total bytes read from disk"

  disk_write_bytes_total:
    type: counter
    description: "Total bytes written to disk"

  disk_io_time_seconds_total:
    type: counter
    description: "Total time spent on I/O operations"

Category: Container Health
  railway_container_restarts_total:
    type: counter
    description: "Number of container restarts"
    alert: "> 3 in 1 hour"

  railway_container_status:
    type: gauge
    labels:
      - status: running, restarting, exited
```

#### Vercel (Web App)

```yaml
Category: Build Performance
  vercel_build_duration_seconds:
    type: gauge
    target: "< 60 seconds"

  vercel_function_cold_start_duration_ms:
    type: histogram
    description: "Time for serverless function to initialize"
    target: "< 1000ms"

  vercel_function_execution_duration_ms:
    type: histogram
    labels:
      - function_name: api_handler, pages/*
    buckets: [10, 50, 100, 500, 1000, 5000]

Category: CDN & Caching
  vercel_cache_hit_rate:
    type: gauge
    description: "% of requests served from cache"
    target: "> 80%"

  vercel_edge_function_latency_ms:
    type: histogram
    description: "Latency of edge functions"
    target: "p95 < 100ms"

Category: Usage & Quota
  vercel_function_execution_count:
    type: counter
    description: "Number of function invocations"

  vercel_bandwidth_bytes_total:
    type: counter
    description: "Total bandwidth used"
```

---

### 1.4 Business & User Metrics

```yaml
Category: User Activity
  active_users_total:
    type: gauge
    description: "Number of unique active users (last 24h)"

  active_sessions_total:
    type: gauge
    description: "Number of active user sessions"

  new_user_signups_total:
    type: counter
    labels:
      - signup_source: organic, referral, paid_ad
    description: "New user registrations per day"

  user_retention_rate:
    type: gauge
    labels:
      - period_days: 1, 7, 30
    description: "% of users returning after N days"

Category: Feature Usage
  feature_usage_total:
    type: counter
    labels:
      - feature: chat_message, search, document_upload
      - user_tier: free, pro, enterprise
    description: "Feature usage counts"

  feature_adoption_rate:
    type: gauge
    labels:
      - feature: chat_message, search, document_upload
    description: "% of active users using feature"

Category: Revenue & Cost
  user_cost_usd_total:
    type: counter
    labels:
      - user_id_hash: anonymized
      - cost_type: api_calls, storage, compute
    description: "Total cost per user"

  daily_cost_usd:
    type: gauge
    description: "Total platform cost in USD per day"

  cost_per_user_per_month:
    type: gauge
    description: "Average monthly cost per active user"

  token_usage_cost_usd:
    type: gauge
    labels:
      - operation: chat, search, embedding
      - model: claude-3.5-sonnet, gpt-4
    description: "Cost breakdown by operation and model"

Category: Quality Metrics
  user_rating_average:
    type: gauge
    description: "Average user satisfaction rating (1-5 stars)"

  response_relevance_score:
    type: gauge
    description: "Average relevance score of AI responses (0-100)"

  citation_accuracy_rate:
    type: gauge
    description: "% of citations that are accurate and relevant"

  user_error_reporting_rate:
    type: counter
    labels:
      - error_type: wrong_answer, hallucination, formatting_issue
    description: "User-reported errors per day"
```

---

## Part 2: SLI/SLO/SLA Definition

### 2.1 SLI Definitions (What to Measure)

#### Availability SLI
```
Definition: % of API requests that return 2xx status code

Calculation:
  (total_2xx_responses / total_requests) * 100

Measurement Points:
  - Every HTTP request to /api/* endpoints
  - Exclude internal health checks (/_stcore/health)
  - Include 3xx redirects as success
  - Include 4xx as failures (client error is failure)

Labels:
  - endpoint: /api/chat, /api/search, /api/auth
  - status_code: 2xx, 3xx, 4xx, 5xx
  - environment: beta, prod
```

#### Latency SLI
```
Definition: % of API requests completed within SLA latency

Calculation:
  Beta: (requests < 200ms) / total_requests
  Prod: (requests < 150ms) / total_requests

Measurement Points:
  - Measure from request receipt to response sent
  - Exclude network latency (start at handler entry)
  - Percentiles tracked: p50, p95, p99

Labels:
  - endpoint: /api/chat, /api/search, /api/auth
  - method: GET, POST
  - environment: beta, prod
```

#### Database Reliability SLI
```
Definition: % of database queries that succeed

Calculation:
  (successful_queries / total_queries) * 100

Measurement Points:
  - Track SELECT, INSERT, UPDATE, DELETE operations
  - Exclude connection pool timeouts (those trigger latency SLI)
  - Count connection failures as errors

Labels:
  - operation: SELECT, INSERT, UPDATE, DELETE
  - table: messages, sessions, embeddings
```

#### Deployment Success SLI
```
Definition: % of deployments that complete successfully

Calculation:
  (successful_deployments / total_deployments) * 100

Success Criteria:
  - All workflow steps pass
  - Smoke tests pass post-deployment
  - Health check returns 200 OK
  - No critical errors in first 5 minutes

Labels:
  - environment: beta, prod
  - component: api, web, database
```

---

### 2.2 SLO Targets (What We Commit To)

#### Primary SLOs

| SLI | Target | Error Budget | Notes |
|-----|--------|--------------|-------|
| **Availability** | 99.9% (Beta: 99.5%) | 43 min/month | Excludes planned maintenance |
| **Latency (p95)** | < 200ms (Beta: 300ms) | 8 hours/month over budget | Measured end-to-end |
| **Database Reliability** | 99.95% | 22 min/month | Excludes backups |
| **Deployment Success** | > 95% | 1 failed deployment/week | Automatic rollback counts as failure |

#### Secondary SLOs (Informational)

| SLI | Target | Note |
|-----|--------|------|
| **P99 Latency** | < 500ms | Use for capacity planning |
| **API Error Rate** | < 0.5% | Includes 4xx and 5xx |
| **Web Page Load (LCP)** | < 2.5s | Core Web Vitals metric |
| **Cache Hit Rate** | > 70% | Optimization metric |
| **Build Success Rate** | > 98% | CI/CD health metric |

---

### 2.3 Error Budget Allocation

Monthly error budget for **Availability SLO (99.9%)**:

```
Total monthly budget: 0.1% = ~43 minutes

Allocation by cause:
  Planned Maintenance: 20 minutes (0.046%)
    - Database maintenance windows
    - Infrastructure updates

  Incident Buffer: 23 minutes (0.053%)
    - Unplanned outages
    - Emergency fixes
    - Third-party failures

When budget depleted:
  - STOP risky deployments
  - HOLD feature releases
  - FOCUS on stability
  - Resume risky work next month
```

#### Tracking Error Budget

```
Week 1: 0 min used -> 43 min remaining
Week 2: 5 min used -> 38 min remaining  (1 incident)
Week 3: 0 min used -> 38 min remaining
Week 4: 10 min used -> 28 min remaining (deployment issue)

Action: With 28 min remaining, proceed carefully with
        feature development but avoid risky deploys
```

---

### 2.4 SLA Definition (Customer Commitments)

#### Service Level Agreement

```
Relay AI SLA - Effective 2025-11-15

1. AVAILABILITY COMMITMENT
   - Service: 99.5% uptime (planned maintenance excluded)
   - Measurement: API availability for authenticated requests
   - Window: Calendar month
   - Credit: 10% of monthly fee if < 99.5%

2. RESPONSE TIME COMMITMENT
   - p95 Latency: < 300ms (95% of requests)
   - Measurement: API response time
   - Exclusion: > 5s single requests don't count
   - Credit: 5% of monthly fee if average p95 > 500ms

3. SUPPORT RESPONSE
   - Critical: 1 hour response time
   - High: 4 hour response time
   - Medium: 24 hour response time

4. PLANNED MAINTENANCE
   - Window: Monthly (2nd Sunday, 2-3 AM EST)
   - Notice: 7 days advance
   - Duration: Max 1 hour
   - Frequency: Max 1/month

5. CREDITS
   - Service Credit: Applied to next invoice
   - Multiple events: Credits are cumulative
   - Maximum: 30% of monthly fee in one month
```

---

## Part 3: Alerting Strategy

### 3.1 Alert Severity Levels

#### CRITICAL (Page On-Call Immediately)

```yaml
Condition: User-facing service is severely degraded

Threshold:
  - API unavailable (0% success rate for 1 minute)
  - Error rate > 50% for 2 minutes
  - Database completely unavailable
  - All smoke tests failing

Response:
  - Immediate PagerDuty alert
  - SMS + call to on-call engineer
  - Auto-create incident ticket
  - 15-minute escalation if not acknowledged
```

**Examples**:
- Error Rate: `error_rate > 50% for 2m` (CRITICAL)
- Availability: `available_requests < 100/min` (if baseline is 1000/min)
- Database: `db_connections_active == 0`
- Deployment: `All smoke tests failed`

---

#### HIGH (Page On-Call Within 5 Minutes)

```yaml
Condition: Service degradation that will impact users soon

Threshold:
  - Error rate 5-50% for 5 minutes
  - Latency p95 > 2 seconds for 10 minutes
  - Memory utilization > 85% for 5 minutes
  - Database query timeout rate > 5%

Response:
  - PagerDuty High alert
  - Notification in Slack #alerts channel
  - Auto-create incident ticket
  - 5-minute escalation if not acknowledged
```

**Examples**:
- Error Rate: `error_rate > 5% for 5m AND error_rate < 50%`
- Latency: `http_request_duration_seconds{quantile="0.95"} > 2.0 for 10m`
- Resource: `process_resident_memory_bytes / max_memory > 0.85 for 5m`
- Database: `db_query_timeout_total > 5 per minute`

---

#### MEDIUM (Create Ticket, Notify Ops)

```yaml
Condition: Service degradation that should be investigated

Threshold:
  - Error rate 1-5% for 15 minutes
  - Latency p95 > 500ms for 20 minutes
  - Memory utilization > 70% for 10 minutes
  - Disk usage > 80%
  - CPU > 75% for 10 minutes

Response:
  - Slack #ops-alerts notification
  - Auto-create ticket in Jira/GitHub Issues
  - No phone page
  - 4-hour SLA for investigation
```

**Examples**:
- Error Rate: `1 < error_rate < 5 for 15m`
- Latency: `http_request_duration_seconds{quantile="0.95"} > 0.5 for 20m`
- Resource: `process_resident_memory_bytes / max_memory > 0.70 for 10m`

---

#### LOW (Log for Review)

```yaml
Condition: Anomalies that may indicate future issues

Threshold:
  - Error rate 0.1-1% for 30 minutes
  - Latency p99 > 2 seconds
  - Non-critical system issues
  - Slow build times > 120 seconds

Response:
  - Log to observability system
  - No immediate notification
  - Reviewed in weekly ops meeting
```

---

### 3.2 Alert Rules Configuration

#### Prometheus Alert Rules

```yaml
# File: config/prometheus/alerts-relay.yml

groups:
  - name: api_availability
    interval: 15s
    rules:
      - alert: APIDown
        expr: |
          (
            count(rate(http_requests_total{environment="beta",status_code=~"2.."}[5m]) > 0)
            /
            count(rate(http_requests_total{environment="beta"}[5m]) > 0)
          ) < 0.5
        for: 1m
        severity: critical
        labels:
          team: platform
          runbook: api-down
        annotations:
          summary: "API is down (< 50% requests succeeding)"
          description: "API error rate critical: {{ $value | humanizePercentage }}"
          dashboard: "https://grafana.internal/d/api-health"

      - alert: HighErrorRate
        expr: |
          (
            sum(rate(http_requests_total{environment="beta",status_code=~"5.."}[5m]))
            /
            sum(rate(http_requests_total{environment="beta"}[5m]))
          ) > 0.05
        for: 5m
        severity: high
        labels:
          team: platform
          runbook: high-error-rate
        annotations:
          summary: "High error rate detected"
          description: "Error rate: {{ $value | humanizePercentage }}"
          dashboard: "https://grafana.internal/d/api-health"

  - name: latency_alerts
    interval: 15s
    rules:
      - alert: HighLatencyP95
        expr: |
          histogram_quantile(0.95,
            sum(rate(http_request_duration_seconds_bucket{environment="beta"}[5m])) by (le)
          ) > 0.2
        for: 10m
        severity: high
        labels:
          team: platform
          runbook: high-latency
        annotations:
          summary: "High P95 latency"
          description: "P95 latency: {{ $value | humanizeDuration }}"

      - alert: HighLatencyP99
        expr: |
          histogram_quantile(0.99,
            sum(rate(http_request_duration_seconds_bucket{environment="beta"}[5m])) by (le)
          ) > 0.5
        for: 5m
        severity: medium
        labels:
          team: platform
        annotations:
          summary: "High P99 latency"
          description: "P99 latency: {{ $value | humanizeDuration }}"

  - name: resource_alerts
    interval: 15s
    rules:
      - alert: HighMemoryUsage
        expr: |
          (process_resident_memory_bytes / 536870912) * 100 > 85
        for: 5m
        severity: high
        labels:
          team: platform
        annotations:
          summary: "High memory usage detected"
          description: "Memory: {{ $value | humanizePercentage }}"

      - alert: HighCPUUsage
        expr: |
          rate(process_cpu_seconds_total[5m]) > 0.7
        for: 10m
        severity: medium
        labels:
          team: platform
        annotations:
          summary: "High CPU usage"
          description: "CPU: {{ $value | humanizePercentage }}"

  - name: database_alerts
    interval: 15s
    rules:
      - alert: DatabaseConnectionPoolFull
        expr: |
          (
            database_connections_active
            /
            database_connections_total
          ) > 0.8
        for: 5m
        severity: high
        labels:
          team: data
          runbook: db-connection-pool
        annotations:
          summary: "Database connection pool > 80%"
          description: "Active connections: {{ $value }}"

      - alert: DatabaseConnectionDown
        expr: |
          database_connections_active == 0
        for: 1m
        severity: critical
        labels:
          team: data
          runbook: db-down
        annotations:
          summary: "Database connections at 0"
          description: "Cannot connect to database"

      - alert: SlowQueries
        expr: |
          rate(database_slow_queries_total[5m]) > 1
        for: 5m
        severity: medium
        labels:
          team: data
        annotations:
          summary: "Slow queries detected"
          description: "{{ $value }} slow queries per second"

  - name: deployment_alerts
    interval: 15s
    rules:
      - alert: DeploymentFailure
        expr: |
          (
            sum(rate(github_workflow_status{status="failure"}[1h]))
            /
            sum(rate(github_workflow_status[1h]))
          ) > 0.05
        for: 0m
        severity: high
        labels:
          team: devops
          runbook: deploy-failure
        annotations:
          summary: "Deployment success rate < 95%"
          description: "Recent failure rate: {{ $value | humanizePercentage }}"

      - alert: SmokeTestFailure
        expr: |
          deployment_smoke_test_status{status="fail"} > 0
        for: 0m
        severity: critical
        labels:
          team: devops
          runbook: smoke-test-failure
        annotations:
          summary: "Post-deployment smoke tests failed"
          description: "Deployment may be broken"

  - name: cost_alerts
    interval: 15s
    rules:
      - alert: DailyCostSpike
        expr: |
          (
            api_cost_usd_total - api_cost_usd_total offset 24h
          ) > 500
        for: 5m
        severity: medium
        labels:
          team: finance
        annotations:
          summary: "Daily cost spike detected"
          description: "Daily cost increase: ${{ $value }}"

      - alert: TokenBudgetExceeded
        expr: |
          llm_tokens_total > 10000000
        for: 1m
        severity: medium
        labels:
          team: product
        annotations:
          summary: "Token budget approaching limit"
          description: "Total tokens: {{ $value }}"
```

---

### 3.3 Alert Deduplication & Grouping

```yaml
# AlertManager configuration for alert grouping

global:
  resolve_timeout: 5m

route:
  receiver: default
  group_by: ['alertname', 'environment', 'team']
  group_wait: 10s
  group_interval: 10s
  repeat_interval: 12h

  routes:
    - match:
        severity: critical
      receiver: critical
      group_wait: 0s
      repeat_interval: 5m

    - match:
        severity: high
      receiver: ops-team
      group_wait: 5s
      repeat_interval: 1h

    - match:
        severity: medium
      receiver: dev-team
      group_wait: 1m
      repeat_interval: 4h

    - match:
        severity: low
      receiver: log-only
      repeat_interval: 24h

receivers:
  - name: critical
    pagerduty_configs:
      - service_key: "{{ secret.PAGERDUTY_SERVICE_KEY }}"
        severity: critical
    slack_configs:
      - channel: '#critical-alerts'
        title: 'CRITICAL: {{ .GroupLabels.alertname }}'
    opsgenie_configs:
      - api_key: "{{ secret.OPSGENIE_KEY }}"

  - name: ops-team
    slack_configs:
      - channel: '#ops-alerts'
        title: 'HIGH: {{ .GroupLabels.alertname }}'

  - name: dev-team
    slack_configs:
      - channel: '#dev-alerts'
        title: 'MEDIUM: {{ .GroupLabels.alertname }}'

  - name: log-only
    # No active receiver - just logged

# Alert suppression during known events
inhibit_rules:
  - source_match:
      alertname: 'Deployment'
    target_match_re:
      alertname: 'HighErrorRate|HighLatency'
    equal: ['environment']
    duration: 5m
    comment: 'Suppress errors during deployment window'

  - source_match:
      alertname: 'DatabaseMaintenance'
    target_match_re:
      alertname: 'DatabaseConnectionDown'
    duration: 2h
    comment: 'Suppress DB alerts during maintenance'
```

---

## Part 4: Dashboard Specifications

### 4.1 System Health Dashboard

**Purpose**: Real-time overview of all system components for on-call engineers

**URL**: `https://grafana.internal/d/system-health`

**Refresh**: 10 seconds (real-time)

**Panels**:

```
Row 1: Status Indicators (4 big numbers)
┌─────────────────┬──────────────┬──────────────┬──────────────┐
│ API Status      │ Error Rate   │ P95 Latency  │ Uptime %     │
│ GREEN/RED       │ 0.2%         │ 180ms        │ 99.94%       │
│ (up for 30d)    │ (< 5%)       │ (target 200) │ (SLO: 99.5%) │
└─────────────────┴──────────────┴──────────────┴──────────────┘

Row 2: Request Metrics (Last 1 Hour)
┌─────────────────────────────┬──────────────────────────────┐
│ Request Rate (RPS)          │ Error Rate %                 │
│ Line chart                  │ Line chart (stacked by code) │
│ Current: 45 RPS             │ Current: 0.2%                │
│                             │ 5xx errors: 1 req/min        │
└─────────────────────────────┴──────────────────────────────┘

Row 3: Latency Distribution (Last 1 Hour)
┌──────────────────────────────────────────────────────────┐
│ Latency Percentiles: P50, P95, P99                        │
│ P50: 50ms | P95: 180ms | P99: 420ms                      │
│ Line chart with bands                                    │
└──────────────────────────────────────────────────────────┘

Row 4: Resource Utilization (Last 6 Hours)
┌──────────────────────┬──────────────────────┬─────────────┐
│ Memory Usage         │ CPU Usage            │ Connections │
│ 420MB / 512MB (82%)  │ 65% (alert: 70%)     │ 42 / 100    │
│ Sparkline            │ Sparkline            │ Sparkline   │
└──────────────────────┴──────────────────────┴─────────────┘

Row 5: Database Health
┌──────────────────────┬──────────────────────┬─────────────┐
│ Active Connections   │ Query Duration p95   │ Slow Queries│
│ 12 / 50              │ 35ms                 │ 0 in 1h     │
│ Gauge                │ Gauge                │ Counter     │
└──────────────────────┴──────────────────────┴─────────────┘

Row 6: Recent Incidents (Last 7 Days)
┌──────────────────────────────────────────────────────────┐
│ Active Incidents & Alerts                                │
│ None currently                                           │
│ Table with: Time, Alert, Severity, Duration, Status     │
└──────────────────────────────────────────────────────────┘
```

---

### 4.2 API Performance Dashboard

**Purpose**: Deep dive into API performance for debugging

**URL**: `https://grafana.internal/d/api-performance`

**Refresh**: 30 seconds

**Panels**:

```
Row 1: Request Rate by Endpoint
┌──────────────────────────────────────────────────────────┐
│ Stacked Bar Chart: RPS by endpoint                        │
│ /api/chat: 30 RPS (66%)                                 │
│ /api/search: 10 RPS (22%)                               │
│ /api/auth: 5 RPS (11%)                                  │
└──────────────────────────────────────────────────────────┘

Row 2: Error Rate by Status Code
┌──────────────────────────────────────────────────────────┐
│ Pie Chart: Error distribution                            │
│ 5xx (Server Errors): 0.1% - 1 error/min                 │
│ 4xx (Client Errors): 0.1% - 1 error/min                 │
│ 2xx (Success): 99.8%                                    │
└──────────────────────────────────────────────────────────┘

Row 3: Latency Distribution by Endpoint
┌────────────────────┬────────────────────┬────────────────┐
│ /api/chat Latency  │ /api/search Latency│ /api/auth      │
│ P50: 45ms          │ P50: 60ms          │ P50: 20ms      │
│ P95: 200ms         │ P95: 250ms         │ P95: 50ms      │
│ P99: 450ms         │ P99: 600ms         │ P99: 100ms     │
│ Histogram buckets  │ Histogram buckets  │ Histogram      │
└────────────────────┴────────────────────┴────────────────┘

Row 4: Response Time Percentiles (Last 6 Hours)
┌──────────────────────────────────────────────────────────┐
│ Line Chart: P50, P95, P99 over time                      │
│ P50 (green): ~50ms                                      │
│ P95 (yellow): ~180ms                                    │
│ P99 (red): ~400ms                                       │
└──────────────────────────────────────────────────────────┘

Row 5: Slow Endpoints (> 1s latency)
┌──────────────────────────────────────────────────────────┐
│ Table: Top slow requests                                 │
│ Endpoint | Count | Avg Latency | Max Latency | Error %   │
│ /search  | 3     | 1200ms      | 2500ms      | 0%        │
│ /embed   | 1     | 1050ms      | 1050ms      | 0%        │
└──────────────────────────────────────────────────────────┘

Row 6: API Error Details
┌──────────────────────────────────────────────────────────┐
│ Table: Recent errors                                     │
│ Time | Endpoint | Status | Error Message | User          │
│ Now  | /chat    | 500    | DB timeout    | (anonymized)  │
└──────────────────────────────────────────────────────────┘

Row 7: Dependency Health
┌────────────────────┬────────────────────┬────────────────┐
│ Database Status    │ Cache Status       │ LLM API Status │
│ UP (1.2ms p95)     │ UP (0.8ms p95)     │ UP (450ms p95) │
│ 99.99% success     │ 98% hit rate       │ 99% success    │
└────────────────────┴────────────────────┴────────────────┘
```

---

### 4.3 User Activity Dashboard

**Purpose**: Track real user behavior and engagement

**URL**: `https://grafana.internal/d/user-activity`

**Refresh**: 1 minute

**Panels**:

```
Row 1: Real-Time Activity
┌──────────────────┬──────────────────┬──────────────────┐
│ Active Users     │ Active Sessions  │ New Signups Today│
│ 234 users        │ 412 sessions     │ 18 new users     │
│ (↑ 12% vs week)  │ (↓ 5% vs week)   │ (↑ 8% vs week)   │
└──────────────────┴──────────────────┴──────────────────┘

Row 2: Page Views (Last 24 Hours)
┌──────────────────────────────────────────────────────────┐
│ Stacked Area Chart: Page views over time                 │
│ /chat: 2,400 views (60%)                                │
│ /docs: 800 views (20%)                                  │
│ /search: 600 views (15%)                                │
│ /settings: 200 views (5%)                               │
└──────────────────────────────────────────────────────────┘

Row 3: Feature Usage
┌────────────────────┬────────────────────┬────────────────┐
│ Chat Messages      │ Search Queries     │ Document Uploads
│ 1,234 messages     │ 456 searches       │ 89 uploads     │
│ (avg 5.3 per user) │ (avg 1.9 per user) │ (avg 0.4)      │
└────────────────────┴────────────────────┴────────────────┘

Row 4: User Retention
┌──────────────────────────────────────────────────────────┐
│ Retention Rate by Days Since Signup                      │
│ Day 1:   95% | Day 7: 65% | Day 30: 42%                 │
│ Line chart showing cohort retention curves               │
└──────────────────────────────────────────────────────────┘

Row 5: Session Duration Distribution
┌──────────────────────────────────────────────────────────┐
│ Histogram: Session length in seconds                     │
│ < 1 min:    20% | 1-5 min: 45% | 5-30 min: 30% | > 30m: 5%
└──────────────────────────────────────────────────────────┘

Row 6: User Satisfaction
┌────────────────────┬────────────────────┬────────────────┐
│ Average Rating     │ Response Quality   │ Error Reports  │
│ 4.2 / 5.0 stars    │ 87% relevant       │ 2.1% of sessions
└────────────────────┴────────────────────┴────────────────┘
```

---

### 4.4 Cost & Revenue Dashboard

**Purpose**: Track financial metrics and optimize spending

**URL**: `https://grafana.internal/d/cost-metrics`

**Refresh**: 5 minutes

**Panels**:

```
Row 1: Daily Cost
┌──────────────────────────────────────────────────────────┐
│ Daily Cost (USD): $234.56 today                          │
│ 30-day trend: $5,234 (↑ 12% from previous month)        │
│ Cost projection: $7,200/month ($↑ 15%)                  │
└──────────────────────────────────────────────────────────┘

Row 2: Cost Breakdown by Component
┌──────────────────────────────────────────────────────────┐
│ Pie Chart: Cost distribution                             │
│ API Calls (Claude 3.5): 65% ($3,450)                    │
│ Search/Embeddings:     20% ($1,060)                     │
│ Database (Supabase):    10% ($530)                       │
│ Vercel (Web):           5% ($270)                        │
└──────────────────────────────────────────────────────────┘

Row 3: Cost by Operation
┌────────────────────┬────────────────────┬────────────────┐
│ Chat Messages      │ Search Queries     │ Document Index │
│ $4,200 (70%)       │ $1,300 (22%)       │ $300 (5%)      │
│ 1.2M tokens/month  │ 400K tokens/month  │ 100K tokens    │
└────────────────────┴────────────────────┴────────────────┘

Row 4: Cost per User (Monthly)
┌──────────────────────────────────────────────────────────┐
│ Line Chart: Average cost per active user over time       │
│ Current: $2.40/user (target: $2.50)                     │
│ Trend: Stable (↓ 2% from last month)                    │
└──────────────────────────────────────────────────────────┘

Row 5: Token Usage by Model
┌────────────────────┬────────────────────┬────────────────┐
│ Claude 3.5 Sonnet  │ GPT-4o             │ Haiku          │
│ 4.2M tokens/month  │ 1.5M tokens/month  │ 2.1M tokens    │
│ $1,680             │ $480               │ $42            │
└────────────────────┴────────────────────┴────────────────┘

Row 6: Cost Anomalies
┌──────────────────────────────────────────────────────────┐
│ Table: Days with unusual cost patterns                   │
│ Date | Cost | vs Avg | % Increase | Reason              │
│ 2025 | $320 | $234   | +36%       | Feature launch      │
│ -11-12                                                   │
└──────────────────────────────────────────────────────────┘

Row 7: Budget vs Actual
┌──────────────────────────────────────────────────────────┐
│ Gauge + Text: November spending                          │
│ Budget: $6,000 | Actual: $5,234 | Remaining: $766      │
│ Utilization: 87% (on track)                             │
└──────────────────────────────────────────────────────────┘
```

---

### 4.5 Deployment Health Dashboard

**Purpose**: Track CI/CD pipeline health and deployment success

**URL**: `https://grafana.internal/d/deployment-health`

**Refresh**: 1 minute

**Panels**:

```
Row 1: Deployment Status (Last 7 Days)
┌──────────────────────────────────────────────────────────┐
│ Overall Success Rate: 94% (28/30 deployments)           │
│ Beta deployments:   96% (24/25)  ✓                      │
│ Prod deployments:   80% (4/5)    ✗ (1 rollback)        │
│ Web deployments:    92% (11/12)  ✓                      │
└──────────────────────────────────────────────────────────┘

Row 2: Deployment Timeline (Last 7 Days)
┌──────────────────────────────────────────────────────────┐
│ Timeline view: Each deployment as a bar                  │
│ Color: Green (success), Red (failure), Orange (rollback) │
│ Time range: Nov 8-15, 2025                              │
└──────────────────────────────────────────────────────────┘

Row 3: Build Metrics
┌────────────────────┬────────────────────┬────────────────┐
│ Avg Build Time     │ Max Build Time     │ Build Failures │
│ 45 seconds         │ 120 seconds        │ 2 (out of 30)  │
│ Target: < 60s      │ Trend: ↑ 5%        │ 6.7% failure   │
└────────────────────┴────────────────────┴────────────────┘

Row 4: Deployment Duration by Stage
┌────────────────────┬────────────────────┬────────────────┐
│ API Deploy (Beta)  │ Web Deploy (Beta)  │ DB Migrations  │
│ Avg: 2m 30s        │ Avg: 1m 45s        │ Avg: 1m 15s    │
│ Min: 1m 20s        │ Min: 1m 10s        │ Min: 50s       │
│ Max: 4m 50s        │ Max: 3m 20s        │ Max: 3m 40s    │
└────────────────────┴────────────────────┴────────────────┘

Row 5: Smoke Test Results
┌──────────────────────────────────────────────────────────┐
│ Post-Deployment Health Checks                            │
│ API Health Check:     ✓ PASS (all 30)                   │
│ Web Page Load:        ✓ PASS (29/30) - 1 timeout        │
│ Database Connectivity: ✓ PASS (all 30)                  │
│ Email Service:        ✓ PASS (all 30)                   │
└──────────────────────────────────────────────────────────┘

Row 6: Recent Deployments (Last 10)
┌──────────────────────────────────────────────────────────┐
│ Table: Last 10 deployments                               │
│ Time | Env | Component | Status | Duration | Error      │
│ Now  | B   | API       | ✓      | 2m 15s   | -          │
│ 45m  | B   | Web       | ✓      | 1m 50s   | -          │
│ 2h   | P   | API       | ✗      | 3m 20s   | Health chk │
└──────────────────────────────────────────────────────────┘

Row 7: Error Budget Tracking
┌──────────────────────────────────────────────────────────┐
│ November Error Budget Status                             │
│ Availability SLO: 99.5% → 43 minutes budget             │
│ Used: 10 minutes | Remaining: 33 minutes                │
│ Status: HEALTHY (76% remaining)                         │
│ Progress bar with color coding                          │
└──────────────────────────────────────────────────────────┘
```

---

## Part 5: Implementation Roadmap

### Phase 1: Foundation (Week 1-2)

#### 1.1 Metrics Instrumentation

**Task**: Add metrics collection to API, Web, and Database

```bash
# API (Python/FastAPI)
pip install prometheus-client

# Implementation:
from prometheus_client import Counter, Histogram, Gauge

http_requests_total = Counter(
    'http_requests_total',
    'Total HTTP requests',
    ['method', 'endpoint', 'status_code']
)

http_request_duration_seconds = Histogram(
    'http_request_duration_seconds',
    'HTTP request latency',
    ['method', 'endpoint'],
    buckets=[0.01, 0.05, 0.1, 0.2, 0.5, 1.0, 2.0, 5.0]
)

# Web (Next.js)
npm install @opentelemetry/api @opentelemetry/sdk-web

# Database (SQLAlchemy)
pip install sqlalchemy-prometheus
```

**Deliverables**:
- [ ] API metrics endpoint (`/metrics`)
- [ ] Web app metrics collection
- [ ] Database query metrics
- [ ] All metrics exposed in Prometheus format

---

#### 1.2 Prometheus Setup

**Task**: Deploy Prometheus for metrics scraping and storage

```yaml
# File: config/prometheus/prometheus.yml

global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  - job_name: 'relay-beta-api'
    static_configs:
      - targets: ['relay-beta-api.railway.app']
    metrics_path: '/metrics'
    scheme: https

  - job_name: 'relay-prod-api'
    static_configs:
      - targets: ['relay-prod-api.railway.app']
    metrics_path: '/metrics'
    scheme: https

  - job_name: 'relay-studio-one'
    static_configs:
      - targets: ['relay-studio-one.vercel.app']
    metrics_path: '/_next/metrics'
    scheme: https
```

**Deliverables**:
- [ ] Prometheus server running (self-hosted or managed service)
- [ ] Metrics being scraped from all components
- [ ] 15-day metrics retention
- [ ] Prometheus UI accessible

---

#### 1.3 Grafana Dashboards

**Task**: Create initial dashboards

```
Dashboards to create:
1. System Health (real-time status overview)
2. API Performance (latency, errors, throughput)
3. User Activity (sessions, feature usage)
4. Deployment Health (build times, success rate)
```

**Deliverables**:
- [ ] 4 dashboards created
- [ ] Dashboards auto-refresh
- [ ] Drill-down capabilities (click to see detail)

---

### Phase 2: Alerting (Week 2-3)

#### 2.1 Alert Rules Configuration

**Task**: Define Prometheus alert rules

```yaml
# File: config/prometheus/alerts.yml
# (See Section 3.2 for full rules)
```

**Deliverables**:
- [ ] 15 alert rules configured
- [ ] Alert rules tested with synthetic data
- [ ] Alert rules version controlled

---

#### 2.2 AlertManager Setup

**Task**: Configure AlertManager for routing and deduplication

**Deliverables**:
- [ ] AlertManager deployed
- [ ] Alert routing rules configured
- [ ] Slack integration working
- [ ] PagerDuty integration working (for critical)

---

#### 2.3 Alert Testing

**Task**: Test alerts with synthetic data

```bash
# Generate synthetic high error rate
for i in {1..100}; do
  curl -i https://relay-beta-api.railway.app/api/nonexistent
done

# Verify alert fires in ~2 minutes
# Verify Slack notification received
# Verify PagerDuty incident created (if critical)
```

**Deliverables**:
- [ ] All alerts tested
- [ ] Alert fatigue assessment (true positive rate > 95%)
- [ ] Alert response time documented

---

### Phase 3: Logging & Tracing (Week 3-4)

#### 3.1 Structured Logging

**Task**: Implement structured JSON logging for all components

```json
// Log format (JSON)
{
  "timestamp": "2025-11-15T10:30:45Z",
  "level": "ERROR",
  "service": "relay-api",
  "environment": "beta",
  "request_id": "req_xyz123",
  "user_id": "hash_abc",
  "endpoint": "/api/chat",
  "status_code": 500,
  "duration_ms": 1234,
  "error_type": "DatabaseTimeout",
  "error_message": "Query exceeded 5s timeout",
  "tags": ["database", "error"],
  "trace_id": "trace_xyz123"
}
```

**Deliverables**:
- [ ] JSON logging configured
- [ ] All services logging in structured format
- [ ] Logs being ingested into centralized service

---

#### 3.2 Distributed Tracing

**Task**: Add OpenTelemetry tracing

```python
# Python/FastAPI setup
from opentelemetry import trace
from opentelemetry.exporter.jaeger import JaegerExporter

tracer = trace.get_tracer(__name__)

@app.post("/api/chat")
async def chat_endpoint(request):
    with tracer.start_as_current_span("chat_request") as span:
        span.set_attribute("user_id", "hash_xyz")
        # ... rest of endpoint
```

**Deliverables**:
- [ ] OpenTelemetry instrumentation added to all services
- [ ] Traces being exported to Jaeger or Tempo
- [ ] Trace UI accessible
- [ ] Trace visualization working

---

### Phase 4: Cost Analytics (Week 4)

#### 4.1 Cost Tracking Events

**Task**: Create cost tracking events for billing

```python
# Every LLM API call logs cost event
def log_cost_event(
    user_id: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    cost_usd: float,
    operation: str = "chat"
):
    event = {
        "timestamp": datetime.utcnow(),
        "user_id": anonymize(user_id),
        "model": model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost_usd": cost_usd,
        "operation": operation,
    }
    # Send to cost analytics backend
```

**Deliverables**:
- [ ] Cost events being logged for all operations
- [ ] Cost data being aggregated by user, operation, model
- [ ] Cost metrics visible in dashboards

---

#### 4.2 Cost Forecasting

**Task**: Implement cost forecasting based on trends

**Deliverables**:
- [ ] Daily cost trends calculated
- [ ] Monthly forecast generated
- [ ] Cost anomalies detected
- [ ] Cost optimization recommendations generated

---

### Phase 5: Runbooks & Documentation (Week 4)

#### 5.1 Runbook Creation

**Task**: Document runbooks for common incidents

**Example Runbook**: High Error Rate

```markdown
# Runbook: High Error Rate Alert

## Alert: error_rate > 5% for 5 minutes

### Severity: HIGH

### Immediate Steps (0-5 min)
1. Acknowledge alert in PagerDuty
2. Open API Performance dashboard
3. Identify which endpoints are failing
4. Check Slack #incidents channel for context

### Diagnosis (5-15 min)
1. Check recent deployments:
   - Was anything deployed in last 30 minutes?
   - If yes, consider rollback
2. Check error logs:
   - `grep "ERROR" /var/log/api.log | tail -50`
3. Check dependencies:
   - Is database up? (`SELECT 1;`)
   - Is cache up? (`redis-cli ping`)
   - Are LLM APIs responding?

### Resolution
- If recent deploy: `railway rollback relay-beta-api`
- If database issue: Scale replicas or restart connections
- If cache issue: Clear cache and restart service
- If LLM API issue: Route to fallback model

### Post-Incident
1. Create GitHub issue with incident summary
2. Add to post-mortem template
3. Schedule incident review meeting
```

**Deliverables**:
- [ ] 10 runbooks created for common alerts
- [ ] Runbooks linked to alerts
- [ ] Runbooks version controlled
- [ ] Runbooks reviewed by team

---

## Part 6: Logging Strategy

### 6.1 Log Levels & Severity

```
DEBUG:   Detailed information for debugging
          - Database query details
          - Function entry/exit
          - Variable values
          - NOT in production

INFO:    General informational messages
          - Request received
          - Processing started
          - Deployment completed

WARN:    Warning conditions that may lead to errors
          - High latency (> 2s)
          - Cache miss rate high
          - Connection pool > 70%

ERROR:   Error conditions that need attention
          - Request failed
          - API returned error
          - Database error
          - Exception thrown

CRITICAL: System-level failures
          - Service down
          - Data loss
          - Security breach
```

---

### 6.2 Log Retention Policy

```
Development:    24 hours (cheap, fast)
Staging/Beta:   7 days
Production:     30 days (with sampling)

Sampling rules:
- INFO/DEBUG: Log 10% in prod (1 in 10 requests)
- WARN: Log 100% in prod
- ERROR/CRITICAL: Log 100% always

Archive:
- Move logs > 30 days old to S3 for compliance
- Keep 1 year for audit trail
```

---

## Part 7: Monitoring Checklist

- [ ] **Metrics**: All 4 golden signals instrumented
- [ ] **Dashboards**: 5 dashboards created and tested
- [ ] **Alerts**: 15 alerts configured with < 5% false positives
- [ ] **SLOs**: SLIs/SLOs/SLAs defined and communicated
- [ ] **Logging**: Structured JSON logging deployed to all services
- [ ] **Tracing**: Distributed tracing with span propagation
- [ ] **Cost Tracking**: Cost events logged and attributed
- [ ] **Runbooks**: 10+ runbooks documented
- [ ] **On-Call**: On-call rotation defined with escalation
- [ ] **Incident Response**: Post-incident review process established
- [ ] **Documentation**: Observability architecture documented
- [ ] **Performance**: < 1% observability overhead verified
- [ ] **Accessibility**: Dashboards accessible to whole team

---

## Part 8: Tools & Technologies

### Recommended Stack

```
Metrics Collection:
  - Prometheus (open source)
  - prometheus-client (Python)
  - @opentelemetry/api (JavaScript)

Metrics Storage:
  - Prometheus (local, 15-day retention)
  - Grafana Cloud (managed, 1+ year)

Alerting:
  - AlertManager (open source)
  - Grafana Alerts (managed)
  - PagerDuty (incident management)
  - Slack (notifications)

Logging:
  - Structured JSON logging
  - ELK Stack (Elasticsearch/Logstash/Kibana)
  - Datadog or New Relic (managed)

Tracing:
  - OpenTelemetry (instrumentation)
  - Jaeger (open source backend)
  - Tempo (managed alternative)

Dashboarding:
  - Grafana (visualization)
  - Datadog Dashboards (managed alternative)

Cost Tracking:
  - Custom events to database
  - Datadog Cost Analytics (managed)
```

---

## Part 9: SLA/Error Budget Examples

### Example 1: November 2025 Error Budget

```
SLO: 99.5% uptime
Error Budget: 0.5% = 43.2 minutes per month

Week 1 (Nov 1-7):
  - 0 incidents
  - Usage: 0 min
  - Remaining: 43.2 min

Week 2 (Nov 8-14):
  - 1 incident: 10 minute database migration outage
  - Usage: 10 min
  - Remaining: 33.2 min

Week 3 (Nov 15-21):
  - 1 incident: 5 minute deploy issue (auto-rollback)
  - Usage: 5 min
  - Remaining: 28.2 min

Week 4 (Nov 22-30):
  - No incidents
  - Usage: 0 min
  - Remaining: 28.2 min

November Final: 28.2 minutes unused (185% of monthly budget used, 15 minutes overage)
Action: Reduce risky changes for December, focus on stability
```

---

## Next Steps

1. **Week 1**: Implement Phase 1 (metrics + Prometheus)
2. **Week 2**: Implement Phase 2 (alerting)
3. **Week 3**: Implement Phase 3 (logging + tracing)
4. **Week 4**: Implement Phase 4 & 5 (cost + docs)
5. **Ongoing**: Monitor, tune thresholds, improve runbooks based on incidents

---

## Contact & Support

**Questions or Need Help?**
- Observability Team: `@observability-team` on Slack
- Incident Hotline: `+1-XXX-INCIDENT` (for critical)
- Documentation: `https://wiki.internal/observability`

---

**Document Version**: 1.0
**Last Updated**: 2025-11-15
**Next Review**: 2025-12-15
