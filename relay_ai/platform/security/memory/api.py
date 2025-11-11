"""
Task D Memory APIs - FastAPI router.

Sprint 62 Phase 2: API scaffold with JWT→RLS→AAD plumbing.
- JWT authentication (Bearer tokens)
- RLS context enforcement (user_hash)
- AAD encryption/decryption wiring
- Reranker circuit breaker (250ms timeout)
- Rate-limit headers
- Observability hooks (Prometheus-ready)
"""

import logging
import time
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request, Response

from relay_ai.crypto.envelope import (
    decrypt_with_aad,  # noqa: F401 - Phase 3 test dep
    encrypt_with_aad,  # noqa: F401 - Phase 3 test dep
    get_aad_from_user_hash,
)
from relay_ai.memory.metrics import get_default_collector
from relay_ai.memory.rls import hmac_user
from relay_ai.memory.schemas import (
    EntitiesRequest,
    EntitiesResponse,
    Entity,
    ErrorResponse,
    IndexRequest,
    IndexResponse,
    QueryRequest,
    QueryResponse,
    QueryResult,
    SummarizeRequest,
    SummarizeResponse,
)
from relay_ai.stream.auth import verify_supabase_jwt  # Existing JWT verifier

logger = logging.getLogger(__name__)

# Feature flags and timeouts
RERANK_ENABLED = True  # Will be env-backed in Phase 3
RERANK_TIMEOUT_MS = 250  # Circuit breaker timeout

# Metrics collector
metrics = get_default_collector()

# Rate-limiting (in-memory, Phase 3)
_rate_limit_state = {
    "limit": 100,
    "remaining": 100,
    "reset_at": int(time.time()) + 3600,
}


def _add_rate_limit_headers(response: Response) -> Response:
    """Add X-RateLimit-* headers to response"""
    response.headers["X-RateLimit-Limit"] = str(_rate_limit_state["limit"])
    response.headers["X-RateLimit-Remaining"] = str(_rate_limit_state["remaining"])
    response.headers["X-RateLimit-Reset"] = str(_rate_limit_state["reset_at"])
    return response


def _record_latency(endpoint: str, ms: float, user_id: str = "unknown", success: bool = True) -> None:
    """Observability hook: record endpoint latency."""
    metrics.record_query_latency(ms, stage=endpoint, user_id=user_id, success=success)
    logger.debug(f"relay_memory_request_latency_ms endpoint={endpoint} ms={ms:.1f}")


def _count_error(endpoint: str, code: int) -> None:
    """Observability hook: record error."""
    logger.debug(f"relay_memory_errors_total endpoint={endpoint} code={code}")


