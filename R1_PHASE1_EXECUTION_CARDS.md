# R1 Memory & Context — Phase 1 Execution (Blockers + Mitigations)

**Phase**: Phase 1 (Blockers)
**Sprint**: 62
**Duration**: 1 week
**Gate**: repo-guardian (security-approved labels)
**Risk**: HIGH (encryption + GPU + RLS)
**Success**: All task cards completed + non-regression suite 100% PASS

---

## TASK A: Schema + RLS + Encryption Columns

**Objective**: Implement PostgreSQL schema with Row-Level Security, encryption columns, and user-isolated partial ANN indexes.

**Deliverables**:
1. Migration: Add columns (`user_hash`, `text_cipher`, `meta_cipher`, `emb_cipher`)
2. RLS policy: `memory_tenant_isolation` (users see only their `user_hash` rows)
3. Indexes: Per-tenant ANN with `user_hash` predicate
4. `app.user_hash` session variable plumbing (Python/FastAPI)
5. Rollback procedure documented

**Dependencies**: None (blocking)

**Estimated LOC**: 150 (SQL migration + Python plumbing)

**Gate**:
- [ ] Migration reversible (tested rollback)
- [ ] RLS policy blocks cross-tenant reads
- [ ] Partial ANN index scans only user's rows (EXPLAIN verified)
- [ ] repo-guardian: `security-approved` label

**Success Criteria**:
```sql
-- Verify RLS blocks cross-user access
SET app.user_hash = 'user_hash_1';
SELECT count(*) FROM memory_chunks;  -- Returns only user_1's rows

SET app.user_hash = 'user_hash_2';
SELECT count(*) FROM memory_chunks;  -- Returns only user_2's rows (different count)
```

---

## TASK B: Encryption Helpers + Write Path

**Objective**: Implement AES-256-GCM encryption for text/meta/shadow vectors. Integrate into indexing pipeline.

**Deliverables**:
1. `src/memory/security.py`: `hmac_user()`, `seal()`, `open_sealed()`
2. Environment vars: `MEMORY_ENCRYPTION_KEY` (32-byte base64), `MEMORY_TENANT_HMAC_KEY`
3. Indexing pipeline: Compute `user_hash`, encrypt text/meta/shadow, upsert plaintext embedding for ANN
4. Encryption helpers unit tests (seal/unseal round-trip)
5. Shadow vector stored and validated

**Dependencies**: Task A (schema)

**Estimated LOC**: 120 (security.py + integration tests)

**Gate**:
- [ ] Encryption key rotation procedure documented
- [ ] Sealed data format is nonce||ciphertext (12-byte nonce)
- [ ] Round-trip decrypt matches plaintext exactly
- [ ] repo-guardian: `security-approved` label

**Success Criteria**:
```python
# Unit test
plaintext = b"sensitive data"
sealed = seal(plaintext)
assert len(sealed) > len(plaintext)  # Ciphertext overhead

decrypted = open_sealed(sealed)
assert decrypted == plaintext  # Round-trip

# Integration: plaintext embedding stored + encrypted shadow stored
embedding_plain = np.array([0.1, 0.2, ...])  # Live in DB for ANN
embedding_cipher = seal(embedding_plain.tobytes())  # Shadow backup
```

---

## TASK C: GPU Provisioning + CE Service + Circuit Breaker

**Objective**: Provision GPU on Railway, implement cross-encoder reranker with latency budget and fail-open circuit breaker.

**Deliverables**:
1. Railway GPU instance: L40 or A100, configured
2. Environment var: `CROSS_ENCODER_MODEL` (default: `cross-encoder/ms-marco-TinyBERT-L-2-v2`)
3. `src/memory/rerank.py`: `rerank()` function with metrics + circuit breaker
4. Feature flag: `RERANK_ENABLED` (true/false to toggle)
5. Metrics: `rerank_ms` (p50/p95), `rerank_skipped_total` (circuit trips)
6. Integration test: CE latency < 200ms p95

**Dependencies**: None (parallel with A, B)

**Estimated LOC**: 80 (rerank.py + integration)

**Gate**:
- [ ] GPU instance verified (nvidia-smi check)
- [ ] Model downloaded & loaded
- [ ] p95 latency ≤ 100–200 ms measured
- [ ] Circuit breaker skips CE if > 250ms (returns ANN order)
- [ ] Feature flag toggles reranking on/off without deploy
- [ ] repo-guardian: `security-approved` label

