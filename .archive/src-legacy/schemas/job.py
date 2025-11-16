"""Job tracking schemas - Sprint 58 Slice 6.

Minimal job lifecycle model for action execution tracking.
Stores per-step status, timestamps, and redacted results.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class JobStatus(str, Enum):
    """Job execution status."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"


class JobRecord(BaseModel):
    """Single job execution record.

    Tracks one action's execution within a plan step.
    Stores status, timestamps, and redacted result/error.
    """

    model_config = ConfigDict(extra="forbid")

    job_id: str = Field(..., description="Unique job identifier (UUID)")
    user_id: str = Field(..., description="User who initiated job")
    plan_id: Optional[str] = Field(None, description="Parent plan UUID (for correlation)")
    action_id: str = Field(..., description="Action identifier (e.g., 'gmail.send')")
    status: JobStatus = Field(default=JobStatus.PENDING, description="Current execution status")
    created_at: datetime = Field(..., description="Job creation timestamp")
    started_at: Optional[datetime] = Field(None, description="Execution start timestamp")
    finished_at: Optional[datetime] = Field(None, description="Execution finish timestamp")
    error: Optional[str] = Field(None, description="Error message if failed (redacted)")
    result: Optional[dict[str, Any]] = Field(None, description="Execution result (redacted)")
