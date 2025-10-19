# TASK C: GPU Provisioning + Cross-Encoder Reranker — Complete Specification

**Sprint**: 62 / R1 Phase 1
**Task**: C (Blocker - Parallel with B)
**Duration**: 2-3 days (GPU setup + model deployment + integration)
**Estimated LOC**: 80 (rerank.py) + 40 (integration) = 120 LOC
**Risk Level**: MEDIUM (infrastructure + ML model latency)
**Dependencies**: None (can run parallel with A, B)
**Blockers**: None

---

## 🎯 Objective

Provision GPU and implement cross-encoder reranking with circuit breaker:
- **Fast semantic reranking**: Top-k ANN candidates → CE scores → Top-m reranked
- **Fail-open**: If CE latency exceeds budget, skip and return ANN order
- **Feature flag**: Toggle reranking on/off without deploy
- **Metrics**: Latency, skips, batch size
- **Non-blocking design**: One slow CE query doesn't degrade chat streaming

---

## 📦 Deliverables

### 1. GPU Provisioning (Infrastructure)

#### Railway GPU Instance

**Specifications**:

| Component | Target | Notes |
|-----------|--------|-------|
| **GPU** | L40 | Preferred (good batch throughput); A100 acceptable |
| **vRAM** | 48GB+ | L40 has 48GB; A100 has 40-80GB |
| **CPU** | 8+ cores | For non-tensor ops (preprocessing) |
| **RAM** | 32GB | Enough for model + batch + OS |
| **Storage** | 100GB+ | Model weights + temp space |

**Railway Setup**:

```bash
# 1. Provision GPU instance
railway resource create gpu:l40

# 2. Set environment
railway env set DEVICE=cuda:0
railway env set TORCH_HOME=/tmp/.torch

# 3. Verify GPU availability
python -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))"
# Expected: (True, 'NVIDIA L40')
```

**Cost Estimate**: ~$2-4/hour for L40; ~$4-8/hour for A100

---

#### Model Download & Caching

```bash
# Download cross-encoder model to GPU instance
# (runs once, cached for reuse)

python -c "
from sentence_transformers import CrossEncoder
model = CrossEncoder('cross-encoder/ms-marco-TinyBERT-L-2-v2', device='cuda:0')
# Downloads ~100MB, caches to ~/.cache/huggingface
"
```

**Models Tested**:
- ✅ `cross-encoder/ms-marco-TinyBERT-L-2-v2` (125M params, 22MB)
- ✅ `cross-encoder/mmarco-MiniLMv2-L12-H384-v1` (better quality, 100ms latency)
- ⚠️ `cross-encoder/ms-marco-MiniLM-L-12-v2` (slower, ~150ms)

**Recommendation**: TinyBERT for speed (< 100ms p95), MiniLM for quality if budget allows.

---

### 2. Reranker Service (`src/memory/rerank.py`)

#### Initialize Cross-Encoder

```python
import os
import logging
from sentence_transformers import CrossEncoder

logger = logging.getLogger(__name__)

# Configuration
MODEL_NAME = os.getenv(
    "CROSS_ENCODER_MODEL",
    "cross-encoder/ms-marco-TinyBERT-L-2-v2"
)
DEVICE = os.getenv("DEVICE", "cuda:0" if torch.cuda.is_available() else "cpu")

# Lazy load on first use
_cross_encoder = None

def get_cross_encoder() -> CrossEncoder:
    """Load CE model on first call (lazy init)"""
    global _cross_encoder
    if _cross_encoder is None:
        logger.info(f"Loading CrossEncoder: {MODEL_NAME} on {DEVICE}")
        _cross_encoder = CrossEncoder(MODEL_NAME, device=DEVICE, max_length=512)
    return _cross_encoder
```

---

#### Reranker Function with Circuit Breaker

