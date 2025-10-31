# R2 Knowledge API Design — Files & Embeddings Layer

**Date**: 2025-10-31
**Phase**: R2 Phase 1 (Design & Schema)
**Status**: Design Complete, Ready for Implementation
**Base Architecture**: Extends R1 Memory API (JWT → RLS → AAD)

---

## 1. Design Overview

### Goal
Extend Relay's knowledge infrastructure from text-only memory chunks to **multi-modal file ingestion**, enabling users to upload, embed, and retrieve documents, images, PDFs, and structured data—all with inherited security (AAD encryption + RLS isolation).

### Architecture Layers

```
┌─────────────────────────────────────────────────────┐
│  Client Layer (FastAPI Endpoints)                   │
│  POST /api/v2/knowledge/upload   (multipart)        │
│  POST /api/v2/knowledge/index    (file → embedding) │
│  GET  /api/v2/knowledge/search   (query + filters)  │
│  GET  /api/v2/knowledge/files    (list + metadata)  │
│  DELETE /api/v2/knowledge/files/{id}                │
├─────────────────────────────────────────────────────┤
│  Security Layer (JWT + RLS + AAD)                   │
│  ├─ JWT validation (Supabase auth)                  │
│  ├─ RLS policies (file_embeddings.user_hash)        │
│  └─ AAD binding (file metadata encryption)          │
├─────────────────────────────────────────────────────┤
│  Processing Pipeline                                │
│  ├─ File extraction (PDF, DOCX, images)             │
│  ├─ Chunking strategy (smart split: 512-2048 tokens)│
│  ├─ Embedding generation (OpenAI ada-002 or local)  │
│  └─ Vector storage (Postgres pgvector)              │
├─────────────────────────────────────────────────────┤
│  Storage Layer                                      │
│  ├─ PostgreSQL: file_embeddings table + RLS         │
│  ├─ S3/local: raw file storage (encrypted)          │
│  └─ Redis: embedding cache + processing queue       │
├─────────────────────────────────────────────────────┤
│  Observability (Prometheus)                         │
│  ├─ file_ingest_latency_ms (histogram)              │
│  ├─ file_embedding_ops_total (counter)              │
│  ├─ file_rls_blocks_total (RLS audit)               │
│  └─ embedding_cache_hits (performance)              │
└─────────────────────────────────────────────────────┘
```

---

## 2. API Endpoint Specification

### 2.1 Upload File

**Endpoint**: `POST /api/v2/knowledge/upload`

**Request**:
```json
{
  "file": <multipart/form-data>,
  "title": "string (optional, max 255)",
  "description": "string (optional, max 1000)",
  "source": "enum: [upload, api, email, slack] (default: upload)",
  "tags": ["array", "of", "strings"] (optional, max 10 tags),
  "metadata": {
    "author": "string",
    "created_date": "ISO8601",
    "custom_fields": "object"
  } (optional, max 2KB)
}
```

**Response (202 Accepted)**:
```json
{
  "request_id": "uuid",
  "file_id": "uuid",
  "status": "queued",
  "message": "File queued for processing",
  "expected_completion_ms": 5000
}
```

**Headers**:
- `X-RateLimit-Limit: 100`
- `X-RateLimit-Remaining: 99`
- `X-RateLimit-Reset: 1698768000`
- `Retry-After: 60` (if rate limited)

**Security**:
- JWT required (Authorization: Bearer {token})
- File size limit: 50MB
- MIME type whitelist: pdf, docx, xlsx, pptx, txt, md, png, jpg, jpeg, webp
- RLS: `file_embeddings.user_hash = current_setting('app.user_hash')`
- AAD: File metadata encrypted with user_hash as binding

---

### 2.2 Index File → Embeddings

**Endpoint**: `POST /api/v2/knowledge/index`

**Request**:
```json
{
  "file_id": "uuid (from upload response)",
  "chunk_strategy": "enum: [smart, fixed_size, semantic] (default: smart)",
  "chunk_overlap": "integer (0-500 tokens, default: 100)",
  "embedding_model": "enum: [ada-002, local, custom] (default: ada-002)",
  "rerank": "boolean (default: true)"
}
```

**Response (200 OK)**:
```json
{
  "file_id": "uuid",
  "chunks_created": 42,
  "tokens_processed": 8900,
  "embedding_latency_ms": 2341,
  "embedding_model_used": "ada-002",
  "vectors_stored": 42,
  "file_url": "/api/v2/knowledge/files/{file_id}",
  "status": "indexed"
}
```

**Failure Response (400 or 503)**:
```json
{
  "error_code": "EMBEDDING_SERVICE_DOWN",
  "detail": "OpenAI embedding service unavailable, will retry in 60s",
  "request_id": "uuid",
  "retry_after_ms": 60000
}
```

---

### 2.3 Search Knowledge

