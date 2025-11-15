# Cost Optimization Action Plan
**Date**: 2025-11-11
**Status**: Ready for Implementation
**Impact**: 15-30% cost reduction possible with quick wins

---

## Phase 1: Quick Wins (This Week - 2-3 hours)

### Action 1.1: Enable Cost Governance Tracking
**File**: Already implemented at `src/cost/enforcer.py`
**Time**: 30 minutes

```python
# Add to your API initialization
from src.cost.enforcer import should_deny, should_throttle, BudgetExceededError
from src.cost.anomaly import detect_anomalies

# Before any API operation:
async def process_request(tenant_id, request):
    # Check if budget is exceeded
    deny, reason = should_deny(tenant_id)
    if deny:
        raise BudgetExceededError(reason)

    # Check if approaching budget (80% threshold)
    throttle, reason = should_throttle(tenant_id)
    if throttle:
        logger.warning(f"Throttle warning: {reason}")
        # Could add rate limiting here

    # Process request...
    # Log cost event...
```

**Immediate Benefit**: Prevent runaway costs, visibility into spending

---

### Action 1.2: Set Up Cost Report Dashboard
**File**: Script at `scripts/cost_report.py`
**Time**: 15 minutes

```bash
# Generate daily cost report
cd /path/to/project
python scripts/cost_report.py > cost_report_$(date +%Y%m%d).txt

# Generate JSON for integration
python scripts/cost_report.py --json > cost_report.json

# Schedule as cron job (recommended)
0 8 * * * cd /path/to/project && python scripts/cost_report.py >> logs/daily_cost_reports.txt
```

**Output**:
```
=== Cost Report (Last 30 Days) ===

Global Spend:
  Daily:   $8.45
  Monthly: $234.67

Per-Tenant Spend:
Tenant               Daily       Monthly  Budget Status
-----------------------------------------------------------------
trial-users         $0.50       $15.00   ✅
premium-users       $5.23       $156.78  ✅
enterprise-tier     $2.72       $62.89   ✅

=== Cost Anomalies ===
(none detected today)
```

**Immediate Benefit**: Visibility into who's spending what, early anomaly detection

---

### Action 1.3: Configure Budget Limits
**File**: `config/budgets.yaml` (create if missing)
**Time**: 15 minutes

```yaml
global:
  daily: 25.0          # Stop at $25/day total
  monthly: 500.0       # Stop at $500/month total

tenants:
  # Trial accounts - very limited
  trial-tier:
    daily: 1.0
    monthly: 10.0

  # Paying customers
  startup-tier:
    daily: 5.0
    monthly: 100.0

  # Premium customers
  premium-tier:
    daily: 25.0
    monthly: 500.0

  # Enterprise customers
  enterprise-tier:
    daily: 100.0
    monthly: 2000.0
```

**Environment Variables** (set in `.env` or Railway):
```bash
BUDGET_SOFT_THRESHOLD=0.8        # Warn at 80%
BUDGET_HARD_THRESHOLD=1.0        # Deny at 100%
GLOBAL_BUDGET_DAILY=25.0
GLOBAL_BUDGET_MONTHLY=500.0
TENANT_BUDGET_DAILY_DEFAULT=5.0
TENANT_BUDGET_MONTHLY_DEFAULT=100.0
```

**Immediate Benefit**: Automatic cost control, prevents surprise bills

---

### Action 1.4: Add GitHub Actions Caching
**File**: `.github/workflows/ci.yml`
**Time**: 10 minutes

```yaml
- name: Cache pip dependencies
  uses: actions/cache@v3
  with:
    path: ~/.cache/pip
    key: ${{ runner.os }}-pip-${{ hashFiles('requirements.txt') }}
    restore-keys: |
      ${{ runner.os }}-pip-

- name: Cache npm dependencies
  working-directory: relay_ai/product/web
  uses: actions/cache@v3
  with:
    path: node_modules
    key: ${{ runner.os }}-npm-${{ hashFiles('relay_ai/product/web/package-lock.json') }}
    restore-keys: |
      ${{ runner.os }}-npm-
```

**Expected Benefit**: 20-30% reduction in workflow time (5-15 min/run)
**Monthly Savings**: 5-10 min (< $0.01/month currently, but scales with usage)

---

## Phase 2: Medium-Term Optimizations (Weeks 2-4)

### Action 2.1: Implement Database Query Caching
**File**: `relay_ai/api/cache.py` (new)
**Time**: 4-6 hours

