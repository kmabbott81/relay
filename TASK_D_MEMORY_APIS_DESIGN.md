# Task D: Memory APIs Implementation Design
**Sprint**: R1 Phase 1
**Date**: 2025-10-20
**Authority**: Lead Architect
**Dependencies**: TASK B (Encryption), TASK C (Reranker), TASK A (Schema + RLS)

---

## Overview

Implement four memory endpoints with full encryption (AES-256-GCM with AAD), row-level security, and the reranker circuit breaker pattern. All endpoints are authenticated via JWT Bearer tokens and enforce user_hash RLS isolation.

---

## Endpoints Specification

### 1. POST /api/v1/memory/index
**Purpose**: Insert or upsert memory chunks with semantic embeddings

**Request**:
```json
{
  "user_hash": "hmac_sha256(user_id)",
  "doc_id": "doc_123",
  "source": "chat",
  "text": "Long chunk of text to embed",
  "metadata": {
    "title": "Chat History",
    "timestamp": "2025-10-20T12:00:00Z",
    "custom_field": "value"
  },
  "tags": ["important", "recent"]
}
```

**Response**:
```json
{
  "id": "mem_uuid",
  "created_at": "2025-10-20T12:00:00Z",
  "indexed_at": "2025-10-20T12:00:01Z",
  "chunk_index": 0,
  "status": "indexed"
}
```

**Security**:
- ✅ Validate `user_hash` matches JWT principal (fail-closed if mismatch)
- ✅ Set RLS context: `SET app.user_hash = <user_hash>`
- ✅ Encrypt `text` with AES-256-GCM(AAD=user_hash): store as `text_cipher`
- ✅ Encrypt `metadata` as JSON with AES-256-GCM(AAD=user_hash): store as `meta_cipher`
- ✅ Generate embedding via API (OpenAI/Cohere) and store plaintext for ANN search
- ✅ Encrypt embedding with AES-256-GCM(AAD=user_hash): store as `emb_cipher` (shadow backup)

**Performance**:
- **Target p95**: ≤ 750ms
- **Budget breakdown**:
  - Text/metadata encryption: 20ms
  - Embedding generation (API): 600ms
  - Database insert + RLS enforcement: 50ms
  - Network latency: 80ms

**Metrics emitted**:
```
memory_index_latency_ms{user_hash=<prefix>, status=success/fail}
memory_index_bytes{direction=in}  # Size of text + metadata
memory_encryption_latency_ms{algorithm=aes256gcm_aad}
```

---

### 2. POST /api/v1/memory/query
**Purpose**: Semantic search with reranker circuit breaker and relevance ranking

**Request**:
```json
{
  "user_hash": "hmac_sha256(user_id)",
  "query": "How do I reset my password?",
  "limit": 10,
  "filters": {
    "source": ["chat", "email"],
    "tags": ["important"],
    "date_range": {
      "from": "2025-10-01",
      "to": "2025-10-20"
    }
  }
}
```

**Response**:
```json
{
  "results": [
    {
      "id": "mem_uuid_1",
      "chunk_index": 0,
      "text": "Password reset instructions...",
      "metadata": {
        "title": "Support Article",
        "source": "chat"
      },
      "score": 0.92,
      "rank": 1,
      "reranked": true,
      "original_rank": 3
    },
    {
      "id": "mem_uuid_2",
      "chunk_index": 1,
      "text": "Account recovery...",
      "score": 0.85,
      "rank": 2,
      "reranked": true,
      "original_rank": 1
    }
  ],
  "count": 2,
  "total_available": 23,
  "latency_breakdown": {
    "embedding_ms": 120,
    "ann_search_ms": 45,
    "reranking_ms": 89,
    "decryption_ms": 15,
    "total_ms": 269
  }
}
```

**Security**:
- ✅ Validate `user_hash` matches JWT principal
- ✅ Set RLS context for query
- ✅ ANN search with RLS filter: `WHERE user_hash = $1 AND embedding <-> $2 LIMIT 32`
- ✅ Decrypt results: AES-256-GCM with AAD validation (fail-closed if AAD mismatch)
- ✅ Rerank top-k (24-32) candidates via circuit breaker (>250ms → return ANN order)

**Performance**:
- **Target p95**: ≤ 350ms
- **Budget breakdown**:
  - Query embedding: 120ms
  - ANN search (HNSW index): 45ms
  - Top-32 decryption: 15ms
  - Reranking (CE): 89ms (150ms timeout with circuit breaker)
  - JSON serialization: 10ms