**Endpoint**: `POST /api/v2/knowledge/search`

**Request**:
```json
{
  "query": "string (max 2000 chars)",
  "query_embedding": "float[] (optional: pre-computed embedding)",
  "filters": {
    "tags": ["array", "of", "tags"] (optional),
    "source": "enum" (optional),
    "created_after": "ISO8601" (optional),
    "created_before": "ISO8601" (optional)
  } (optional),
  "top_k": "integer (1-100, default: 10)",
  "similarity_threshold": "float (0.0-1.0, default: 0.7)",
  "include_metadata": "boolean (default: true)"
}
```

**Response (200 OK)**:
```json
{
  "query": "...",
  "results": [
    {
      "rank": 1,
      "chunk_id": "uuid",
      "file_id": "uuid",
      "file_title": "...",
      "text": "...",
      "similarity_score": 0.92,
      "chunk_index": 3,
      "metadata": {
        "source": "upload",
        "tags": ["finance", "quarterly"],
        "created_date": "2025-10-15"
      },
      "position_in_file": {
        "page": 5,
        "section": "Executive Summary"
      }
    }
  ],
  "total_results": 42,
  "latency_ms": 145,
  "embedding_model_used": "ada-002"
}
```

---

### 2.4 List Files

**Endpoint**: `GET /api/v2/knowledge/files?limit=20&offset=0`

**Response (200 OK)**:
```json
{
  "files": [
    {
      "file_id": "uuid",
      "title": "Q4 2025 Financial Report",
      "source": "upload",
      "size_bytes": 2450000,
      "chunks_count": 127,
      "created_at": "2025-10-31T10:45:00Z",
      "indexed_at": "2025-10-31T10:47:32Z",
      "tags": ["finance", "quarterly"],
      "url": "/api/v2/knowledge/files/{file_id}"
    }
  ],
  "total": 147,
  "limit": 20,
  "offset": 0,
  "next_page_url": "/api/v2/knowledge/files?limit=20&offset=20"
}
```

---

### 2.5 Delete File

**Endpoint**: `DELETE /api/v2/knowledge/files/{file_id}`

**Response (204 No Content)**

**On Success**: File + all chunks deleted, RLS verified (only owner can delete)

**On Error (403 Forbidden)**:
```json
{
  "error_code": "RLS_VIOLATION",
  "detail": "You do not have permission to delete this file",
  "request_id": "uuid"
}
```

---

## 3. Data Models (Pydantic v2)

### 3.1 FileUploadRequest
```python
from pydantic import BaseModel, Field, FileUrl
from enum import Enum

class FileSource(str, Enum):
    UPLOAD = "upload"
    API = "api"
    EMAIL = "email"
    SLACK = "slack"

class FileUploadRequest(BaseModel):
    title: str | None = Field(None, max_length=255)
    description: str | None = Field(None, max_length=1000)
    source: FileSource = FileSource.UPLOAD
    tags: list[str] = Field(default_factory=list, max_items=10)
    metadata: dict = Field(default_factory=dict, max_length=2048)

    model_config = {"json_schema_extra": {
        "example": {
            "title": "Quarterly Report",
            "source": "upload",
            "tags": ["finance", "2025-Q4"]
        }
    }}
```

### 3.2 FileIndexRequest
```python
class ChunkStrategy(str, Enum):
    SMART = "smart"
    FIXED_SIZE = "fixed_size"
    SEMANTIC = "semantic"

class EmbeddingModel(str, Enum):
    ADA_002 = "ada-002"
    LOCAL = "local"
    CUSTOM = "custom"

class FileIndexRequest(BaseModel):
    file_id: UUID
    chunk_strategy: ChunkStrategy = ChunkStrategy.SMART
    chunk_overlap: int = Field(100, ge=0, le=500)
    embedding_model: EmbeddingModel = EmbeddingModel.ADA_002
    rerank: bool = True
```

### 3.3 SearchRequest
```python
class SearchRequest(BaseModel):
    query: str = Field(..., max_length=2000)
    query_embedding: list[float] | None = None
    filters: dict | None = None
    top_k: int = Field(10, ge=1, le=100)
    similarity_threshold: float = Field(0.7, ge=0.0, le=1.0)
    include_metadata: bool = True
```

### 3.4 SearchResult
```python
class SearchResultItem(BaseModel):
    rank: int
    chunk_id: UUID
    file_id: UUID
    file_title: str
    text: str
    similarity_score: float
    chunk_index: int
    metadata: dict
    position_in_file: dict | None = None

class SearchResponse(BaseModel):
    query: str
    results: list[SearchResultItem]
    total_results: int
    latency_ms: int
    embedding_model_used: str
```

---

## 4. Security Model

### 4.1 JWT + RLS + AAD Stacking