**Success Criteria**:
```python
# Benchmark: 100 queries, 24 candidates each
candidates = ["doc1", "doc2", ..., "doc24"]
times = []
for query in queries:
    t0 = time.perf_counter()
    rerank(query, candidates)
    times.append((time.perf_counter() - t0) * 1000)

p95 = np.percentile(times, 95)
assert p95 < 200, f"p95={p95}ms exceeds budget"

# Circuit breaker test
# Simulate slow GPU: p95 becomes 300ms
# Verify rerank_skipped_total increments
```

---

## TASK D: API Endpoints + Pydantic Contracts + Tests

**Objective**: Implement `/memory/{index, query, summarize, entities}` endpoints with strict validation and comprehensive tests.

**Deliverables**:
1. `POST /api/v1/memory/index`: Chunk(512/64) → embed → encrypt → upsert
2. `POST /api/v1/memory/query`: ANN 24 → decay → CE 8→3 → citations
3. `POST /api/v1/memory/summarize`: Fetch + summarize + store as synthetic doc
4. `POST /api/v1/memory/entities`: NER on text/thread → store in `meta_cipher`
5. Pydantic contracts: `MemoryIndexRequest`, `MemoryQueryRequest`, `MemorySummaryRequest`, `MemoryEntityRequest`
6. Unit tests: Validation (max payload, max chunks, etc.)
7. Integration tests: End-to-end index → query → retrieve
8. Security tests: Cross-tenant leakage blocked, encryption verified

**Dependencies**: Tasks A, B, C (blockers complete)

**Estimated LOC**: 300 (endpoints + Pydantic + tests)

**Gate**:
- [ ] All endpoints auth-protected (inherit R0.5 JWT)
- [ ] Rate limits inherited (separate bucket for memory ops)
- [ ] Payload cap: 1MB; chunk cap: 200 chunks/call
- [ ] Pydantic validation rejects invalid input (422)
- [ ] Cross-tenant query blocked (RLS verified)
- [ ] Encryption round-trip verified (store encrypted → retrieve decrypted)
- [ ] repo-guardian: `security-approved` label

**Success Criteria**:
```python
# Unit: Validation rejects large payloads
with pytest.raises(ValueError):
    request = MemoryIndexRequest(
        doc_id="test",
        source="chat",
        text="x" * 1_000_001  # Exceeds 1MB
    )

# Integration: Cross-tenant isolation
user_1_token = create_token("user_1")
user_2_token = create_token("user_2")

# User 1 indexes
index_memory(user_1_token, doc_id="doc1", text="user 1 data")

# User 2 queries — should NOT see user 1's data
results = query_memory(user_2_token, query="user 1")
assert len(results) == 0  # RLS + isolation verified
```

---

## TASK E: Non-Regression Test Suite + Metrics

**Objective**: Implement comprehensive non-regression suite to ensure R0.5 baselines survive R1 launch.

**Deliverables**:
1. `tests/non_regression/test_r0_5_baseline.py`
2. Baseline tests:
   - TTFV p95 < 1.5s (R0.5: 1.1s)
   - SSE success ≥ 99.6% (R0.5 baseline)
   - Auth latency < 50ms
   - DB pool ≤ 80% utilization under 100 RPS
3. Memory API tests:
   - Index latency p95 < 750ms
   - Query latency p95 < 350ms (ANN + CE)
   - CE p95 < 200ms
4. Metrics instrumentation:
   - `memory_index_latency_ms` (p50, p95)
   - `memory_query_latency_ms` (p50, p95, with sub-timers: ann, rerank, total)
   - `memory_query_candidates_total`
   - `memory_rerank_skipped_total` (circuit breaker trips)
   - Error counters: `reason={timeout, bad_request, quota, rate, server}`

**Dependencies**: Tasks A–D

**Estimated LOC**: 150 (tests + metrics)

**Gate**:
- [ ] All R0.5 baseline tests PASS (TTFV, SSE, auth)
- [ ] All R1 latency targets MET (index, query, CE)
- [ ] Memory-specific metrics emitted correctly
- [ ] Alerting thresholds documented
- [ ] repo-guardian: approval gate

