# TASK B & C Parallel Execution Kickoff Directive

**Date**: 2025-10-19
**Status**: 🟢 **AUTHORIZED TO EXECUTE**
**Authority**: R1 Phase 1 Production Deployment Complete

---

## Executive Authorization

**TASK A has been successfully deployed to production** with full RLS enforcement verified.

**Immediate Authorization**: TASK B and TASK C teams are **CLEARED TO EXECUTE IMMEDIATELY** in parallel with 3-4 day and 2-3 day timelines respectively.

---

## TASK B - Encryption Helpers (Crypto Team)

### Authorization Details

**Status**: 🟢 **GO - START TODAY**
**Timeline**: 3-4 days (complete by Day 4)
**Team**: Security Lead + 1-2 crypto engineers
**Dependency**: None (can start in parallel with TASK A production monitoring)

### Deliverables (Locked Specification)

#### 1. Core Module: `src/memory/security.py` (120 LOC)

Three required functions:

```python
def hmac_user(user_id: str) -> str:
    """Deterministic HMAC-SHA256(MEMORY_TENANT_HMAC_KEY, user_id)

    Returns 64-character hex string for RLS policy matching.
    Used to compute user_hash for tenant isolation at encryption layer.
    """
    pass

def seal(plaintext: bytes, aad: bytes = b"") -> bytes:
    """AES-256-GCM encryption with AAD binding

    Format: nonce (12 bytes) || ciphertext || auth_tag (16 bytes)
    AAD (Additional Authenticated Data) = user_hash

    Prevents: Cross-tenant decryption (if user B tries to decrypt user A's blob
             with wrong AAD, InvalidTag is raised)
    """
    pass

def open_sealed(blob: bytes, aad: bytes = b"") -> bytes:
    """AES-256-GCM decryption

    Raises: InvalidTag if AAD mismatch or tampering detected
    Fail-closed: No plaintext fallback, always raises on failure
    """
    pass
```

#### 2. Unit Tests: `tests/memory/test_encryption.py` (80+ LOC)

**Test Classes Required:**

```python
class TestSealRoundTrip:
    """Verify basic encrypt/decrypt functionality"""
    # 5+ test cases

class TestAADBinding:
    """CRITICAL: Verify cross-tenant prevention"""
    # Must include: test_seal_aad_binding()
    # Requirement: seal(..., aad=b"user_a") + open_sealed(..., aad=b"user_b")
    #            MUST raise InvalidTag

class TestTamperDetection:
    """Verify corruption detection"""
    # 3+ test cases: bit flip, nonce corruption, tag corruption

class TestThroughput:
    """Performance: >= 5k ops/sec"""
    # Must measure latency: p50, p95, p99
    # Requirement: p99 < 1ms

class TestIntegration:
    """Write path integration with RLS"""
    # 2-3 test cases
```

**CRITICAL TEST (Must Pass):**
```python
def test_aad_binding_prevents_cross_tenant_decryption():
    """This is the SECURITY GATE. Do not proceed without this passing."""
    plaintext = b"sensitive data"

    # User A encrypts with their hash
    user_a_hash = b"user_a_hash_aaaa"
    ciphertext = seal(plaintext, aad=user_a_hash)

    # User B CANNOT decrypt with wrong hash
    user_b_hash = b"user_b_hash_bbbb"
    with pytest.raises(InvalidTag):
        open_sealed(ciphertext, aad=user_b_hash)  # MUST FAIL
```

#### 3. Write Path Integration

**Location**: `index_memory_chunk()` function

