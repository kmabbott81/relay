# R2 File Embedding Pipeline — Technical Architecture

**Date**: 2025-10-31
**Phase**: R2 Phase 1 Design
**Scope**: File ingestion → chunking → embedding → vector storage

---

## 1. Pipeline Overview

```
┌──────────────┐
│ File Upload  │  POST /api/v2/knowledge/upload (multipart)
│ (Multipart)  │  Validate MIME type, size, JWT
└──────┬───────┘
       │ 202 Accepted (file_id returned)
       ▼
┌──────────────────────────────┐
│ Upload Handler               │  Process in async queue
│ - Validate file (MIME)       │  Store in S3/local (encrypted)
│ - Extract metadata (AAD)     │  Create files DB entry
│ - Set processing_status=queued
└──────┬───────────────────────┘
       │
       ▼
┌──────────────────────────────┐
│ File Extraction              │  Extract text from PDF/DOCX/images
│ - PDF: pypdf or pdfplumber   │  Limit: 50MB → ~50K tokens
│ - DOCX: python-docx          │  Stream processing for large files
│ - Images: pytesseract + OCR  │  Set processing_status=processing
└──────┬───────────────────────┘
       │
       ▼
┌──────────────────────────────────────────────┐
│ Smart Chunking Strategy                      │
│ (Configurable: smart, fixed_size, semantic)  │
│                                              │
│ SMART (default):                             │
│ - Tokenize text via tiktoken                 │
│ - Target chunk size: 512-2048 tokens         │
│ - Split on sentence/paragraph boundaries     │
│ - Preserve context via overlap (100 tokens)  │
│ - Max 50K tokens per file → ~25-50 chunks    │
│                                              │
│ FIXED_SIZE:                                  │
│ - Exact 1024-token chunks, no semantic split │
│ - For structured data (tables, code blocks)  │
│                                              │
│ SEMANTIC:                                    │
│ - Use LLM to detect logical boundaries       │
│ - Sections, chapters, topics                 │
│ - Higher quality chunks, fewer of them       │
└──────┬───────────────────────┘
       │ Produces: List[ChunkMetadata]
       ▼
┌───────────────────────────────────────┐
│ Embedding Generation                  │
│ - Batch chunks (max 100 per request)  │
│ - Call embedding service:             │
│   OpenAI ada-002 (1536-dim)            │
│   OR local model (if available)        │
│ - Rate limit: 3000 requests/min        │
│ - Circuit breaker: fail-open to ANN    │
│ - Cost tracking (ada-002: $0.1/1M)     │
└──────┬───────────────────────┘
       │ Produces: List[Embedding]
       │ Metrics: embedding_latency_ms
       ▼
┌───────────────────────────────────────────┐
│ AAD Encryption & Storage                  │
│ - For each chunk:                         │
│   - Generate: aad = HMAC(user_hash || file_id)
│   - Encrypt: metadata_encrypted           │
│   - Store in file_embeddings table        │
│ - RLS enforced at insert time             │
│ - Partition by user_hash                  │
└──────┬───────────────────────────────────┘
       │ DB writes: Set[file_embeddings]
       ▼
┌──────────────────────────────┐
│ Index Update & Cleanup       │
│ - files.indexed_at = NOW()   │
│ - files.chunks_count = count │
│ - files.processing_status    │
│   = "completed"              │
│ - Delete raw file from S3    │
│   (keep encrypted metadata)  │
└──────┬───────────────────────┘
       │
       ▼
    ✅ Complete
    Metrics: file_ingest_latency_ms
```

---

## 2. Detailed Component Specification

### 2.1 File Upload Handler

**Location**: `src/knowledge/handlers/upload.py`

**Responsibility**: Accept multipart upload, validate, store file

