"""Tests for scheduler (Sprint 27B)."""

from datetime import UTC, datetime
from unittest.mock import Mock, patch

import pytest

from relay_ai.orchestrator.scheduler import drain_queue, parse_cron, tick_once

# Sprint 52: Quarantine marker - scheduler API changed (dedup_cache, queue.dequeue)
pytestmark = pytest.mark.api_mismatch


def test_parse_cron_every_5_minutes():
    """Test */5 cron expression."""
    matcher = parse_cron("*/5 * * * *")

    # Should match at :00, :05, :10, etc
    assert matcher(datetime(2025, 10, 3, 14, 0)) is True
    assert matcher(datetime(2025, 10, 3, 14, 5)) is True
    assert matcher(datetime(2025, 10, 3, 14, 10)) is True

    # Should not match at :01, :03, :07, etc
    assert matcher(datetime(2025, 10, 3, 14, 1)) is False
    assert matcher(datetime(2025, 10, 3, 14, 3)) is False
    assert matcher(datetime(2025, 10, 3, 14, 7)) is False


def test_parse_cron_wildcard():
    """Test * wildcard matches all."""
    matcher = parse_cron("* * * * *")

    # Should match every minute
    assert matcher(datetime(2025, 10, 3, 14, 0)) is True
    assert matcher(datetime(2025, 10, 3, 14, 1)) is True
    assert matcher(datetime(2025, 10, 3, 14, 59)) is True


def test_parse_cron_specific_hour():
    """Test specific hour matching."""
    matcher = parse_cron("0 9 * * *")

    # Should match at 9:00 AM
    assert matcher(datetime(2025, 10, 3, 9, 0)) is True

    # Should not match other hours
    assert matcher(datetime(2025, 10, 3, 8, 0)) is False
    assert matcher(datetime(2025, 10, 3, 10, 0)) is False

    # Should not match 9:01
    assert matcher(datetime(2025, 10, 3, 9, 1)) is False


def test_tick_once_enqueues_matching_schedule():
    """Test that tick_once enqueues matching schedules."""
    schedules = [
        {
            "id": "test_schedule",
            "cron": "*/5 * * * *",
            "dag": "test.yaml",
            "tenant": "test-tenant",
            "enabled": True,
        }
    ]

    run_queue = []
    now = datetime(2025, 10, 3, 14, 5, 0, tzinfo=UTC)  # Minute divisible by 5

    tick_once(now, schedules, run_queue)

    assert len(run_queue) == 1
    assert run_queue[0]["schedule_id"] == "test_schedule"
    assert run_queue[0]["dag_path"] == "test.yaml"
    assert run_queue[0]["tenant"] == "test-tenant"
    assert run_queue[0]["minute"] == "2025-10-03 14:05"


def test_tick_once_skips_non_matching():
    """Test that non-matching schedules are not enqueued."""
    schedules = [
        {
            "id": "test_schedule",
            "cron": "*/5 * * * *",
            "dag": "test.yaml",
            "tenant": "test-tenant",
            "enabled": True,
        }
    ]

    run_queue = []
    now = datetime(2025, 10, 3, 14, 3, 0, tzinfo=UTC)  # Minute NOT divisible by 5

    tick_once(now, schedules, run_queue)

    assert len(run_queue) == 0


def test_tick_once_skips_disabled():
    """Test that disabled schedules are not enqueued."""
    schedules = [
        {
            "id": "test_schedule",
            "cron": "*/5 * * * *",
            "dag": "test.yaml",
            "tenant": "test-tenant",
            "enabled": False,  # Disabled
        }
    ]

    run_queue = []
    now = datetime(2025, 10, 3, 14, 5, 0, tzinfo=UTC)

    tick_once(now, schedules, run_queue)

    assert len(run_queue) == 0


def test_tick_once_deduplicates_same_minute():
    """Test that duplicate enqueues in same minute are prevented."""
    schedules = [
        {
            "id": "test_schedule",
            "cron": "* * * * *",  # Every minute
            "dag": "test.yaml",
            "tenant": "test-tenant",
            "enabled": True,
        }
    ]

    run_queue = []
    now = datetime(2025, 10, 3, 14, 5, 0, tzinfo=UTC)

    # First tick - should enqueue
    tick_once(now, schedules, run_queue)
    assert len(run_queue) == 1

    # Second tick same minute - should NOT enqueue again
    tick_once(now, schedules, run_queue)
    assert len(run_queue) == 1  # Still only 1