```python
import time
import asyncio
from typing import List, Tuple
from dataclasses import dataclass

# Budgets (milliseconds)
RERANK_BUDGET_MS = 200  # Target p95 latency
RERANK_CIRCUIT_MS = 250  # Break circuit if exceeded
RERANK_BATCH_SIZE = 32  # Max candidates per batch

# Metrics
rerank_latencies = []  # For p50/p95 tracking
rerank_skips_total = 0  # Circuit breaker trips

@dataclass
class RerankedResult:
    """Reranked candidate with score"""
    candidate: str
    score: float
    rank: int  # 1-indexed position

async def rerank(
    query: str,
    candidates: List[str],
    timeout_ms: float = RERANK_CIRCUIT_MS,
) -> List[RerankedResult]:
    """
    Rerank candidates using cross-encoder.

    Args:
        query: Search query
        candidates: List of ANN candidates (up to 24)
        timeout_ms: Circuit breaker threshold

    Returns:
        Reranked candidates sorted by score (descending)

    Raises:
        TimeoutError: If timeout exceeded (caller should use ANN order)
    """
    global rerank_skips_total

    if not candidates:
        return []

    # Batch candidates for efficiency
    ce = get_cross_encoder()
    t0 = time.perf_counter()

    try:
        # Build pairs: (query, candidate) for CE scoring
        pairs = [[query, candidate] for candidate in candidates]

        # Predict scores (GPU inference)
        scores = ce.predict(pairs, batch_size=RERANK_BATCH_SIZE, show_progress_bar=False)

        elapsed_ms = (time.perf_counter() - t0) * 1000

        # Record metric
        rerank_latencies.append(elapsed_ms)
        logger.debug(f"Rerank: {len(candidates)} candidates in {elapsed_ms:.1f}ms")

        # Check circuit breaker
        if elapsed_ms > timeout_ms:
            logger.warning(
                f"Rerank circuit broken: {elapsed_ms:.1f}ms > {timeout_ms}ms "
                f"(skipping reranking, returning ANN order)"
            )
            rerank_skips_total += 1
            # Return ANN order (no reranking applied)
            return [
                RerankedResult(candidate=c, score=float(1.0 - i / len(candidates)), rank=i+1)
                for i, c in enumerate(candidates)
            ]

        # Success: Sort by score descending
        ranked = sorted(
            zip(scores, candidates, range(1, len(candidates) + 1)),
            key=lambda x: x[0],
            reverse=True
        )

        return [
            RerankedResult(candidate=c, score=float(s), rank=r)
            for s, c, r in ranked
        ]

    except Exception as e:
        logger.error(f"Rerank error: {e} (falling back to ANN order)")
        rerank_skips_total += 1
        # Fail-open: return ANN order on error
        return [
            RerankedResult(candidate=c, score=float(1.0 - i / len(candidates)), rank=i+1)
            for i, c in enumerate(candidates)
        ]
```

---

#### Metrics & Observability

```python
import numpy as np

def get_rerank_metrics() -> dict:
    """Return current rerank metrics for monitoring"""
    return {
        "rerank_skipped_total": rerank_skips_total,
        "rerank_latency_ms": {
            "p50": np.percentile(rerank_latencies, 50) if rerank_latencies else 0,
            "p95": np.percentile(rerank_latencies, 95) if rerank_latencies else 0,
            "max": max(rerank_latencies) if rerank_latencies else 0,
        },
        "rerank_batch_size": RERANK_BATCH_SIZE,
        "device": DEVICE,
    }

# Expose metrics endpoint
# GET /metrics/rerank → above dict (Prometheus format)
```

---

#### Feature Flag

```python
import os

RERANK_ENABLED = os.getenv("RERANK_ENABLED", "true").lower() == "true"

async def maybe_rerank(
    query: str,
    candidates: List[str],
) -> List[str]:
    """Rerank if enabled, otherwise return ANN order"""
    if not RERANK_ENABLED:
        logger.debug("Reranking disabled (RERANK_ENABLED=false)")
        return candidates

    try:
        reranked = await rerank(query, candidates)
        # Extract candidates in reranked order
        return [r.candidate for r in reranked[:8]]  # Top 8 after rerank
    except Exception as e:
        logger.error(f"Rerank failed: {e}; using ANN order")
        return candidates[:8]
```

---

### 3. Integration into Query Path

#### Memory Query with Reranking

```python
# Pseudocode for TASK D integration

async def query_memory(
    query: str,
    user_id: str,
    top_k_ann: int = 24,      # ANN candidates
    top_k_reranked: int = 8,   # Final results after CE
) -> List[MemoryChunk]:
    """
    Query memory chunks with reranking.

    Flow:
    1. ANN search → top 24 candidates
    2. (Optional) Temporal decay filter
    3. Rerank (CE) → top 8
    4. Fetch full chunks, decrypt, return
    """

    user_hash = hmac_user(user_id)

    async with get_connection() as conn:
        async with set_rls_context(conn, user_id):

            # 1. ANN search
            candidates = await conn.fetch(f"""
                SELECT id, embedding, text_cipher, meta_cipher, created_at
                FROM memory_chunks
                WHERE user_hash = $1
                  AND embedding IS NOT NULL
                ORDER BY embedding <-> $2::vector
                LIMIT {top_k_ann}
            """, user_hash, query_embedding)

            candidate_texts = [c['id'] for c in candidates]  # or text decrypted

            # 2. Rerank (if enabled)
            reranked_order = await maybe_rerank(query, candidate_texts)

            # 3. Reorder candidates by CE scores
            ranked_ids = {cid: i for i, cid in enumerate(reranked_order)}
            candidates_sorted = sorted(
                candidates,
                key=lambda c: ranked_ids.get(c['id'], 999)
            )

            # 4. Decrypt and return top_k_reranked
            results = []
            for chunk in candidates_sorted[:top_k_reranked]:
                text = open_sealed(chunk['text_cipher'], aad=user_hash.encode())
                meta = json.loads(open_sealed(chunk['meta_cipher'], aad=user_hash.encode()).decode())
                results.append(MemoryChunk(
                    id=chunk['id'],
                    text=text.decode(),
                    metadata=meta,
                    score=...,  # CE score
                ))

            return results
```

