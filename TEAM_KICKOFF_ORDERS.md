# 🚀 Team Kickoff Orders — TASK B + C (Start TODAY)

**Date**: 2025-10-19
**Status**: TASK A staging in progress; B+C execute in parallel
**Approval**: Specs locked, ready to execute

---

## 📋 TASK B Kickoff Order — Security Team

**Task**: Encryption Helpers + Write Path
**Duration**: 3-4 days (deliver by Day 3-4)
**Owner**: [Security Lead]
**Spec**: `TASK_B_ENCRYPTION_SPECIFICATION.md` (locked)

### Deliverables

#### 1. Core Module: `src/memory/security.py` (120 LOC)

```python
# Three functions required:

def hmac_user(user_id: str) -> str:
    """Deterministic HMAC-SHA256(MEMORY_TENANT_HMAC_KEY, user_id)"""
    # Returns 64-character hex string
    # Used for RLS policy matching

def seal(plaintext: bytes, aad: bytes = b"") -> bytes:
    """AES-256-GCM encryption with AAD binding"""
    # Format: nonce (12 bytes) || ciphertext || auth tag
    # AAD prevents cross-tenant decryption (user B can't decrypt user A's data)

def open_sealed(blob: bytes, aad: bytes = b"") -> bytes:
    """AES-256-GCM decryption"""
    # Raises InvalidTag if AAD mismatch or tampering detected
    # Fail-closed: no plaintext fallback
```

#### 2. Unit Tests: `tests/memory/test_encryption.py` (80+ LOC)

**Test Classes**:
- `TestSealRoundTrip`: Round-trip encryption/decryption
- `TestAADBinding`: Cross-tenant prevention (AAD mismatch fails)
- `TestTamperDetection`: 1-bit corruption raises InvalidTag
- `TestThroughput`: ≥ 5k ops/sec, p95 < 1ms latency
- `TestIntegration`: Write path integration with RLS

**Critical Tests**:
```python
def test_seal_aad_binding(self):
    """AAD mismatch prevents cross-tenant decryption"""
    encrypted = seal(plaintext, aad=b"user_hash_a")
    with pytest.raises(InvalidTag):
        open_sealed(encrypted, aad=b"user_hash_b")  # ← MUST FAIL
```

#### 3. Write Path Integration

**Location**: `src/memory/index.py` or integrate into `TASK D` endpoint

**Function**: `index_memory_chunk(conn, user_id, doc_id, source, text, embedding, metadata)`

**Flow**:
```python
1. user_hash = hmac_user(user_id)
2. async with set_rls_context(conn, user_id):
3.    text_cipher = seal(text.encode(), aad=user_hash.encode())
4.    meta_cipher = seal(json.dumps(metadata).encode(), aad=user_hash.encode())
5.    emb_cipher = seal(embedding.tobytes(), aad=user_hash.encode())
6.    # Store: text_cipher, meta_cipher, emb_cipher (encrypted)
7.    #        embedding plaintext (for ANN indexing)
8.    # Insert into memory_chunks with RLS enforcement
```

### Key Management

**Environment Variables**:
```bash
MEMORY_ENCRYPTION_KEY=<32-byte base64>     # AES-256 key
MEMORY_TENANT_HMAC_KEY=<32-byte base64>    # HMAC key
```

**Generation**:
```bash
python -c "import os, base64; print(base64.b64encode(os.urandom(32)).decode())"
```

**Rotation Strategy**:
- MEMORY_ENCRYPTION_KEY: Quarterly (dual-write for gradual migration)
- MEMORY_TENANT_HMAC_KEY: Annually (requires full reindex)

### Compensating Controls

**Documented Exception**:
> Plaintext embeddings required for pgvector ANN indexing. Mitigated by:
> - RLS policy (hard tenant boundary)
> - Volume encryption (database at-rest encryption)
> - Shadow backup (emb_cipher for compliance export)
> - Audit logging (all access logged)

### Gates & Approval

- [ ] `security.py` implements all 3 functions
- [ ] Tests: 20+ cases, round-trip, AAD binding, tamper detection
- [ ] Throughput: ≥ 5k ops/sec verified
- [ ] No hardcoded keys or secrets
- [ ] Fail-closed defaults implemented
- [ ] Code review: Crypto correctness verified
- [ ] Label: `security-approved` applied by repo-guardian
- [ ] Ready for merge into TASK D

### Success Criteria