**Success Criteria**:
```python
# Non-regression: R0.5 baseline protected
def test_sse_ttfv_under_1_5s():
    ttfv = measure_ttfv(stream_chat("Hello"))
    assert ttfv < 1.5, f"TTFV regressed: {ttfv}s"

def test_database_pool_not_exhausted():
    # 25 memory queries + 25 auth calls concurrently
    with ThreadPoolExecutor(max_workers=50) as pool:
        memory_futures = [pool.submit(query_memory, "test") for _ in range(25)]
        auth_futures = [pool.submit(validate_jwt, token) for _ in range(25)]

        # All auth must succeed within 100ms (no pool starvation)
        for future in auth_futures:
            result = future.result(timeout=0.1)
            assert result.success

# R1: Latency targets met
def test_query_latency_under_350ms():
    latencies = [measure_query_latency(q) for q in queries]
    p95 = np.percentile(latencies, 95)
    assert p95 < 0.35, f"Query p95={p95}s exceeds 350ms"
```

---

## TASK F: Canary Deployment + Auto-Rollback

**Objective**: Implement canary deployment pattern (5% traffic) with automatic rollback on error/latency spikes.

**Deliverables**:
1. Feature flags: `MEMORY_ENABLED` (true/false), `MEMORY_CANARY_PCT` (0–100)
2. Canary logic: Route `MEMORY_CANARY_PCT` of memory requests to new code
3. Auto-rollback triggers:
   - `memory_query_error_rate > 0.01` (1%)
   - `memory_query_p95 > 400ms` (grace: 1.1x budget)
4. Monitoring dashboard: Error rate, latency p50/p95, canary traffic %
5. Runbook: Manual canary promotion from 5% → 50% → 100%

**Dependencies**: Tasks A–E (all must be ready)

**Estimated LOC**: 100 (feature flags + rollback logic)

**Gate**:
- [ ] Canary traffic isolated (no cross-contamination)
- [ ] Rollback triggers verify in staging
- [ ] Dashboard shows canary metrics separately
- [ ] repo-guardian: approval gate

**Success Criteria**:
```python
# Canary: 5% of requests to new code
if random.random() < 0.05:  # 5%
    result = query_memory_new(query)
else:
    result = query_memory_old(query)

# Auto-rollback: error rate spike
if memory_error_rate > 0.01:
    MEMORY_ENABLED = False  # Kill switch
    alert("Memory API disabled: high error rate")
```

---

## Phase 1 Execution Flow

**Week 1: Tasks A–C (parallel)**
```
Day 1–2: Task A (schema + RLS)
Day 1–2: Task B (encryption helpers)
Day 1–2: Task C (GPU + CE service)
  ├─ All tasks repo-guardian gated
  └─ Merge when all 3 PASS

Day 3–4: Task D (API endpoints + tests)
  ├─ Depends on A, B, C complete
  └─ Comprehensive security + integration tests

Day 5: Task E (non-regression suite)
  ├─ Depends on D complete
  └─ Verify R0.5 baselines intact

Day 6–7: Task F (canary deployment)
  ├─ Ready for staging promotion
  └─ Runbook finalized
```

**Week 2: Staging Validation (Phase 2)**
```
Day 1–3: Load test (1M chunks, 100 RPS)
  └─ Verify p95: query ≤ 350ms, index ≤ 750ms, CE ≤ 200ms

Day 4: Non-regression suite PASS
  └─ TTFV, SSE, auth baselines intact

Day 5: Canary 5% for 1 hour
  └─ Auto-rollback ready

Day 6: Manual promote 50% → 100%
  └─ Production ready
```

---

## Acceptance Criteria (Phase 1 COMPLETE)

**✅ GO FOR STAGING if:**
- [ ] Task A: Schema + RLS + indexes deployed
- [ ] Task B: Encryption helpers + write path live
- [ ] Task C: GPU provisioned, CE service < 200ms p95
- [ ] Task D: API endpoints fully tested, cross-tenant isolation verified
- [ ] Task E: Non-regression suite 100% PASS (TTFV, SSE, auth, pool)
- [ ] Task F: Canary deployment + auto-rollback runbook ready
- [ ] **repo-guardian**: All tasks `security-approved` labeled

**✅ All task cards have clear success criteria, gate conditions, and estimated LOC**

---

## How to Use These Task Cards

1. **Copy each TASK section** into your sprint planning tool
2. **Assign owners**: A (DBA/schema), B (security), C (ML infra), D (API), E (QA), F (DevOps)
3. **Parallel execution**: A, B, C can run simultaneously (different layers)
4. **Sequential gating**: D depends on A+B+C; E depends on D; F depends on all
5. **Gate at each task**: repo-guardian must approve before merge
6. **Move to Phase 2** when all Phase 1 tasks PASS

---

**Ready to kick off Phase 1 blockers immediately.** 🚀
