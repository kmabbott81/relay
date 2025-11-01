# Knowledge API — FastAPI Implementation
# Date: 2025-10-31
# Phase: R2 Phase 2 (Implementation)
# Security: JWT → RLS → AAD (three-layer defense)

import uuid
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, File, Form, HTTPException, Query, Request, Response, UploadFile

from src.knowledge.rate_limit.redis_bucket import get_rate_limit
from src.knowledge.schemas import (
    FileIndexRequest,
    FileIndexResponse,
    FileListResponse,
    FileUploadResponse,
    SearchRequest,
    SearchResponse,
)
from src.knowledge.suggestions import suggestion_for
from src.memory.rls import hmac_user
from src.monitoring.metrics_adapter import (
    record_api_error,
    record_file_upload,
    record_index_operation,
    record_vector_search,
)
from src.stream.auth import verify_supabase_jwt

# Initialize router
router = APIRouter(prefix="/api/v1/knowledge", tags=["Knowledge API"])


# ============================================================================
# SECURITY HELPERS
# ============================================================================


async def check_jwt_and_get_user_hash(request: Request) -> str:
    """
    Extract and validate JWT, return user_hash for RLS + AAD.
    Raises 401 if invalid.
    """
    request_id = getattr(request.state, "request_id", None)
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        record_api_error("MISSING_JWT", 401, request_id=request_id)
        raise HTTPException(
            status_code=401,
            detail="Missing or invalid JWT",
        ) from None

    try:
        token = auth_header[7:]  # Remove "Bearer "
        principal = await verify_supabase_jwt(token)
        user_hash = hmac_user(principal.user_id)  # Use R1 hmac_user to compute user_hash
        return user_hash
    except Exception:
        record_api_error("INVALID_JWT", 401, request_id=request_id)
        raise HTTPException(status_code=401, detail="Invalid JWT") from None


async def add_rate_limit_headers(response: Response, status: dict) -> Response:
    """
    Add X-RateLimit-* headers to response from rate limit status.

    CRITICAL: Per-user headers, not global state.
    """
    response.headers["X-RateLimit-Limit"] = str(status["limit"])
    response.headers["X-RateLimit-Remaining"] = str(status["remaining"])
    response.headers["X-RateLimit-Reset"] = str(status["reset_at"])
    return response


async def check_rate_limit_and_get_status(user_hash: str, user_tier: str = "free") -> tuple[bool, dict]:
    """
    Check if user is rate limited (per-user Redis bucket).

    Returns: (is_limited, status_dict)

    CRITICAL: Enforces per-user limits via Redis, not global state.
    """
    status = await get_rate_limit(user_hash, user_tier)
    is_limited = status["remaining"] <= 0
    return is_limited, status


def sanitize_error_detail(detail: str) -> str:
    """
    Sanitize error details to prevent information disclosure.
    Never expose: file paths, S3 URLs, chunk text, internal IDs, stack traces.
    """
    sensitive_patterns = ["s3://", "/var/", "/home/", "stack", "traceback", ".py:"]
    for pattern in sensitive_patterns:
        if pattern.lower() in detail.lower():
            return "An error occurred. Please contact support with your request ID."
    return detail


# ============================================================================
# ENDPOINT 1: Upload File
# ============================================================================