✅ When:
- `seal(plaintext)` + `open_sealed(blob)` round-trip works
- Wrong AAD fails with InvalidTag (cross-tenant prevented)
- 1-bit corruption detected and rejected
- Throughput > 5k ops/sec
- Write path encrypts text/meta/embedding correctly
- All tests passing + coverage > 90%

### Blockers

❌ If:
- Keys missing → ValueError (fail-closed)
- AAD binding not enforced → Security issue
- Throughput < 5k ops/sec → Performance concern
- Tests fail → Do not merge

---

## 📋 TASK C Kickoff Order — ML Ops Team

**Task**: GPU Provisioning + Cross-Encoder Reranker
**Duration**: 2-3 days (deliver by Day 2-3)
**Owner**: [ML Ops Lead]
**Spec**: `TASK_C_RERANKER_SPECIFICATION.md` (locked)

### Deliverables

#### 1. GPU Infrastructure

**Provisioning (Railway)**:
```bash
railway resource create gpu:l40
# or
railway resource create gpu:a100
```

**Specifications**:
- GPU: L40 (48GB vRAM) preferred, A100 acceptable
- CPU: 8+ cores
- RAM: 32GB
- Storage: 100GB+

**Verification**:
```bash
nvidia-smi  # Shows GPU device
python -c "import torch; print(torch.cuda.is_available())"  # True
```

#### 2. Core Service: `src/memory/rerank.py` (80 LOC)

```python
# Three key functions:

async def rerank(query: str, candidates: List[str], timeout_ms: float = 250) -> List[RerankedResult]:
    """Rerank candidates with circuit breaker"""
    # CE scoring with latency budget
    # If > timeout_ms: skip CE, return ANN order (fail-open)

def get_cross_encoder() -> CrossEncoder:
    """Lazy-load CE model on first call"""
    # Model: cross-encoder/ms-marco-TinyBERT-L-2-v2
    # Loaded on DEVICE (cuda:0)

async def maybe_rerank(query: str, candidates: List[str]) -> List[str]:
    """Feature-flagged reranking"""
    # If RERANK_ENABLED=true: rerank
    # If false: return ANN order (no-op)
```

#### 3. Unit Tests: `tests/memory/test_rerank.py` (40 LOC)

**Test Classes**:
- `TestCrossEncoderInit`: Model loads correctly
- `TestReranking`: Semantic quality, latency under budget
- `TestCircuitBreaker`: Timeout → skip CE
- `TestFeatureFlag`: RERANK_ENABLED toggle
- `TestMetrics`: Latency/skips collected

**Critical Test**:
```python
@pytest.mark.asyncio
async def test_rerank_latency_under_budget(self):
    """p95 latency < 150ms for 24 candidates"""
    candidates = ["doc " + str(i) for i in range(24)]
    elapsed_ms = measure_time(await rerank(query, candidates))
    assert elapsed_ms < 150, f"Exceeded budget: {elapsed_ms}ms"
```

#### 4. Metrics & Monitoring

**Expose via**:
```python
def get_rerank_metrics() -> dict:
    return {
        "rerank_skipped_total": count,  # Circuit breaker trips
        "rerank_latency_ms": {
            "p50": ...,
            "p95": ...,  # Must be < 150ms
            "max": ...,
        },
        "device": "cuda:0",
    }
```

### Performance Targets

| Metric | Target | Notes |
|--------|--------|-------|
| Model load | < 5 sec | GPU startup |
| p50 latency | < 50 ms | TinyBERT typical |
| p95 latency | < 150 ms | Budget for 24 candidates |
| p99 latency | < 250 ms | Circuit breaker threshold |
| Throughput | ≥ 100 q/min | Single GPU |
| Batch size | 32 | Optimal for VRAM |

### Load Test Script

```bash
# Test 100 queries with 24 candidates each
python tests/rerank/load_test.sh

# Expected:
# p50: 45-80ms
# p95: 100-150ms
# p99: 200-250ms
```

### Feature Flag

```bash
RERANK_ENABLED=true   # Default (enable reranking)
RERANK_ENABLED=false  # Disable (return ANN order only)
```

### Circuit Breaker Logic

```python
if elapsed_ms > RERANK_CIRCUIT_MS (250ms):
    # Skip CE, return ANN order
    rerank_skips_total += 1
    return [RerankedResult(c, score=1.0 - i/len(candidates), rank=i+1)
            for i, c in enumerate(candidates)]
```

### Gates & Approval