**Flow**:
```python
async def index_memory_chunk(conn, user_id, doc_id, source, text, embedding, metadata):
    # 1. Compute user_hash = HMAC-SHA256(user_id)
    user_hash = hmac_user(user_id)

    # 2. Set RLS context for this user
    async with set_rls_context(conn, user_id):
        # 3. Encrypt text with user_hash as AAD
        text_cipher = seal(text.encode(), aad=user_hash.encode())

        # 4. Encrypt metadata with user_hash as AAD
        meta_json = json.dumps(metadata).encode()
        meta_cipher = seal(meta_json, aad=user_hash.encode())

        # 5. Encrypt embedding backup with user_hash as AAD
        emb_cipher = seal(embedding.tobytes(), aad=user_hash.encode())

        # 6. Insert into memory_chunks
        # Store: text_cipher, meta_cipher, emb_cipher (encrypted)
        # Store: embedding plaintext (for ANN indexing)
        await conn.execute("""
            INSERT INTO memory_chunks
            (user_hash, doc_id, source, text_cipher, meta_cipher,
             embedding, emb_cipher, chunk_index, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW())
        """, (user_hash, doc_id, source, text_cipher, meta_cipher,
              embedding, emb_cipher, 0))
```

### Key Management

**Environment Variables**:
```bash
MEMORY_ENCRYPTION_KEY=<32-byte base64>      # AES-256 key
MEMORY_TENANT_HMAC_KEY=<32-byte base64>     # HMAC key
```

**Generation**:
```bash
python -c "import os, base64; print(base64.b64encode(os.urandom(32)).decode())"
```

**Rotation Strategy**:
- MEMORY_ENCRYPTION_KEY: Quarterly (dual-write for gradual migration)
- MEMORY_TENANT_HMAC_KEY: Annually (requires full reindex)

### Success Criteria

✅ **Required Before Merge:**
- [ ] `seal()` and `open_sealed()` round-trip works
- [ ] AAD binding test PASSES (cross-tenant prevented)
- [ ] 1-bit corruption raises InvalidTag
- [ ] Throughput >= 5k ops/sec verified
- [ ] Write path encrypts text/meta/embedding
- [ ] All 20+ tests passing
- [ ] Coverage > 90%
- [ ] Code review completed
- [ ] `security-approved` label applied by repo-guardian

❌ **Do NOT merge if:**
- Tests failing
- Throughput < 5k ops/sec
- AAD binding NOT enforced (SECURITY FAILURE)
- Keys hardcoded or logged
- No repo-guardian approval

### Timeline (3-4 Days)

**Day 1**: Implement `seal()`, `open_sealed()`, `hmac_user()` functions
- Checkpoint: All 3 functions working, unit tests framework in place

**Day 2**: Implement full unit test suite (80+ LOC)
- Checkpoint: 20+ tests passing, AAD binding verified
- Latency measured: should easily exceed 5k ops/sec

**Day 3**: Write path integration
- Checkpoint: Integration complete, all tests still passing

**Day 4**: Code review + security approval
- Checkpoint: `security-approved` label applied, ready to merge

### Resources Provided

- `TASK_B_ENCRYPTION_SPECIFICATION.md` (Locked specification)
- `TASK_B_SECURITY_REVIEW_REPORT.md` (Security analysis)
- `TASK_B_IMPLEMENTATION_CHECKLIST.md` (Day-by-day guide)
- `TASK_B_SECURITY_QUICK_REFERENCE.md` (Quick reference)
- `src/memory/rls.py` (Reference for hmac_user already implemented)

---

## TASK C - Cross-Encoder Reranker (ML Ops Team)

### Authorization Details

**Status**: 🟢 **GO - START TODAY**
**Timeline**: 2-3 days (complete by Day 3)
**Team**: ML Ops Lead + 1 ML engineer
**Dependency**: None (can start in parallel)

### Deliverables (Locked Specification)

#### 1. GPU Infrastructure

**Provisioning**:
```bash
railway resource create gpu:l40    # L40 preferred (48GB vRAM)
# or
railway resource create gpu:a100   # A100 acceptable
```

**Verification**:
```bash
nvidia-smi                                              # Shows GPU
python -c "import torch; print(torch.cuda.is_available())"  # True
```

#### 2. Core Service: `src/memory/rerank.py` (80 LOC)