```python
async def handle_file_upload(
    request: Request,
    file: UploadFile,
    title: str | None,
    description: str | None,
    tags: list[str],
    metadata: dict,
) -> FileUploadResponse:
    """
    1. Validate JWT (from request.headers['Authorization'])
    2. Extract user_hash from token (via verify_supabase_jwt)
    3. Validate file:
       - Size < 50MB
       - MIME type in whitelist
    4. Store file to S3/local (encrypted with AAD)
    5. Create DB entry (files table)
    6. Queue for processing (Redis or in-memory)
    7. Return 202 Accepted with file_id
    """

    MIME_WHITELIST = {
        'application/pdf',
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        'application/vnd.ms-excel',
        'text/plain',
        'text/markdown',
        'image/png', 'image/jpeg',
    }

    # Validate JWT
    principal = await verify_supabase_jwt(request.headers['Authorization'])
    user_hash = get_aad_from_user_hash(principal.user_id)

    # Validate file
    if file.size > 50 * 1024 * 1024:  # 50MB
        raise HTTPException(status_code=413, detail="File too large") from None

    if file.content_type not in MIME_WHITELIST:
        raise HTTPException(status_code=400, detail="Invalid file type") from None

    # Store file (encrypted)
    file_id = uuid.uuid4()
    s3_path = f"user_files/{user_hash}/{file_id}"
    await store_file_encrypted(file.file, s3_path, user_hash)

    # Create DB entry
    await db.execute(
        """
        INSERT INTO files (id, user_hash, title, s3_path, processing_status)
        SET app.user_hash = %s
        VALUES (%s, %s, %s, %s, 'queued')
        """,
        user_hash, file_id, title or file.filename, s3_path
    )

    # Queue for processing
    await queue_file_for_processing(file_id, user_hash)

    return FileUploadResponse(
        file_id=file_id,
        status="queued",
        request_id=request.headers.get('X-Request-ID', str(uuid.uuid4()))
    )
```

**Metrics**:
- `file_upload_size_bytes` (histogram)
- `file_upload_duration_ms` (histogram)
- `file_upload_errors_total` (counter by error_code)

---

### 2.2 File Extraction

**Location**: `src/knowledge/extractors/factory.py`

**Extraction Strategies**:

```python
class FileExtractor(ABC):
    """Base class for format-specific extraction"""

    async def extract(self, file_path: str) -> ExtractedContent:
        """Returns: ExtractedContent(text, metadata, page_breaks)"""
        pass

class PDFExtractor(FileExtractor):
    """Extract text from PDF using pdfplumber"""

    async def extract(self, file_path: str) -> ExtractedContent:
        # Read PDF
        # Extract text preserving structure
        # Track page numbers for position tracking
        # Return: text, page_breaks, metadata
        pass

class DocxExtractor(FileExtractor):
    """Extract from DOCX (Word) using python-docx"""

    async def extract(self, file_path: str) -> ExtractedContent:
        # Extract paragraphs, tables, images
        # Preserve formatting hints (bold, headers)
        # Return: text, structure metadata
        pass

class ImageExtractor(FileExtractor):
    """OCR images using pytesseract"""

    async def extract(self, file_path: str) -> ExtractedContent:
        # Run Tesseract OCR
        # Track confidence scores
        # Return: text, confidence metadata
        pass

# Router
EXTRACTORS = {
    'application/pdf': PDFExtractor(),
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document': DocxExtractor(),
    'image/png': ImageExtractor(),
    # ... more
}

async def extract_file(
    s3_path: str,
    mime_type: str,
    user_hash: str,
) -> ExtractedContent:
    extractor = EXTRACTORS.get(mime_type)
    if not extractor:
        raise ValueError(f"No extractor for {mime_type}")

    file_bytes = await download_encrypted_file(s3_path, user_hash)
    return await extractor.extract(file_bytes)
```

**Metrics**:
- `file_extraction_duration_ms` (histogram by format)
- `file_extraction_errors_total` (counter by format + error)

---

### 2.3 Chunking Strategies

**Location**: `src/knowledge/chunking/strategies.py`

