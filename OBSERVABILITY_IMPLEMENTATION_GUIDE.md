# Observability Implementation Guide
## Session 2025-11-11 Changes

**Date**: 2025-11-15
**Status**: Implementation Ready
**Timeline**: 4 weeks

---

## Quick Start (Day 1-2)

### 1. Deploy Prometheus

```bash
# Option A: Docker (Local/Development)
docker run -d \
  --name prometheus \
  -p 9090:9090 \
  -v $(pwd)/observability/PROMETHEUS_CONFIG.yml:/etc/prometheus/prometheus.yml \
  -v $(pwd)/observability/ALERT_RULES.yml:/etc/prometheus/rules/api-alerts.yml \
  prom/prometheus --config.file=/etc/prometheus/prometheus.yml

# Option B: Railway (Production)
# Deploy as service alongside relay-api
railway service create prometheus \
  --image prom/prometheus:latest \
  --env PROMETHEUS_CONFIG_FILE=/etc/prometheus/prometheus.yml
```

### 2. Deploy Grafana

```bash
# Docker (Local)
docker run -d \
  --name grafana \
  -p 3000:3000 \
  -e GF_SECURITY_ADMIN_PASSWORD=admin \
  grafana/grafana

# Access: http://localhost:3000
# Default login: admin / admin
```

### 3. Add Prometheus Data Source to Grafana

```bash
# Via API (recommended for automation)
curl -X POST http://localhost:3000/api/datasources \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Prometheus",
    "type": "prometheus",
    "url": "http://prometheus:9090",
    "access": "proxy",
    "isDefault": true
  }'
```

---

## Phase 1: Metrics Instrumentation (Days 1-5)

### 1.1 API Metrics (Python/FastAPI)

**File**: `relay_ai/api/main.py`

```python
from prometheus_client import Counter, Histogram, Gauge, generate_latest
from prometheus_client.registry import REGISTRY
from fastapi import FastAPI, Request
from fastapi.responses import Response
import time

app = FastAPI()

# Define metrics
http_requests_total = Counter(
    'http_requests_total',
    'Total HTTP requests',
    ['method', 'endpoint', 'status_code', 'environment']
)

http_request_duration_seconds = Histogram(
    'http_request_duration_seconds',
    'HTTP request latency in seconds',
    ['method', 'endpoint', 'environment'],
    buckets=[0.01, 0.05, 0.1, 0.2, 0.5, 1.0, 2.0, 5.0]
)

http_requests_in_flight = Gauge(
    'http_requests_in_flight',
    'Number of requests currently being processed',
    ['method', 'endpoint']
)

# Business metrics
chat_messages_total = Counter(
    'chat_messages_total',
    'Total chat messages processed',
    ['model', 'status', 'user_id_hash']
)

llm_tokens_total = Counter(
    'llm_tokens_total',
    'Total tokens used for LLM calls',
    ['model', 'token_type', 'operation']  # token_type: input, output
)

api_cost_usd_total = Counter(
    'api_cost_usd_total',
    'Total API cost in USD',
    ['operation', 'model']
)

database_query_duration_seconds = Histogram(
    'database_query_duration_seconds',
    'Database query latency',
    ['operation', 'table'],
    buckets=[0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0]
)

# Middleware for request tracking
@app.middleware("http")
async def track_requests(request: Request, call_next):
    method = request.method
    endpoint = request.url.path
    environment = os.getenv('RELAY_STAGE', 'unknown')

    http_requests_in_flight.labels(method=method, endpoint=endpoint).inc()
    start_time = time.time()

    try:
        response = await call_next(request)
        status_code = response.status_code
    except Exception as e:
        status_code = 500
        raise
    finally:
        duration = time.time() - start_time
        http_requests_in_flight.labels(method=method, endpoint=endpoint).dec()
        http_requests_total.labels(
            method=method,
            endpoint=endpoint,
            status_code=status_code,
            environment=environment
        ).inc()
        http_request_duration_seconds.labels(
            method=method,
            endpoint=endpoint,
            environment=environment
        ).observe(duration)

# Metrics endpoint
@app.get("/metrics")
def metrics():
    """Prometheus metrics endpoint"""
    return Response(
        content=generate_latest(REGISTRY),
        media_type="text/plain; version=0.0.4"
    )

# Example: Chat endpoint with metrics
@app.post("/api/chat")
async def chat_endpoint(request: ChatRequest):
    model = request.model  # e.g., "claude-3.5-sonnet"

    try:
        # Call LLM
        response = await llm.create_message(
            model=model,
            messages=request.messages
        )

        # Track tokens
        input_tokens = response.usage.input_tokens
        output_tokens = response.usage.output_tokens

        llm_tokens_total.labels(
            model=model,
            token_type='input',
            operation='chat'
        ).inc(input_tokens)

        llm_tokens_total.labels(
            model=model,
            token_type='output',
            operation='chat'
        ).inc(output_tokens)

        # Track cost
        cost = calculate_cost(model, input_tokens, output_tokens)
        api_cost_usd_total.labels(
            operation='chat',
            model=model
        ).inc(cost)

        # Track message
        chat_messages_total.labels(
            model=model,
            status='success',
            user_id_hash=hash_user_id(request.user_id)
        ).inc()

        return response

    except Exception as e:
        chat_messages_total.labels(
            model=model,
            status='error',
            user_id_hash=hash_user_id(request.user_id)
        ).inc()
        raise
```

