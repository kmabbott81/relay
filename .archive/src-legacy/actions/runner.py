"""Action runner - Routes actions to appropriate adapters.

Sprint 55 Week 3: Adapter router for AI Orchestrator execution.
"""

from typing import Any

from .execution import get_executor


async def run_action(
    action_provider: str,
    action_name: str,
    params: dict[str, Any],
    workspace_id: str,
    actor_id: str,
) -> dict[str, Any]:
    """Run an action via appropriate adapter.

    Args:
        action_provider: Provider name (e.g., "google", "microsoft")
        action_name: Action ID (e.g., "gmail.send")
        params: Action parameters
        workspace_id: Workspace identifier
        actor_id: Actor identifier

    Returns:
        Execution result dict with status, result, error

    Raises:
        NotImplementedError: If provider not configured
        ValueError: If action validation fails
    """
    # Get executor
    executor = get_executor()

    # Generate preview
    full_action_id = f"{action_name}"
    preview = executor.preview(full_action_id, params)

    # Execute via preview/execute flow
    result = await executor.execute(
        preview_id=preview.preview_id,
        idempotency_key=None,  # Already handled by queue
        workspace_id=workspace_id,
        actor_id=actor_id,
    )

    return {
        "status": result.status.value,
        "result": result.result,
        "error": result.error,
        "duration_ms": result.duration_ms,
        "run_id": result.run_id,
    }