```
Layer 1: JWT Authentication
├─ Required on all /api/v2/knowledge/* endpoints
├─ Extracts: user_id, org_id, email from token claims
└─ Failure: 401 Unauthorized

Layer 2: Row-Level Security (PostgreSQL)
├─ file_embeddings table has RLS enabled
├─ Policy: file_embeddings.user_hash = COALESCE(current_setting('app.user_hash'), '')
├─ Enforced at DB level (no app-side filtering)
└─ Failure: 0 rows returned (not visible to user)

Layer 3: Additional Authenticated Data (AAD)
├─ File metadata encrypted with AES-256-GCM
├─ Binding: user_hash + file_id derived via HMAC-SHA256
├─ Decryption fails if user_hash or file_id mismatch
└─ Failure: ValueError raised, 403 Forbidden to user
```

### 4.2 File Access Control

| Operation | Auth | RLS | AAD | Response |
|-----------|------|-----|-----|----------|
| Upload file | JWT ✅ | N/A | Encrypt | 202 Accepted |
| Index file | JWT ✅ | RLS ✅ | Verify | 200 OK or 403 |
| Search | JWT ✅ | RLS ✅ | Verify | 200 + results |
| List files | JWT ✅ | RLS ✅ | N/A | 200 + list |
| Delete file | JWT ✅ | RLS ✅ | Verify | 204 or 403 |

### 4.3 Threat Model

**Threat 1**: User A queries User B's embeddings
- **Mitigation**: RLS policy at DB layer returns 0 rows
- **Audit**: Counted in `file_rls_blocks_total` metric
- **Response**: Empty result set (200 OK, no data leak)

**Threat 2**: User A spoofs user_hash to decrypt User B's metadata
- **Mitigation**: AAD binding includes user_hash + file_id
- **Audit**: Failed AAD validation logs error
- **Response**: 403 Forbidden, sanitized error message

**Threat 3**: Rate limiting bypass via X-Forwarded-For spoofing
- **Mitigation**: Rate limiter keyed on JWT claims (user_id) + IP
- **Audit**: Counted in rate_limit_bypasses metric
- **Response**: 429 Too Many Requests

---

## 5. Vector Storage Schema

### 5.1 Table: file_embeddings

```sql
CREATE TABLE file_embeddings (
  -- Primary Key
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

  -- File Reference
  file_id UUID NOT NULL,
  chunk_index INT NOT NULL,
  UNIQUE(file_id, chunk_index),

  -- Content & Vector
  text_content TEXT NOT NULL,
  embedding vector(1536),  -- OpenAI ada-002 dimension

  -- Security (RLS)
  user_hash TEXT NOT NULL,  -- SET by app.user_hash via trigger

  -- Metadata (AAD-encrypted)
  metadata_encrypted BYTEA NOT NULL,  -- {"title", "source", "tags", "position"}
  metadata_aad TEXT NOT NULL,  -- HMAC(user_hash || file_id)

  -- Performance Indexes
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW(),

  -- Partitioning (optional, by user_hash for scale)
  CONSTRAINT file_embeddings_user_hash_check CHECK (LENGTH(user_hash) > 0)
) PARTITION BY HASH(user_hash);

-- Indexes for search
CREATE INDEX idx_file_embeddings_user_hash
  ON file_embeddings (user_hash);

CREATE INDEX idx_file_embeddings_vector
  ON file_embeddings USING HNSW (embedding vector_cosine_ops);

-- Enable RLS
ALTER TABLE file_embeddings ENABLE ROW LEVEL SECURITY;

CREATE POLICY file_embeddings_user_isolation
  ON file_embeddings FOR ALL
  USING (user_hash = COALESCE(current_setting('app.user_hash'), ''));
```

### 5.2 Table: files

```sql
CREATE TABLE files (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

  -- File Metadata
  title TEXT NOT NULL,
  description TEXT,
  file_size_bytes BIGINT NOT NULL,
  mime_type TEXT NOT NULL,

  -- Source & Processing
  source TEXT NOT NULL,  -- 'upload', 'api', 'email', 'slack'
  s3_path TEXT,  -- encrypted path to raw file in S3
  processing_status TEXT,  -- 'queued', 'processing', 'completed', 'failed'

  -- Security (RLS)
  user_hash TEXT NOT NULL,

  -- Metadata
  tags TEXT[] NOT NULL DEFAULT '{}',
  metadata_encrypted BYTEA,  -- author, created_date, custom_fields
  metadata_aad TEXT,

  -- Timestamps
  created_at TIMESTAMP DEFAULT NOW(),
  indexed_at TIMESTAMP,

  -- Audit
  last_accessed_at TIMESTAMP,
  chunks_count INT DEFAULT 0
) PARTITION BY HASH(user_hash);

-- Indexes
CREATE INDEX idx_files_user_hash ON files (user_hash);
CREATE INDEX idx_files_source ON files (source);
CREATE INDEX idx_files_created_at ON files (created_at DESC);

-- RLS
ALTER TABLE files ENABLE ROW LEVEL SECURITY;

CREATE POLICY files_user_isolation
  ON files FOR ALL
  USING (user_hash = COALESCE(current_setting('app.user_hash'), ''));
```

