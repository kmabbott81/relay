"""Pydantic models for /api/v1/stream validation.

Sprint 61b R0.5 Security Hotfix: Input validation (length, enum, format).
"""

from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field, constr, validator

# Allowed models (whitelist)
ALLOWED_MODELS = {"gpt-4o", "gpt-4o-mini", "claude-3.5-sonnet"}


class StreamRequest(BaseModel):
    """Validated streaming request."""

    message: constr(min_length=1, max_length=8192) = Field(..., description="User message (1-8192 chars)")
    model: str = Field(default="gpt-4o-mini", description="Model name (whitelist enforced)")
    stream_id: Optional[UUID] = Field(default=None, description="Optional idempotency key (UUIDv4)")
    cost_cap_usd: float = Field(default=0.50, ge=0.0, le=1.0, description="Cost safety cap ($0-$1)")

    @validator("model")
    def validate_model(cls, v):
        """Validate model is whitelisted."""
        if v not in ALLOWED_MODELS:
            raise ValueError(f"Model must be one of {ALLOWED_MODELS}, got {v}")
        return v

    @validator("message")
    def validate_message_not_blank(cls, v):
        """Validate message is not just whitespace."""
        if not v or not v.strip():
            raise ValueError("Message cannot be empty or whitespace only")
        return v

    class Config:
        schema_extra = {
            "example": {
                "message": "Explain quantum computing",
                "model": "gpt-4o-mini",
                "stream_id": "123e4567-e89b-12d3-a456-426614174000",
                "cost_cap_usd": 0.10,
            }
        }


class AnonymousSessionRequest(BaseModel):
    """Request to mint anonymous session token."""

    ttl_seconds: int = Field(default=604800, ge=3600, le=2592000, description="Token TTL (1h to 30d)")

    class Config:
        schema_extra = {"example": {"ttl_seconds": 604800}}


class StreamError(BaseModel):
    """Error response (sanitized, no stack traces)."""

    error_code: str = Field(..., description="Error category (rate_limited, quota_exceeded, invalid_input)")
    detail: str = Field(..., description="User-friendly message")
    retry_after: Optional[int] = Field(None, description="Seconds to wait before retry")

    class Config:
        schema_extra = {
            "example": {
                "error_code": "rate_limited",
                "detail": "Rate limited: 30 requests per 30s",
                "retry_after": 30,
            }
        }