**Reranker Circuit Breaker**:
- Timeout: 250ms (if exceeded, skip CE and return ANN order)
- Fail-open: On any error, return ANN order (preserves TTFV budget)
- Logging: Emit `memory_rerank_timeout` metric when circuit opens

**Metrics emitted**:
```
memory_query_latency_ms{user_hash=<prefix>, status=success/fail}
memory_query_embedding_ms
memory_query_ann_results{limit=<k>}
memory_query_decryption_ms
memory_rerank_latency_ms{reranker_status=success/timeout/error}
memory_rerank_circuit_breaker{state=open/closed}
```

---

### 3. POST /api/v1/memory/summarize
**Purpose**: Compress a set of memory chunks into a structured summary

**Request**:
```json
{
  "user_hash": "hmac_sha256(user_id)",
  "memory_ids": ["mem_uuid_1", "mem_uuid_2", "mem_uuid_3"],
  "style": "bullet_points",
  "max_tokens": 500
}
```

**Response**:
```json
{
  "summary": "- Key point 1\n- Key point 2\n- Key point 3",
  "entities": [
    {"name": "Alice", "type": "person", "frequency": 5},
    {"name": "Product X", "type": "product", "frequency": 3}
  ],
  "key_decisions": [
    "Decided to migrate to cloud",
    "Chose provider Y over Z"
  ],
  "tokens_used": 237,
  "processing_time_ms": 892,
  "model_used": "gpt-4o-mini"
}
```

**Security**:
- ✅ Validate `user_hash` matches JWT principal
- ✅ Set RLS context for queries
- ✅ Decrypt each memory_id with AAD validation
- ✅ Verify all chunks belong to requesting user (RLS + AAD double-check)
- ✅ Summarization prompt includes user_hash in system context (prevent prompt injection)

**Performance**:
- **Target p95**: ≤ 1000ms
- **Budget breakdown**:
  - Fetch chunks from DB (RLS): 50ms
  - Decrypt N chunks: 100ms
  - API call to summarization model: 750ms
  - JSON parsing: 20ms
  - Response serialization: 10ms

**Metrics emitted**:
```
memory_summarize_latency_ms{user_hash=<prefix>, chunk_count=<N>}
memory_summarize_tokens{direction=in/out}
memory_summarize_api_latency_ms{model=gpt-4o-mini}
```

---

### 4. POST /api/v1/memory/entities
**Purpose**: Extract and rank named entities from memory chunks

**Request**:
```json
{
  "user_hash": "hmac_sha256(user_id)",
  "memory_ids": ["mem_uuid_1", "mem_uuid_2"],
  "entity_types": ["person", "organization", "location", "product"],
  "min_frequency": 1
}
```

**Response**:
```json
{
  "entities": [
    {
      "name": "Alice",
      "type": "person",
      "frequency": 7,
      "contexts": [
        "Alice is a software engineer",
        "Alice prefers remote work"
      ],
      "confidence": 0.98
    },
    {
      "name": "TechCorp",
      "type": "organization",
      "frequency": 4,
      "contexts": [
        "TechCorp is hiring",
        "Joined TechCorp in 2023"
      ],
      "confidence": 0.95
    }
  ],
  "extraction_time_ms": 523,
  "model_used": "ner-small"
}
```

**Security**:
- ✅ Validate `user_hash` matches JWT principal
- ✅ Set RLS context
- ✅ Decrypt chunks with AAD validation
- ✅ Entity extraction does NOT emit PII by default (configurable)

**Performance**:
- **Target p95**: ≤ 500ms
- **Budget breakdown**:
  - Fetch chunks: 50ms
  - Decrypt N chunks: 80ms
  - Entity extraction (local NER model): 300ms
  - Ranking and deduplication: 50ms
  - Serialization: 20ms

**Metrics emitted**:
```
memory_entities_latency_ms{user_hash=<prefix>, entity_count=<N>}
memory_entities_extracted{type=person|org|location|product}
```

---

## Security Architecture

### Encryption with AAD (Additional Authenticated Data)

**Enhancement to crypto/envelope.py**:

```python
def encrypt_with_aad(plaintext: bytes, aad: bytes, keyring_key: dict) -> dict:
    """
    Encrypt with AES-256-GCM + AAD binding.

    AAD = HMAC-SHA256(MEMORY_TENANT_HMAC_KEY, user_hash)
    This binds ciphertext to user_hash: decryption fails if user_hash changes.
    """
    aad_digest = hmac.new(
        MEMORY_TENANT_HMAC_KEY.encode(),
        aad,
        hashlib.sha256
    ).digest()

    # Encrypt with AAD
    aesgcm = AESGCM(key_material)
    ciphertext = aesgcm.encrypt(nonce, plaintext, aad_digest)

    return {
        "key_id": key_id,
        "nonce": base64.b64encode(nonce).decode(),
        "ciphertext": base64.b64encode(ciphertext[:-16]).decode(),
        "tag": base64.b64encode(ciphertext[-16:]).decode(),
        "aad_bound_to": aad.decode()  # For audit trail
    }

def decrypt_with_aad(envelope: dict, aad: bytes, keyring_get_fn=None) -> bytes:
    """
    Decrypt with AAD validation.

    Raises ValueError if AAD doesn't match (fail-closed).
    """
    # Recompute AAD digest
    aad_digest = hmac.new(
        MEMORY_TENANT_HMAC_KEY.encode(),
        aad,
        hashlib.sha256
    ).digest()

    # Decrypt with AAD
    aesgcm = AESGCM(key_material)
    ciphertext_with_tag = ciphertext + tag
    plaintext = aesgcm.decrypt(nonce, ciphertext_with_tag, aad_digest)

    return plaintext
```

### Row-Level Security (RLS) + AAD Defense-in-Depth

```python
# In each endpoint:
async with set_rls_context(conn, principal["user_id"]):
    # RLS policy ensures only user's rows are visible
    # All queries have WHERE user_hash = <current>

    # Plus: AAD validation ensures ciphertext can't be moved to another user
    encrypted_text = await conn.fetchval(
        "SELECT text_cipher FROM memory_chunks WHERE id = $1",
        chunk_id
    )

    # Decrypt with AAD = user_hash
    plaintext = decrypt_with_aad(
        encrypted_text,
        aad=principal["user_hash"].encode(),
        keyring_get_fn=get_key
    )
    # If user_hash doesn't match AAD, decrypt fails immediately
```

---

## Integration with TASK B & C

### TASK B (Encryption Helpers)
- ✅ Use existing crypto/envelope.py for base encryption
- ✅ **Enhance with AAD support**: Add `encrypt_with_aad()` and `decrypt_with_aad()`
- ✅ Test AAD validation failure scenarios

### TASK C (Reranker)
- ✅ Import `maybe_rerank()` from memory/rerank.py
- ✅ Call in `/memory/query` with 250ms timeout
- ✅ On timeout: circuit breaker returns ANN order (fail-open)
- ✅ Emit metrics for rerank latency and circuit breaker state

### TASK A (Schema + RLS)
- ✅ memory_chunks table already created with RLS policies
- ✅ Use existing `hmac_user()` and `set_rls_context()` from memory/rls.py
- ✅ Verify RLS + AAD combination prevents cross-user access

---

## Implementation Phases

### Phase 1: Encryption Enhancement (1-2 hours)
1. Add AAD support to crypto/envelope.py
2. Add tests for AAD validation failures
3. Verify backward compatibility with non-AAD envelopes

### Phase 2: Endpoint Scaffolding (2-3 hours)
1. Create src/memory/api.py with FastAPI router
2. Add endpoints to webapi.py
3. Add JWT authentication and RLS context injection
4. Implement error handling (401, 403, 422, 500)

### Phase 3: Core Implementation (8-10 hours)
1. `/memory/index`: encryption, embedding generation, database insert
2. `/memory/query`: ANN search, reranking, result decryption
3. `/memory/summarize`: batch fetch, summarization API call
4. `/memory/entities`: NER extraction, entity ranking

### Phase 4: Metrics & Observability (2-3 hours)
1. Emit latency metrics for each endpoint
2. Add p95 tracking for guardrail compliance
3. Add rate limit headers to responses
4. Add structured logs for debugging

### Phase 5: Testing & Performance Tuning (3-4 hours)
1. Unit tests for each endpoint
2. Integration tests with mock LLM APIs
3. Load testing for p95 latency validation
4. RLS isolation verification tests

---

## Database Queries