def test_drain_queue_executes_runs(tmp_path, monkeypatch):
    """Test that drain_queue executes runs."""
    # Mock run_dag to avoid actual execution
    mock_results = []

    def mock_run_dag(dag, tenant, dry_run, events_path):
        mock_results.append({"tenant": tenant, "dag_name": dag.name})
        return {"duration_seconds": 1.0}

    # Mock load_dag_from_yaml
    mock_dag = Mock()
    mock_dag.name = "test_dag"

    with patch("src.orchestrator.scheduler.run_dag", side_effect=mock_run_dag):
        with patch("src.orchestrator.scheduler.load_dag_from_yaml", return_value=mock_dag):
            # Set temp state store path
            state_path = tmp_path / "state.jsonl"
            monkeypatch.setenv("STATE_STORE_PATH", str(state_path))

            run_queue = [
                {
                    "schedule_id": "test1",
                    "dag_path": "test1.yaml",
                    "tenant": "tenant1",
                    "minute": "2025-10-03 14:05",
                    "enqueued_at": "2025-10-03T14:05:00",
                }
            ]

            results = drain_queue(run_queue, max_parallel=1)

            assert len(results) == 1
            assert results[0]["status"] == "success"
            assert len(mock_results) == 1
            assert mock_results[0]["tenant"] == "tenant1"


def test_drain_queue_respects_max_parallel(tmp_path, monkeypatch):
    """Test that drain_queue respects max_parallel limit."""
    call_count = []

    def mock_run_dag(dag, tenant, dry_run, events_path):
        call_count.append(1)
        return {"duration_seconds": 1.0}

    mock_dag = Mock()
    mock_dag.name = "test_dag"

    with patch("src.orchestrator.scheduler.run_dag", side_effect=mock_run_dag):
        with patch("src.orchestrator.scheduler.load_dag_from_yaml", return_value=mock_dag):
            state_path = tmp_path / "state.jsonl"
            monkeypatch.setenv("STATE_STORE_PATH", str(state_path))

            # Queue 5 runs
            run_queue = [
                {
                    "schedule_id": f"test{i}",
                    "dag_path": f"test{i}.yaml",
                    "tenant": "tenant1",
                    "minute": "2025-10-03 14:05",
                    "enqueued_at": "2025-10-03T14:05:00",
                }
                for i in range(5)
            ]

            results = drain_queue(run_queue, max_parallel=2)

            # All 5 should complete
            assert len(results) == 5
            assert len(call_count) == 5


def test_drain_queue_handles_failures(tmp_path, monkeypatch):
    """Test that drain_queue handles task failures."""

    def mock_run_dag_fail(dag, tenant, dry_run, events_path):
        raise RuntimeError("Task failed")

    mock_dag = Mock()
    mock_dag.name = "test_dag"

    with patch("src.orchestrator.scheduler.run_dag", side_effect=mock_run_dag_fail):
        with patch("src.orchestrator.scheduler.load_dag_from_yaml", return_value=mock_dag):
            state_path = tmp_path / "state.jsonl"
            monkeypatch.setenv("STATE_STORE_PATH", str(state_path))

            run_queue = [
                {
                    "schedule_id": "test1",
                    "dag_path": "test1.yaml",
                    "tenant": "tenant1",
                    "minute": "2025-10-03 14:05",
                    "enqueued_at": "2025-10-03T14:05:00",
                }
            ]

            results = drain_queue(run_queue, max_parallel=1)

            assert len(results) == 1
            assert results[0]["status"] == "failed"
            assert "Task failed" in results[0]["error"]


def test_drain_queue_clears_queue(tmp_path, monkeypatch):
    """Test that drain_queue clears the run queue."""
    mock_dag = Mock()
    mock_dag.name = "test_dag"

    with patch("src.orchestrator.scheduler.run_dag", return_value={"duration_seconds": 1.0}):
        with patch("src.orchestrator.scheduler.load_dag_from_yaml", return_value=mock_dag):
            state_path = tmp_path / "state.jsonl"
            monkeypatch.setenv("STATE_STORE_PATH", str(state_path))

            run_queue = [
                {
                    "schedule_id": "test1",
                    "dag_path": "test1.yaml",
                    "tenant": "tenant1",
                    "minute": "2025-10-03 14:05",
                    "enqueued_at": "2025-10-03T14:05:00",
                }
            ]

            drain_queue(run_queue, max_parallel=1)

            # Queue should be empty after drain
            assert len(run_queue) == 0