async def _verify_jwt_and_extract_user_id(request: Request) -> str:
    """
    Verify JWT from Authorization header and extract user_id.

    Raises:
        HTTPException(401): Missing or invalid Bearer token
    """
    auth_header = request.headers.get("Authorization", "")
    if not auth_header or not auth_header.startswith("Bearer "):
        logger.warning("Missing or invalid Authorization header")
        raise HTTPException(
            status_code=401,
            detail="Missing or invalid Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = auth_header.split(" ", 1)[1]

    try:
        principal = await verify_supabase_jwt(token)
        user_id = principal.user_id  # principal is a Pydantic model, not a dict
        if not user_id:
            logger.warning("JWT valid but missing user_id claim")
            raise HTTPException(status_code=401, detail="Invalid JWT: missing user_id")
        return user_id
    except Exception as e:
        logger.warning(f"JWT verification failed: {e}")
        raise HTTPException(status_code=401, detail="Invalid JWT") from None


# Create router
router = APIRouter(
    prefix="/api/v1/memory",
    tags=["memory"],
    responses={
        401: {"model": ErrorResponse, "description": "Missing or invalid JWT"},
        403: {"model": ErrorResponse, "description": "Permission denied (RLS or AAD validation failed)"},
        422: {"model": ErrorResponse, "description": "Validation error"},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
        503: {"model": ErrorResponse, "description": "Service temporarily unavailable"},
    },
)


# ============================================================================
# Endpoint 1: POST /memory/index
# ============================================================================


@router.post("/index", response_model=IndexResponse, summary="Insert/upsert memory chunk")
async def memory_index(request: Request, req: IndexRequest, response: Response) -> IndexResponse:
    """
    Insert or upsert a memory chunk with semantic embedding.

    Security:
    - Validates JWT and extracts user_id
    - Sets RLS context (app.user_hash = hmac_user(user_id))
    - Encrypts text/metadata with AES-256-GCM + AAD binding

    Performance Target:
    - p95 ≤ 750ms (end-to-end, including embedding API)

    Example:
        POST /memory/index
        Authorization: Bearer <token>
        {
            "user_id": "user_123",
            "text": "Long chunk text...",
            "metadata": {"title": "...", "source": "..."},
            "model": "text-embedding-3-small"
        }

        Response:
        {
            "id": "mem_uuid",
            "created_at": "2025-10-20T...",
            "indexed_at": "2025-10-20T...",
            "chunk_index": 0,
            "status": "indexed"
        }
    """
    request_id = str(uuid4())
    start_ms = time.time() * 1000

    try:
        # 1. Verify JWT and extract user_id
        user_id = await _verify_jwt_and_extract_user_id(request)

        # 2. Compute user_hash and RLS context
        user_hash = hmac_user(user_id)
        aad = get_aad_from_user_hash(user_hash)  # noqa: F841 - Phase 3: used in encrypt_with_aad

        # 3. (Phase 3) Database insert with RLS
        # async with set_rls_context(conn, user_id):
        #     # Encrypt
        #     text_envelope = encrypt_with_aad(req.text.encode(), aad, active_key())
        #     # Insert memory_chunks row
        #     ...

        # For Phase 2 scaffold: return mock response
        elapsed_ms = time.time() * 1000 - start_ms
        _record_latency("index", elapsed_ms, user_id=user_id, success=True)

        # Add rate-limit headers
        _add_rate_limit_headers(response)

        return IndexResponse(
            id=str(uuid4()),
            created_at="2025-10-20T00:00:00Z",
            indexed_at="2025-10-20T00:00:01Z",
            chunk_index=0,
            status="indexed",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Index failed (request_id={request_id}): {e}")
        _count_error("index", 500)
        raise HTTPException(status_code=503, detail="Internal server error") from None


# ============================================================================
# Endpoint 2: POST /memory/query
# ============================================================================


@router.post("/query", response_model=QueryResponse, summary="Semantic search with optional reranking")
async def memory_query(request: Request, req: QueryRequest) -> QueryResponse:
    """
    Query memory by semantic similarity.

    Flow:
    1. Verify JWT and set RLS context
    2. Generate query embedding
    3. ANN search (HNSW) with RLS filter
    4. Decrypt top-k results with AAD validation (fail-closed on mismatch)
    5. Optionally rerank with cross-encoder (circuit breaker: 250ms timeout)

    Security:
    - RLS ensures only user's chunks visible
    - AAD validation prevents cross-user access even if DB is compromised
    - Fail-closed: any AAD mismatch returns 403

    Performance Target:
    - p95 ≤ 350ms (including reranking if enabled, with circuit breaker)

    Circuit Breaker:
    - If reranking exceeds 250ms, skip CE and return ANN order (fail-open)
    - Preserves TTFV budget under high load

    Example:
        POST /memory/query
        Authorization: Bearer <token>
        {
            "user_id": "user_123",
            "query": "How do I reset my password?",
            "k": 10,
            "rerank": true
        }

        Response:
        {
            "results": [
                {
                    "id": "mem_uuid",
                    "text": "Password reset steps...",
                    "score": 0.92,
                    "rank": 1,
                    "reranked": true,
                    "original_rank": 3
                }
            ],
            "count": 1,
            "total_available": 23,
            "latency_breakdown": {
                "embedding_ms": 120,
                "ann_search_ms": 45,
                "reranking_ms": 89,
                "decryption_ms": 15,
                "total_ms": 269
            }
        }
    """
    request_id = str(uuid4())
    start_ms = time.time() * 1000

    try:
        # 1. Verify JWT and extract user_id
        user_id = await _verify_jwt_and_extract_user_id(request)

        # 2. Compute user_hash and RLS context
        user_hash = hmac_user(user_id)
        aad = get_aad_from_user_hash(user_hash)  # noqa: F841 - Phase 3: used in decrypt_with_aad

        # 3. (Phase 3) Generate embedding, ANN search, decrypt
        # async with set_rls_context(conn, user_id):
        #     embedding = await embed_query(req.query)
        #     rows = await conn.fetch(
        #         "SELECT id, text_cipher FROM memory_chunks WHERE ... ORDER BY embedding <-> $1 LIMIT $2",
        #         embedding, req.k
        #     )
        #     candidates = []
        #     for row in rows:
        #         try:
        #             plaintext = decrypt_with_aad(row["text_cipher"], aad)
        #             candidates.append(plaintext)
        #         except ValueError:
        #             raise PermissionError("AAD validation failed")
        #
        #     # 4. Reranking with circuit breaker
        #     if req.rerank and RERANK_ENABLED:
        #         try:
        #             ranked = await asyncio.wait_for(
        #                 maybe_rerank(req.query, candidates),
        #                 timeout=RERANK_TIMEOUT_MS / 1000.0
        #             )
        #         except asyncio.TimeoutError:
        #             logger.warning(f"Reranking timeout ({RERANK_TIMEOUT_MS}ms), returning ANN order")
        #             ranked = candidates

        # For Phase 2 scaffold: return mock response
        elapsed_ms = time.time() * 1000 - start_ms
        _record_latency("query", elapsed_ms)

        return QueryResponse(
            results=[
                QueryResult(
                    id=str(uuid4()),
                    text="Sample memory chunk...",
                    score=0.92,
                    rank=1,
                    reranked=False,
                    original_rank=1,
                )
            ],
            count=1,
            total_available=1,
            latency_breakdown={
                "embedding_ms": 120,
                "ann_search_ms": 45,
                "reranking_ms": 0,
                "decryption_ms": 15,
                "total_ms": 180,
            },
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Query failed (request_id={request_id}): {e}")
        _count_error("query", 500)
        raise HTTPException(status_code=503, detail="Internal server error") from None


# ============================================================================
# Endpoint 3: POST /memory/summarize
# ============================================================================


@router.post("/summarize", response_model=SummarizeResponse, summary="Compress memory into summary")
async def memory_summarize(request: Request, req: SummarizeRequest) -> SummarizeResponse:
    """
    Summarize a set of memory chunks.

    Flow:
    1. Verify JWT and set RLS context
    2. Fetch chunks from DB (RLS-filtered)
    3. Decrypt with AAD validation (fail-closed)
    4. Call summarization LLM
    5. Extract entities and key decisions

    Security:
    - RLS ensures only user's chunks accessible
    - AAD validation on every chunk (any mismatch = 403)
    - Summarization prompt includes user_hash to prevent injection

    Performance Target:
    - p95 ≤ 1000ms (dominated by LLM API call)

    Example:
        POST /memory/summarize
        Authorization: Bearer <token>
        {
            "user_id": "user_123",
            "chunk_ids": ["mem_uuid1", "mem_uuid2"],
            "style": "bullet_points",
            "max_tokens": 500
        }
    """
    request_id = str(uuid4())
    start_ms = time.time() * 1000

    try:
        # 1. Verify JWT
        user_id = await _verify_jwt_and_extract_user_id(request)

        # 2. Compute user_hash
        user_hash = hmac_user(user_id)
        aad = get_aad_from_user_hash(user_hash)  # noqa: F841 - Phase 3: used in decrypt_with_aad

        # 3. (Phase 3) Fetch, decrypt, summarize
        # async with set_rls_context(conn, user_id):
        #     chunks = await conn.fetch(
        #         "SELECT id, text_cipher FROM memory_chunks WHERE id = ANY($1)",
        #         req.chunk_ids
        #     )
        #     texts = []
        #     for chunk in chunks:
        #         plaintext = decrypt_with_aad(chunk["text_cipher"], aad)
        #         texts.append(plaintext.decode())
        #     summary = await call_summarization_api(texts, req.style, req.max_tokens)

        elapsed_ms = time.time() * 1000 - start_ms
        _record_latency("summarize", elapsed_ms)

        return SummarizeResponse(
            summary="- Key point 1\n- Key point 2",
            entities=[Entity(name="Alice", type="person", frequency=1, confidence=0.95)],
            key_decisions=["Decided to proceed"],
            tokens_used=150,
            processing_time_ms=int(elapsed_ms),
            model_used="gpt-4o-mini",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Summarize failed (request_id={request_id}): {e}")
        _count_error("summarize", 500)
        raise HTTPException(status_code=503, detail="Internal server error") from None


# ============================================================================
# Endpoint 4: POST /memory/entities
# ============================================================================


@router.post("/entities", response_model=EntitiesResponse, summary="Extract named entities")
async def memory_entities(request: Request, req: EntitiesRequest) -> EntitiesResponse:
    """
    Extract and rank named entities from memory.

    Flow:
    1. Verify JWT and set RLS context
    2. If chunk_ids provided: fetch and decrypt (AAD validation)
    3. If text provided: use directly (already trusted)
    4. Run NER extraction
    5. Filter by entity_types and min_frequency
    6. Rank by frequency

    Security:
    - RLS ensures only user's chunks accessible
    - AAD validation on each chunk
    - No PII in response by default

    Performance Target:
    - p95 ≤ 500ms (local NER model)

    Example:
        POST /memory/entities
        Authorization: Bearer <token>
        {
            "user_id": "user_123",
            "chunk_ids": ["mem_uuid"],
            "entity_types": ["person", "org"],
            "min_frequency": 1
        }
    """
    request_id = str(uuid4())
    start_ms = time.time() * 1000

    try:
        # 1. Verify JWT
        user_id = await _verify_jwt_and_extract_user_id(request)

        # 2. Compute user_hash
        user_hash = hmac_user(user_id)
        aad = get_aad_from_user_hash(user_hash)  # noqa: F841 - Phase 3: used in decrypt_with_aad

        # 3. (Phase 3) Extract entities
        # if req.chunk_ids:
        #     async with set_rls_context(conn, user_id):
        #         chunks = await conn.fetch(...)
        #         texts = [decrypt_with_aad(chunk["text_cipher"], aad).decode() for chunk in chunks]
        # else:
        #     texts = [req.text]
        # entities = await extract_entities(texts, req.entity_types, req.min_frequency)

        elapsed_ms = time.time() * 1000 - start_ms
        _record_latency("entities", elapsed_ms)

        return EntitiesResponse(
            entities=[Entity(name="Sample Org", type="org", frequency=2, confidence=0.9)],
            extraction_time_ms=int(elapsed_ms),
            model_used="ner-small",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Entities failed (request_id={request_id}): {e}")
        _count_error("entities", 500)
        raise HTTPException(status_code=503, detail="Internal server error") from None


# ============================================================================
# Rate-limit headers (Phase 3: wired via FastAPI app middleware)
# ============================================================================
# Note: Middleware will be added at app level in webapi.py
# For now, individual endpoints include rate-limit headers in responses
# Phase 3: Migrate to centralized middleware with actual limiter integration