- [ ] GPU provisioned & nvidia-smi shows device
- [ ] Model downloads and loads (< 5 sec)
- [ ] Rerank service implements all functions
- [ ] p95 latency < 150ms (100 query test)
- [ ] Circuit breaker tested (timeout handling)
- [ ] Feature flag toggles reranking on/off
- [ ] Metrics endpoint returns valid JSON
- [ ] Tests passing (40+ cases)
- [ ] Label: `perf-approved` applied by repo-guardian
- [ ] Ready for TASK D integration

### Success Criteria

✅ When:
- GPU available: `torch.cuda.is_available() == True`
- Model loads: CrossEncoder initialized
- `rerank()` scores candidates correctly
- p95 < 150ms on 24-candidate queries
- Circuit breaker skips CE if > 250ms
- `maybe_rerank()` toggles reranking with RERANK_ENABLED
- Metrics collected and accessible
- All tests passing

### Blockers

❌ If:
- GPU not available → Cannot proceed (dependency)
- Model download fails → Check internet, manual download
- p95 > 250ms → Adjust batch size, profile GPU
- Feature flag doesn't work → Integration failure
- Tests fail → Do not merge

---

## 🔄 Integration Points (For TASK D)

### TASK B Integration

```python
from src.memory.security import seal, open_sealed, hmac_user

async def index_memory_chunk(...):
    user_hash = hmac_user(user_id)
    text_cipher = seal(text.encode(), aad=user_hash.encode())
    # ... store encrypted data
```

### TASK C Integration

```python
from src.memory.rerank import maybe_rerank, get_rerank_metrics

async def query_memory(...):
    candidates = [... ANN search ...]
    reranked = await maybe_rerank(query, candidates)
    results = [... decrypt and return ...]

# Metrics endpoint
@app.get("/metrics/memory")
async def memory_metrics():
    return get_rerank_metrics()
```

---

## 📅 Timeline

### TASK B (Crypto): Days 1-4

```
Day 1: Implement security.py functions
Day 2: Unit tests (round-trip, AAD, tamper)
Day 3: Write path integration
Day 4: Code review + repo-guardian approval
```

### TASK C (Reranker): Days 1-3

```
Day 0-1: GPU provisioned, model cached
Day 1-2: Rerank service + tests
Day 2-3: Load test + tuning, p95 verified
Day 3: Code review + repo-guardian approval
```

---

## ✅ Sync Points

| Date | Event | Blocker |
|------|-------|---------|
| Today | B+C kickoff | None (parallel) |
| Day 3 | B core crypto tested | For TASK D |
| Day 3 | C p95 baseline | For TASK E non-regression |
| Day 4 | B+C code review | For merge |
| Day 5 | TASK D starts (D depends on B+C) | B+C must be complete |

---

## 📞 Support & Escalation

### TASK B Issues

| Issue | Escalation |
|-------|-----------|
| AAD binding not working | Security review |
| Throughput < 5k ops/sec | Crypto team profile |
| Test failures | Review implementation |
| Key management questions | Security lead |

### TASK C Issues

| Issue | Escalation |
|-------|-----------|
| GPU unavailable | Infrastructure |
| Model download fails | ML Ops |
| p95 > 150ms | Profile GPU, adjust batch |
| OOM errors | Increase vRAM or batch down |

---

## 🎯 Success Criteria (Both Teams)

✅ **Merged when**:
- All tests passing (80+ LOC tests)
- Performance targets met
- Code reviewed
- `security-approved` or `perf-approved` label applied
- Ready for TASK D integration

❌ **Do NOT merge if**:
- Tests failing
- Performance targets missed
- AAD binding not enforced (TASK B)
- Circuit breaker not working (TASK C)
- No repo-guardian approval

---

## 📋 Checklist for Team Leads

**TASK B Lead**:
- [ ] Spec read and understood
- [ ] Team assigned
- [ ] Development environment ready
- [ ] Dependencies installed (cryptography, pytest)
- [ ] Day 1 checkpoint: seal/open_sealed working
- [ ] Day 2 checkpoint: tests passing
- [ ] Day 3 checkpoint: write path integrated
- [ ] Day 4: Code review + approval

**TASK C Lead**:
- [ ] Spec read and understood
- [ ] Team assigned
- [ ] GPU provisioned and tested
- [ ] Model cached locally
- [ ] Day 0 checkpoint: GPU available
- [ ] Day 1 checkpoint: rerank service working
- [ ] Day 2 checkpoint: p95 < 150ms baseline
- [ ] Day 3: Code review + approval

---

**Status**: 🟢 **GO FOR TODAY**
**Next**: Start implementation, sync at daily standup
**Gate**: Merge when all tests pass + repo-guardian approval