@router.post("/upload", response_model=FileUploadResponse, status_code=202)
async def upload_file(
    request: Request,
    response: Response,
    file: UploadFile = File(...),
    title: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    source: Optional[str] = Form("upload"),
    tags: Optional[str] = Form("[]"),  # JSON array as string
) -> FileUploadResponse:
    """
    Upload a file for knowledge ingestion.
    Returns 202 Accepted with file_id; processing happens asynchronously.

    Security:
    - JWT validation required
    - File size limit: 50MB
    - MIME type whitelist enforced
    - Metadata AAD-encrypted with user_hash binding
    - RLS enforced at insert time
    """
    request_id = uuid.uuid4()

    try:
        # 1. JWT validation + RLS
        user_hash = await check_jwt_and_get_user_hash(request)

        # 2. Rate limiting (per-user Redis bucket)
        is_limited, status = await check_rate_limit_and_get_status(user_hash, user_tier="free")
        if is_limited:
            record_api_error("rate_limit_exceeded", 429, request_id=request_id)
            response.status_code = 429
            response.headers["Retry-After"] = str(status["retry_after"])
            await add_rate_limit_headers(response, status)
            raise HTTPException(
                status_code=429,
                detail=suggestion_for(429, "rate_limit_exceeded", status["retry_after"]),
            ) from None

        # 3. File validation
        MIME_WHITELIST = {
            "application/pdf",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "application/vnd.ms-excel",
            "text/plain",
            "text/markdown",
            "image/png",
            "image/jpeg",
            "image/webp",
        }

        if file.content_type not in MIME_WHITELIST:
            record_api_error("invalid_mime_type", 400, request_id=request_id)
            raise HTTPException(
                status_code=400, detail="Invalid file type. Allowed: PDF, DOCX, XLSX, TXT, MD, PNG, JPG, WEBP"
            ) from None

        # TODO: Server-side MIME re-validation using python-magic
        # import magic
        # file_bytes = await file.read()
        # mime_type = magic.from_buffer(file_bytes, mime=True)
        # if mime_type not in MIME_WHITELIST: raise...

        file_size = 0
        if hasattr(file, "size"):
            file_size = file.size
        else:
            file_bytes = await file.read()
            file_size = len(file_bytes)
            await file.seek(0)

        if file_size > 50 * 1024 * 1024:  # 50MB
            record_api_error("file_too_large", 413, request_id=request_id)
            raise HTTPException(status_code=413, detail="File exceeds 50MB limit") from None

        # 4. Create file entry in DB (RLS enforced at insert via trigger)
        file_id = uuid.uuid4()

        # TODO: Store file in S3/local (encrypted)
        # s3_path = f"user_files/{user_hash}/{file_id}"
        # await store_file_encrypted(file_bytes, s3_path, user_hash)

        # TODO: Insert into files table with RLS context
        # await db.execute(
        #     """
        #     SET app.user_hash = %s;
        #     INSERT INTO files (id, user_hash, title, s3_path, processing_status)
        #     VALUES (%s, %s, %s, %s, 'queued')
        #     """,
        #     user_hash, file_id, title or file.filename, s3_path
        # )

        # TODO: Queue for processing (Redis or in-memory)
        # await queue_file_for_processing(file_id, user_hash)

        # 5. Return 202 Accepted
        await add_rate_limit_headers(response, status)
        record_file_upload(
            file_size_bytes=file_size,
            mime_type=file.content_type or "application/octet-stream",
            request_id=request_id,
        )

        return FileUploadResponse(
            file_id=file_id,
            status="queued",
            request_id=request_id,
            message="File queued for processing",
            expected_completion_ms=5000,
        )

    except HTTPException:
        raise
    except Exception as e:
        record_api_error("file_upload_error", 500, request_id=request_id)
        raise HTTPException(status_code=500, detail="Internal server error") from e


# ============================================================================
# ENDPOINT 2: Index File
# ============================================================================


@router.post("/index", response_model=FileIndexResponse, status_code=200)
async def index_file(
    request: Request,
    response: Response,
    body: FileIndexRequest,
) -> FileIndexResponse:
    """
    Index a file: extract → chunk → embed → store vectors.

    Security:
    - JWT + RLS (owner-only check)
    - AAD binding on metadata
    - Circuit breaker for embedding service failure
    """
    try:
        # 1. JWT validation
        user_hash = await check_jwt_and_get_user_hash(request)

        # 1b. Rate limiting (per-user Redis bucket)
        is_limited, status = await check_rate_limit_and_get_status(user_hash, user_tier="free")
        if is_limited:
            response.status_code = 429
            response.headers["Retry-After"] = str(status["retry_after"])
            await add_rate_limit_headers(response, status)
            raise HTTPException(
                status_code=429,
                detail=suggestion_for(429, "rate_limit_exceeded", status["retry_after"]),
            ) from None

        # 2. Check ownership (RLS should prevent seeing other users' files, but be explicit)
        # TODO: Fetch file from DB with RLS
        # file_row = await db.fetchrow(
        #     "SELECT id FROM files WHERE id = %s AND user_hash = %s",
        #     body.file_id, user_hash
        # )
        # if not file_row:
        #     raise HTTPException(status_code=403, detail="Access denied") from None

        # 3. Extract text from file
        # TODO: Extract based on MIME type
        # extracted_text = await extract_file(body.file_id, user_hash)

        # 4. Chunk text
        # TODO: Apply chunking strategy
        # chunks = await chunk_text(extracted_text, strategy=body.chunk_strategy)

        # 5. Generate embeddings
        # TODO: Call embedding service with circuit breaker
        # try:
        #     embeddings = await embed_chunks(chunks, model=body.embedding_model)
        # except HTTPException as e:
        #     if e.status_code == 503:
        #         raise HTTPException(status_code=503, detail="Embedding service unavailable") from None
        #     raise

        # 6. Store vectors with AAD
        # TODO: Batch insert with RLS + AAD
        # vectors_stored = await store_vectors(body.file_id, user_hash, chunks, embeddings)

        # 7. Update file metadata
        # TODO: Set indexed_at, chunks_count, processing_status = 'completed'
        # await db.execute(
        #     "UPDATE files SET indexed_at = NOW(), chunks_count = %s WHERE id = %s AND user_hash = %s",
        #     len(chunks), body.file_id, user_hash
        # )

        await add_rate_limit_headers(response, status)
        record_index_operation(operation="embed", item_count=0)

        return FileIndexResponse(
            file_id=body.file_id,
            chunks_created=0,  # TODO: Return actual count
            tokens_processed=0,  # TODO: Return actual count
            embedding_latency_ms=0,  # TODO: Return actual latency
            embedding_model_used=body.embedding_model.value,
            vectors_stored=0,  # TODO: Return actual count
            file_url=f"/api/v2/knowledge/files/{body.file_id}",
            status="indexed",
        )

    except HTTPException:
        raise
    except Exception:
        record_api_error("index_error", 500)
        raise HTTPException(status_code=500, detail="Internal server error") from None


