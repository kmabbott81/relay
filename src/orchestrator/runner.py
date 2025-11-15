"""
DAG Runner - Executes tasks in topological order with retries and event logging.
Supports checkpoint tasks for human-in-the-loop approvals (Sprint 31).
"""

import json
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path

from .checkpoints import (
    create_checkpoint,
    get_resume_token,
    write_resume_token,
)
from .graph import DAG, merge_payloads, toposort, validate


class RunnerError(Exception):
    """Raised when DAG execution fails."""

    pass


def log_event(event: dict, events_path: str) -> None:
    """Log event to JSONL file."""
    Path(events_path).parent.mkdir(parents=True, exist_ok=True)
    with open(events_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(event) + "\n")


def run_dag(
    dag: DAG,
    *,
    tenant: str = "local-dev",
    dry_run: bool = False,
    max_retries_default: int = 0,
    events_path: str | None = None,
    dag_run_id: str | None = None,
    start_from_task: str | None = None,
    resume_state: dict | None = None,
) -> dict:
    """
    Execute a DAG with retry support, event logging, and checkpoint pause/resume.

    Args:
        dag: DAG to execute
        tenant: Tenant ID
        dry_run: If True, print plan without executing
        max_retries_default: Default max retries per task
        events_path: Path to write events
        dag_run_id: Unique run identifier (generated if None)
        start_from_task: Task ID to resume from (for checkpoint resume)
        resume_state: Previous task outputs (for checkpoint resume)

    Returns:
        Dict with execution results (includes status: "completed" or "paused")

    Raises:
        RunnerError: If execution fails
    """
    if events_path is None:
        events_path = os.getenv("ORCH_EVENTS_PATH", "logs/orchestrator_events.jsonl")

    if dag_run_id is None:
        dag_run_id = str(uuid.uuid4())
    # Validate DAG
    try:
        validate(dag)
    except Exception as e:
        raise RunnerError(f"DAG validation failed: {e}") from e

    # Get execution order
    try:
        ordered_tasks = toposort(dag)
    except Exception as e:
        raise RunnerError(f"Failed to sort DAG: {e}") from e

    if dry_run:
        print("=" * 60)
        print(f"DRY RUN: DAG '{dag.name}'")
        print("=" * 60)
        print(f"Tenant: {tenant}")
        print(f"Tasks: {len(ordered_tasks)}")
        print("\nExecution Plan:")
        for i, task in enumerate(ordered_tasks, 1):
            deps = ", ".join(task.depends_on) if task.depends_on else "none"
            print(f"  {i}. {task.id} (workflow: {task.workflow_ref}, depends_on: {deps})")
        print("=" * 60)
        return {"dry_run": True, "tasks_planned": len(ordered_tasks)}

    # Execute tasks
    start_time = datetime.now(UTC)
    task_outputs = resume_state if resume_state else {}
    tasks_succeeded = 0
    tasks_failed = 0

    # Determine which tasks to execute
    if start_from_task:
        # Find index of task to resume from
        start_idx = next((i for i, t in enumerate(ordered_tasks) if t.id == start_from_task), 0)
        tasks_to_execute = ordered_tasks[start_idx:]

        # Count tasks that succeeded before the pause by reading events log
        if Path(events_path).exists():
            with open(events_path, encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        event = json.loads(line)
                        if event.get("dag_run_id") == dag_run_id and event.get("event") == "task_ok":
                            tasks_succeeded += 1
    else:
        tasks_to_execute = ordered_tasks

        # Log dag_start only for new runs
        log_event(
            {
                "timestamp": start_time.isoformat(),
                "event": "dag_start",
                "dag_name": dag.name,
                "dag_run_id": dag_run_id,
                "tenant": tenant,
                "task_count": len(ordered_tasks),
            },
            events_path,
        )

    for task in tasks_to_execute:
        task_start = datetime.now(UTC)

        # Handle checkpoint tasks
        if task.type == "checkpoint":
            checkpoint_id = f"{dag_run_id}_{task.id}"

            # Merge upstream outputs for checkpoint context
            upstream_outputs = {dep_id: task_outputs.get(dep_id, {}) for dep_id in task.depends_on}
            merged_params = {**task.params, **merge_payloads(upstream_outputs)}

            # Create checkpoint record
            create_checkpoint(
                checkpoint_id=checkpoint_id,
                dag_run_id=dag_run_id,
                task_id=task.id,
                tenant=tenant,
                prompt=task.prompt or f"Approve checkpoint {task.id}?",
                required_role=task.required_role,
                inputs=task.inputs,
            )

            # Log checkpoint_pending event
            log_event(
                {
                    "timestamp": task_start.isoformat(),
                    "event": "checkpoint_pending",
                    "dag_name": dag.name,
                    "dag_run_id": dag_run_id,
                    "task_id": task.id,
                    "checkpoint_id": checkpoint_id,
                },
                events_path,
            )

            # Find next task after checkpoint
            current_idx = ordered_tasks.index(task)
            next_task_id = ordered_tasks[current_idx + 1].id if current_idx + 1 < len(ordered_tasks) else None

            if next_task_id:
                # Write resume token
                write_resume_token(dag_run_id, next_task_id, tenant)

            # Return paused status
            return {
                "status": "paused",
                "dag_run_id": dag_run_id,
                "dag_name": dag.name,
                "checkpoint_id": checkpoint_id,
                "task_outputs": task_outputs,
                "tasks_succeeded": tasks_succeeded,
                "message": f"Paused at checkpoint '{task.id}'. Use resume_dag() after approval.",
            }

        # Handle workflow tasks
        log_event(
            {
                "timestamp": task_start.isoformat(),
                "event": "task_start",
                "dag_name": dag.name,
                "dag_run_id": dag_run_id,
                "task_id": task.id,
                "workflow_ref": task.workflow_ref,
            },
            events_path,
        )

        # Merge upstream outputs into params
        upstream_outputs = {dep_id: task_outputs.get(dep_id, {}) for dep_id in task.depends_on}
        merged_params = {**task.params, **merge_payloads(upstream_outputs)}

        # Get workflow function
        try:
            from relay_ai.workflows.adapter import WORKFLOW_MAP

            workflow_fn = WORKFLOW_MAP.get(task.workflow_ref)
            if not workflow_fn:
                raise RunnerError(f"Unknown workflow: {task.workflow_ref}")
        except ImportError as e:
            raise RunnerError(f"Failed to import workflow adapter: {e}") from e

        # Execute with retries
        max_retries = task.retries if task.retries > 0 else max_retries_default

        for attempt in range(max_retries + 1):
            try:
                output = workflow_fn(merged_params)
                task_outputs[task.id] = output or {}

                log_event(
                    {
                        "timestamp": datetime.now(UTC).isoformat(),
                        "event": "task_ok",
                        "dag_name": dag.name,
                        "dag_run_id": dag_run_id,
                        "task_id": task.id,
                        "attempt": attempt + 1,
                    },
                    events_path,
                )

                tasks_succeeded += 1
                break
            except Exception as e:
                if attempt < max_retries:
                    log_event(
                        {
                            "timestamp": datetime.now(UTC).isoformat(),
                            "event": "task_retry",
                            "dag_name": dag.name,
                            "dag_run_id": dag_run_id,
                            "task_id": task.id,
                            "attempt": attempt + 1,
                            "error": str(e),
                        },
                        events_path,
                    )
                else:
                    log_event(
                        {
                            "timestamp": datetime.now(UTC).isoformat(),
                            "event": "task_fail",
                            "dag_name": dag.name,
                            "dag_run_id": dag_run_id,
                            "task_id": task.id,
                            "error": str(e),
                        },
                        events_path,
                    )
                    tasks_failed += 1
                    raise RunnerError(f"Task '{task.id}' failed after {max_retries + 1} attempts: {e}") from e

    end_time = datetime.now(UTC)
    duration = (end_time - start_time).total_seconds()

    log_event(
        {
            "timestamp": end_time.isoformat(),
            "event": "dag_done",
            "dag_name": dag.name,
            "dag_run_id": dag_run_id,
            "tenant": tenant,
            "tasks_succeeded": tasks_succeeded,
            "tasks_failed": tasks_failed,
            "duration_seconds": duration,
        },
        events_path,
    )

    return {
        "status": "success",
        "dag_run_id": dag_run_id,
        "dag_name": dag.name,
        "tasks_succeeded": tasks_succeeded,
        "tasks_failed": tasks_failed,
        "duration_seconds": duration,
        "task_outputs": task_outputs,
    }


def resume_dag(dag_run_id: str, *, tenant: str, dag: DAG | None = None) -> dict:
    """
    Resume a paused DAG after checkpoint approval.

    Args:
        dag_run_id: DAG run identifier to resume
        tenant: Tenant identifier
        dag: DAG object (required if not stored)

    Returns:
        Dict with execution results

    Raises:
        RunnerError: If resume fails
    """
    # Get resume token
    token = get_resume_token(dag_run_id)

    if not token:
        raise RunnerError(f"No resume token found for DAG run {dag_run_id}")

    next_task_id = token["next_task_id"]

    # Find checkpoint for this DAG run
    # The checkpoint_id format is: {dag_run_id}_{task_id}
    # We need to find the checkpoint that was pending
    from .checkpoints import list_checkpoints

    checkpoints = list_checkpoints(tenant=tenant)
    checkpoint = None

    for cp in checkpoints:
        if cp["dag_run_id"] == dag_run_id:
            checkpoint = cp
            break

    if not checkpoint:
        raise RunnerError(f"No checkpoint found for DAG run {dag_run_id}")

    # Verify checkpoint is approved
    if checkpoint["status"] != "approved":
        raise RunnerError(f"Checkpoint {checkpoint['checkpoint_id']} not approved, cannot resume")

    # Merge approval data into task outputs
    # This allows downstream tasks to use the approval inputs
    task_outputs = {}

    if checkpoint.get("approval_data"):
        checkpoint_task_id = checkpoint["task_id"]
        task_outputs[checkpoint_task_id] = checkpoint["approval_data"]

    if dag is None:
        raise RunnerError("DAG object required to resume execution")

    # Log checkpoint approved event
    events_path = os.getenv("ORCH_EVENTS_PATH", "logs/orchestrator_events.jsonl")

    log_event(
        {
            "timestamp": datetime.now(UTC).isoformat(),
            "event": "checkpoint_approved",
            "dag_name": dag.name,
            "dag_run_id": dag_run_id,
            "checkpoint_id": checkpoint["checkpoint_id"],
            "approved_by": checkpoint["approved_by"],
        },
        events_path,
    )

    # Resume execution from next task
    return run_dag(
        dag,
        tenant=tenant,
        dag_run_id=dag_run_id,
        start_from_task=next_task_id,
        resume_state=task_outputs,
    )
