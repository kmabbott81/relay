"""Tests for metric emission resilience - Sprint 58 Slice 6.

Verifies that metrics are emitted BEFORE JobStore mutations,
so they're not lost if the store fails.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from relay_ai.ai.job_store import JobStore
from relay_ai.ai.orchestrator import AIOrchestrator
from relay_ai.schemas.ai_plan import PlannedAction, PlanResult
from relay_ai.schemas.permissions import EffectivePermissions, RBACRegistry


@pytest.fixture
def orchestrator():
    """Create orchestrator with fresh job store and permissive RBAC."""
    rbac = MagicMock(spec=RBACRegistry)
    rbac.get_user_permissions = MagicMock(
        return_value=MagicMock(
            spec=EffectivePermissions,
            can_execute=MagicMock(return_value=True),
        )
    )
    return AIOrchestrator(rbac=rbac, job_store=JobStore())


@pytest.mark.asyncio
@pytest.mark.anyio
async def test_metrics_emitted_before_store_mutation(orchestrator: AIOrchestrator):
    """Metrics are emitted BEFORE job store mutation on success."""
    from src.telemetry import jobs as job_metrics

    # Track emission order
    calls = []

    # Mock JobStore.finish_ok to track when it's called
    original_finish_ok = orchestrator.job_store.finish_ok

    async def tracked_finish_ok(*args, **kwargs):
        calls.append("finish_ok")
        return await original_finish_ok(*args, **kwargs)

    orchestrator.job_store.finish_ok = tracked_finish_ok

    # Mock metric functions to track when they're called
    original_inc_job = job_metrics.inc_job
    original_inc_provider = job_metrics.inc_job_by_provider

    def tracked_inc_job(*args, **kwargs):
        calls.append("inc_job")
        return original_inc_job(*args, **kwargs)

    def tracked_inc_provider(*args, **kwargs):
        calls.append("inc_provider")
        return original_inc_provider(*args, **kwargs)

    job_metrics.inc_job = tracked_inc_job
    job_metrics.inc_job_by_provider = tracked_inc_provider

    try:
        # Create a simple plan
        plan = PlanResult(
            prompt="Test",
            intent="test",
            steps=[
                PlannedAction(action_id="test.step1", description="Step 1", params={}),
            ],
            confidence=0.9,
            explanation="Test",
        )

        # Create executor mock
        executor = MagicMock()
        executor.execute = AsyncMock(return_value={"message": "ok"})
        executor.preview = MagicMock(return_value=MagicMock(preview_id="test_preview"))

        # Execute
        await orchestrator.execute_plan(
            user_id="user_123",
            plan=plan,
            executor=executor,
            plan_id="plan_456",
        )

        # Verify metrics were emitted before store mutation
        assert "inc_job" in calls, "inc_job should have been called"
        assert "finish_ok" in calls, "finish_ok should have been called"

        # Check order: metrics should be emitted before mutation
        inc_job_idx = calls.index("inc_job")
        finish_ok_idx = calls.index("finish_ok")
        assert inc_job_idx < finish_ok_idx, "Metrics should be emitted BEFORE JobStore mutation"

    finally:
        # Restore original functions
        job_metrics.inc_job = original_inc_job
        job_metrics.inc_job_by_provider = original_inc_provider


@pytest.mark.asyncio
@pytest.mark.anyio
async def test_metrics_emitted_before_store_error(orchestrator: AIOrchestrator):
    """Metrics are emitted BEFORE job store mutation on error."""
    from src.telemetry import jobs as job_metrics

    # Track emission order
    calls = []

    # Mock JobStore.finish_err to track when it's called
    original_finish_err = orchestrator.job_store.finish_err

    async def tracked_finish_err(*args, **kwargs):
        calls.append("finish_err")
        return await original_finish_err(*args, **kwargs)

    orchestrator.job_store.finish_err = tracked_finish_err

    # Mock metric functions
    original_inc_job = job_metrics.inc_job

    def tracked_inc_job(*args, **kwargs):
        calls.append("inc_job")
        return original_inc_job(*args, **kwargs)

    job_metrics.inc_job = tracked_inc_job

    try:
        # Create a plan
        plan = PlanResult(
            prompt="Test",
            intent="test",
            steps=[
                PlannedAction(action_id="test.step1", description="Step 1", params={}),
            ],
            confidence=0.9,
            explanation="Test",
        )

        # Create executor that fails
        executor = MagicMock()
        executor.execute = AsyncMock(side_effect=Exception("Execution failed"))
        executor.preview = MagicMock(return_value=MagicMock(preview_id="test_preview"))

        # Execute (will fail)
        await orchestrator.execute_plan(
            user_id="user_123",
            plan=plan,
            executor=executor,
            plan_id="plan_456",
        )

        # Verify metrics were emitted before store mutation
        assert "inc_job" in calls, "inc_job should have been called for failed job"
        assert "finish_err" in calls, "finish_err should have been called"

        # Check order: metrics should be emitted before mutation
        inc_job_idx = calls.index("inc_job")
        finish_err_idx = calls.index("finish_err")
        assert inc_job_idx < finish_err_idx, "Metrics should be emitted BEFORE JobStore mutation on error"

    finally:
        # Restore
        job_metrics.inc_job = original_inc_job
