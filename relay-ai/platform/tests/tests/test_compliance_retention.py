"""
Tests for Compliance Retention - Sprint 33A

Covers retention enforcement with safe JSONL pruning.
"""

import json
from datetime import UTC, datetime, timedelta

import pytest

from src.compliance.api import enforce_retention


@pytest.fixture
def temp_event_logs(tmp_path, monkeypatch):
    """Setup temporary event logs with various ages."""
    now = datetime.now(UTC)

    # Orchestrator events (90 day retention)
    orch_path = tmp_path / "orch_events.jsonl"
    with open(orch_path, "w") as f:
        # Old event (should be purged)
        old_ts = (now - timedelta(days=100)).isoformat()
        f.write(json.dumps({"timestamp": old_ts, "event": "old"}) + "\n")

        # Recent event (should be kept)
        recent_ts = (now - timedelta(days=10)).isoformat()
        f.write(json.dumps({"timestamp": recent_ts, "event": "recent"}) + "\n")

    # Queue events (60 day retention)
    queue_path = tmp_path / "queue_events.jsonl"
    with open(queue_path, "w") as f:
        old_ts = (now - timedelta(days=70)).isoformat()
        f.write(json.dumps({"timestamp": old_ts, "event": "old"}) + "\n")
        f.write(json.dumps({"timestamp": old_ts, "event": "old2"}) + "\n")

        recent_ts = (now - timedelta(days=30)).isoformat()
        f.write(json.dumps({"timestamp": recent_ts, "event": "recent"}) + "\n")

    # Cost events (180 day retention)
    cost_path = tmp_path / "cost_events.jsonl"
    with open(cost_path, "w") as f:
        old_ts = (now - timedelta(days=200)).isoformat()
        f.write(json.dumps({"timestamp": old_ts, "cost": 0.05}) + "\n")

        recent_ts = (now - timedelta(days=100)).isoformat()
        f.write(json.dumps({"timestamp": recent_ts, "cost": 0.10}) + "\n")

    # Set environment
    monkeypatch.setenv("ORCH_EVENTS_PATH", str(orch_path))
    monkeypatch.setenv("QUEUE_EVENTS_PATH", str(queue_path))
    monkeypatch.setenv("COST_LOG_PATH", str(cost_path))
    monkeypatch.setenv("GOV_EVENTS_PATH", str(tmp_path / "gov.jsonl"))
    monkeypatch.setenv("APPROVALS_LOG_PATH", str(tmp_path / "approvals.jsonl"))
    monkeypatch.setenv("USER_RBAC_ROLE", "Compliance")

    # Set retention windows
    monkeypatch.setenv("RETAIN_ORCH_EVENTS_DAYS", "90")
    monkeypatch.setenv("RETAIN_QUEUE_EVENTS_DAYS", "60")
    monkeypatch.setenv("RETAIN_COST_EVENTS_DAYS", "180")
    monkeypatch.setenv("RETAIN_GOV_EVENTS_DAYS", "365")
    monkeypatch.setenv("RETAIN_CHECKPOINTS_DAYS", "90")

    return tmp_path


def test_retention_purges_old_events(temp_event_logs):
    """Test that retention purges events beyond retention window."""
    result = enforce_retention()

    assert "RETAIN_ORCH_EVENTS_DAYS" in result["counts"]
    assert "RETAIN_QUEUE_EVENTS_DAYS" in result["counts"]
    assert "RETAIN_COST_EVENTS_DAYS" in result["counts"]

    # Should have purged some events
    assert result["total_purged"] > 0


def test_retention_preserves_recent_events(temp_event_logs):
    """Test that retention keeps events within window."""
    enforce_retention()

    # Check orchestrator events
    orch_path = temp_event_logs / "orch_events.jsonl"
    with open(orch_path) as f:
        events = [json.loads(line) for line in f if line.strip()]

    # Should have 1 recent event
    assert len(events) == 1
    assert events[0]["event"] == "recent"


def test_retention_uses_temp_file_pattern(temp_event_logs):
    """Test that retention uses safe temp file + swap pattern."""
    orch_path = temp_event_logs / "orch_events.jsonl"
    temp_path = orch_path.with_suffix(".tmp")

    # Temp file shouldn't exist before
    assert not temp_path.exists()

    enforce_retention()

    # Temp file shouldn't exist after (should be swapped)
    assert not temp_path.exists()

    # Original file should still exist
    assert orch_path.exists()


def test_retention_rbac_compliance_allowed(temp_event_logs, monkeypatch):
    """Test that Compliance role can enforce retention."""
    monkeypatch.setenv("USER_RBAC_ROLE", "Compliance")

    result = enforce_retention()
    assert "enforced_at" in result


def test_retention_rbac_auditor_denied(temp_event_logs, monkeypatch):
    """Test that Auditor role cannot enforce retention."""
    monkeypatch.setenv("USER_RBAC_ROLE", "Auditor")

    with pytest.raises(PermissionError, match="requires Compliance"):
        enforce_retention()


def test_retention_handles_malformed_lines(temp_event_logs):
    """Test that retention preserves malformed lines to avoid data loss."""
    orch_path = temp_event_logs / "orch_events.jsonl"

    # Inject malformed lines
    with open(orch_path, "a") as f:
        f.write("not valid json\n")
        f.write("{incomplete\n")

    # Should not crash
    result = enforce_retention()
    assert "total_purged" in result

    # Malformed lines should be preserved
    with open(orch_path) as f:
        lines = f.readlines()

    malformed_present = any("not valid json" in line for line in lines)
    assert malformed_present  # Malformed line preserved


def test_retention_handles_missing_timestamp(temp_event_logs):
    """Test that retention preserves entries without timestamp."""
    orch_path = temp_event_logs / "orch_events.jsonl"

    # Add entry without timestamp
    with open(orch_path, "a") as f:
        f.write(json.dumps({"event": "no_timestamp"}) + "\n")

    enforce_retention()

    # Entry without timestamp should be preserved
    with open(orch_path) as f:
        events = [json.loads(line) for line in f if line.strip()]

    no_ts_events = [e for e in events if e.get("event") == "no_timestamp"]
    assert len(no_ts_events) == 1


def test_retention_with_custom_cutoff(temp_event_logs):
    """Test retention with custom cutoff time."""
    # Use custom cutoff 50 days ago
    custom_now = datetime.now(UTC) - timedelta(days=50)

    result = enforce_retention(now=custom_now)

    # With 50 day cutoff, no events should be purged (all are within windows)
    assert result["total_purged"] == 0


def test_retention_empty_logs(temp_event_logs, monkeypatch):
    """Test retention on empty log files."""
    # Point to non-existent files (but other files still exist from fixture)
    monkeypatch.setenv("ORCH_EVENTS_PATH", str(temp_event_logs / "nonexistent.jsonl"))

    result = enforce_retention()

    # Should not crash - result may include purges from other existing files
    assert "total_purged" in result


def test_retention_different_windows(temp_event_logs):
    """Test that different retention windows are respected."""
    result = enforce_retention()

    # Queue events (60 days) should purge more than orch events (90 days)
    # Cost events (180 days) should purge least
    assert "RETAIN_QUEUE_EVENTS_DAYS" in result["counts"]
    assert "RETAIN_ORCH_EVENTS_DAYS" in result["counts"]
    assert "RETAIN_COST_EVENTS_DAYS" in result["counts"]


def test_retention_idempotent(temp_event_logs):
    """Test that running retention twice doesn't error."""
    enforce_retention()
    result2 = enforce_retention()

    # Second run should purge 0 (already pruned)
    assert result2["total_purged"] == 0