---

## 6. Rate Limiting & Quotas

### 6.1 Knowledge API Rate Limits

| Endpoint | Limit | Window | Burst |
|----------|-------|--------|-------|
| POST /upload | 50 files/hour | per user | 10 files/minute |
| POST /index | 1000 chunks/hour | per user | 100 chunks/10s |
| POST /search | 1000 queries/hour | per user | 100 queries/10s |
| GET /files | 100 requests/hour | per user | 20 requests/10s |
| DELETE /files | 100 deletions/hour | per user | 10 deletions/10s |

### 6.2 Storage Quotas

| Tier | File Storage | Chunk Limit | Monthly |
|------|--------------|-------------|---------|
| Free | 500MB | 10,000 | 50 file uploads |
| Pro | 10GB | 1M | Unlimited uploads |
| Enterprise | Unlimited | Unlimited | Unlimited |

---

## 7. Error Handling & Standardization

### 7.1 Error Response Format

```json
{
  "error_code": "ENUM_VALUE",
  "detail": "Human readable message",
  "request_id": "uuid",
  "suggestion": "Try X or contact support"
}
```

### 7.2 Error Codes

| Code | HTTP | Cause | Recovery |
|------|------|-------|----------|
| INVALID_JWT | 401 | Missing or invalid token | Refresh token |
| RLS_VIOLATION | 403 | User not owner of file | Check file_id |
| AAD_MISMATCH | 403 | AAD decryption failed | Integrity check failed |
| FILE_NOT_FOUND | 404 | file_id doesn't exist | Verify file_id |
| RATE_LIMIT_EXCEEDED | 429 | Too many requests | Wait + retry |
| EMBEDDING_SERVICE_DOWN | 503 | OpenAI/service unavailable | Retry (backoff) |
| INVALID_FILE_FORMAT | 400 | Unsupported MIME type | Upload valid file |
| FILE_TOO_LARGE | 413 | Exceeds 50MB limit | Split file |

---

## 8. Performance Targets

### 8.1 Latency SLOs

| Operation | p50 | p95 | p99 |
|-----------|-----|-----|-----|
| File upload | 500ms | 2s | 5s |
| Embedding generation | 200ms | 500ms | 1s |
| Vector search | 100ms | 300ms | 750ms |
| File listing | 50ms | 150ms | 300ms |
| File deletion | 100ms | 250ms | 500ms |
| **End-to-end indexing** | 2s | 5s | 10s |

### 8.2 Resource Efficiency

- Embedding model: OpenAI ada-002 (1536 dimensions)
- Chunk size: 512-2048 tokens (adaptive)
- Vector index: HNSW (PostgreSQL pgvector extension)
- Fallback: IVFFlat if HNSW unavailable
- Compression: gzip for metadata + file storage

---

## 9. Rollout Plan

### Phase 1 (R2 Phase 1 - This): Design + Schema
- ✅ Design documents (KNOWLEDGE_API_DESIGN.md)
- ✅ Vector schema (VECTORSTORE_SCHEMA.sql)
- ✅ Test stubs (schemas, API, integration)
- ✅ Metrics schema definition

### Phase 2 (R2 Phase 2 - Next): Core Implementation
- API endpoints: upload, index, search (with JWT+RLS+AAD)
- File extraction (PDF, DOCX, images)
- Embedding pipeline (OpenAI integration)
- Vector search (PostgreSQL pgvector)
- Integration tests (44/44 maintained + 15 new)

### Phase 3 (R2 Phase 3): Production Readiness
- Load testing (1000 files, 100K vectors)
- Performance optimization (indexing, caching)
- Security audit (AAD verification, RLS validation)
- Staging deployment validation

---

## 10. Success Criteria

✅ **Design**: All endpoints documented with Pydantic schemas
✅ **Security**: RLS + AAD tests in integration suite
✅ **Performance**: Latency SLOs defined, load profile established
✅ **Observability**: Metrics exported (ingest_latency, embedding_ops)
✅ **No Regression**: R1 Phase 4 tests (44/44) still passing
✅ **Roadmap**: Updated to "R2: Files & Knowledge Phase 1 Complete"

---

**Next Steps**: Proceed to Phase 2 implementation (core endpoints + embedding pipeline)

**References**:
- R1 Phase 4: INFRA_VALIDATION_CHECKLIST_R1_PHASE4.md
- Memory API: src/memory/api.py (JWT+RLS+AAD pattern)
- Metrics: PROMETHEUS_METRICS_SCHEMA.yaml