```python
async def rerank(query: str, candidates: List[str],
                 timeout_ms: float = 250) -> List[RerankedResult]:
    """Rerank candidates with circuit breaker

    If latency > timeout_ms: skip CE, return ANN order (fail-open)
    """
    pass

def get_cross_encoder() -> CrossEncoder:
    """Lazy-load CE model on first call

    Model: cross-encoder/ms-marco-TinyBERT-L-2-v2
    Loaded on DEVICE (cuda:0)
    """
    pass

async def maybe_rerank(query: str, candidates: List[str]) -> List[str]:
    """Feature-flagged reranking

    If RERANK_ENABLED=true: rerank
    If false: return ANN order (no-op)
    """
    pass
```

#### 3. Unit Tests: `tests/memory/test_rerank.py` (40 LOC)

**Test Classes**:
```python
class TestCrossEncoderInit:
    """Model loads correctly"""

class TestReranking:
    """Semantic quality + latency"""

class TestCircuitBreaker:
    """Timeout handling"""

class TestFeatureFlag:
    """RERANK_ENABLED toggle"""

class TestMetrics:
    """Latency and skip tracking"""
```

**CRITICAL TEST (Must Pass):**
```python
@pytest.mark.asyncio
async def test_rerank_latency_under_budget():
    """p95 latency < 150ms for 24 candidates (PERFORMANCE GATE)"""
    candidates = [f"doc {i}" for i in range(24)]

    # Measure 100 queries
    latencies = []
    for _ in range(100):
        start = time.time()
        await rerank(query, candidates)
        latencies.append((time.time() - start) * 1000)

    p95_latency = sorted(latencies)[95]
    assert p95_latency < 150, f"p95={p95_latency}ms exceeds budget"
```

### Performance Targets

| Metric | Target | Notes |
|--------|--------|-------|
| Model load | < 5 sec | GPU startup |
| p50 latency | < 50 ms | TinyBERT typical |
| **p95 latency** | **< 150 ms** | **CRITICAL BUDGET** |
| p99 latency | < 250 ms | Circuit breaker threshold |
| Throughput | >= 100 q/min | Single GPU |
| Batch size | 32 | Optimal for VRAM |

### Feature Flag

```bash
RERANK_ENABLED=true   # Enable reranking (default)
RERANK_ENABLED=false  # Disable (return ANN order only)
```

### Metrics Endpoint

```python
def get_rerank_metrics() -> dict:
    return {
        "rerank_skipped_total": count,      # Circuit breaker trips
        "rerank_latency_ms": {
            "p50": ...,
            "p95": ...,    # Must be < 150ms
            "max": ...
        },
        "device": "cuda:0",
    }
```

### Success Criteria

✅ **Required Before Merge:**
- [ ] GPU provisioned: `torch.cuda.is_available() == True`
- [ ] Model loads: CrossEncoder initialized
- [ ] `rerank()` scores candidates correctly
- [ ] p95 latency < 150ms (100 query test)
- [ ] Circuit breaker skips > 250ms
- [ ] `maybe_rerank()` toggles with RERANK_ENABLED
- [ ] Metrics collected and accessible
- [ ] All 40+ tests passing
- [ ] `perf-approved` label applied by repo-guardian

❌ **Do NOT merge if:**
- GPU not available (blocking)
- Model download fails
- p95 > 250ms (performance unacceptable)
- Feature flag doesn't work
- Tests failing

### Timeline (2-3 Days)

**Day 0-1**: GPU provisioning + model caching
- Checkpoint: `nvidia-smi` shows device, model downloaded

**Day 1-2**: Reranker service implementation + tests
- Checkpoint: `rerank()` working, latency measured

**Day 2-3**: Load testing + p95 verification + tuning
- Checkpoint: p95 < 150ms confirmed on 100 query load

**Day 3**: Code review + performance approval
- Checkpoint: `perf-approved` label applied, ready to merge

### Resources Provided

- `TASK_C_RERANKER_SPECIFICATION.md` (Locked specification)
- `TEAM_KICKOFF_ORDERS.md` (TASK C section with detailed steps)

---

## Execution Instructions

### For TASK B Team (Crypto)