**Installation**:
```bash
pip install prometheus-client
```

---

### 1.2 Web App Metrics (Next.js)

**File**: `relay_ai/product/web/lib/metrics.ts`

```typescript
import { incrementCounter, recordHistogram, gaugeSet } from '@opentelemetry/api';

// Page load metrics
export function recordPageLoad(pageName: string, loadTimeMs: number) {
  recordHistogram('web_page_load_time_seconds', loadTimeMs / 1000, {
    page_name: pageName,
    device_type: getDeviceType()
  });
}

// Core Web Vitals
export function recordCoreWebVitals() {
  // Largest Contentful Paint (LCP)
  new PerformanceObserver((entryList) => {
    const entries = entryList.getEntries();
    const lastEntry = entries[entries.length - 1];
    recordHistogram('largest_contentful_paint_seconds', lastEntry.renderTime / 1000, {
      page_name: getCurrentPage()
    });
  }).observe({ entryTypes: ['largest-contentful-paint'] });

  // Cumulative Layout Shift (CLS)
  let clsValue = 0;
  new PerformanceObserver((entryList) => {
    for (const entry of entryList.getEntries()) {
      if (!entry.hadRecentInput) {
        clsValue += entry.value;
      }
    }
    gaugeSet('cumulative_layout_shift', clsValue, {
      page_name: getCurrentPage()
    });
  }).observe({ entryTypes: ['layout-shift'] });

  // First Input Delay (FID)
  new PerformanceObserver((entryList) => {
    for (const entry of entryList.getEntries()) {
      recordHistogram('first_input_delay_seconds', entry.processingDuration / 1000, {
        page_name: getCurrentPage()
      });
    }
  }).observe({ entryTypes: ['first-input'] });
}

// User interactions
export function recordButtonClick(buttonName: string) {
  incrementCounter('click_event_total', 1, {
    button_name: buttonName,
    page_name: getCurrentPage()
  });
}

export function recordFormSubmission(formName: string, status: 'success' | 'error') {
  incrementCounter('form_submission_total', 1, {
    form_name: formName,
    status: status
  });
}

// Session tracking
export function recordSessionDuration(durationSeconds: number) {
  recordHistogram('session_duration_seconds', durationSeconds, {
    user_type: isAuthenticated() ? 'authenticated' : 'anonymous'
  });
}

// API client errors
export function recordAPIError(endpoint: string, errorType: string, statusCode?: number) {
  incrementCounter('api_call_errors_client_total', 1, {
    endpoint: endpoint,
    error_type: errorType,
    status_code: statusCode?.toString() || 'unknown'
  });
}
```

**Usage in Components**:
```typescript
// pages/chat.tsx
import { recordPageLoad, recordButtonClick } from '@/lib/metrics';

export default function ChatPage() {
  useEffect(() => {
    // Record page load
    recordPageLoad('chat', performance.now());
    recordCoreWebVitals();
  }, []);

  const handleSendMessage = () => {
    recordButtonClick('send_message');
    // ... send message logic
  };

  return (
    <button onClick={handleSendMessage}>
      Send Message
    </button>
  );
}
```

---

### 1.3 Database Metrics (SQLAlchemy)

**File**: `relay_ai/api/db/metrics.py`

