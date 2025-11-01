# Knowledge API Schemas — Pydantic v2 Models
# Date: 2025-10-31
# Phase: R2 Phase 2 (Implementation)
# Purpose: Request/response validation with full security context

from datetime import datetime
from enum import Enum
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

# ============================================================================
# ENUMS
# ============================================================================


class FileSource(str, Enum):
    """Source of file upload"""

    UPLOAD = "upload"
    API = "api"
    EMAIL = "email"
    SLACK = "slack"


class ChunkStrategy(str, Enum):
    """Chunking strategy for text splitting"""

    SMART = "smart"
    FIXED_SIZE = "fixed_size"
    SEMANTIC = "semantic"


class EmbeddingModel(str, Enum):
    """Embedding model selection"""

    ADA_002 = "ada-002"
    LOCAL = "local"
    CUSTOM = "custom"


class ErrorCode(str, Enum):
    """Standardized error codes"""

    INVALID_JWT = "INVALID_JWT"
    RLS_VIOLATION = "RLS_VIOLATION"
    AAD_MISMATCH = "AAD_MISMATCH"
    FILE_NOT_FOUND = "FILE_NOT_FOUND"
    RATE_LIMIT_EXCEEDED = "RATE_LIMIT_EXCEEDED"
    EMBEDDING_SERVICE_DOWN = "EMBEDDING_SERVICE_DOWN"
    INVALID_FILE_FORMAT = "INVALID_FILE_FORMAT"
    FILE_TOO_LARGE = "FILE_TOO_LARGE"


# ============================================================================
# REQUEST MODELS
# ============================================================================


class FileUploadRequest(BaseModel):
    """Request model for POST /api/v2/knowledge/upload (multipart form)"""

    title: Optional[str] = Field(None, max_length=255, description="File title")
    description: Optional[str] = Field(None, max_length=1000, description="File description")
    source: FileSource = Field(FileSource.UPLOAD, description="Upload source")
    tags: list[str] = Field(default_factory=list, max_length=10, description="File tags (max 10)")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Custom metadata (max 2KB)")

    @field_validator("metadata")
    @classmethod
    def validate_metadata_size(cls, v: dict) -> dict:
        """Ensure metadata doesn't exceed 2KB when serialized"""
        import json

        if len(json.dumps(v)) > 2048:
            raise ValueError("Metadata exceeds 2KB limit")
        return v

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, v: list[str]) -> list[str]:
        """Validate tag format"""
        for tag in v:
            if not (1 <= len(tag) <= 50):
                raise ValueError("Tag length must be 1-50 characters")
            if not all(c.isalnum() or c in "-_" for c in tag):
                raise ValueError("Tags can only contain alphanumeric, dash, and underscore")
        return v

    model_config = {
        "json_schema_extra": {
            "example": {
                "title": "Q4 Financial Report",
                "description": "Quarterly financial analysis",
                "source": "upload",
                "tags": ["finance", "2025"],
                "metadata": {"author": "John Doe"},
            }
        }
    }


class FileIndexRequest(BaseModel):
    """Request model for POST /api/v2/knowledge/index"""

    file_id: UUID = Field(..., description="File ID from upload response")
    chunk_strategy: ChunkStrategy = Field(ChunkStrategy.SMART, description="Text chunking strategy")
    chunk_overlap: int = Field(100, ge=0, le=500, description="Overlap between chunks in tokens")
    embedding_model: EmbeddingModel = Field(EmbeddingModel.ADA_002, description="Embedding model to use")
    rerank: bool = Field(True, description="Enable reranking")

    model_config = {
        "json_schema_extra": {
            "example": {
                "file_id": "550e8400-e29b-41d4-a716-446655440000",
                "chunk_strategy": "smart",
                "chunk_overlap": 100,
                "embedding_model": "ada-002",
                "rerank": True,
            }
        }
    }