```python
from functools import lru_cache
import hashlib
import json
from datetime import datetime, timedelta

class QueryCache:
    def __init__(self, ttl_minutes=30):
        self.ttl_minutes = ttl_minutes
        self.cache = {}

    def get_cache_key(self, query: str, params: dict) -> str:
        """Generate cache key from query and params"""
        key_str = f"{query}:{json.dumps(params, sort_keys=True)}"
        return hashlib.md5(key_str.encode()).hexdigest()

    def get(self, query: str, params: dict):
        """Retrieve cached query result if not expired"""
        key = self.get_cache_key(query, params)
        if key in self.cache:
            result, expiry = self.cache[key]
            if datetime.now() < expiry:
                logger.info(f"Cache hit for query (saved DB call)")
                return result
            else:
                del self.cache[key]
        return None

    def set(self, query: str, params: dict, result):
        """Cache query result with TTL"""
        key = self.get_cache_key(query, params)
        expiry = datetime.now() + timedelta(minutes=self.ttl_minutes)
        self.cache[key] = (result, expiry)

# Usage in API endpoints:
query_cache = QueryCache(ttl_minutes=30)

@app.get("/api/queries/{user_id}")
async def get_user_queries(user_id: str):
    query = "SELECT * FROM queries WHERE user_id = ?"
    params = {"user_id": user_id}

    # Check cache first
    cached = query_cache.get(query, params)
    if cached:
        return cached

    # If not cached, query database
    result = db.execute(query, params)

    # Cache result
    query_cache.set(query, params, result)

    return result
```

**Expected Benefit**: 15-30% reduction in database queries
**Monthly Savings**: $0.20-0.50/month (scales to $5-10/month at 100 users)

---

### Action 2.2: Optimize Slow Queries
**File**: Review `relay_ai/api/queries.py`
**Time**: 3-5 hours

**Diagnostic Steps**:
```sql
-- Enable query logging on Railway PostgreSQL
SET log_statement = 'all';
SET log_min_duration_statement = 1000;  -- Log queries > 1 second

-- Find slow queries in logs
SELECT query, mean_time, calls
FROM pg_stat_statements
ORDER BY mean_time DESC
LIMIT 10;

-- Check for missing indexes
SELECT schemaname, tablename, indexname
FROM pg_indexes
WHERE schemaname != 'pg_catalog'
ORDER BY tablename;

-- Analyze query execution plan
EXPLAIN ANALYZE SELECT * FROM queries WHERE user_id = 'user-123';
```

**Common Optimization Patterns**:
1. **Add missing indexes** on frequently filtered columns
2. **Fix N+1 queries** (multiple rounds to DB)
3. **Batch similar queries** (combine 10 queries into 1)
4. **Archive old data** (queries slow down with size)

**Expected Benefit**: 20-50% speedup on database operations
**Monthly Savings**: $1-3/month (scales to $10-30/month at scale)

---

### Action 2.3: Implement Query Result Compression
**File**: `relay_ai/api/middleware.py`
**Time**: 2-3 hours

```python
import gzip
import json

@app.middleware("http")
async def compress_response(request, call_next):
    response = await call_next(request)

    # Only compress JSON responses
    if "application/json" in response.headers.get("content-type", ""):
        # Check if client accepts gzip
        if "gzip" in request.headers.get("accept-encoding", ""):
            # Compress response body
            original_body = await response.body()
            compressed = gzip.compress(original_body)

            # Only use compression if it saves space
            if len(compressed) < len(original_body):
                response.headers["content-encoding"] = "gzip"
                response.body = compressed
                logger.info(f"Compressed response: {len(original_body)} -> {len(compressed)} bytes")

    return response
```

**Expected Benefit**: 40-60% reduction in network bandwidth
**Monthly Savings**: $1-5/month on egress costs

---

## Phase 3: Scaling Optimizations (Month 2+)

### Action 3.1: Implement Redis Caching Layer
**File**: `relay_ai/cache/redis.py` (new)
**Time**: 6-8 hours
**Cost**: $5-20/month for Redis hosting

```python
import redis
from typing import Optional

class RedisCache:
    def __init__(self, url: str):
        self.redis = redis.from_url(url)
        self.default_ttl = 3600  # 1 hour

    def get(self, key: str) -> Optional[dict]:
        """Get value from cache"""
        value = self.redis.get(key)
        return json.loads(value) if value else None

    def set(self, key: str, value: dict, ttl: int = None):
        """Set value with TTL"""
        ttl = ttl or self.default_ttl
        self.redis.setex(key, ttl, json.dumps(value))

    def delete(self, key: str):
        """Delete key"""
        self.redis.delete(key)

# Usage in endpoints:
cache = RedisCache(os.getenv("REDIS_URL"))

@app.get("/api/user/{user_id}/profile")
async def get_user_profile(user_id: str):
    cache_key = f"user:{user_id}:profile"

    # Check Redis cache
    cached = cache.get(cache_key)
    if cached:
        logger.info(f"Redis cache hit: {cache_key}")
        return cached

    # Query database
    user = db.query(User).filter(User.id == user_id).first()

    # Cache for 1 hour
    cache.set(cache_key, user.to_dict(), ttl=3600)

    return user
```

