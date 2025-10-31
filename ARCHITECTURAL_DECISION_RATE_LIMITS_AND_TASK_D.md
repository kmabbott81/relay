# Architectural Decision: Rate Limits & Task D Kickoff
**Date**: 2025-10-20T00:52Z
**Authority**: Lead Architect (ChatGPT + Claude Code)
**Decision**: Proceed with Task D immediately; improve test harness rather than loosen guardrails

---

## Decision Rationale

### What the 429s Mean
Extended canary soak hit HTTP 429 (Too Many Requests) after 8 requests because **rate limiting is working as designed**:
- Per-IP budget: ~2 rps (60/30s)
- Per-user budget: ~1 rps (30/30s)
- Anonymous quotas: ~20/hour, 100 lifetime per token

Firing 500 requests rapidly from a single IP across 5 anon tokens saturates these buckets. **This is healthy behavior**, not a platform failure.

### Why Not Loosen Production Limits?
❌ **Option 2 (raise limits temporarily)**: Hides real-world behavior; risks collateral impact; bad trade-off for testing convenience.

❌ **Option 3 (investigate before Task D)**: 429s are expected and explained; investigation doesn't improve safety; blocks forward progress unnecessarily.

✅ **Chosen Path (proceed with Task D; fix the test harness)**: Preserves security envelope, improves signal quality, maintains momentum.

---

## Decision: PROCEED WITH TASK D

**Immediate Action**: Start R1 Task D (Memory APIs) implementation now.

**Initial Canary Status**: ✅ **STANDS** (10 requests, 100% success, promoted to 100% traffic)

**Extended Soak Status**: ⏸️ **DEFER** (rerun with proper pacing post-implementation)

---

## Parallel Work: Fix Test Harness & Add Observability

### P2.1: Improve Extended Soak Harness (30–45 min)
**Goal**: Gather statistically sound 500-request p95 under actual rate limits

**Changes**:
1. **Pace below limits**:
   - ≤1.8 rps total from single IP
   - ≤1 rps per token
   - Add jitter and exponential backoff on 429

2. **Shard the load**:
   - Use **10–20 anon tokens** (instead of 5)
   - Attempt 2+ source IPs if possible (distribute load)

3. **Respect quotas**:
   - Keep per-token requests ≤20/hour
   - Spread test across multiple short runs if needed

4. **Record Retry-After**:
   - Parse `Retry-After` headers from 429 responses
   - Compute compliance rate (should be ~100% when respecting headers)

**Outcome**: Valid p95 metrics **without undermining security**.

---

### P2.2: Add Rate Limit Visibility (60–90 min)
**Goal**: Make rate limiting transparent, auditable, and measurable

**Changes to API**:

1. **Structured logs on 429**:
   ```json
   {
     "event": "rate_limit_exceeded",
     "bucket": "ip|user|anon_hour|anon_lifetime",
     "remaining": 0,
     "reset_at": "2025-10-20T00:53:00Z",
     "request_id": "req_xyz"
   }
   ```

2. **Response headers** (per RFC 6585):
   ```
   X-RateLimit-Limit: 60
   X-RateLimit-Remaining: 0
   X-RateLimit-Reset: 1729408380
   Retry-After: 45
   ```

3. **Prometheus metrics**:
   ```
   relay_ratelimit_hits_total{bucket="ip|user|anon_hour|anon_lifetime"}
   relay_ratelimit_remaining_gauge{bucket="..."}
   relay_ratelimit_wait_seconds_histogram{bucket="..."}
   ```

**Integration**: Feeds directly into Prom/Graf when Railway observability is complete.

---

### P2.3: Canary-Runner Service Token (60 min)
**Goal**: Enable repeatable, controlled performance tests without weakening public limits

**Design**:

1. **New token type**: `canary-runner` (JWT claim)
   ```json
   {
     "sub": "canary-runner-0-20251020",
     "scope": "canary-runner",
     "ttl": "10m",
     "ip_allowlist": ["CI_IP", "your_runner_IP"],
     "rate_limit_bucket": "canary-runner"
   }
   ```

2. **Rate limits** (separate bucket):
   - 100 rps (for repeatable tests)
   - 10,000 total requests/10 min
   - Auto-expire after TTL

3. **Enforcement**:
   - Validate IP against allowlist
   - Check TTL (reject if expired)
   - Route to separate rate limit bucket
   - No broader data access than anon user

**Usage**:
```bash
# Generate token (automation)
CANARY_TOKEN=$(generate_canary_token --ttl 10m --ip $RUNNER_IP)

# Run soak with proper pacing
./improved_soak.sh --token $CANARY_TOKEN --requests 500 --rps 50
```