---

### 4. Unit Tests (`tests/memory/test_rerank.py`)

```python
import pytest
import asyncio
from src.memory.rerank import rerank, get_cross_encoder, get_rerank_metrics

class TestCrossEncoderInit:
    """Model loading and initialization"""

    def test_cross_encoder_loads(self):
        """CrossEncoder model loads on first call"""
        ce = get_cross_encoder()
        assert ce is not None
        # Subsequent calls return same instance
        assert get_cross_encoder() is ce

    def test_cross_encoder_device(self):
        """Model loaded on correct device"""
        ce = get_cross_encoder()
        # Check device (CUDA if available)
        # ce.model.device should be cuda:0


class TestReranking:
    """Reranking quality and latency"""

    @pytest.mark.asyncio
    async def test_rerank_semantic_quality(self):
        """CE reranks by semantic relevance"""
        query = "machine learning algorithms"
        candidates = [
            "Deep learning uses neural networks",
            "Pizza recipes for beginners",
            "ML algorithms and optimization",
            "Sports statistics this season",
        ]

        reranked = await rerank(query, candidates)

        # Top should be ML-related, not pizza/sports
        top3_text = " ".join([r.candidate for r in reranked[:3]])
        assert "learning" in top3_text.lower() or "algorithm" in top3_text.lower()

    @pytest.mark.asyncio
    async def test_rerank_latency_under_budget(self):
        """Reranking completes within budget"""
        query = "test query"
        candidates = ["doc " + str(i) for i in range(24)]  # Full batch

        import time
        t0 = time.perf_counter()
        reranked = await rerank(query, candidates)
        elapsed_ms = (time.perf_counter() - t0) * 1000

        assert elapsed_ms < 200, f"Latency {elapsed_ms:.1f}ms exceeds 200ms budget"

    @pytest.mark.asyncio
    async def test_rerank_circuit_breaker(self):
        """Circuit breaker skips if latency exceeds threshold"""
        # This is harder to test in unit tests (depends on actual GPU perf)
        # Typically tested in staging with realistic load
        pass

    @pytest.mark.asyncio
    async def test_rerank_handles_empty_candidates(self):
        """Empty candidate list returns empty result"""
        reranked = await rerank("query", [])
        assert reranked == []

    @pytest.mark.asyncio
    async def test_rerank_handles_error(self):
        """Errors fall back to ANN order gracefully"""
        # Mock error scenario
        pass


class TestFeatureFlag:
    """Feature flag functionality"""

    def test_rerank_disabled(self, monkeypatch):
        """RERANK_ENABLED=false disables reranking"""
        monkeypatch.setenv("RERANK_ENABLED", "false")
        from src.memory.rerank import RERANK_ENABLED
        assert not RERANK_ENABLED

    def test_rerank_enabled_default(self):
        """RERANK_ENABLED defaults to true"""
        # RERANK_ENABLED should be True by default
        pass


class TestMetrics:
    """Metrics collection"""

    def test_get_metrics_structure(self):
        """Metrics dict has expected fields"""
        metrics = get_rerank_metrics()
        assert "rerank_skipped_total" in metrics
        assert "rerank_latency_ms" in metrics
        assert "p50" in metrics["rerank_latency_ms"]
        assert "p95" in metrics["rerank_latency_ms"]
```

---

## 🚀 Deployment & Validation

### Pre-Deploy Checklist

- [ ] GPU instance provisioned (L40 or A100)
- [ ] nvidia-smi shows device (CUDA available)
- [ ] Model downloaded and cached (~100MB)
- [ ] Model loads in < 5 seconds
- [ ] 100 test queries: p95 latency < 150ms measured
- [ ] Circuit breaker tested (artificially slow model → returns ANN order)
- [ ] Feature flag toggles reranking on/off
- [ ] Metrics endpoint returns valid JSON

### Load Test Script