1. **Read Documentation** (30 min)
   - `TASK_B_ENCRYPTION_SPECIFICATION.md`
   - `TASK_B_SECURITY_REVIEW_REPORT.md`
   - `TEAM_KICKOFF_ORDERS.md` (TASK B section)

2. **Setup Environment** (30 min)
   - Add `cryptography>=42.0.0` to requirements.txt
   - Create `src/memory/security.py`
   - Create `tests/memory/test_encryption.py`

3. **Day 1: Core Functions** (4-6 hours)
   - Implement `seal()`, `open_sealed()`, `hmac_user()`
   - Run basic unit tests

4. **Day 2: Full Test Suite** (6-8 hours)
   - Complete 20+ unit tests
   - Verify AAD binding (CRITICAL)
   - Measure throughput

5. **Day 3: Integration** (4-6 hours)
   - Integrate into write path
   - End-to-end testing

6. **Day 4: Review** (2-4 hours)
   - Code review
   - Request `security-approved` label
   - Merge when approved

### For TASK C Team (ML Ops)

1. **Read Documentation** (30 min)
   - `TASK_C_RERANKER_SPECIFICATION.md`
   - `TEAM_KICKOFF_ORDERS.md` (TASK C section)

2. **Day 0-1: GPU Setup** (2-4 hours)
   - Provision GPU (L40 or A100)
   - Verify: `nvidia-smi`, `torch.cuda.is_available()`
   - Download model

3. **Day 1-2: Service Implementation** (6-8 hours)
   - Implement `rerank()`, `get_cross_encoder()`, `maybe_rerank()`
   - Create unit tests
   - Measure latency

4. **Day 2-3: Load Testing** (4-6 hours)
   - Run 100-query load test
   - Verify p95 < 150ms
   - Optimize batch size if needed

5. **Day 3: Review & Approval** (2-4 hours)
   - Code review
   - Request `perf-approved` label
   - Merge when approved

---

## Parallel Execution Coordination

### Daily Standup (3 PM UTC)

Both teams join standup to report:
- **TASK B**: Checkpoint progress, blockers, PRs ready for review
- **TASK C**: Checkpoint progress, GPU status, latency measurements

### Merge Gate

**Both teams must deliver by Day 5**:
- TASK B: `security-approved` label
- TASK C: `perf-approved` label

**Day 6**: Integration into TASK D (API endpoints)

### Communication

**Slack Channel**: #r1-phase1-execution
**Escalation**: deployment-lead@company.com

---

## Critical Success Factors

### TASK B (Crypto)

**Do NOT proceed without:**
- AAD binding test PASSING (cross-tenant prevention verified)
- All 20+ tests PASSING
- Throughput >= 5k ops/sec confirmed

### TASK C (Reranker)

**Do NOT proceed without:**
- GPU verified working (`torch.cuda.is_available() == True`)
- p95 latency < 150ms (100 query test)
- All 40+ tests PASSING

---

## Production Integration (Day 6+)

Once both TASK B and TASK C teams deliver with approval labels:

**TASK D Implementation**: API endpoints for memory query/indexing
- Uses crypto functions from TASK B
- Uses reranker from TASK C
- Integrated with TASK A RLS

**Timeline**: Days 6-10

---

## Authorization Summary

✅ **TASK A**: LIVE IN PRODUCTION
✅ **TASK B**: AUTHORIZED TO START (3-4 day sprint)
✅ **TASK C**: AUTHORIZED TO START (2-3 day sprint)

**Next Gate**: Day 5 delivery with approval labels

---

## Final Notes

**This is a full authorization to execute immediately.** Both teams have locked specifications, security reviews completed, and all resources prepared.

**Expected Timeline:**
- Days 1-4: TASK B execution
- Days 1-3: TASK C execution
- Day 5: Both teams deliver
- Day 6+: TASK D integration
- Total: Days 6-10 for complete R1 Phase 1 rollout

**Status**: 🟢 **GO FOR EXECUTION**

---

**Generated**: 2025-10-19 11:50 UTC
**Authority**: R1 Phase 1 Production Deployment Complete
**Approval**: TASK A verified in production, TASK B+C authorized for parallel execution