### Index endpoint:
```sql
INSERT INTO memory_chunks (
    user_hash, doc_id, source, text_cipher, meta_cipher,
    embedding, emb_cipher, chunk_index, tags, model
)
VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
RETURNING id, created_at;
-- RLS enforces: user_hash = current_setting('app.user_hash')
```

### Query endpoint:
```sql
SELECT id, text_cipher, meta_cipher, embedding, chunk_index
FROM memory_chunks
WHERE user_hash = current_setting('app.user_hash')
ORDER BY embedding <-> $1::vector
LIMIT 32;
-- HNSW index accelerates distance computation
-- RLS policy filters rows before indexing
```

### Summarize/Entities endpoints:
```sql
SELECT id, text_cipher, meta_cipher
FROM memory_chunks
WHERE id = ANY($1::uuid[])
  AND user_hash = current_setting('app.user_hash');
-- RLS ensures only user's chunks are returned
-- Fail if any chunk_id doesn't belong to user
```

---

## Guardrails & Observability

### Performance Guardrails
| Endpoint | p95 Target | Timeout | Fail-Close |
|----------|-----------|---------|-----------|
| /memory/index | 750ms | 2s | Return 503 |
| /memory/query | 350ms | 1s | Return empty results |
| /memory/summarize | 1000ms | 2s | Return 503 |
| /memory/entities | 500ms | 1s | Return empty entities |

### Security Guardrails
- ✅ All endpoints validate JWT + user_hash
- ✅ All endpoints enforce RLS context
- ✅ All endpoints validate AAD on decryption (fail-closed)
- ✅ All endpoints log security events (RLS violations, AAD failures)

### Metrics Emitted
```
memory_index_latency_ms{status=success/fail}
memory_query_latency_ms{status=success/fail}
memory_query_rerank_circuit_breaker{state=open/closed}
memory_summarize_latency_ms{chunk_count=<N>}
memory_entities_latency_ms{entity_count=<N>}
memory_decryption_failures_total{reason=aad_mismatch/key_not_found}
memory_rls_violations_total
```

---

## Error Handling

| Status | Scenario | Response |
|--------|----------|----------|
| 401 | Missing JWT | `{"detail": "Missing Authorization header"}` |
| 403 | user_hash mismatch | `{"detail": "Permission denied"}` |
| 403 | AAD validation failed | `{"detail": "Permission denied"}` (no PII) |
| 404 | Chunk not found or RLS violation | `{"detail": "Not found"}` |
| 422 | Invalid request body | `{"detail": "Invalid request"}` |
| 429 | Rate limit exceeded | `{"detail": "Too many requests"}` with Retry-After header |
| 503 | Timeout on external API | `{"detail": "Service temporarily unavailable"}` |
| 500 | Database error | `{"detail": "Internal server error"}` with request_id |

---

## Success Criteria

### Functional
- ✅ All four endpoints implemented and tested
- ✅ AES-256-GCM encryption with AAD support
- ✅ RLS + AAD defense-in-depth verified
- ✅ Reranker circuit breaker active with 250ms timeout
- ✅ All responses include latency metadata

### Performance
- ✅ /memory/index p95 ≤ 750ms (without external API variance)
- ✅ /memory/query p95 ≤ 350ms (with reranking)
- ✅ /memory/summarize p95 ≤ 1000ms
- ✅ /memory/entities p95 ≤ 500ms
- ✅ TTFV preserved ≤ 1.5s on production canary

### Security
- ✅ Zero RLS violations in tests
- ✅ Zero AAD validation bypasses
- ✅ All PII encrypted in transit and at rest
- ✅ Audit log entries for all access patterns

### Observability
- ✅ All metrics emitted and queryable in Prometheus
- ✅ Rate limit headers present in all responses
- ✅ Structured logs for debugging and audit

---

## Timeline

| Phase | Duration | Completion |
|-------|----------|-----------|
| Encryption Enhancement | 1-2h | T+2h |
| Endpoint Scaffolding | 2-3h | T+5h |
| Core Implementation | 8-10h | T+15h |
| Metrics & Observability | 2-3h | T+18h |
| Testing & Tuning | 3-4h | T+21h |
| **Total** | **16-23h** | **T+21h** |

**Parallel work** (P2, P1): Can proceed independently

---

**Status**: ✅ **DESIGN COMPLETE** → Ready for Phase 1 (Encryption Enhancement)
