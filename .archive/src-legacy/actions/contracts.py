"""Actions API contracts and Pydantic models.

Sprint 49 Phase B: Real actions framework with provider adapters.
"""

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class Provider(str, Enum):
    """Action provider types."""

    INDEPENDENT = "independent"
    MICROSOFT = "microsoft"
    GOOGLE = "google"
    APPLE_BRIDGE = "apple_bridge"


class ActionStatus(str, Enum):
    """Action execution status."""

    PENDING = "pending"
    PREVIEW = "preview"
    EXECUTING = "executing"
    SUCCESS = "success"
    FAILED = "failed"


class ActionDefinition(BaseModel):
    """Action schema returned by /actions list endpoint."""

    id: str = Field(..., description="Unique action identifier (e.g., 'webhook.save')")
    name: str = Field(..., description="Human-readable action name")
    description: str = Field(..., description="Action description")
    provider: Provider = Field(..., description="Provider type")
    schema_: dict[str, Any] = Field(..., alias="schema", description="JSON Schema for action parameters")
    enabled: bool = Field(True, description="Whether action is enabled for execution")


class PreviewRequest(BaseModel):
    """Request to preview an action."""

    action: str = Field(..., description="Action ID (e.g., 'webhook.save')")
    params: dict[str, Any] = Field(..., description="Action parameters")


class PreviewResponse(BaseModel):
    """Response from action preview."""

    preview_id: str = Field(..., description="Preview ID for execution")
    action: str = Field(..., description="Action ID")
    provider: Provider = Field(..., description="Provider type")
    summary: str = Field(..., description="Human-readable summary of what will happen")
    params: dict[str, Any] = Field(..., description="Validated parameters")
    warnings: list[str] = Field(default_factory=list, description="Preview warnings")
    expires_at: str = Field(..., description="Preview expiry timestamp (ISO 8601)")


class ExecuteRequest(BaseModel):
    """Request to execute a previewed action."""

    preview_id: str = Field(..., description="Preview ID from preview response")
    idempotency_key: Optional[str] = Field(None, description="Client-provided idempotency key (UUID v4)")


class ExecuteResponse(BaseModel):
    """Response from action execution."""

    run_id: str = Field(..., description="Unique execution run ID")
    action: str = Field(..., description="Action ID")
    provider: Provider = Field(..., description="Provider type")
    status: ActionStatus = Field(..., description="Execution status")
    result: Optional[dict[str, Any]] = Field(None, description="Execution result data")
    error: Optional[str] = Field(None, description="Error message if failed")
    duration_ms: Optional[int] = Field(None, description="Execution duration in milliseconds")
    request_id: str = Field(..., description="Request ID for tracing")


class ActionError(BaseModel):
    """Error response from actions API."""

    error: str = Field(..., description="Error message")
    code: str = Field(..., description="Error code")
    details: Optional[dict[str, Any]] = Field(None, description="Additional error details")
