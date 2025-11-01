"""Tests for JSONL state store (Sprint 27B)."""


from src.orchestrator.state_store import index_by, last_runs, record_event


def test_record_and_read_events(tmp_path):
    """Test recording and reading events."""
    store_path = tmp_path / "state.jsonl"

    # Record events
    record_event({"event": "test1", "value": 1}, path=str(store_path))
    record_event({"event": "test2", "value": 2}, path=str(store_path))
    record_event({"event": "test3", "value": 3}, path=str(store_path))

    # Read back
    events = last_runs(limit=10, path=str(store_path))

    assert len(events) == 3
    assert events[0]["event"] == "test3"  # Most recent first
    assert events[1]["event"] == "test2"
    assert events[2]["event"] == "test1"


def test_last_runs_respects_limit(tmp_path):
    """Test that last_runs respects limit."""
    store_path = tmp_path / "state.jsonl"

    # Record 10 events
    for i in range(10):
        record_event({"event": f"test{i}", "value": i}, path=str(store_path))

    # Request only last 3
    events = last_runs(limit=3, path=str(store_path))

    assert len(events) == 3
    assert events[0]["event"] == "test9"
    assert events[1]["event"] == "test8"
    assert events[2]["event"] == "test7"


def test_empty_file_returns_empty_list(tmp_path):
    """Test reading from empty file."""
    store_path = tmp_path / "state.jsonl"
    store_path.touch()  # Create empty file

    events = last_runs(limit=10, path=str(store_path))
    assert events == []


def test_missing_file_returns_empty_list(tmp_path):
    """Test reading from missing file."""
    store_path = tmp_path / "nonexistent.jsonl"

    events = last_runs(limit=10, path=str(store_path))
    assert events == []


def test_corrupted_lines_skipped(tmp_path):
    """Test that corrupted JSON lines are skipped."""
    store_path = tmp_path / "state.jsonl"

    # Write mix of valid and invalid lines
    with open(store_path, "w", encoding="utf-8") as f:
        f.write('{"event": "valid1"}\n')
        f.write("invalid json line\n")
        f.write('{"event": "valid2"}\n')
        f.write('{"incomplete": \n')
        f.write('{"event": "valid3"}\n')

    events = last_runs(limit=10, path=str(store_path))

    assert len(events) == 3
    assert events[0]["event"] == "valid3"
    assert events[1]["event"] == "valid2"
    assert events[2]["event"] == "valid1"


def test_auto_adds_timestamp(tmp_path):
    """Test that timestamp is automatically added."""
    store_path = tmp_path / "state.jsonl"

    record_event({"event": "test"}, path=str(store_path))

    events = last_runs(limit=1, path=str(store_path))

    assert "timestamp" in events[0]
    assert events[0]["event"] == "test"


def test_index_by_groups_events(tmp_path):
    """Test indexing events by field."""
    store_path = tmp_path / "state.jsonl"

    # Record events with schedule_id field
    record_event({"schedule_id": "sched1", "status": "success"}, path=str(store_path))
    record_event({"schedule_id": "sched1", "status": "failed"}, path=str(store_path))
    record_event({"schedule_id": "sched2", "status": "success"}, path=str(store_path))
    record_event({"schedule_id": "sched2", "status": "success"}, path=str(store_path))
    record_event({"schedule_id": "sched3", "status": "success"}, path=str(store_path))

    # Index by schedule_id
    index = index_by("schedule_id", limit=100, path=str(store_path))

    assert len(index) == 3
    assert len(index["sched1"]) == 2
    assert len(index["sched2"]) == 2
    assert len(index["sched3"]) == 1


def test_index_by_respects_limit(tmp_path):
    """Test that index_by respects limit."""
    store_path = tmp_path / "state.jsonl"

    # Record 10 events
    for i in range(10):
        record_event({"schedule_id": f"sched{i % 3}", "value": i}, path=str(store_path))

    # Index with limit=5 (only last 5 events)
    index = index_by("schedule_id", limit=5, path=str(store_path))

    # Count total events in index
    total = sum(len(events) for events in index.values())
    assert total == 5


def test_index_by_empty_file(tmp_path):
    """Test indexing empty file."""
    store_path = tmp_path / "state.jsonl"
    store_path.touch()

    index = index_by("schedule_id", limit=100, path=str(store_path))
    assert index == {}


def test_concurrent_writes_append_correctly(tmp_path):
    """Test simulated concurrent writes (sequential in test)."""
    store_path = tmp_path / "state.jsonl"

    # Simulate multiple writers
    for i in range(5):
        record_event({"writer": "A", "value": i}, path=str(store_path))
        record_event({"writer": "B", "value": i}, path=str(store_path))

    events = last_runs(limit=100, path=str(store_path))
    assert len(events) == 10

    # Check interleaved pattern
    assert events[-1]["writer"] == "A"  # First write
    assert events[-2]["writer"] == "B"  # Second write
