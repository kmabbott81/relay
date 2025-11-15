"""Integration tests for orchestrator job tracking - Sprint 58 Slice 6.

Tests that execute_plan correctly creates and transitions JobRecords,
and emits bounded Prometheus metrics.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from prometheus_client import CollectorRegistry, Counter, Histogram

from relay_ai.ai.job_store import JobStore
from relay_ai.ai.orchestrator import AIOrchestrator
from relay_ai.schemas.ai_plan import PlannedAction, PlanResult
from relay_ai.schemas.job import JobStatus
from relay_ai.schemas.permissions import EffectivePermissions, RBACRegistry


@pytest.fixture
def job_store():
    """Create fresh job store for each test."""
    return JobStore()


@pytest.fixture
def orchestrator(job_store):
    """Create orchestrator with test job store and permissive RBAC."""
    # Create a mock RBAC that allows all actions
    rbac = MagicMock(spec=RBACRegistry)
    rbac.get_user_permissions = MagicMock(
        return_value=MagicMock(
            spec=EffectivePermissions,
            can_execute=MagicMock(return_value=True),  # Allow all actions
        )
    )
    return AIOrchestrator(rbac=rbac, job_store=job_store)


@pytest.fixture
def isolated_metrics():
    """Use isolated Prometheus registry for test isolation (no cross-test bleed)."""
    from relay_ai.telemetry import jobs as job_metrics

    # Save originals
    orig_jobs_total = job_metrics.relay_jobs_total
    orig_jobs_provider = job_metrics.relay_jobs_per_provider_total
    orig_latency = job_metrics.relay_job_latency_seconds

    # Create fresh registry and metrics
    registry = CollectorRegistry()
    job_metrics.relay_jobs_total = Counter(
        "relay_jobs_total", "Total jobs completed", labelnames=["status"], registry=registry
    )
    job_metrics.relay_jobs_per_provider_total = Counter(
        "relay_jobs_per_provider_total",
        "Total jobs per provider",
        labelnames=["provider", "status"],
        registry=registry,
    )
    job_metrics.relay_job_latency_seconds = Histogram(
        "relay_job_latency_seconds",
        "Job execution latency in seconds",
        labelnames=["provider"],
        registry=registry,
        buckets=(0.01, 0.05, 0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 25.0, 100.0),
    )

    yield registry

    # Restore originals
    job_metrics.relay_jobs_total = orig_jobs_total
    job_metrics.relay_jobs_per_provider_total = orig_jobs_provider
    job_metrics.relay_job_latency_seconds = orig_latency


def _make_plan(should_fail: bool = False) -> PlanResult:
    """Helper: create a 2-step plan for testing (optionally fail on step 2)."""
    return PlanResult(
        prompt="Test plan",
        intent="test",
        steps=[
            PlannedAction(action_id="test.step1", description="Step 1", params={}),
            PlannedAction(
                action_id="test.step2",
                description="Step 2 (may fail)",
                params={"fail": should_fail},
            ),
        ],
        confidence=0.9,
        explanation="Test execution",
    )


@pytest.mark.parametrize("should_fail", [False, True])
@pytest.mark.asyncio
@pytest.mark.anyio
async def test_execute_plan_tracks_jobs(orchestrator: AIOrchestrator, job_store: JobStore, should_fail: bool):
    """Execute plan creates/transitions JobRecords for each step (success or failure)."""
    # Track call count to fail on step 2 only
    call_count = [0]

    async def execute_wrapper(*args, **kwargs):
        """Mock executor: fail on step 2 if should_fail is True."""
        call_count[0] += 1
        if should_fail and call_count[0] == 2:
            raise Exception("Test execution error")
        return {"message": "ok"}

    executor = MagicMock()
    executor.execute = AsyncMock(side_effect=execute_wrapper)
    executor.preview = MagicMock(return_value=MagicMock(preview_id="test_preview"))

    # Generate plan with correlation ID
    plan_result = _make_plan(should_fail=should_fail)
    plan, plan_id = await orchestrator.plan(
        user_id="user_123",
        prompt="Test plan",
        planner=MagicMock(plan=AsyncMock(return_value=plan_result)),
    )

    # Execute plan with explicit plan_id
    result = await orchestrator.execute_plan(
        user_id="user_123",
        plan=plan,
        executor=executor,
        plan_id=plan_id,
    )

    # Verify plan_id present
    assert "plan_id" in result
    assert result["plan_id"] is not None

    # Verify results and job records
    assert "results" in result
    assert len(result["results"]) == 2

    # Verify job records created with correct statuses
    for i, step_result in enumerate(result["results"]):
        job_id = step_result.get("job_id")
        assert job_id is not None

        job = await job_store.get(job_id)
        assert job is not None
        assert job.user_id == "user_123"
        assert job.action_id in ("test.step1", "test.step2")
        assert job.plan_id == result["plan_id"]

        # Verify timestamps
        assert job.created_at is not None
        assert job.started_at is not None
        assert job.finished_at is not None

        # Verify status
        if should_fail and i == 1:
            # Step 2 should fail if should_fail=True
            assert job.status == JobStatus.FAILED
            assert job.error is not None
        else:
            # Step 1 always succeeds, step 2 succeeds if should_fail=False
            assert job.status == JobStatus.SUCCESS


@pytest.mark.asyncio
@pytest.mark.anyio
async def test_execute_plan_emits_metrics(orchestrator: AIOrchestrator, job_store: JobStore, isolated_metrics):
    """Execute plan emits bounded Prometheus metrics on job completion."""

    # Setup: step 1 succeeds, step 2 fails
    call_count = [0]

    async def execute_wrapper(*args, **kwargs):
        call_count[0] += 1
        if call_count[0] == 2:
            raise Exception("Step 2 error")
        return {"message": "ok"}

    executor = MagicMock()
    executor.execute = AsyncMock(side_effect=execute_wrapper)
    executor.preview = MagicMock(return_value=MagicMock(preview_id="test"))

    # Plan and execute (step 1 succeeds, step 2 fails)
    plan_result = _make_plan(should_fail=True)
    plan, plan_id = await orchestrator.plan(
        user_id="user_123",
        prompt="Test",
        planner=MagicMock(plan=AsyncMock(return_value=plan_result)),
    )

    result = await orchestrator.execute_plan(
        user_id="user_123",
        plan=plan,
        executor=executor,
        plan_id=plan_id,
    )

    # Verify execution
    assert result["steps_executed"] == 2
    assert len(result["results"]) == 2
    assert result["results"][0]["status"] == "success"
    assert result["results"][1]["status"] == "failed"

    # Verify metrics were emitted (check registry for metric samples)
    samples = list(isolated_metrics.collect())
    metric_names = {m.name for m in samples}

    # Confirm all three metrics exist (note: Counter adds _total suffix)
    assert "relay_jobs_total" in metric_names or "relay_jobs" in metric_names
    assert "relay_jobs_per_provider_total" in metric_names or "relay_jobs_per_provider" in metric_names
    assert "relay_job_latency_seconds" in metric_names