class SearchRequest(BaseModel):
    """Request model for POST /api/v2/knowledge/search"""

    query: str = Field(..., max_length=2000, description="Search query")
    query_embedding: Optional[list[float]] = Field(None, description="Pre-computed embedding (1536-dim for ada-002)")
    filters: Optional[dict[str, Any]] = Field(None, description="Search filters")
    top_k: int = Field(10, ge=1, le=100, description="Number of results to return")
    similarity_threshold: float = Field(0.7, ge=0.0, le=1.0, description="Minimum similarity score (0.0-1.0)")
    include_metadata: bool = Field(True, description="Include metadata in results")

    @field_validator("filters")
    @classmethod
    def validate_filters(cls, v: Optional[dict]) -> Optional[dict]:
        """Validate filter schema"""
        if v is None:
            return v
        allowed_keys = {"tags", "source", "created_after", "created_before"}
        for key in v.keys():
            if key not in allowed_keys:
                raise ValueError(f"Invalid filter key: {key}. Allowed: {allowed_keys}")
        return v

    model_config = {
        "json_schema_extra": {
            "example": {
                "query": "financial metrics",
                "filters": {"tags": ["finance"], "source": "upload"},
                "top_k": 10,
                "similarity_threshold": 0.7,
            }
        }
    }


# ============================================================================
# RESPONSE MODELS
# ============================================================================


class FileUploadResponse(BaseModel):
    """Response for POST /api/v2/knowledge/upload (202 Accepted)"""

    file_id: UUID = Field(..., description="Unique file ID")
    status: str = Field("queued", description="Processing status")
    request_id: UUID = Field(..., description="Request ID for tracing")
    message: str = Field("File queued for processing", description="Status message")
    expected_completion_ms: int = Field(5000, description="Estimated completion time (ms)")


class FileIndexResponse(BaseModel):
    """Response for POST /api/v2/knowledge/index (200 OK)"""

    file_id: UUID = Field(..., description="File ID indexed")
    chunks_created: int = Field(..., description="Number of chunks created")
    tokens_processed: int = Field(..., description="Total tokens processed")
    embedding_latency_ms: int = Field(..., description="Embedding generation latency")
    embedding_model_used: str = Field(..., description="Embedding model used")
    vectors_stored: int = Field(..., description="Vectors successfully stored")
    file_url: str = Field(..., description="URL to access file metadata")
    status: str = Field("indexed", description="Indexing status")


class Entity(BaseModel):
    """Entity extracted from knowledge"""

    name: str = Field(..., description="Entity name")
    entity_type: str = Field(..., description="Type (PERSON, ORG, LOCATION, etc.)")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score")


class SearchResultItem(BaseModel):
    """Single result from vector search"""

    rank: int = Field(..., description="Rank in result set (1-indexed)")
    chunk_id: UUID = Field(..., description="Chunk ID")
    file_id: UUID = Field(..., description="Parent file ID")
    file_title: str = Field(..., description="File title")
    text: str = Field(..., description="Chunk text content")
    similarity_score: float = Field(..., ge=0.0, le=1.0, description="Cosine similarity score")
    chunk_index: int = Field(..., description="Chunk index in file")
    metadata: dict[str, Any] = Field(..., description="Chunk metadata")
    position_in_file: Optional[dict[str, Any]] = Field(None, description="Position in file (page, section, etc.)")


class SearchResponse(BaseModel):
    """Response for POST /api/v2/knowledge/search (200 OK)"""

    query: str = Field(..., description="Original query")
    results: list[SearchResultItem] = Field(..., description="Search results")
    total_results: int = Field(..., description="Total matching results")
    latency_ms: int = Field(..., description="Query latency (ms)")
    embedding_model_used: str = Field(..., description="Embedding model used")
    cache_hit: bool = Field(False, description="Whether result was from cache")


class FileMetadata(BaseModel):
    """File metadata in list response"""

    file_id: UUID = Field(..., description="File ID")
    title: str = Field(..., description="File title")
    source: FileSource = Field(..., description="Upload source")
    size_bytes: int = Field(..., description="File size in bytes")
    chunks_count: int = Field(..., description="Number of chunks")
    created_at: datetime = Field(..., description="Creation timestamp")
    indexed_at: Optional[datetime] = Field(None, description="Indexing completion time")
    tags: list[str] = Field(default_factory=list, description="File tags")
    url: str = Field(..., description="File metadata URL")


class FileListResponse(BaseModel):
    """Response for GET /api/v2/knowledge/files (200 OK)"""

    files: list[FileMetadata] = Field(..., description="File list")
    total: int = Field(..., description="Total file count")
    limit: int = Field(..., description="Page limit")
    offset: int = Field(..., description="Page offset")
    next_page_url: Optional[str] = Field(None, description="Next page URL")


