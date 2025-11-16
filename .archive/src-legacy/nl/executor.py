"""Plan Executor for Natural Language Commands.

Executes action plans with approval gating, RBAC checks, and audit logging.
"""

import os
from dataclasses import dataclass, field
from typing import Optional

from ..graph.actions import execute_action
from ..orchestrator.checkpoints import (
    create_checkpoint,
    get_checkpoint,
)
from ..security.audit import AuditAction, AuditLogger, AuditResult
from .planner import Plan


@dataclass
class ExecutionResult:
    """Result of plan execution."""

    status: str  # dry, paused, success, error
    plan: Plan
    checkpoint_id: Optional[str] = None
    results: list[dict] = field(default_factory=list)  # Step execution results
    audit_ids: list[str] = field(default_factory=list)
    error: Optional[str] = None


def execute_plan(
    plan: Plan,
    *,
    tenant: str,
    user_id: str,
    dry_run: bool = False,
) -> ExecutionResult:
    """Execute action plan.

    Process:
    1. If dry_run: return preview only
    2. If requires_approval: create checkpoint, return paused
    3. Execute steps via action router
    4. Record audit events
    5. Return result

    Args:
        plan: Action plan to execute
        tenant: Tenant ID
        user_id: User ID
        dry_run: If True, return preview without executing

    Returns:
        ExecutionResult with status and details

    Example:
        >>> result = execute_plan(plan, tenant="t1", user_id="u1", dry_run=True)
        >>> result.status
        'dry'
    """
    # Dry run - return preview only
    if dry_run:
        return ExecutionResult(
            status="dry",
            plan=plan,
            results=[{"step": i, "preview": step.description} for i, step in enumerate(plan.steps)],
        )

    # Check if approval required
    if plan.requires_approval:
        return _create_approval_checkpoint(plan, tenant, user_id)

    # Execute plan
    return _execute_steps(plan, tenant, user_id)


def resume_plan(
    checkpoint_id: str,
    *,
    tenant: str,
    user_id: str,
) -> ExecutionResult:
    """Resume plan execution after approval.

    Args:
        checkpoint_id: Checkpoint ID to resume from
        tenant: Tenant ID
        user_id: User ID

    Returns:
        ExecutionResult

    Raises:
        ValueError: If checkpoint not found or not approved
    """
    # Get checkpoint
    checkpoint = get_checkpoint(checkpoint_id)

    if not checkpoint:
        raise ValueError(f"Checkpoint not found: {checkpoint_id}")

    if checkpoint["status"] != "approved":
        raise ValueError(f"Checkpoint not approved: {checkpoint['status']}")

    # Extract plan from checkpoint metadata
    plan_data = checkpoint.get("metadata", {}).get("plan")

    if not plan_data:
        raise ValueError("Plan data not found in checkpoint")

    # Reconstruct plan (simplified - in production would deserialize fully)
    from .planner import Plan as PlanClass

    plan = PlanClass(
        plan_id=plan_data.get("plan_id", ""),
        intent=None,  # Not needed for execution
        steps=[],  # Will be populated
        metadata=plan_data.get("metadata", {}),
    )

    # Execute
    return _execute_steps(plan, tenant, user_id, checkpoint_id=checkpoint_id)


def _create_approval_checkpoint(plan: Plan, tenant: str, user_id: str) -> ExecutionResult:
    """Create approval checkpoint for high-risk plan.

    Args:
        plan: Plan requiring approval
        tenant: Tenant ID
        user_id: User ID

    Returns:
        ExecutionResult with status='paused'
    """
    checkpoint_id = f"nlp-approval-{plan.plan_id}"

    # Get approver role from env
    approver_role = os.getenv("NL_APPROVER_ROLE", "Operator")

    # Create checkpoint
    checkpoint = create_checkpoint(
        checkpoint_id=checkpoint_id,
        dag_run_id=plan.plan_id,
        task_id="nl_command_approval",
        tenant=tenant,
        prompt=plan.preview,
        required_role=approver_role,
        inputs={"plan_id": plan.plan_id},
    )

    # Store plan in checkpoint metadata (for resume)
    checkpoint["metadata"] = {
        "plan": {
            "plan_id": plan.plan_id,
            "intent": {
                "verb": plan.intent.verb,
                "original_command": plan.intent.original_command,
            },
            "steps": [
                {
                    "action": step.action,
                    "graph_id": step.graph_id,
                    "description": step.description,
                }
                for step in plan.steps
            ],
            "metadata": plan.metadata,
        }
    }

    # Log audit event
    audit_logger = AuditLogger(os.getenv("AUDIT_DIR", "audit"))
    audit_id = audit_logger.log(
        tenant_id=tenant,
        user_id=user_id,
        action=AuditAction.RUN_WORKFLOW,
        resource_type="nl_command",
        resource_id=plan.plan_id,
        result=AuditResult.SUCCESS,
        reason="Checkpoint created for approval",
        metadata={
            "checkpoint_id": checkpoint_id,
            "risk_level": plan.risk_level,
        },
    )

    return ExecutionResult(
        status="paused",
        plan=plan,
        checkpoint_id=checkpoint_id,
        audit_ids=[audit_id],
    )


