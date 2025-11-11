"""Tests for orchestrator analytics helpers (Sprint 27C)."""

from datetime import UTC, datetime, timedelta

from relay_ai.orchestrator.analytics import (
    load_events,
    per_tenant_load,
    summarize_dags,
    summarize_schedules,
    summarize_tasks,
)


def test_load_events_from_file(tmp_path):
    """Test loading events from JSONL file."""
    events_file = tmp_path / "test_events.jsonl"

    # Write sample events
    with open(events_file, "w", encoding="utf-8") as f:
        f.write('{"event": "test1", "timestamp": "2025-10-03T10:00:00"}\n')
        f.write('{"event": "test2", "timestamp": "2025-10-03T10:01:00"}\n')
        f.write('{"event": "test3", "timestamp": "2025-10-03T10:02:00"}\n')

    events = load_events(events_file, limit=10)

    assert len(events) == 3
    assert events[0]["event"] == "test3"  # Most recent first
    assert events[1]["event"] == "test2"
    assert events[2]["event"] == "test1"


def test_load_events_skips_corrupted_lines(tmp_path):
    """Test that corrupted lines are skipped."""
    events_file = tmp_path / "test_events.jsonl"

    with open(events_file, "w", encoding="utf-8") as f:
        f.write('{"event": "valid1"}\n')
        f.write("invalid json line\n")
        f.write('{"event": "valid2"}\n')

    events = load_events(events_file, limit=10)

    assert len(events) == 2
    assert events[0]["event"] == "valid2"
    assert events[1]["event"] == "valid1"


def test_load_events_missing_file():
    """Test loading from missing file returns empty list."""
    events = load_events("/nonexistent/file.jsonl", limit=10)
    assert events == []


def test_load_events_respects_limit(tmp_path):
    """Test that load_events respects limit."""
    events_file = tmp_path / "test_events.jsonl"

    # Write 100 events
    with open(events_file, "w", encoding="utf-8") as f:
        for i in range(100):
            f.write(f'{{"event": "test{i}"}}\n')

    events = load_events(events_file, limit=10)

    assert len(events) == 10
    # Should get last 10 events (90-99)
    assert events[0]["event"] == "test99"
    assert events[9]["event"] == "test90"


def test_summarize_tasks_empty_events():
    """Test summarize_tasks with no events."""
    stats = summarize_tasks([], window_hours=24)

    assert stats["all_time"]["tasks_started"] == 0
    assert stats["all_time"]["tasks_ok"] == 0
    assert stats["all_time"]["tasks_fail"] == 0
    assert stats["last_24h"]["tasks_ok"] == 0


def test_summarize_tasks_counts_events():
    """Test summarize_tasks counts task events correctly."""
    now = datetime.now(UTC)
    recent = now.isoformat()
    old = (now - timedelta(hours=48)).isoformat()

    events = [
        {"event": "task_start", "timestamp": recent},
        {"event": "task_ok", "timestamp": recent},
        {"event": "task_start", "timestamp": recent},
        {"event": "task_fail", "timestamp": recent},
        {"event": "task_ok", "timestamp": old},  # Old event (not in last 24h)
        {"event": "task_retry", "timestamp": recent},
    ]

    stats = summarize_tasks(events, window_hours=24)

    # All time
    assert stats["all_time"]["tasks_started"] == 2
    assert stats["all_time"]["tasks_ok"] == 2
    assert stats["all_time"]["tasks_fail"] == 1
    assert stats["all_time"]["tasks_retry"] == 1

    # Last 24h (excludes old event)
    assert stats["last_24h"]["tasks_started"] == 2
    assert stats["last_24h"]["tasks_ok"] == 1  # Only recent ok
    assert stats["last_24h"]["tasks_fail"] == 1


def test_summarize_tasks_calculates_error_rate():
    """Test error rate calculation."""
    now = datetime.now(UTC).isoformat()

    events = [
        {"event": "task_start", "timestamp": now},
        {"event": "task_ok", "timestamp": now},
        {"event": "task_start", "timestamp": now},
        {"event": "task_fail", "timestamp": now},
        {"event": "task_start", "timestamp": now},
        {"event": "task_ok", "timestamp": now},
        {"event": "task_start", "timestamp": now},
        {"event": "task_fail", "timestamp": now},
    ]

    stats = summarize_tasks(events, window_hours=24)

    # 2 failures out of 4 started = 50% error rate
    assert stats["last_24h"]["error_rate"] == 0.5


def test_summarize_dags_empty_events():
    """Test summarize_dags with no events."""
    runs = summarize_dags([], limit=10)
    assert runs == []


