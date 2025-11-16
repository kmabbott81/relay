"""AI Orchestrator with permissions guards + job tracking - Sprint 58 Slice 6.

Manages action plan execution with role-based permission filtering and job lifecycle tracking.
"""

import re
from collections.abc import Mapping
from typing import Any, Optional
from uuid import uuid4

from relay_ai.ai.job_store import JobStore, get_job_store
from relay_ai.schemas.ai_plan import PlanResult
from relay_ai.schemas.permissions import RBACRegistry, default_rbac
from relay_ai.telemetry import jobs as job_metrics


class AIOrchestrator:
    """Orchestrator for AI-planned action execution with RBAC + job tracking."""

    def __init__(self, rbac: Optional[RBACRegistry] = None, job_store: Optional[JobStore] = None):
        """Initialize orchestrator with optional RBAC registry and job store.

        Args:
            rbac: RBAC registry (defaults to built-in roles if None)
            job_store: Job store (defaults to global singleton if None; useful for testing)
        """
        self.rbac = rbac or default_rbac()
        self.job_store = job_store or get_job_store()

    def _guard_plan_steps(self, user_id: str, plan: PlanResult) -> PlanResult:
        """Filter plan steps based on user permissions.

        Removes disallowed actions and returns filtered plan.
        If all steps are filtered, returns empty plan with explanation.

        Args:
            user_id: User UUID
            plan: Original plan from AI planner

        Returns:
            Filtered plan with only allowed actions
        """
        # Get user permissions
        user_perms = self.rbac.get_user_permissions(user_id)

        # Filter steps
        allowed_steps = [step for step in plan.steps if user_perms.can_execute(step.action_id)]

        # Return filtered plan (or original if all allowed)
        if len(allowed_steps) == len(plan.steps):
            return plan

        # Create new plan with allowed steps only
        return PlanResult(
            prompt=plan.prompt,
            intent=plan.intent,
            steps=allowed_steps,
            confidence=plan.confidence * (len(allowed_steps) / len(plan.steps)) if plan.steps else 0.0,
            explanation=f"{plan.explanation} (filtered by permissions: {len(plan.steps) - len(allowed_steps)} steps removed)",
        )

    async def plan(
        self,
        user_id: str,
        prompt: str,
        planner: Any,  # src.ai.planner.ActionPlanner
        context: Optional[dict[str, Any]] = None,
    ) -> tuple[PlanResult, str]:
        """Generate and guard action plan, returning (plan, plan_id) for correlation.

        Args:
            user_id: User UUID
            prompt: Natural language prompt
            planner: ActionPlanner instance
            context: Optional execution context

        Returns:
            Tuple of (filtered_plan, plan_id) for job correlation
        """
        # Generate plan
        plan = await planner.plan(prompt, context)

        # Guard: filter disallowed steps
        guarded_plan = self._guard_plan_steps(user_id, plan)

        # Return plan with explicit correlation ID (no hidden attributes)
        plan_id = str(uuid4())
        return guarded_plan, plan_id

    async def execute_plan(
        self,
        user_id: str,
        plan: PlanResult,
        executor: Any,  # src.actions.execution.ActionExecutor
        plan_id: str,
        workspace_id: str = "default",
    ) -> dict[str, Any]:
        """Execute plan with pre-execute permission re-check + job tracking.

        Args:
            user_id: User UUID
            plan: Action plan (should be pre-guarded)
            executor: ActionExecutor instance
            plan_id: Correlation ID from plan() tuple (required)
            workspace_id: Workspace UUID

        Returns:
            Execution results per step with job IDs and plan_id
        """
        # Re-guard: final permission check before execute
        guarded_plan = self._guard_plan_steps(user_id, plan)

        # Check if plan is empty after filtering
        if not guarded_plan.steps:
            return {
                "success": False,
                "error": "No executable actions: all steps filtered by permissions",
                "steps_executed": 0,
                "steps_denied": len(plan.steps),
                "plan_id": plan_id,
            }

        # Execute guarded steps with job tracking
        results = []
        for idx, step in enumerate(guarded_plan.steps):
            # Create job record for this step
            job = await self.job_store.create(
                user_id=user_id,
                action_id=step.action_id,
                plan_id=plan_id,
            )

            try:
                # Mark job as running
                await self.job_store.start(job.job_id)

                # Execute step
                preview = executor.preview(step.action_id, step.params)
                raw_result = await executor.execute(
                    preview_id=preview.preview_id,
                    workspace_id=workspace_id,
                    actor_id=user_id,
                )

                # Normalize result to dict
                normalized_result = _normalize_result(raw_result)

                # Emit metrics BEFORE job store mutation (for resilience)
                job_metrics.inc_job("success")
                try:
                    provider = job_metrics._provider_from_action_id(step.action_id)
                    job_metrics.inc_job_by_provider(provider, "success")
                except ValueError:
                    # Skip provider metrics if action_id format is invalid
                    provider = None

                # Mark job as success with normalized result
                updated_job = await self.job_store.finish_ok(job.job_id, result=normalized_result)

                # Record latency after job state updated
                if provider and updated_job and updated_job.started_at and updated_job.finished_at:
                    latency = (updated_job.finished_at - updated_job.started_at).total_seconds()
                    job_metrics.observe_job_latency(provider, max(0.0, latency))

                results.append(
                    {
                        "step_index": idx,
                        "action_id": step.action_id,
                        "job_id": job.job_id,
                        "status": normalized_result.get("status", "success"),
                        "result": normalized_result.get("result"),
                    }
                )
            except Exception as e:
                # Safe error string (regex-based PII scrubbing)
                error_msg = _safe_error_str(e)

                # Emit metrics BEFORE job store mutation (for resilience)
                job_metrics.inc_job("failed")
                try:
                    provider = job_metrics._provider_from_action_id(step.action_id)
                    job_metrics.inc_job_by_provider(provider, "failed")
                except ValueError:
                    # Skip provider metrics if action_id format is invalid
                    provider = None

                # Mark job as failed
                updated_job = await self.job_store.finish_err(job.job_id, error=error_msg)

                # Record latency after job state updated
                if provider and updated_job and updated_job.started_at and updated_job.finished_at:
                    latency = (updated_job.finished_at - updated_job.started_at).total_seconds()
                    job_metrics.observe_job_latency(provider, max(0.0, latency))

                results.append(
                    {
                        "step_index": idx,
                        "action_id": step.action_id,
                        "job_id": job.job_id,
                        "status": "failed",
                        "error": error_msg,
                    }
                )

        return {
            "success": True,
            "steps_executed": len(results),
            "results": results,
            "plan_id": plan_id,
        }


