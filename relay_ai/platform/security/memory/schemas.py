"""
Pydantic schemas for Task D memory APIs.

Sprint 62 Phase 2: Request/response models for /memory/* endpoints.
Validates input, enforces size limits, whitelists models, and provides fail-closed validation.
"""

from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator

# Request Models


class IndexRequest(BaseModel):
    """Request to insert/upsert a memory chunk."""

    user_id: str = Field(..., description="User identifier", min_length=1, max_length=255)
    text: str = Field(..., description="Chunk text", min_length=1, max_length=50000)
    metadata: Optional[dict[str, Any]] = Field(default=None, description="Optional metadata (JSON)", max_length=10000)
    model: Optional[str] = Field(
        default="text-embedding-3-small",
        description="Embedding model (whitelisted)",
        pattern="^[a-z0-9_-]+$",
    )
    doc_id: Optional[str] = Field(default=None, description="Source document ID")
    source: Optional[str] = Field(
        default="api",
        description="Source type: api, chat, email, upload",
        pattern="^(api|chat|email|upload)$",
    )
    tags: Optional[list[str]] = Field(default=None, description="Search tags")

    @field_validator("metadata")
    @classmethod
    def validate_metadata_size(cls, v):
        """Enforce metadata JSON size limit."""
        if v is not None and len(str(v)) > 10000:
            raise ValueError("Metadata too large (max 10KB)")
        return v


class QueryRequest(BaseModel):
    """Request to query memory by semantic similarity."""

    user_id: str = Field(..., description="User identifier", min_length=1, max_length=255)
    query: str = Field(..., description="Search query", min_length=1, max_length=2000)
    k: int = Field(default=24, description="Results to return", ge=1, le=100)
    rerank: bool = Field(default=True, description="Enable cross-encoder reranking")


class SummarizeRequest(BaseModel):
    """Request to summarize memory chunks."""

    user_id: str = Field(..., description="User identifier", min_length=1, max_length=255)
    chunk_ids: list[str] = Field(..., description="Chunk IDs to summarize", min_length=1, max_length=50)
    style: str = Field(
        default="bullet_points",
        description="Summary style",
        pattern="^(bullet_points|narrative|key_takeaways)$",
    )
    max_tokens: int = Field(default=500, description="Max tokens in summary", ge=50, le=2000)


class EntitiesRequest(BaseModel):
    """Request to extract named entities from memory."""

    user_id: str = Field(..., description="User identifier", min_length=1, max_length=255)
    chunk_ids: Optional[list[str]] = Field(default=None, description="Specific chunk IDs to extract from")
    text: Optional[str] = Field(default=None, description="Or provide raw text")
    entity_types: Optional[list[str]] = Field(
        default=None,
        description="Filter by entity type: person, org, location, product",
    )
    min_frequency: int = Field(default=1, description="Min occurrences to include", ge=1, le=1000)

    @field_validator("entity_types")
    @classmethod
    def validate_entity_types(cls, v):
        """Whitelist entity types."""
        allowed = {"person", "org", "location", "product"}
        if v and not all(t in allowed for t in v):
            raise ValueError(f"Invalid entity types. Allowed: {allowed}")
        return v


# Response Models


class IndexResponse(BaseModel):
    """Response from index endpoint."""

    id: str = Field(..., description="Chunk UUID")
    created_at: str = Field(..., description="ISO timestamp")
    indexed_at: str = Field(..., description="ISO timestamp")
    chunk_index: int = Field(..., description="Position in document")
    status: str = Field(..., description="indexed, updated, or skipped")


class QueryResult(BaseModel):
    """Single result from query."""

    id: str
    text: str
    metadata: Optional[dict[str, Any]] = None
    score: float
    rank: int
    reranked: bool
    original_rank: int


class QueryResponse(BaseModel):
    """Response from query endpoint."""

    results: list[QueryResult]
    count: int = Field(..., description="Results returned")
    total_available: int = Field(..., description="Total matches available")
    latency_breakdown: Optional[dict[str, float]] = Field(default=None, description="Latency by component (ms)")


class Entity(BaseModel):
    """Named entity."""

    name: str
    type: str
    frequency: int
    contexts: Optional[list[str]] = None
    confidence: float = Field(ge=0.0, le=1.0)


class SummarizeResponse(BaseModel):
    """Response from summarize endpoint."""

    summary: str
    entities: list[Entity] = Field(default_factory=list)
    key_decisions: list[str] = Field(default_factory=list)
    tokens_used: int
    processing_time_ms: int
    model_used: str


class EntitiesResponse(BaseModel):
    """Response from entities endpoint."""

    entities: list[Entity]
    extraction_time_ms: int
    model_used: str


# Error Response


class ErrorResponse(BaseModel):
    """Standard error response."""

    detail: str = Field(..., description="Error message")
    code: str = Field(..., description="Error code: AUTH_REQUIRED, PERMISSION_DENIED, VALIDATION_ERROR, etc.")
    request_id: Optional[str] = Field(default=None, description="Correlation ID for debugging")