```python
from prometheus_client import Counter, Histogram
from sqlalchemy import event
from sqlalchemy.engine import Engine
import time

database_query_duration_seconds = Histogram(
    'database_query_duration_seconds',
    'Database query latency',
    ['operation', 'table', 'status'],
    buckets=[0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0, 5.0]
)

database_queries_total = Counter(
    'database_queries_total',
    'Total database queries',
    ['operation', 'table', 'status']
)

database_slow_queries_total = Counter(
    'database_slow_queries_total',
    'Database queries exceeding 1 second',
    ['table']
)

database_connections_active = Gauge(
    'database_connections_active',
    'Current active database connections'
)

# Hook into SQLAlchemy events
@event.listens_for(Engine, "before_cursor_execute")
def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    context._query_start_time = time.time()

@event.listens_for(Engine, "after_cursor_execute")
def after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    total_time = time.time() - context._query_start_time

    # Parse operation and table from SQL
    operation = extract_operation(statement)  # SELECT, INSERT, etc.
    table = extract_table(statement)
    status = 'success'

    # Record metrics
    database_queries_total.labels(
        operation=operation,
        table=table,
        status=status
    ).inc()

    database_query_duration_seconds.labels(
        operation=operation,
        table=table,
        status=status
    ).observe(total_time)

    # Track slow queries
    if total_time > 1.0:
        database_slow_queries_total.labels(table=table).inc()

def extract_operation(sql: str) -> str:
    """Extract SQL operation from query"""
    upper_sql = sql.upper().strip()
    if upper_sql.startswith('SELECT'):
        return 'SELECT'
    elif upper_sql.startswith('INSERT'):
        return 'INSERT'
    elif upper_sql.startswith('UPDATE'):
        return 'UPDATE'
    elif upper_sql.startswith('DELETE'):
        return 'DELETE'
    else:
        return 'OTHER'

def extract_table(sql: str) -> str:
    """Extract table name from query"""
    # Simple extraction - can be enhanced
    if 'FROM' in sql.upper():
        parts = sql.upper().split('FROM')
        if len(parts) > 1:
            table_name = parts[1].split()[0]
            return table_name
    return 'unknown'
```

---

## Phase 2: Alert Configuration (Days 5-10)

### 2.1 AlertManager Setup

**File**: `config/alertmanager/alertmanager.yml`

```yaml
global:
  resolve_timeout: 5m
  slack_api_url: "{{ secret.SLACK_WEBHOOK_URL }}"

templates:
  - '/etc/alertmanager/templates/*.tmpl'

route:
  receiver: 'default'
  group_by: ['alertname', 'environment', 'team']
  group_wait: 10s
  group_interval: 10s
  repeat_interval: 12h

  routes:
    # Critical alerts - immediate notification
    - match:
        severity: critical
      receiver: 'critical'
      group_wait: 0s
      repeat_interval: 5m

    # High priority - ops team
    - match:
        severity: high
      receiver: 'ops-team'
      group_wait: 5s
      repeat_interval: 1h

    # Medium priority - dev team
    - match:
        severity: medium
      receiver: 'dev-team'
      group_wait: 1m
      repeat_interval: 4h

    # Low - just log
    - match:
        severity: low
      receiver: 'log-only'
      repeat_interval: 24h

receivers:
  - name: 'critical'
    slack_configs:
      - channel: '#critical-alerts'
        title: 'CRITICAL: {{ .GroupLabels.alertname }}'
        text: '{{ range .Alerts }}{{ .Annotations.description }}{{ end }}'
        send_resolved: true

    # Optional: PagerDuty integration
    pagerduty_configs:
      - service_key: '{{ secret.PAGERDUTY_SERVICE_KEY }}'
        severity: critical

  - name: 'ops-team'
    slack_configs:
      - channel: '#ops-alerts'
        title: 'HIGH: {{ .GroupLabels.alertname }}'

  - name: 'dev-team'
    slack_configs:
      - channel: '#dev-alerts'
        title: 'MEDIUM: {{ .GroupLabels.alertname }}'

  - name: 'log-only'
    # No active notifications - just logged

# Alert suppression rules
inhibit_rules:
  # Suppress errors during deployments
  - source_match:
      alertname: 'Deployment'
    target_match_re:
      alertname: 'HighErrorRate|HighLatency'
    equal: ['environment']
    duration: 5m

  # Suppress DB alerts during maintenance windows
  - source_match:
      alertname: 'DatabaseMaintenance'
    target_match_re:
      alertname: 'DatabaseConnectionDown|SlowQueries'
    duration: 2h
```