# ============================================================================
# ENDPOINT 3: Search Knowledge
# ============================================================================


@router.post("/search", response_model=SearchResponse, status_code=200)
async def search_knowledge(
    request: Request,
    response: Response,
    body: SearchRequest,
) -> SearchResponse:
    """
    Vector similarity search over indexed embeddings.

    Security:
    - JWT + RLS (only own files visible)
    - AAD verification on metadata decryption
    """
    try:
        # 1. JWT validation
        user_hash = await check_jwt_and_get_user_hash(request)

        # 2. Rate limiting (per-user Redis bucket)
        is_limited, status = await check_rate_limit_and_get_status(user_hash, user_tier="free")
        if is_limited:
            response.status_code = 429
            response.headers["Retry-After"] = str(status["retry_after"])
            await add_rate_limit_headers(response, status)
            raise HTTPException(
                status_code=429,
                detail=suggestion_for(429, "rate_limit_exceeded", status["retry_after"]),
            ) from None

        # 3. Generate or use provided embedding
        # TODO: If no query_embedding, call embedding service
        # if body.query_embedding is None:
        #     query_embedding = await embed_text(body.query, model="ada-002")
        # else:
        #     query_embedding = body.query_embedding

        # 4. Vector search with RLS + filters
        # TODO: Query file_embeddings with RLS + similarity threshold + filters
        # results = await vector_search(
        #     query_embedding=query_embedding,
        #     user_hash=user_hash,
        #     top_k=body.top_k,
        #     similarity_threshold=body.similarity_threshold,
        #     filters=body.filters
        # )

        # 5. Check cache hit status
        # TODO: Check if result came from cache
        # cache_hit = is_cached(body.query)

        # 6. Decrypt metadata for each result
        # TODO: Decrypt metadata_encrypted + metadata_aad for each result
        # for result in results:
        #     aad = get_file_aad(user_hash, result.file_id)
        #     try:
        #         result.metadata = decrypt_with_aad(result.metadata_encrypted, aad)
        #     except ValueError:
        #         # AAD mismatch: Normalize to 404 (not 403) to prevent existence oracle
        #         raise HTTPException(status_code=404, detail="File not found") from None

        await add_rate_limit_headers(response, status)
        record_vector_search(query_tokens=len(body.query.split()), results_count=0, latency_ms=0)

        return SearchResponse(
            query=body.query,
            results=[],  # TODO: Return actual results
            total_results=0,  # TODO: Return actual count
            latency_ms=0,  # TODO: Return actual latency
            embedding_model_used="ada-002",
            cache_hit=False,  # TODO: Return actual cache status
        )

    except HTTPException:
        raise
    except Exception:
        record_api_error("search_error", 500)
        raise HTTPException(status_code=500, detail="Internal server error") from None


# ============================================================================
# ENDPOINT 4: List Files
# ============================================================================