def _execute_steps(
    plan: Plan,
    tenant: str,
    user_id: str,
    checkpoint_id: Optional[str] = None,
) -> ExecutionResult:
    """Execute plan steps.

    Args:
        plan: Plan to execute
        tenant: Tenant ID
        user_id: User ID
        checkpoint_id: Optional checkpoint ID (for audit trail)

    Returns:
        ExecutionResult
    """
    audit_logger = AuditLogger(os.getenv("AUDIT_DIR", "audit"))
    results = []
    audit_ids = []

    # Log plan start
    start_audit_id = audit_logger.log(
        tenant_id=tenant,
        user_id=user_id,
        action=AuditAction.RUN_WORKFLOW,
        resource_type="nl_command",
        resource_id=plan.plan_id,
        result=AuditResult.SUCCESS,
        reason="Plan execution started",
        metadata={
            "checkpoint_id": checkpoint_id,
            "step_count": len(plan.steps),
        },
    )
    audit_ids.append(start_audit_id)

    # Execute each step
    for i, step in enumerate(plan.steps):
        try:
            # Special handling for search (no action execution)
            if step.action == "search.execute":
                results.append(
                    {
                        "step": i,
                        "action": step.action,
                        "status": "success",
                        "description": step.description,
                        "result": step.payload,
                    }
                )
                continue

            # Execute action via router
            action_result = execute_action(
                action=step.action,
                graph_id=step.graph_id,
                payload=step.payload,
                user_id=user_id,
                tenant=tenant,
            )

            # Record result
            results.append(
                {
                    "step": i,
                    "action": step.action,
                    "status": "success",
                    "description": step.description,
                    "result": action_result,
                }
            )

            # Log step success
            step_audit_id = audit_logger.log(
                tenant_id=tenant,
                user_id=user_id,
                action=AuditAction.RUN_WORKFLOW,
                resource_type="nl_step",
                resource_id=f"{plan.plan_id}-step-{i}",
                result=AuditResult.SUCCESS,
                metadata={
                    "step_action": step.action,
                    "graph_id": step.graph_id,
                },
            )
            audit_ids.append(step_audit_id)

        except Exception as e:
            # Log step failure
            error_msg = str(e)

            results.append(
                {
                    "step": i,
                    "action": step.action,
                    "status": "error",
                    "description": step.description,
                    "error": error_msg,
                }
            )

            step_audit_id = audit_logger.log(
                tenant_id=tenant,
                user_id=user_id,
                action=AuditAction.RUN_WORKFLOW,
                resource_type="nl_step",
                resource_id=f"{plan.plan_id}-step-{i}",
                result=AuditResult.ERROR,
                reason=error_msg,
                metadata={
                    "step_action": step.action,
                    "graph_id": step.graph_id,
                },
            )
            audit_ids.append(step_audit_id)

            # Stop execution on first error
            return ExecutionResult(
                status="error",
                plan=plan,
                results=results,
                audit_ids=audit_ids,
                error=error_msg,
            )

    # Log plan completion
    complete_audit_id = audit_logger.log(
        tenant_id=tenant,
        user_id=user_id,
        action=AuditAction.RUN_WORKFLOW,
        resource_type="nl_command",
        resource_id=plan.plan_id,
        result=AuditResult.SUCCESS,
        reason="Plan execution completed",
        metadata={
            "checkpoint_id": checkpoint_id,
            "steps_completed": len(results),
        },
    )
    audit_ids.append(complete_audit_id)

    return ExecutionResult(
        status="success",
        plan=plan,
        results=results,
        audit_ids=audit_ids,
    )


def get_execution_history(tenant: str, limit: int = 50) -> list[dict]:
    """Get recent NL command execution history.

    Args:
        tenant: Tenant ID
        limit: Maximum results

    Returns:
        List of execution records
    """
    audit_logger = AuditLogger(os.getenv("AUDIT_DIR", "audit"))

    # Read audit log for NL commands
    # This is a simplified implementation
    # In production would query audit store properly

    history = []

    try:
        audit_path = audit_logger._get_audit_path()

        if not audit_path.exists():
            return []

        import json

        with open(audit_path, encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue

                try:
                    record = json.loads(line)

                    # Filter for NL commands
                    if (
                        record.get("tenant_id") == tenant
                        and record.get("resource_type") == "nl_command"
                        and "started" in record.get("reason", "").lower()
                    ):
                        history.append(record)

                except json.JSONDecodeError:
                    continue

    except Exception:
        pass

    # Sort by timestamp (newest first)
    history.sort(key=lambda x: x.get("timestamp", ""), reverse=True)

    return history[:limit]