def test_summarize_dags_tracks_runs():
    """Test summarize_dags tracks DAG runs correctly."""
    events = [
        {"event": "dag_start", "dag_name": "dag1", "timestamp": "2025-10-03T10:00:00"},
        {"event": "task_ok", "dag_name": "dag1"},
        {"event": "task_ok", "dag_name": "dag1"},
        {"event": "task_fail", "dag_name": "dag1"},
        {
            "event": "dag_done",
            "dag_name": "dag1",
            "duration_seconds": 5.2,
            "timestamp": "2025-10-03T10:00:05",
        },
        {"event": "dag_start", "dag_name": "dag2", "timestamp": "2025-10-03T10:01:00"},
        {"event": "task_ok", "dag_name": "dag2"},
        {
            "event": "dag_done",
            "dag_name": "dag2",
            "duration_seconds": 2.1,
            "timestamp": "2025-10-03T10:01:02",
        },
    ]

    runs = summarize_dags(events, limit=10)

    assert len(runs) == 2

    # dag2 should be first (more recent)
    assert runs[0]["dag_name"] == "dag2"
    assert runs[0]["status"] == "completed"
    assert runs[0]["tasks_ok"] == 1
    assert runs[0]["duration"] == 2.1

    # dag1 should be second
    assert runs[1]["dag_name"] == "dag1"
    assert runs[1]["status"] == "completed"
    assert runs[1]["tasks_ok"] == 2
    assert runs[1]["tasks_fail"] == 1
    assert runs[1]["duration"] == 5.2


def test_summarize_dags_respects_limit():
    """Test summarize_dags respects limit."""
    events = []
    for i in range(20):
        events.append(
            {
                "event": "dag_start",
                "dag_name": f"dag{i}",
                "timestamp": f"2025-10-03T10:{i:02d}:00",
            }
        )

    runs = summarize_dags(events, limit=5)

    assert len(runs) == 5
    # Should get most recent 5 (15-19)
    assert runs[0]["dag_name"] == "dag19"
    assert runs[4]["dag_name"] == "dag15"


def test_summarize_schedules_empty_events():
    """Test summarize_schedules with no events."""
    schedules = summarize_schedules([])
    assert schedules == []


def test_summarize_schedules_tracks_runs():
    """Test summarize_schedules tracks schedule runs."""
    events = [
        {
            "event": "schedule_enqueued",
            "schedule_id": "sched1",
            "timestamp": "2025-10-03T10:00:00",
        },
        {
            "event": "run_started",
            "schedule_id": "sched1",
            "timestamp": "2025-10-03T10:00:01",
        },
        {
            "event": "run_finished",
            "schedule_id": "sched1",
            "status": "success",
            "timestamp": "2025-10-03T10:00:05",
        },
        {
            "event": "schedule_enqueued",
            "schedule_id": "sched1",
            "timestamp": "2025-10-03T10:05:00",
        },
        {
            "event": "run_started",
            "schedule_id": "sched1",
            "timestamp": "2025-10-03T10:05:01",
        },
        {
            "event": "run_finished",
            "schedule_id": "sched1",
            "status": "failed",
            "timestamp": "2025-10-03T10:05:05",
        },
    ]

    schedules = summarize_schedules(events)

    assert len(schedules) == 1

    sched = schedules[0]
    assert sched["schedule_id"] == "sched1"
    assert sched["enqueued_count"] == 2
    assert sched["started_count"] == 2
    assert sched["finished_count"] == 2
    assert sched["success_count"] == 1
    assert sched["failed_count"] == 1
    assert sched["last_status"] == "failed"


def test_per_tenant_load_empty_events():
    """Test per_tenant_load with no events."""
    tenants = per_tenant_load([], window_hours=24)
    assert tenants == []


def test_per_tenant_load_aggregates_by_tenant():
    """Test per_tenant_load aggregates by tenant."""
    now = datetime.now(UTC)
    recent = now.isoformat()

    events = [
        {"event": "dag_start", "tenant": "tenant1", "timestamp": recent},
        {"event": "task_ok", "tenant": "tenant1", "timestamp": recent},
        {"event": "task_ok", "tenant": "tenant1", "timestamp": recent},
        {"event": "dag_start", "tenant": "tenant2", "timestamp": recent},
        {"event": "task_ok", "tenant": "tenant2", "timestamp": recent},
        {"event": "task_fail", "tenant": "tenant2", "timestamp": recent},
    ]

    tenants = per_tenant_load(events, window_hours=24)

    assert len(tenants) == 2

    # Sorted by run count descending
    assert tenants[0]["tenant"] == "tenant1" or tenants[0]["tenant"] == "tenant2"

    tenant1 = next(t for t in tenants if t["tenant"] == "tenant1")
    assert tenant1["runs"] == 1
    assert tenant1["tasks"] == 2
    assert tenant1["error_rate"] == 0.0

    tenant2 = next(t for t in tenants if t["tenant"] == "tenant2")
    assert tenant2["runs"] == 1
    assert tenant2["tasks"] == 2
    assert tenant2["error_rate"] == 0.5  # 1 error out of 2 tasks


def test_per_tenant_load_filters_by_window():
    """Test per_tenant_load filters by time window."""
    now = datetime.now(UTC)
    recent = now.isoformat()
    old = (now - timedelta(hours=48)).isoformat()

    events = [
        {"event": "dag_start", "tenant": "tenant1", "timestamp": recent},
        {"event": "task_ok", "tenant": "tenant1", "timestamp": recent},
        {"event": "dag_start", "tenant": "tenant2", "timestamp": old},  # Too old
        {"event": "task_ok", "tenant": "tenant2", "timestamp": old},
    ]

    tenants = per_tenant_load(events, window_hours=24)

    # Only tenant1 should be included
    assert len(tenants) == 1
    assert tenants[0]["tenant"] == "tenant1"