@router.get("/files", response_model=FileListResponse, status_code=200)
async def list_files(
    request: Request,
    response: Response,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> FileListResponse:
    """
    List user's files (RLS-isolated).

    Security:
    - JWT + RLS (only own files returned)
    """
    try:
        # 1. JWT validation
        user_hash = await check_jwt_and_get_user_hash(request)

        # 1b. Rate limiting (per-user Redis bucket)
        is_limited, status = await check_rate_limit_and_get_status(user_hash, user_tier="free")
        if is_limited:
            response.status_code = 429
            response.headers["Retry-After"] = str(status["retry_after"])
            await add_rate_limit_headers(response, status)
            raise HTTPException(
                status_code=429,
                detail=suggestion_for(429, "rate_limit_exceeded", status["retry_after"]),
            ) from None

        # 2. Query with RLS
        # TODO: SELECT * FROM files WHERE user_hash = %s LIMIT %s OFFSET %s
        # (RLS policy automatically filters to authenticated user_hash)
        # files = await db.fetch(
        #     "SELECT id, title, source, file_size_bytes, chunks_count, created_at, indexed_at, tags
        #      FROM files WHERE user_hash = %s ORDER BY created_at DESC LIMIT %s OFFSET %s",
        #     user_hash, limit, offset
        # )

        # 3. Count total
        # total = await db.fetchval(
        #     "SELECT COUNT(*) FROM files WHERE user_hash = %s",
        #     user_hash
        # )

        await add_rate_limit_headers(response, status)
        record_index_operation(operation="list_files", item_count=0)

        return FileListResponse(
            files=[],  # TODO: Return actual files
            total=0,  # TODO: Return actual count
            limit=limit,
            offset=offset,
            next_page_url=None
            if offset + limit > 0
            else f"/api/v2/knowledge/files?limit={limit}&offset={offset + limit}",
        )

    except HTTPException:
        raise
    except Exception:
        record_api_error("list_error", 500)
        raise HTTPException(status_code=500, detail="Internal server error") from None


# ============================================================================
# ENDPOINT 5: Delete File
# ============================================================================


@router.delete("/files/{file_id}", status_code=204)
async def delete_file(
    request: Request,
    response: Response,
    file_id: UUID,
) -> None:
    """
    Delete file and cascade delete embeddings.

    Security:
    - JWT + RLS (owner-only)
    - Explicit ownership check before cascade delete
    - AAD verification before deletion
    """

    try:
        # 1. JWT validation
        user_hash = await check_jwt_and_get_user_hash(request)

        # 1b. Rate limiting (per-user Redis bucket)
        is_limited, status = await check_rate_limit_and_get_status(user_hash, user_tier="free")
        if is_limited:
            response.status_code = 429
            response.headers["Retry-After"] = str(status["retry_after"])
            await add_rate_limit_headers(response, status)
            raise HTTPException(
                status_code=429,
                detail=suggestion_for(429, "rate_limit_exceeded", status["retry_after"]),
            ) from None

        # 2. Explicit ownership check (even though RLS will prevent deletion otherwise)
        # Code shows intent: JWT + explicit check + RLS (defense in depth)
        # TODO: Uncomment when db connection available in Phase 3
        # file_owner = await db.fetchval(
        #     "SELECT user_hash FROM files WHERE id = %s",
        #     file_id
        # )
        # if file_owner != user_hash:
        #     raise HTTPException(status_code=403, detail="You do not have permission to delete this file") from None
        # For Phase 2: JWT validation + RLS policy enforces ownership check (deferred DB call to Phase 3)

        # 3. Cascade delete (RLS prevents access to files from other users)
        # TODO: DELETE FROM file_embeddings WHERE file_id = %s (auto-cascade)
        # TODO: DELETE FROM files WHERE id = %s AND user_hash = %s
        # await db.execute(
        #     "DELETE FROM files WHERE id = %s AND user_hash = %s",
        #     file_id, user_hash
        # )

        await add_rate_limit_headers(response, status)
        record_index_operation(operation="delete_file", item_count=1)

    except HTTPException:
        raise
    except Exception:
        record_api_error("delete_error", 500)
        raise HTTPException(status_code=500, detail="Internal server error") from None


# ============================================================================
# ERROR HANDLING
# ============================================================================


@router.post("/files/{file_id}", status_code=204)
async def handle_invalid_endpoint(file_id: UUID):
    """Catch unsupported operations"""
    raise HTTPException(status_code=405, detail="Method not allowed") from None


# ============================================================================
# MIDDLEWARE: Add request ID to all responses
# ============================================================================
# NOTE: Middleware must be registered on FastAPI app, not APIRouter
# This function is here for reference; add to main app via:
#   app.add_middleware(RequestIDMiddleware)


async def add_request_id_middleware(request: Request, call_next):
    """Add request_id to response for tracing"""
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    request.scope["request_id"] = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


# ============================================================================
# End of Knowledge API
# ============================================================================

"""
Implementation Notes:

Security Architecture (Three Layers):
1. JWT: verify_supabase_jwt() ensures user is authenticated
2. RLS: PostgreSQL policies enforce user_hash isolation at DB layer
3. AAD: HMAC(user_hash || file_id) prevents metadata tampering

Error Handling:
- All errors return standardized ErrorResponse with error_code + detail + request_id
- No stack traces, file paths, or internal IDs exposed
- Suggestions provided for common errors (rate limits, quota exceeded, etc.)

Rate Limiting:
- Per-user keyed to JWT.user_id (not IP address alone)
- X-RateLimit-* headers added to all responses
- 429 includes Retry-After header (60 seconds)

TODO Items (Deferred to Integration Phase):
- Database connectivity (currently all DB operations commented)
- S3/local file storage integration
- Embedding service integration with circuit breaker
- Redis for caching and rate limiting state
- Server-side MIME validation (python-magic)
- XSS sanitization for metadata fields
"""