---

### P1: Railway Prom/Graf Rebuild (Tomorrow, ~90–120 min)
**Goal**: Production-grade observability without hacks; replaces temporary client-side metrics

**Requirements**:
1. **$PORT binding**: Prometheus and Grafana respect Railway's injected `$PORT` env var
2. **Health checks**: Both services respond to `GET /:PORT/health`
3. **Data sources & dashboards**: Pre-provisioned with Canary guardrails
4. **Token scoping**:
   - Prometheus: read-only API access
   - Grafana: Editor for Canary folder only

**Success Criteria**:
- Both public HTTPS endpoints healthy and responsive
- Canary guardrails PromQLs returning numerics (TTFV, SSE, RLS errors, etc.)
- Dashboard UIDs archived for audit trail

---

## Task D: R1 Memory APIs Implementation

### Scope
Implement four new memory endpoints with full encryption, RLS, and performance budgets:

1. **`POST /memory/index`**: Insert/upsert memory entries
   - Payload: `{user_hash, memory: {title, summary, tags, metadata}}`
   - Response: `{id, created_at, indexed_at}`
   - Performance: p95 ≤ 750ms

2. **`POST /memory/query`**: Semantic search across memory
   - Payload: `{user_hash, query, limit, filters}`
   - Response: `{results: [{id, title, summary, score}], count}`
   - Performance: p95 ≤ 350ms

3. **`POST /memory/summarize`**: Compress memory thread
   - Payload: `{user_hash, memory_ids}`
   - Response: `{summary, entities, key_decisions}`
   - Performance: p95 ≤ 1000ms

4. **`POST /memory/entities`**: Extract and rank entities
   - Payload: `{user_hash, memory_ids}`
   - Response: `{entities: [{name, type, frequency, context}]}`
   - Performance: p95 ≤ 500ms

### Security Requirements
- ✅ Row-level security: User_hash validated on every request
- ✅ AES-256-GCM encryption with AAD binding (prevents cross-user decryption)
- ✅ Fail-closed architecture (errors → no plaintext fallback)

### Performance Budget
- **Query p95**: ≤ 350ms (dominated by ANN latency)
- **Index p95**: ≤ 750ms (includes encryption + embedding)
- **TTFV impact**: Preserve p95 ≤ 1.5s (don't add streaming overhead)
- **SSE guardrail**: ≥ 99.6% (keep error rate low)

### Integration Points
- **TASK B (Encryption Helpers)**: Use live AES-256-GCM with AAD
- **TASK C (Reranker)**: Wire reranker into `/memory/query` for semantic ranking
- **RLS Policies**: Enforce user_hash scoping via PostgreSQL session variables
- **Observability**: Emit metrics (TTFV, SSE success rate, RLS errors, ANN latency, DB pool)

---

## Timeline

| Phase | Task | Duration | Dependency |
|-------|------|----------|------------|
| **Immediate** | Task D: Implement memory APIs | 8–12h | None (start now) |
| **Parallel** | P2.1: Improved soak harness | 30–45min | Can start immediately |
| **Parallel** | P2.2: Rate limit visibility | 60–90min | Can start immediately |
| **Parallel** | P2.3: Canary-runner token | 60min | Can start immediately |
| **Tomorrow** | P1: Railway Prom/Graf rebuild | 90–120min | Can start after initial Task D phase |
| **Post-Implementation** | Extended soak (500-request rerun) | 30–45min | Task D MVP complete + improved harness ready |

---

## Guardrails & Auto-Rollback

**Unmodified from Initial Canary**:
- Success ratio ≥ 99.6%
- p95 TTFV ≤ 1500ms
- Zero 5xx errors

**New Task D Guardrails**:
- Query p95 ≤ 350ms
- Index p95 ≤ 750ms
- SSE ≥ 99.6%
- RLS errors = 0

**Auto-rollback trigger**: Any guardrail breach → immediate production rollback to r0.5-hotfix.

---

## Decision Sign-Off

| Role | Status | Authority |
|------|--------|-----------|
| Lead Architect | ✅ **APPROVED** | ChatGPT |
| Executor | ✅ **READY** | Claude Code |
| Timeline | ✅ **ACCEPTED** | No blocking delays |

---

## Next Steps

1. ✅ **Document decision** (this file)
2. ✅ **Update todos** (Task D pending, P2.1-P2.3 queued, P1 retained)
3. ✅ **Proceed with Task D kickoff** (explore codebase, design APIs, begin implementation)
4. ⏭️ **Queue P2 & P1 work** (start after initial Task D phase)

---

**Status**: ✅ **DECISION APPROVED - PROCEED WITH TASK D**