---

## Phase 3: Dashboard Creation (Days 10-15)

### 3.1 System Health Dashboard JSON

**File**: `observability/dashboards/system-health.json`

```json
{
  "dashboard": {
    "title": "System Health - Relay AI",
    "tags": ["system", "health", "golden-signals"],
    "timezone": "browser",
    "refresh": "10s",
    "panels": [
      {
        "id": 1,
        "title": "API Status",
        "type": "stat",
        "targets": [
          {
            "expr": "api:success_rate:5m",
            "legendFormat": "Success Rate"
          }
        ],
        "fieldConfig": {
          "defaults": {
            "thresholds": {
              "mode": "absolute",
              "steps": [
                {"color": "red", "value": 0},
                {"color": "yellow", "value": 0.95},
                {"color": "green", "value": 0.99}
              ]
            },
            "unit": "percentunit",
            "custom": {"hideFrom": {"tooltip": false, "viz": false}}
          }
        }
      },
      {
        "id": 2,
        "title": "Error Rate",
        "type": "stat",
        "targets": [
          {
            "expr": "api:error_rate:5m * 100"
          }
        ]
      },
      {
        "id": 3,
        "title": "P95 Latency",
        "type": "stat",
        "targets": [
          {
            "expr": "api:request_duration:p95:5m"
          }
        ]
      },
      {
        "id": 4,
        "title": "Request Rate (Last 1 Hour)",
        "type": "timeseries",
        "targets": [
          {
            "expr": "rate(http_requests_total[5m])"
          }
        ]
      }
    ]
  }
}
```

### 3.2 Import Dashboard via Grafana UI

```
1. Grafana → Dashboards → Import
2. Upload dashboard JSON
3. Select Prometheus data source
4. Click Import
```

---

## Phase 4: SLO Tracking (Days 15-20)

### 4.1 SLO Metrics Recording

**File**: `relay_ai/observability/slo.py`

```python
from prometheus_client import Gauge
from datetime import datetime, timedelta

# SLI: Availability
sli_availability_percent = Gauge(
    'sli_availability_percent',
    'Service availability SLI (% of successful requests)',
    ['environment']
)

# SLO: Availability (99.9%)
slo_availability_target = Gauge(
    'slo_availability_target_percent',
    'Availability SLO target',
    ['environment']
)

# Error Budget
error_budget_remaining_seconds = Gauge(
    'error_budget_remaining_seconds',
    'Remaining error budget for the month',
    ['environment']
)

def update_slo_metrics():
    """Update SLO tracking metrics"""

    # Calculate availability for last 30 days
    total_requests = get_metric_sum('http_requests_total', days=30)
    failed_requests = get_metric_sum(
        'http_requests_total',
        labels={'status_code': '5..'},
        days=30
    )

    availability = (total_requests - failed_requests) / total_requests * 100
    sli_availability_percent.labels(environment='beta').set(availability)

    # Calculate error budget (99.5% SLO for Beta)
    slo_target = 99.5
    slo_target_gauge.labels(environment='beta').set(slo_target)

    # Error budget = 0.5% of month = 10,800 seconds
    total_error_budget_seconds = 30 * 24 * 60 * 60 * (1 - slo_target/100)

    # Used = minutes of downtime
    downtime_minutes = (100 - availability) / 100 * 30 * 24 * 60
    used_error_budget_seconds = downtime_minutes * 60

    remaining_seconds = max(0, total_error_budget_seconds - used_error_budget_seconds)
    error_budget_remaining_seconds.labels(environment='beta').set(remaining_seconds)
```

---

## Phase 5: Cost Tracking (Days 20-25)

### 5.1 Cost Event Logging

**File**: `relay_ai/api/services/cost_tracker.py`