```python
class ChunkingStrategy(ABC):
    async def chunk(
        self,
        text: str,
        metadata: dict,
        overlap_tokens: int = 100,
    ) -> list[Chunk]:
        """Returns: List[Chunk(text, start_idx, end_idx, metadata)]"""
        pass

class SmartChunker(ChunkingStrategy):
    """Intelligently chunk on sentence/paragraph boundaries"""

    async def chunk(self, text: str, metadata: dict, overlap_tokens: int = 100):
        tokenizer = tiktoken.encoding_for_model("gpt-3.5-turbo")
        tokens = tokenizer.encode(text)

        # Define chunk boundaries
        chunk_size_tokens = 1024  # Configurable
        step_size = chunk_size_tokens - overlap_tokens

        chunks = []
        for i in range(0, len(tokens), step_size):
            chunk_tokens = tokens[i : i + chunk_size_tokens]
            chunk_text = tokenizer.decode(chunk_tokens)

            # Post-process: find nearest sentence boundary
            chunk_text = truncate_to_sentence_end(chunk_text)

            chunks.append(Chunk(
                text=chunk_text,
                token_count=len(tokenizer.encode(chunk_text)),
                metadata={
                    **metadata,
                    "chunk_index": len(chunks),
                    "start_token": i,
                    "end_token": i + len(chunk_tokens)
                }
            ))

        return chunks

class FixedSizeChunker(ChunkingStrategy):
    """Exact chunk sizes (for structured data)"""

    async def chunk(self, text: str, metadata: dict, overlap_tokens: int = 100):
        # Split at exactly chunk_size_tokens, no smart boundaries
        # Used for code, tables, structured logs
        pass

class SemanticChunker(ChunkingStrategy):
    """Use LLM to detect semantic boundaries"""

    async def chunk(self, text: str, metadata: dict, overlap_tokens: int = 100):
        # Send text to LLM (Claude or GPT-4)
        # Request: "Break this text into logical sections"
        # Higher quality chunks, fewer artifacts
        # Higher cost/latency
        pass
```

**Metrics**:
- `file_chunks_created_total` (counter by strategy)
- `file_chunk_size_tokens` (histogram)
- `chunking_duration_ms` (histogram)

---

### 2.4 Embedding Generation

**Location**: `src/knowledge/embedding/service.py`

```python
class EmbeddingService:
    """Wrapper around embedding providers (OpenAI, local, etc.)"""

    async def embed_batch(
        self,
        texts: list[str],
        model: str = "ada-002",
        retry_attempts: int = 3,
    ) -> list[Embedding]:
        """
        Embed a batch of texts.

        Params:
        - texts: list of strings (max 100 per call)
        - model: "ada-002", "local", "custom"
        - retry_attempts: exponential backoff

        Returns: list[float[1536]] (OpenAI dimensions)
        """

        if model == "ada-002":
            return await self._embed_openai(texts, retry_attempts)
        elif model == "local":
            return await self._embed_local(texts)
        else:
            raise ValueError(f"Unknown model: {model}")

    async def _embed_openai(self, texts: list[str], retry_attempts: int):
        """Call OpenAI embedding API with backoff"""

        for attempt in range(retry_attempts):
            try:
                response = await openai.Embedding.acreate(
                    input=texts,
                    model="text-embedding-ada-002",
                )
                return [item['embedding'] for item in response['data']]
            except openai.error.RateLimitError:
                if attempt == retry_attempts - 1:
                    raise HTTPException(status_code=503, detail="Embedding service rate limited") from None
                await asyncio.sleep(2 ** attempt)  # Exponential backoff
            except openai.error.APIError as e:
                metrics.record_embedding_error("openai_api_error")
                if attempt == retry_attempts - 1:
                    raise HTTPException(status_code=503, detail="Embedding service down") from None
                await asyncio.sleep(2 ** attempt)

        return []

    async def _embed_local(self, texts: list[str]):
        """Use local embedding model (ONNX or similar)"""
        # Faster (no network), cheaper, but lower quality
        # Load model on startup
        pass
```

**Circuit Breaker** (fail-open pattern):
```python
class EmbeddingCircuitBreaker:
    """
    If embedding service is down, fall back to:
    1. Cached embeddings (Redis)
    2. ANN (Approximate Nearest Neighbor without embeddings)
    3. Full-text search
    """

    async def embed_with_fallback(self, texts: list[str]) -> list[Embedding]:
        try:
            embeddings = await self.embedding_service.embed_batch(texts)
            self.circuit_state = "closed"  # Reset
            return embeddings
        except HTTPException as e:
            if e.status_code == 503:
                self.circuit_state = "open"
                metrics.record_circuit_breaker_trip("embedding_service")
                # Fall back to cached or ANN
                return await self._get_fallback_embeddings(texts)
            raise
```

**Metrics**:
- `embedding_generation_latency_ms` (histogram)
- `embedding_ops_total` (counter)
- `embedding_cache_hits_total` (counter)
- `embedding_circuit_breaker_trips_total` (counter)

---

### 2.5 Vector Storage & Indexing

**Location**: `src/knowledge/storage/vector_db.py`