**When to Implement**: At 100+ users or when database costs exceed $20/month
**Expected Benefit**: 40-70% reduction in database queries
**Monthly Savings**: $5-15/month

---

### Action 3.2: Database Read Replicas
**File**: Railway configuration
**Time**: 2-3 hours
**Cost**: +$20-30/month

**Setup Steps**:
1. Create read replica in Railway
2. Route SELECT queries to replica
3. Route INSERT/UPDATE/DELETE to primary
4. Monitor replication lag

```python
# Usage in code:
class Database:
    def __init__(self):
        self.primary = create_connection(PRIMARY_DB_URL)
        self.replica = create_connection(REPLICA_DB_URL)

    def query_read(self, sql):
        """Use replica for reads"""
        return self.replica.execute(sql)

    def query_write(self, sql):
        """Use primary for writes"""
        return self.primary.execute(sql)
```

**When to Implement**: At 500+ users with high read load
**Expected Benefit**: Distribute read load, improve performance
**Monthly Savings**: Offsets 50% of database costs through efficiency

---

## Phase 4: Production Hardening (Month 3+)

### Action 4.1: Implement Cost Anomaly Detection
**Already Implemented**: `src/cost/anomaly.py`
**Time**: 30 minutes to activate

```python
from src.cost.anomaly import detect_anomalies

# Run daily anomaly check
async def daily_cost_check():
    anomalies = detect_anomalies()

    for anomaly in anomalies:
        logger.warning(f"Cost anomaly detected for {anomaly['tenant']}")
        logger.warning(f"  Today: ${anomaly['today_spend']:.2f}")
        logger.warning(f"  Baseline: ${anomaly['baseline_mean']:.2f}")
        logger.warning(f"  Threshold: ${anomaly['threshold']:.2f} ({anomaly['sigma']}σ)")

        # Send alert to admin
        send_slack_alert(f"Cost anomaly: {anomaly['tenant']}")

# Schedule in your task queue:
schedule.daily(daily_cost_check, at_time="09:00")
```

**Expected Benefit**: Early warning of cost issues
**Monthly Savings**: $0 but prevents $100+ surprise bills

---

### Action 4.2: Add Model Selection Optimization
**File**: `relay_ai/llm/model_selector.py` (new)
**Time**: 3-4 hours

```python
from enum import Enum

class LLMModel(Enum):
    HAIKU = {
        "name": "claude-3-haiku",
        "input_price": 0.00025,  # per 1K tokens
        "output_price": 0.00125,
        "best_for": ["classification", "extraction", "simple_qa"],
        "latency_ms": 200
    }
    SONNET = {
        "name": "claude-3.5-sonnet",
        "input_price": 0.003,
        "output_price": 0.015,
        "best_for": ["reasoning", "generation", "complex_analysis"],
        "latency_ms": 500
    }

class ModelSelector:
    @staticmethod
    def select_model(task_type: str, quality_threshold: float = 0.8) -> LLMModel:
        """Select optimal model for task"""

        # Simple tasks -> use Haiku (90% cheaper)
        if task_type in ["classification", "extraction", "simple_qa"]:
            return LLMModel.HAIKU

        # Complex tasks -> use Sonnet
        if task_type in ["reasoning", "generation", "complex_analysis"]:
            return LLMModel.SONNET

        # Default to Haiku for cost efficiency
        return LLMModel.HAIKU

# Usage:
model = ModelSelector.select_model("classification")
response = call_llm(prompt, model=model.name)
```

**Expected Benefit**: 50-90% cost reduction for simple tasks
**Monthly Savings**: $10-30/month (with significant usage)

---

## Phase 5: Monitoring & Continuous Optimization

### Monthly Cost Review Checklist

**First Monday of Every Month** (15 minutes):
- [ ] Run `python scripts/cost_report.py`
- [ ] Check for anomalies in `logs/governance_events.jsonl`
- [ ] Review budgets in `config/budgets.yaml`
- [ ] Document spending trends
- [ ] Adjust budgets if needed

**Quarterly Deep Dive** (1 hour):
- [ ] Analyze top 10 most expensive operations
- [ ] Review slow query logs
- [ ] Check cache hit rates
- [ ] Evaluate model selection efficiency
- [ ] Plan tier upgrades if approaching limits

---

## Implementation Priority Matrix

