"""Tests for cost ledger (Sprint 30)."""

import json
import os
from datetime import UTC, datetime, timedelta

from src.cost.ledger import load_cost_events, rollup, window_sum


def test_load_cost_events_empty(tmp_path):
    """Test loading from empty/missing file."""
    os.environ["COST_EVENTS_PATH"] = str(tmp_path / "missing.jsonl")
    events = load_cost_events()
    assert events == []


def test_load_cost_events_with_window(tmp_path):
    """Test loading with time window."""
    events_file = tmp_path / "cost_events.jsonl"
    os.environ["COST_EVENTS_PATH"] = str(events_file)

    now = datetime.now(UTC)
    old_timestamp = (now - timedelta(days=40)).isoformat()
    recent_timestamp = now.isoformat()

    with open(events_file, "w") as f:
        f.write(json.dumps({"timestamp": old_timestamp, "cost_estimate": 1.0}) + "\n")
        f.write(json.dumps({"timestamp": recent_timestamp, "cost_estimate": 2.0}) + "\n")

    # Load last 30 days (should exclude old event)
    events = load_cost_events(path=events_file, window_days=30)

    assert len(events) == 1
    assert events[0]["cost_estimate"] == 2.0


def test_rollup_by_tenant(tmp_path):
    """Test rollup by tenant."""
    events = [
        {"tenant": "tenant-1", "cost_estimate": 1.0},
        {"tenant": "tenant-1", "cost_estimate": 2.0},
        {"tenant": "tenant-2", "cost_estimate": 5.0},
    ]

    result = rollup(events, by=("tenant",))

    assert len(result) == 2
    # Sorted by cost descending
    assert result[0]["tenant"] == "tenant-2"
    assert result[0]["cost"] == 5.0
    assert result[1]["tenant"] == "tenant-1"
    assert result[1]["cost"] == 3.0  # 1.0 + 2.0


def test_rollup_by_day(tmp_path):
    """Test rollup by day."""
    events = [
        {"timestamp": "2025-10-01T10:00:00Z", "cost_estimate": 1.0},
        {"timestamp": "2025-10-01T11:00:00Z", "cost_estimate": 2.0},
        {"timestamp": "2025-10-02T10:00:00Z", "cost_estimate": 5.0},
    ]

    result = rollup(events, by=("day",))

    assert len(result) == 2
    assert result[0]["day"] == "2025-10-02"
    assert result[0]["cost"] == 5.0
    assert result[1]["day"] == "2025-10-01"
    assert result[1]["cost"] == 3.0


def test_window_sum_global(tmp_path):
    """Test window sum for global."""
    now = datetime.now(UTC)
    today = now.isoformat()
    yesterday = (now - timedelta(days=1)).isoformat()
    old = (now - timedelta(days=5)).isoformat()

    events = [
        {"timestamp": today, "tenant": "tenant-1", "cost_estimate": 1.0},
        {"timestamp": yesterday, "tenant": "tenant-1", "cost_estimate": 2.0},
        {"timestamp": old, "tenant": "tenant-1", "cost_estimate": 3.0},
    ]

    # Last 1 day (today only)
    total = window_sum(events, tenant=None, days=1)
    assert total == 1.0

    # Last 3 days (today + yesterday)
    total = window_sum(events, tenant=None, days=3)
    assert total == 3.0


def test_window_sum_by_tenant(tmp_path):
    """Test window sum filtered by tenant."""
    now = datetime.now(UTC).isoformat()

    events = [
        {"timestamp": now, "tenant": "tenant-1", "cost_estimate": 1.0},
        {"timestamp": now, "tenant": "tenant-2", "cost_estimate": 2.0},
    ]

    total = window_sum(events, tenant="tenant-1", days=1)
    assert total == 1.0