```python
class VectorStore:
    """Abstract interface for vector storage"""

    async def insert_vectors(
        self,
        file_id: UUID,
        user_hash: str,
        chunks_with_embeddings: list[Chunk],
    ) -> int:
        """Insert vectors into index, return count"""
        pass

    async def search(
        self,
        query_embedding: list[float],
        user_hash: str,
        top_k: int = 10,
        filters: dict | None = None,
    ) -> list[SearchResult]:
        """Find top-k similar vectors"""
        pass

class PostgresVectorStore(VectorStore):
    """PostgreSQL with pgvector extension"""

    async def insert_vectors(
        self,
        file_id: UUID,
        user_hash: str,
        chunks_with_embeddings: list[Chunk],
    ) -> int:
        """
        Insert into file_embeddings table:
        - id: UUID
        - file_id, chunk_index, user_hash
        - text_content, embedding
        - metadata_encrypted (AAD-wrapped)
        """

        # Set RLS context
        await db.execute(
            "SET app.user_hash = %s",
            user_hash
        )

        # Batch insert with AAD encryption
        query = """
        INSERT INTO file_embeddings
        (file_id, chunk_index, text_content, embedding, user_hash, metadata_encrypted, metadata_aad)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """

        aad = get_aad_from_user_hash(user_hash)

        rows_inserted = 0
        for chunk in chunks_with_embeddings:
            metadata_encrypted = encrypt_with_aad(
                chunk.metadata,
                aad + str(file_id)  # Bind to file
            )

            await db.execute(
                query,
                file_id,
                chunk.chunk_index,
                chunk.text,
                chunk.embedding,  # Vector type
                user_hash,
                metadata_encrypted,
                aad
            )
            rows_inserted += 1

        return rows_inserted

    async def search(
        self,
        query_embedding: list[float],
        user_hash: str,
        top_k: int = 10,
        filters: dict | None = None,
    ) -> list[SearchResult]:
        """
        Vector search using pgvector cosine similarity.
        RLS automatically filters to user_hash.
        """

        await db.execute("SET app.user_hash = %s", user_hash)

        query = """
        SELECT
          id, file_id, chunk_index, text_content,
          1 - (embedding <=> %s::vector) as similarity_score
        FROM file_embeddings
        WHERE user_hash = COALESCE(current_setting('app.user_hash'), '')
        ORDER BY similarity_score DESC
        LIMIT %s
        """

        results = await db.fetch(query, query_embedding, top_k)

        return [
            SearchResult(
                chunk_id=row['id'],
                file_id=row['file_id'],
                similarity_score=row['similarity_score'],
                text=row['text_content'],
            )
            for row in results
        ]
```

**Metrics**:
- `vector_insert_latency_ms` (histogram)
- `vector_search_latency_ms` (histogram)
- `vector_index_size_bytes` (gauge)

---

### 2.6 AAD Encryption Wrapper

**Location**: `src/knowledge/encryption/aad.py`

```python
def get_file_aad(user_hash: str, file_id: UUID) -> str:
    """
    Generate Additional Authenticated Data for file chunks.

    AAD = HMAC-SHA256(user_hash || file_id)

    Ensures that metadata encrypted for User A + File X
    cannot be decrypted by User B or for File Y.
    """
    combined = f"{user_hash}:{file_id}".encode()
    return hmac.new(HMAC_KEY, combined, hashlib.sha256).hexdigest()

async def encrypt_file_metadata(metadata: dict, user_hash: str, file_id: UUID) -> bytes:
    """Encrypt file metadata with AAD binding"""
    aad = get_file_aad(user_hash, file_id)
    return encrypt_with_aad(metadata, aad)

async def decrypt_file_metadata(encrypted: bytes, user_hash: str, file_id: UUID) -> dict:
    """Decrypt file metadata, verify AAD binding"""
    aad = get_file_aad(user_hash, file_id)
    try:
        return decrypt_with_aad(encrypted, aad)
    except ValueError:
        # AAD mismatch: user_hash or file_id changed
        raise HTTPException(status_code=403, detail="Cannot access file metadata") from None
```

---

## 3. Async Processing Queue

### 3.1 Job Queue Model