```python
from datetime import datetime
from dataclasses import dataclass
from typing import Optional
import hashlib
import json

@dataclass
class CostEvent:
    timestamp: datetime
    user_id_hash: str
    operation: str  # chat, search, embedding
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    environment: str = 'beta'

async def log_cost_event(event: CostEvent):
    """Log cost event for billing and analytics"""

    # Store in database for audit trail
    await db.cost_events.insert({
        'timestamp': event.timestamp,
        'user_id_hash': event.user_id_hash,
        'operation': event.operation,
        'model': event.model,
        'input_tokens': event.input_tokens,
        'output_tokens': event.output_tokens,
        'cost_usd': event.cost_usd,
        'environment': event.environment
    })

    # Emit metrics for real-time tracking
    llm_tokens_total.labels(
        model=event.model,
        token_type='input',
        operation=event.operation
    ).inc(event.input_tokens)

    llm_tokens_total.labels(
        model=event.model,
        token_type='output',
        operation=event.operation
    ).inc(event.output_tokens)

    api_cost_usd_total.labels(
        operation=event.operation,
        model=event.model
    ).inc(event.cost_usd)

def hash_user_id(user_id: str) -> str:
    """Hash user ID for privacy while maintaining consistency"""
    return hashlib.sha256(user_id.encode()).hexdigest()[:16]

# Example usage in chat endpoint
@app.post("/api/chat")
async def chat_endpoint(request: ChatRequest):
    response = await llm.create_message(
        model=request.model,
        messages=request.messages
    )

    # Calculate cost
    model_costs = {
        'claude-3.5-sonnet': {'input': 0.003, 'output': 0.015},
        'gpt-4': {'input': 0.03, 'output': 0.06}
    }

    costs = model_costs.get(request.model, {})
    input_cost = response.usage.input_tokens * costs.get('input', 0) / 1000
    output_cost = response.usage.output_tokens * costs.get('output', 0) / 1000
    total_cost = input_cost + output_cost

    # Log cost event
    await log_cost_event(CostEvent(
        timestamp=datetime.utcnow(),
        user_id_hash=hash_user_id(request.user_id),
        operation='chat',
        model=request.model,
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
        cost_usd=total_cost
    ))

    return response
```

---

## Testing & Validation

### Test Alert Rules

```bash
# Start Prometheus with alerts
docker run -d \
  --name prometheus-test \
  -p 9090:9090 \
  -v $(pwd)/observability/ALERT_RULES.yml:/etc/prometheus/rules/api-alerts.yml \
  prom/prometheus

# Generate high error rate to trigger alert
for i in {1..100}; do
  curl -i https://relay-beta-api.railway.app/api/nonexistent 2>/dev/null | head -1 &
done

# Check Prometheus for firing alerts
curl http://localhost:9090/api/v1/alerts | jq '.data.alerts[] | select(.state=="firing")'
```

---

## Deployment Checklist

### Pre-Launch (Week 1)
- [ ] Prometheus running and scraping metrics
- [ ] Grafana dashboards created and tested
- [ ] Alert rules configured and tested
- [ ] AlertManager routing validated
- [ ] Team trained on dashboards and alerts

### Soft Launch (Week 2)
- [ ] Enable metrics in Beta environment
- [ ] Monitor for 7 days with reduced alerting
- [ ] Tune alert thresholds based on baseline
- [ ] Collect feedback from on-call team

### Production Launch (Week 3)
- [ ] Enable metrics in Production
- [ ] Enable all alert routing
- [ ] PagerDuty integration active
- [ ] Incident runbooks documented
- [ ] Team on-call rotation scheduled

### Continuous Improvement (Week 4+)
- [ ] Weekly alert effectiveness review
- [ ] Monthly cost analysis
- [ ] Quarterly capacity planning
- [ ] Incident review process

---

## Support & Troubleshooting

### Common Issues

**Prometheus not scraping metrics**
```bash
# Check target status
curl http://localhost:9090/api/v1/targets

# Test metrics endpoint
curl https://relay-beta-api.railway.app/metrics

# Check Prometheus logs
docker logs prometheus
```

**Alerts not firing**
```bash
# Check alert rules loaded
curl http://localhost:9090/api/v1/rules | jq '.data.groups[].rules[]'

# Check AlertManager connectivity
curl http://localhost:9093/api/v1/alerts

# Manually trigger alert for testing
docker exec prometheus promtool check rules /etc/prometheus/rules/*.yml
```

**No data in Grafana**
```bash
# Verify Prometheus datasource
curl http://localhost:3000/api/datasources

# Check query syntax
# Use Prometheus UI first: http://localhost:9090/graph
# Then test in Grafana
```

---

## References

- **Prometheus Docs**: https://prometheus.io/docs/
- **Grafana Dashboarding**: https://grafana.com/docs/grafana/latest/features/panels/
- **Golden Signals**: https://sre.google/sre-book/monitoring-distributed-systems/
- **SRE Book**: https://sre.google/sre-book/

---

**Next**: Review `OBSERVABILITY_2025-11-11.md` for complete architecture details