| Action | Impact | Effort | Timeline | ROI |
|--------|--------|--------|----------|-----|
| **1.1: Cost Governance** | High | Low | Now | Immediate |
| **1.2: Cost Reports** | High | Low | Now | Immediate |
| **1.3: Budget Limits** | High | Low | Now | Immediate |
| **1.4: GitHub Caching** | Medium | Low | Week 1 | Medium |
| **2.1: Query Caching** | High | Medium | Weeks 2-4 | High |
| **2.2: Query Optimization** | High | Medium | Weeks 2-4 | High |
| **2.3: Response Compression** | Medium | Medium | Weeks 2-4 | Medium |
| **3.1: Redis Layer** | High | High | Month 2+ | Very High |
| **3.2: Read Replicas** | High | Medium | Month 2+ | Very High |
| **4.1: Anomaly Detection** | High | Low | Month 3+ | Immediate |
| **4.2: Model Selection** | High | Medium | Month 3+ | Very High |

---

## Success Metrics

### Track These Monthly:
1. **Total Monthly Cost**
   - Current: $10/month
   - Target at 100 users: $40-50/month
   - Alert if exceeds: $100/month

2. **Cost per User**
   - Current: N/A (beta)
   - Target: < $0.50/user/month
   - Alert if exceeds: > $1/user/month

3. **Database Query Cost**
   - Current: < $1/month
   - After caching: 20-50% reduction
   - Goal: < $0.50 per 1,000 queries

4. **API Cost Efficiency**
   - Track cost per API request
   - Optimize top 10% most expensive requests
   - Goal: < $0.0001 per request average

5. **Budget Adherence**
   - Soft threshold alerts: 0 (if > 0, optimize)
   - Hard threshold blocks: 0 (if > 0, increase budget)
   - Anomaly detections: < 2 per month

---

## Expected Cost Impact

| Phase | Timeframe | Savings | Cumulative |
|-------|-----------|---------|------------|
| **Current State** | Now | Baseline | $10/mo |
| **Phase 1** | Week 1 | $0-1/mo | $9-10/mo |
| **Phase 2** | Weeks 2-4 | $2-5/mo | $5-8/mo |
| **Phase 3** | Month 2+ | $5-10/mo | $0-5/mo* |
| **Phase 4** | Month 3+ | $5-15/mo | $-5-5/mo* |

*Note: At higher scale, infrastructure costs increase but efficiency improves, keeping cost/user constant

---

## Quick Reference: Cost Governance Commands

```bash
# Generate cost report
python scripts/cost_report.py

# JSON export for dashboards
python scripts/cost_report.py --json > report.json

# Tenant-specific analysis
python scripts/cost_report.py --tenant premium-tier --days 7

# Check governance events (anomalies, budget violations)
tail -f logs/governance_events.jsonl

# View current budgets
cat config/budgets.yaml

# Test budget enforcement
python -c "from src.cost.enforcer import should_deny; print(should_deny('test-tenant'))"
```

---

## Questions & Troubleshooting

**Q: How do I know if I'm over budget?**
A: Check logs/governance_events.jsonl for "budget_deny" events. The cost report CLI will also show budget status with red flags (🚨).

**Q: Can I retroactively cache old queries?**
A: Yes, implement cache warming on startup:
```python
# Warm cache with top 100 common queries
for query in get_top_100_queries():
    result = db.execute(query)
    cache.set(query_id, result, ttl=86400)  # 24 hour TTL
```

**Q: What's the quickest 15-minute optimization?**
A: Enable cost governance + set budget limits. This prevents cost issues while other optimizations are built.

**Q: Should I upgrade tiers now or wait?**
A: Current tiers (Railway Eco, Vercel Hobby) are sufficient until 100+ users. No upgrade needed for 4-6 months.

**Q: How do I explain costs to investors?**
A: Use the cost report to show:
- Cost per user (currently N/A, will be $0.10-0.30 at scale)
- Cost as % of revenue (should be < 5%)
- Cost trajectory (staying flat as users grow = efficient scaling)

---

## Resources

**Built-in Cost Tools**:
- Cost governance: `src/cost/` directory
- Cost reports: `scripts/cost_report.py`
- Governance events: `logs/governance_events.jsonl`
- Budget config: `config/budgets.yaml`

**External Resources**:
- Railway pricing: https://railway.app/pricing
- Vercel pricing: https://vercel.com/pricing
- Anthropic pricing: https://www.anthropic.com/pricing
- OpenAI pricing: https://openai.com/pricing

---

**Status**: Ready to implement Phase 1 immediately
**Estimated Time to Full Optimization**: 3-4 weeks
**Estimated Cost Savings**: 30-50% reduction possible with all phases

Start with Phase 1 today. It takes 90 minutes and provides immediate visibility & control.