```python
class EmbeddingJob(BaseModel):
    """Job to be processed asynchronously"""

    job_id: UUID
    file_id: UUID
    user_hash: str
    status: str  # "queued", "processing", "completed", "failed"

    chunk_strategy: str = "smart"
    embedding_model: str = "ada-002"

    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None

    error: str | None = None
    chunks_created: int = 0
    tokens_processed: int = 0
    latency_ms: int = 0
```

### 3.2 Job Processing (Background Worker)

```python
class EmbeddingJobProcessor:
    """Background worker processing embedding jobs"""

    async def process_job(self, job: EmbeddingJob):
        """
        Pipeline:
        1. Fetch file from S3
        2. Extract text
        3. Chunk text
        4. Generate embeddings
        5. Store vectors (with RLS + AAD)
        6. Update job status
        7. Emit metrics
        """

        start_time = time.time()
        job.status = "processing"
        job.started_at = datetime.now()

        try:
            # 1. Extract
            extracted = await self.extract_file(job.file_id, job.user_hash)

            # 2. Chunk
            chunks = await self.chunk_text(
                extracted.text,
                strategy=job.chunk_strategy
            )

            # 3. Embed
            embeddings = await self.embedding_service.embed_batch(
                [chunk.text for chunk in chunks],
                model=job.embedding_model
            )

            # 4. Attach embeddings to chunks
            chunks_with_embeddings = [
                {**chunk, "embedding": embedding}
                for chunk, embedding in zip(chunks, embeddings)
            ]

            # 5. Store
            stored_count = await self.vector_store.insert_vectors(
                job.file_id,
                job.user_hash,
                chunks_with_embeddings
            )

            # 6. Update job
            job.status = "completed"
            job.chunks_created = stored_count
            job.completed_at = datetime.now()

        except Exception as e:
            job.status = "failed"
            job.error = str(e)
            metrics.record_embedding_job_failure(job.error)

        # 7. Metrics
        job.latency_ms = int((time.time() - start_time) * 1000)
        metrics.record_file_ingest_latency(job.latency_ms)

        # Persist job result
        await self.save_job(job)
```

---

## 4. Error Recovery & Retries

```python
class EmbeddingJobRetryPolicy:
    """Exponential backoff with circuit breaker"""

    MAX_ATTEMPTS = 3
    BASE_DELAY_MS = 1000
    MAX_DELAY_MS = 60000

    async def retry_with_backoff(self, job: EmbeddingJob):
        """Retry failed jobs with exponential backoff"""

        attempt = 0
        while attempt < self.MAX_ATTEMPTS:
            try:
                await self.process_job(job)
                return  # Success
            except Exception as e:
                attempt += 1
                if attempt >= self.MAX_ATTEMPTS:
                    job.status = "failed"
                    job.error = f"Failed after {self.MAX_ATTEMPTS} attempts: {e}"
                    break

                delay_ms = min(
                    self.BASE_DELAY_MS * (2 ** attempt),
                    self.MAX_DELAY_MS
                )
                await asyncio.sleep(delay_ms / 1000)
```

---

## 5. Metrics Summary

| Metric | Type | Dimensions | Alert Threshold |
|--------|------|-----------|-----------------|
| `file_ingest_latency_ms` | Histogram | p50, p95, p99 | > 10s (p95) |
| `file_embedding_ops_total` | Counter | by_model, by_status | None (informational) |
| `embedding_cache_hits_total` | Counter | by_model | None |
| `embedding_circuit_breaker_trips_total` | Counter | service | > 0 (alert) |
| `file_rls_blocks_total` | Counter | by_operation | > 0 (critical) |
| `file_extraction_duration_ms` | Histogram | by_format | > 5s (p95) |
| `file_chunks_created_total` | Counter | by_strategy | None |
| `vector_insert_latency_ms` | Histogram | by_store | > 2s (p95) |
| `vector_search_latency_ms` | Histogram | by_store | > 500ms (p95) |

---

## 6. Success Criteria

✅ All pipeline stages async and resilient
✅ AAD + RLS applied at each stage
✅ Circuit breaker for embedding service
✅ Exponential backoff for retries
✅ Metrics exported to Prometheus
✅ Error responses sanitized (no stack traces)
✅ Load test: 1000 files, 100K vectors in < 1 hour

---

**Reference**: KNOWLEDGE_API_DESIGN.md (API endpoints), src/crypto/envelope.py (AAD encryption)