def _normalize_result(raw: Any) -> dict[str, Any]:
    """Normalize executor result to dict.

    Handles both dict and object-based results. Extracts standard fields:
    status, result, error. Caller is responsible for PII redaction upstream.

    Args:
        raw: Executor result (dict or object with attributes)

    Returns:
        Normalized dict with status, result, error fields
    """
    if isinstance(raw, Mapping):
        return dict(raw)

    out = {}
    for attr in ("status", "result", "error"):
        if hasattr(raw, attr):
            out[attr] = getattr(raw, attr)
    return out


def _safe_error_str(e: Exception, max_len: int = 500) -> str:
    """Convert exception to safe error string.

    Performs regex-based scrubbing for common PII patterns (credentials, tokens, keys, etc.)
    and caps length to prevent log injection. Caller remains responsible for
    full PII redaction if error originates from user input.

    Args:
        e: Exception to convert
        max_len: Max length of error string (default 500)

    Returns:
        Scrubbed, length-capped error message
    """
    s = str(e)

    # Regex patterns for common credential formats (case-insensitive)
    patterns = [
        # Credential keys and values: api_key=..., token: ..., etc.
        r"(?i)(api[_-]?key|auth[_-]?token|access[_-]?token|secret[_-]?key|authorization)[\s:=]+[^\s;,}]+",
        # Bearer tokens (followed by token value)
        r"(?i)bearer\s+[^\s;,}]+",
        # JWT-like patterns (3+ base64 segments separated by dots)
        r"eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+",
        # AWS-like patterns (AKIA... or starts with A3T/AGPA etc)
        r"(?i)A(?:KIA|3T|GPA|IDA|ROA|RPA)[A-Z0-9]{16}",
        # Common UUID patterns in credentials context
        r"(?i)(?:api_?key|secret|password|token)[\s:=]+[\w-]{8}-[\w-]{4}-[\w-]{4}-[\w-]{4}-[\w-]{12}",
        # Base64-encoded strings that might be secrets (40+ chars)
        r"(?i)(?:secret|password|token|key)[\s:=]+[A-Za-z0-9+/]{40,}[=]*",
    ]

    # Apply all patterns, replace matches with ***
    for pattern in patterns:
        s = re.sub(pattern, "***", s)

    # Generic fallback: replace common sensitive keywords and their values
    # Match patterns like: key: value, key=value, key: "value"
    generic_patterns = [
        r"(?i)(api_key|auth_token|access_token|secret|password|bearer|authorization)[\s:=]+[^\s;,}]+",
    ]
    for pattern in generic_patterns:
        s = re.sub(pattern, r"\1=***", s)

    return s[:max_len]


# Global orchestrator instance
_orchestrator: Optional[AIOrchestrator] = None


def get_orchestrator(rbac: Optional[RBACRegistry] = None) -> AIOrchestrator:
    """Get or create global orchestrator instance."""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = AIOrchestrator(rbac)
    return _orchestrator
