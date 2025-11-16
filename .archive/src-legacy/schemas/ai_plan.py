"""AI Action Plan Schemas - Sprint 58 Slice 5 Foundations.

Pydantic schemas for AI action planning with strict validation.
These schemas define the structure for:
- Natural language → structured action plans (PlannedAction, PlanResult)
- Action execution results and dependency tracking
- Multi-step workflow orchestration

Sprint 58 Foundations: Extracted from relay_ai.ai.planner for reusability and testing.
Sprint 58 Slice 5: Added strict validation (extra='forbid', params bounds, action_id regex).
"""

import json
import re
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Security constants (Sprint 58 hardening)
ACTION_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$")
MAX_PARAMS_KEYS = 50
MAX_PARAMS_DEPTH = 5
MAX_PARAMS_STRLEN = 10_000

SENSITIVE_KEYS = {
    "password",
    "token",
    "authorization",
    "api_key",
    "apiKey",
    "secret",
    "bearer",
    "access_token",
    "refresh_token",
    "auth",
}


def _max_depth(obj: Any, depth: int = 0) -> int:
    """Calculate maximum nesting depth of an object."""
    if not isinstance(obj, (dict, list, tuple)):
        return depth
    if isinstance(obj, dict):
        return max([depth] + [_max_depth(v, depth + 1) for v in obj.values()]) if obj else depth
    return max([depth] + [_max_depth(v, depth + 1) for v in obj]) if obj else depth


def _json_strlen(obj: Any) -> int:
    """Get approximate serialized JSON length."""
    try:
        return len(json.dumps(obj))
    except Exception:
        return 0


class PlannedAction(BaseModel):
    """Single action in a multi-step plan.

    Represents one atomic step in an AI-generated action plan.
    Actions can depend on previous actions via depends_on indices.

    Example:
        action = PlannedAction(
            action_id="gmail.send",
            description="Send thank you email to John",
            params={"to": "john@example.com", "subject": "Thank you"},
            depends_on=None
        )
    """

    model_config = ConfigDict(extra="forbid")  # Reject unknown fields (Sprint 58 hardening)

    action_id: str = Field(
        ..., description="Action identifier (e.g., 'gmail.send', 'calendar.create_event')", min_length=1
    )
    description: str = Field(..., description="Human-readable explanation of what this action does", min_length=1)
    params: dict[str, Any] = Field(default_factory=dict, description="Action parameters extracted from user prompt")
    depends_on: Optional[list[int]] = Field(None, description="List of step indices this action depends on (0-indexed)")

    @field_validator("action_id")
    @classmethod
    def validate_action_id_format(cls, v: str) -> str:
        """Validate action_id follows 'provider.action' format (strict: lowercase alphanumeric + underscore)."""
        if not ACTION_ID_PATTERN.match(v):
            raise ValueError(
                f"action_id must match 'provider.action' with lowercase letters/digits/underscores, got: {v}"
            )
        return v

    @field_validator("params")
    @classmethod
    def validate_params(cls, v: dict[str, Any]) -> dict[str, Any]:
        """Validate params size, depth, and nesting constraints (Sprint 58 hardening)."""
        if len(v) > MAX_PARAMS_KEYS:
            raise ValueError(f"params has {len(v)} keys, max is {MAX_PARAMS_KEYS}")
        if _max_depth(v) > MAX_PARAMS_DEPTH:
            raise ValueError(f"params nesting depth exceeds {MAX_PARAMS_DEPTH}")
        if _json_strlen(v) > MAX_PARAMS_STRLEN:
            raise ValueError(f"params serialized size exceeds {MAX_PARAMS_STRLEN} bytes")
        return v

    @field_validator("depends_on")
    @classmethod
    def validate_depends_on(cls, v: Optional[list[int]]) -> Optional[list[int]]:
        """Validate depends_on indices are non-negative."""
        if v is not None:
            if any(idx < 0 for idx in v):
                raise ValueError("depends_on indices must be non-negative")
        return v


class PlanResult(BaseModel):
    """Structured plan generated from natural language prompt.

    The complete output of the AI planner, including:
    - Original prompt and extracted intent
    - Ordered list of actions to execute
    - Confidence score and explanation

    Example:
        plan = PlanResult(
            prompt="Send thank you email to John",
            intent="send_email",
            steps=[PlannedAction(...)],
            confidence=0.95,
            explanation="Clear request with all required info"
        )
    """

    model_config = ConfigDict(extra="forbid")  # Reject unknown fields (Sprint 58 hardening)

    prompt: str = Field(..., description="Original user prompt", min_length=1)
    intent: str = Field(..., description="Extracted intent (e.g., 'send_email_and_schedule')", min_length=1)
    steps: list[PlannedAction] = Field(default_factory=list, description="Ordered action steps to execute")
    confidence: float = Field(..., description="Confidence in plan accuracy (0.0-1.0)", ge=0.0, le=1.0)
    explanation: str = Field(..., description="Why the AI chose this plan", min_length=1)

    @field_validator("steps")
    @classmethod
    def validate_steps_dependencies(cls, v: list[PlannedAction]) -> list[PlannedAction]:
        """Validate that all depends_on indices are valid and acyclic."""
        n = len(v)
        for i, step in enumerate(v):
            if step.depends_on:
                for dep_idx in step.depends_on:
                    if dep_idx == i:
                        raise ValueError(f"Step {i} has self-reference in depends_on")
                    if dep_idx >= i:
                        raise ValueError(
                            f"Step {i} depends on step {dep_idx}, but dependencies must reference earlier steps"
                        )
                    if dep_idx >= n:
                        raise ValueError(f"Step {i} depends on step {dep_idx}, but only {n} steps exist")
        return v

    def safe_dict(self) -> dict[str, Any]:
        """Export plan with sensitive fields in params redacted.

        Prevents accidental PII leak in API responses. Redacts known sensitive keys
        (password, token, api_key, etc.) with ***REDACTED***.
        """

        def redact_sensitive(obj: Any) -> Any:
            """Recursively redact sensitive keys."""
            if isinstance(obj, dict):
                return {
                    k: "***REDACTED***" if k.lower() in SENSITIVE_KEYS else redact_sensitive(v) for k, v in obj.items()
                }
            if isinstance(obj, list):
                return [redact_sensitive(v) for v in obj]
            return obj

        data = self.model_dump()
        for step in data.get("steps", []):
            step["params"] = redact_sensitive(step.get("params", {}))
        return data


# Legacy aliases for backward compatibility with src.ai.planner
ActionStep = PlannedAction
ActionPlan = PlanResult
