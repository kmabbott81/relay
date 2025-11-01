"""
Tests for DAG runner execution and retry logic.
"""

from pathlib import Path

import pytest

from src.orchestrator.graph import DAG, Task
from src.orchestrator.runner import RunnerError, run_dag


def test_dry_run_prints_plan_no_side_effects(capsys):
    """Test that dry-run prints plan without executing."""
    tasks = [
        Task(id="t1", workflow_ref="inbox_drive_sweep", params={}),
        Task(id="t2", workflow_ref="weekly_report_pack", params={}, depends_on=["t1"]),
    ]
    dag = DAG(name="test_dag", tasks=tasks)

    result = run_dag(dag, dry_run=True)

    captured = capsys.readouterr()
    assert "DRY RUN" in captured.out
    assert "test_dag" in captured.out
    assert "t1" in captured.out
    assert "t2" in captured.out

    # Result indicates dry run
    assert result["dry_run"] is True
    assert result["tasks_planned"] == 2


def test_retry_path_first_fails_second_succeeds(monkeypatch, tmp_path):
    """Test retry logic: first attempt fails, second succeeds."""
    # Track call count
    call_count = {"inbox_drive_sweep": 0}

    def failing_then_succeeding_adapter(params):
        call_count["inbox_drive_sweep"] += 1
        if call_count["inbox_drive_sweep"] == 1:
            raise RuntimeError("Simulated failure")
        return {"summary": "Success on retry"}

    # Monkeypatch the workflow map
    from src.workflows import adapter

    original_map = adapter.WORKFLOW_MAP.copy()
    adapter.WORKFLOW_MAP["inbox_drive_sweep"] = failing_then_succeeding_adapter

    try:
        tasks = [
            Task(id="t1", workflow_ref="inbox_drive_sweep", params={}, retries=1),
        ]
        dag = DAG(name="test_dag", tasks=tasks)

        events_path = str(tmp_path / "events.jsonl")
        result = run_dag(dag, dry_run=False, events_path=events_path)

        # Should succeed after retry
        assert result["tasks_succeeded"] == 1
        assert result["tasks_failed"] == 0

        # Check events logged
        events_content = Path(events_path).read_text()
        assert "task_start" in events_content
        assert "task_retry" in events_content
        assert "task_ok" in events_content
        assert "dag_done" in events_content

    finally:
        # Restore original map
        adapter.WORKFLOW_MAP.update(original_map)


def test_task_failure_raises_runner_error(tmp_path):
    """Test that task failure raises RunnerError."""

    def always_fails(params):
        raise RuntimeError("Task always fails")

    from src.workflows import adapter

    original_map = adapter.WORKFLOW_MAP.copy()
    adapter.WORKFLOW_MAP["inbox_drive_sweep"] = always_fails

    try:
        tasks = [
            Task(id="t1", workflow_ref="inbox_drive_sweep", params={}, retries=0),
        ]
        dag = DAG(name="test_dag", tasks=tasks)

        events_path = str(tmp_path / "events.jsonl")

        with pytest.raises(RunnerError, match="failed after"):
            run_dag(dag, dry_run=False, events_path=events_path)

    finally:
        adapter.WORKFLOW_MAP.update(original_map)


def test_payload_passing_between_tasks(tmp_path):
    """Test that outputs from upstream tasks are passed to downstream."""
    from src.workflows import adapter

    original_map = adapter.WORKFLOW_MAP.copy()

    received_params = {}

    def task1_adapter(params):
        return {"output": "data_from_task1", "count": 42}

    def task2_adapter(params):
        received_params.update(params)
        return {"output": "data_from_task2"}

    adapter.WORKFLOW_MAP["inbox_drive_sweep"] = task1_adapter
    adapter.WORKFLOW_MAP["weekly_report_pack"] = task2_adapter

    try:
        tasks = [
            Task(id="t1", workflow_ref="inbox_drive_sweep", params={"original": "value"}),
            Task(id="t2", workflow_ref="weekly_report_pack", params={}, depends_on=["t1"]),
        ]
        dag = DAG(name="test_dag", tasks=tasks)

        events_path = str(tmp_path / "events.jsonl")
        _result = run_dag(dag, dry_run=False, events_path=events_path)

        # Check t2 received namespaced outputs from t1
        assert "t1__output" in received_params
        assert received_params["t1__output"] == "data_from_task1"
        assert received_params["t1__count"] == 42

    finally:
        adapter.WORKFLOW_MAP.update(original_map)