class FileDeleteResponse(BaseModel):
    """Response for DELETE /api/v2/knowledge/files/{id} (204 No Content)"""

    status: str = Field("deleted", description="Deletion status")
    request_id: UUID = Field(..., description="Request ID")


class ErrorResponse(BaseModel):
    """Standardized error response (4xx, 5xx)"""

    error_code: str = Field(..., description="Error code enum")
    detail: str = Field(..., description="Human-readable error message")
    request_id: UUID = Field(..., description="Request ID for support")
    suggestion: Optional[str] = Field(None, description="Suggested action for user")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "error_code": "INVALID_JWT",
                    "detail": "Token expired or invalid",
                    "request_id": "550e8400-e29b-41d4-a716-446655440000",
                    "suggestion": "Refresh your authentication token and try again",
                },
                {
                    "error_code": "RATE_LIMIT_EXCEEDED",
                    "detail": "Too many requests",
                    "request_id": "550e8400-e29b-41d4-a716-446655440001",
                    "suggestion": "Wait 60 seconds before retrying. Upgrade to Pro for higher limits.",
                },
                {
                    "error_code": "FILE_TOO_LARGE",
                    "detail": "File exceeds 50MB limit",
                    "request_id": "550e8400-e29b-41d4-a716-446655440002",
                    "suggestion": "Compress the file or split into smaller pieces (max 50MB each)",
                },
            ]
        }
    }


class SummarizeRequest(BaseModel):
    """Request for POST /api/v2/knowledge/summarize"""

    query: str = Field(..., max_length=2000, description="Summary query/topic")
    top_k: int = Field(10, ge=1, le=100, description="Number of chunks to summarize")
    max_length: Optional[int] = Field(None, description="Max summary length in tokens")


class SummarizeResponse(BaseModel):
    """Response for POST /api/v2/knowledge/summarize"""

    query: str = Field(..., description="Original query")
    summary: str = Field(..., description="Generated summary")
    source_chunks: int = Field(..., description="Number of chunks used")
    latency_ms: int = Field(..., description="Generation latency")


class EntitiesRequest(BaseModel):
    """Request for POST /api/v2/knowledge/entities"""

    query: str = Field(..., max_length=2000, description="Entity extraction query")
    top_k: int = Field(10, ge=1, le=100, description="Number of chunks to analyze")
    entity_types: Optional[list[str]] = Field(None, description="Filter to specific entity types")


class EntitiesResponse(BaseModel):
    """Response for POST /api/v2/knowledge/entities"""

    query: str = Field(..., description="Original query")
    entities: list[Entity] = Field(..., description="Extracted entities")
    source_chunks: int = Field(..., description="Number of chunks analyzed")
    latency_ms: int = Field(..., description="Extraction latency")


# ============================================================================
# INTERNAL MODELS (Not exposed in API)
# ============================================================================


class FileEmbedding(BaseModel):
    """Internal model for stored embeddings"""

    id: UUID
    file_id: UUID
    chunk_index: int
    text_content: str
    embedding: list[float]  # 1536-dim for ada-002
    user_hash: str
    metadata_encrypted: bytes
    metadata_aad: str
    created_at: datetime


class EmbeddingJob(BaseModel):
    """Internal model for async job tracking"""

    id: UUID
    file_id: UUID
    user_hash: str
    status: str  # queued, processing, completed, failed
    chunks_created: int = 0
    tokens_processed: int = 0
    latency_ms: Optional[int] = None
    error_message: Optional[str] = None
    attempt_count: int = 0
    max_attempts: int = 3


# ============================================================================
# End of Schemas
# ============================================================================

"""
Pydantic v2 Validation Features Used:
- Field validators: metadata_size, tags format, filters schema
- Size constraints: max_length on strings, max_items on lists
- Numeric bounds: ge/le for integers and floats
- Enums: FileSource, ChunkStrategy, EmbeddingModel, ErrorCode
- Optional fields with defaults
- json_schema_extra for examples and documentation

Security Considerations:
- No user_hash or internal IDs exposed in API models
- Error responses sanitized (no stack traces, file paths, or system info)
- AAD binding documented but not exposed in schema (handled in security layer)
- RLS enforcement at DB layer, not modeled here
"""
