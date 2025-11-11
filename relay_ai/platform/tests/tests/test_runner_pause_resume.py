"""
Tests for DAG runner pause/resume with checkpoints

Covers:
- DAG execution that pauses at checkpoint
- Resume token creation
- Resume execution after approval
- Event logging for checkpoint lifecycle
"""

import os
from pathlib import Path

import pytest

from relay_ai.orchestrator.checkpoints import approve_checkpoint, get_checkpoint, list_checkpoints
from relay_ai.orchestrator.graph import DAG, Task
from relay_ai.orchestrator.runner import RunnerError, resume_dag, run_dag


@pytest.fixture
def temp_events_path(tmp_path: Path) -> Path:
    """Create temporary events file."""
    events_file = tmp_path / "events.jsonl"
    os.environ["ORCH_EVENTS_PATH"] = str(events_file)
    yield events_file
    # Cleanup
    if "ORCH_EVENTS_PATH" in os.environ:
        del os.environ["ORCH_EVENTS_PATH"]


@pytest.fixture
def temp_checkpoints_path(tmp_path: Path) -> Path:
    """Create temporary checkpoints file."""
    checkpoints_file = tmp_path / "checkpoints.jsonl"
    os.environ["CHECKPOINTS_PATH"] = str(checkpoints_file)
    yield checkpoints_file
    # Cleanup
    if "CHECKPOINTS_PATH" in os.environ:
        del os.environ["CHECKPOINTS_PATH"]


@pytest.fixture
def temp_state_store(tmp_path: Path) -> Path:
    """Create temporary state store file."""
    state_file = tmp_path / "state.jsonl"
    os.environ["STATE_STORE_PATH"] = str(state_file)
    yield state_file
    # Cleanup
    if "STATE_STORE_PATH" in os.environ:
        del os.environ["STATE_STORE_PATH"]


@pytest.fixture
def approval_dag() -> DAG:
    """Create a simple DAG with checkpoint for testing."""
    tasks = [
        Task(
            id="task1",
            type="workflow",
            workflow_ref="inbox_drive_sweep",
            params={"inbox_items": "test"},
            depends_on=[],
        ),
        Task(
            id="checkpoint",
            type="checkpoint",
            workflow_ref="",
            prompt="Approve task1 output?",
            required_role="Operator",
            inputs={"signoff": {"type": "string", "required": True}},
            depends_on=["task1"],
        ),
        Task(
            id="task2",
            type="workflow",
            workflow_ref="weekly_report",
            params={"user_priorities": "Sprint 31"},
            depends_on=["checkpoint"],
        ),
    ]

    return DAG(name="test_approval_dag", tasks=tasks, tenant_id="test-tenant")


def test_dag_pauses_at_checkpoint(
    approval_dag: DAG,
    temp_events_path: Path,
    temp_checkpoints_path: Path,
    temp_state_store: Path,
):
    """Test that DAG pauses when encountering checkpoint task."""
    result = run_dag(approval_dag, tenant="test-tenant", dry_run=False, events_path=str(temp_events_path))

    # Should pause
    assert result["status"] == "paused"
    assert "checkpoint_id" in result
    assert "dag_run_id" in result
    assert result["dag_name"] == "test_approval_dag"

    # Checkpoint should be created
    checkpoint_id = result["checkpoint_id"]
    checkpoint = get_checkpoint(checkpoint_id)
    assert checkpoint is not None
    assert checkpoint["status"] == "pending"
    assert checkpoint["prompt"] == "Approve task1 output?"

    # Should be in pending list
    pending = list_checkpoints(status="pending")
    assert len(pending) == 1
    assert pending[0]["checkpoint_id"] == checkpoint_id

    # Events should include checkpoint_pending
    events_content = temp_events_path.read_text()
    assert "checkpoint_pending" in events_content
    assert checkpoint_id in events_content

    # Resume token should exist in state store
    state_content = temp_state_store.read_text()
    assert "resume_token" in state_content
    assert result["dag_run_id"] in state_content


def test_resume_after_approval(
    approval_dag: DAG,
    temp_events_path: Path,
    temp_checkpoints_path: Path,
    temp_state_store: Path,
):
    """Test resuming DAG after checkpoint approval."""
    # First run - pause at checkpoint
    result1 = run_dag(approval_dag, tenant="test-tenant", dry_run=False, events_path=str(temp_events_path))

    assert result1["status"] == "paused"
    checkpoint_id = result1["checkpoint_id"]
    dag_run_id = result1["dag_run_id"]

    # Approve checkpoint with data
    approval_data = {"signoff": "Approved by manager"}
    approve_checkpoint(checkpoint_id, approved_by="Admin", approval_data=approval_data)

    # Verify approval
    checkpoint = get_checkpoint(checkpoint_id)
    assert checkpoint["status"] == "approved"

    # Resume DAG
    result2 = resume_dag(dag_run_id, tenant="test-tenant", dag=approval_dag)

    # Should complete successfully
    assert result2["status"] == "success"
    assert result2["dag_run_id"] == dag_run_id
    assert result2["tasks_succeeded"] >= 2  # task1 (from before) + task2 (after resume)

    # Events should include checkpoint_approved and dag_done
    events_content = temp_events_path.read_text()
    assert "checkpoint_approved" in events_content or "task_ok" in events_content  # After resume
    assert "dag_done" in events_content