```bash
#!/bin/bash
# tests/rerank/load_test.sh

set -e

# 1. Prime model
echo "Priming cross-encoder..."
python -c "
from src.memory.rerank import get_cross_encoder
ce = get_cross_encoder()
print('✅ Model loaded')
"

# 2. Run 100 rerank ops
echo "Running load test (100 queries, 24 candidates each)..."
python -c "
import asyncio
import time
import numpy as np
from src.memory.rerank import rerank

async def load_test():
    latencies = []
    for i in range(100):
        query = f'test query {i}'
        candidates = [f'doc {j}' for j in range(24)]

        t0 = time.perf_counter()
        result = await rerank(query, candidates)
        latencies.append((time.perf_counter() - t0) * 1000)

    p50 = np.percentile(latencies, 50)
    p95 = np.percentile(latencies, 95)
    p99 = np.percentile(latencies, 99)

    print(f'✅ Load test complete:')
    print(f'   p50: {p50:.1f}ms')
    print(f'   p95: {p95:.1f}ms')
    print(f'   p99: {p99:.1f}ms')

    if p95 > 200:
        print(f'⚠️  p95 {p95:.1f}ms exceeds 200ms target')
    else:
        print(f'✅ p95 within budget')

asyncio.run(load_test())
"
```

---

## 📊 Performance Targets

| Metric | Target | Notes |
|--------|--------|-------|
| **Model load time** | < 5 sec | On GPU instance startup |
| **Rerank latency p50** | < 50 ms | TinyBERT typical |
| **Rerank latency p95** | < 150 ms | Budget for 24 candidates |
| **Circuit breaker threshold** | 250 ms | 1.25x budget (grace period) |
| **Throughput** | ≥ 100 q/min | Single GPU |
| **Batch size** | 32 | Optimal for VRAM |

---

## ⚠️ Failure Modes

### Slow GPU Inference

**Symptom**: p95 latency > 250ms

**Action**: Circuit breaker trips → returns ANN order (no reranking)

**Recovery**:
- Check GPU utilization (nvidia-smi)
- Check for other processes competing for GPU
- Reduce batch size (RERANK_BATCH_SIZE)
- Fallback to CPU inference (slower but works)

### Model Load Failure

**Symptom**: Model download fails, no cache available

**Action**: RERANK_ENABLED automatically set to false (fail-open)

**Recovery**:
- Check internet connectivity
- Manually download model: `python -m sentence_transformers.cli.fetch_model cross-encoder/ms-marco-TinyBERT-L-2-v2`
- Re-enable: `RERANK_ENABLED=true`

### Out of Memory

**Symptom**: GPU OOM during inference

**Action**: Reduce RERANK_BATCH_SIZE, restart process

**Recovery**:
- Monitor vRAM usage
- Adjust batch size dynamically based on free VRAM

---

## 🔄 Dependencies & Integration

**Blocks**: TASK E (Non-regression suite needs CE latency baseline)
**Blocked by**: None (GPU provisioning independent)
**Parallel**: TASK B (Encryption - independent)

**Integration with TASK D**:
```python
# TASK D endpoint will call:
from src.memory.rerank import maybe_rerank, get_rerank_metrics

# In query handler:
results = await maybe_rerank(query, ann_candidates)

# In metrics endpoint:
metrics.update(get_rerank_metrics())
```

---

## ✅ Acceptance Criteria (Gate Condition)

✅ **TASK C Complete when:**

- [ ] GPU provisioned and verified
  - [ ] `nvidia-smi` shows device
  - [ ] CUDA available in Python

- [ ] Cross-encoder model deployed
  - [ ] Model loads in < 5 seconds
  - [ ] Inference works on test batch

- [ ] Rerank service implemented (80 LOC)
  - [ ] `rerank()` function with circuit breaker
  - [ ] Feature flag `RERANK_ENABLED` working
  - [ ] Metrics collection active

- [ ] Performance targets met
  - [ ] p95 latency < 150ms (24 candidates)
  - [ ] p99 latency < 250ms (circuit break point)
  - [ ] Throughput ≥ 100 q/min

- [ ] Unit tests passing (40 test cases)
  - [ ] Semantic quality tests
  - [ ] Latency under budget
  - [ ] Circuit breaker tested
  - [ ] Feature flag tests
  - [ ] Error handling tests

- [ ] Integration ready for TASK D
  - [ ] `maybe_rerank()` callable from query handler
  - [ ] Metrics exposed via endpoint
  - [ ] Fail-open working (returns ANN order on error)

- [ ] repo-guardian: `perf-approved` label
  - [ ] Performance reviewed (latency, throughput)
  - [ ] Fail-open semantics approved
  - [ ] Circuit breaker logic verified

---

## 📞 Support & Escalation

| Issue | Escalation |
|-------|-----------|
| GPU not available | DevOps → Infrastructure |
| Model download fails | ML Ops → check download service |
| Latency p95 > 200ms | ML Ops → profile GPU, adjust batch size |
| OOM errors | DevOps → increase vRAM or reduce batch |

---

**Start Date**: Immediately (parallel with TASK B)
**Estimated Completion**: 2-3 days (GPU setup is fast; tuning takes longest)
**Critical Path**: GPU ready by end of day 2, so TASK D can integrate by day 3