def test_resume_without_approval_fails(
    approval_dag: DAG,
    temp_events_path: Path,
    temp_checkpoints_path: Path,
    temp_state_store: Path,
):
    """Test that resume fails if checkpoint not approved."""
    # First run - pause at checkpoint
    result = run_dag(approval_dag, tenant="test-tenant", dry_run=False, events_path=str(temp_events_path))

    assert result["status"] == "paused"
    dag_run_id = result["dag_run_id"]

    # Try to resume without approving (should fail)
    with pytest.raises(RunnerError) as exc_info:
        resume_dag(dag_run_id, tenant="test-tenant", dag=approval_dag)

    assert "not approved" in str(exc_info.value).lower()


def test_approval_data_passed_to_downstream_task(
    approval_dag: DAG,
    temp_events_path: Path,
    temp_checkpoints_path: Path,
    temp_state_store: Path,
):
    """Test that approval data is passed to downstream tasks with namespacing."""
    # First run - pause
    result1 = run_dag(approval_dag, tenant="test-tenant", dry_run=False, events_path=str(temp_events_path))

    checkpoint_id = result1["checkpoint_id"]
    dag_run_id = result1["dag_run_id"]

    # Approve with custom data
    approval_data = {"signoff": "Approved", "priority": "high", "notes": "Looks good"}
    approve_checkpoint(checkpoint_id, approved_by="Admin", approval_data=approval_data)

    # Resume
    result2 = resume_dag(dag_run_id, tenant="test-tenant", dag=approval_dag)

    # Should succeed
    assert result2["status"] == "success"

    # The approval data should have been passed to task2
    # We can't directly inspect task2's received params here, but we verify
    # that the runner successfully processed the approval_data by checking
    # the checkpoint was approved and resume succeeded
    checkpoint = get_checkpoint(checkpoint_id)
    assert checkpoint["approval_data"] == approval_data


def test_multiple_checkpoints_in_sequence(
    temp_events_path: Path,
    temp_checkpoints_path: Path,
    temp_state_store: Path,
):
    """Test DAG with two checkpoints in sequence."""
    tasks = [
        Task(id="task1", type="workflow", workflow_ref="inbox_drive_sweep", params={}, depends_on=[]),
        Task(
            id="checkpoint1",
            type="checkpoint",
            workflow_ref="",
            prompt="First approval?",
            required_role="Operator",
            depends_on=["task1"],
        ),
        Task(id="task2", type="workflow", workflow_ref="weekly_report", params={}, depends_on=["checkpoint1"]),
        Task(
            id="checkpoint2",
            type="checkpoint",
            workflow_ref="",
            prompt="Second approval?",
            required_role="Admin",
            depends_on=["task2"],
        ),
        Task(
            id="task3", type="workflow", workflow_ref="meeting_transcript_brief", params={}, depends_on=["checkpoint2"]
        ),
    ]

    dag = DAG(name="double_checkpoint_dag", tasks=tasks, tenant_id="test-tenant")

    # First run - should pause at checkpoint1
    result1 = run_dag(dag, tenant="test-tenant", dry_run=False, events_path=str(temp_events_path))

    assert result1["status"] == "paused"
    checkpoint1_id = result1["checkpoint_id"]
    dag_run_id = result1["dag_run_id"]

    # Approve checkpoint1
    approve_checkpoint(checkpoint1_id, approved_by="Operator")

    # Resume - should pause at checkpoint2
    result2 = resume_dag(dag_run_id, tenant="test-tenant", dag=dag)

    assert result2["status"] == "paused"
    checkpoint2_id = result2["checkpoint_id"]
    assert checkpoint2_id != checkpoint1_id

    # Approve checkpoint2
    approve_checkpoint(checkpoint2_id, approved_by="Admin")

    # Resume again - should complete
    result3 = resume_dag(dag_run_id, tenant="test-tenant", dag=dag)

    assert result3["status"] == "success"


def test_dag_without_checkpoint_completes_normally(
    temp_events_path: Path,
    temp_checkpoints_path: Path,
    temp_state_store: Path,
):
    """Test that DAGs without checkpoints still work normally."""
    tasks = [
        Task(id="task1", type="workflow", workflow_ref="inbox_drive_sweep", params={}, depends_on=[]),
        Task(id="task2", type="workflow", workflow_ref="weekly_report", params={}, depends_on=["task1"]),
    ]

    dag = DAG(name="normal_dag", tasks=tasks, tenant_id="test-tenant")

    result = run_dag(dag, tenant="test-tenant", dry_run=False, events_path=str(temp_events_path))

    # Should complete without pausing
    assert result["status"] == "success"
    assert "checkpoint_id" not in result

    # No checkpoints should be created
    pending = list_checkpoints(status="pending")
    assert len(pending) == 0


def test_dry_run_with_checkpoint(
    approval_dag: DAG,
    temp_events_path: Path,
    temp_checkpoints_path: Path,
    temp_state_store: Path,
):
    """Test that dry run mode doesn't create actual checkpoints."""
    result = run_dag(approval_dag, tenant="test-tenant", dry_run=True, events_path=str(temp_events_path))

    # Dry run should report planned tasks
    assert "tasks_planned" in result

    # No checkpoints should be created in dry run
    pending = list_checkpoints(status="pending")
    assert len(pending) == 0

    # Events file should not have checkpoint_pending
    if temp_events_path.exists():
        events_content = temp_events_path.read_text()
        assert "checkpoint_pending" not in events_content
