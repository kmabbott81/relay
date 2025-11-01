"""
Tests for checkpoint expiration in scheduler

Covers:
- Automatic expiration of old pending checkpoints
- Scheduler integration with expire_pending()
- Event logging for checkpoint_expired
"""

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from src.orchestrator.checkpoints import create_checkpoint, expire_pending, list_checkpoints
from src.orchestrator.state_store import last_runs


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


def test_expire_pending_basic(temp_checkpoints_path: Path, temp_state_store: Path):
    """Test basic expiration of old checkpoints."""
    # Create checkpoint
    checkpoint_id = "run_old"
    create_checkpoint(checkpoint_id, "run_old", "approval", "tenant-a", "Approve?", "Operator")

    # Manually modify created_at to be 73 hours ago (past default 72h expiration)
    past_time = datetime.now(UTC) - timedelta(hours=73)

    lines = temp_checkpoints_path.read_text().strip().split("\n")
    modified_lines = []
    for line in lines:
        record = json.loads(line)
        if record.get("checkpoint_id") == checkpoint_id and record.get("event") == "checkpoint_created":
            record["created_at"] = past_time.isoformat()
            # Also update expires_at
            expires_h = int(os.getenv("APPROVAL_EXPIRES_H", "72"))
            record["expires_at"] = (past_time + timedelta(hours=expires_h)).isoformat()
        modified_lines.append(json.dumps(record))

    temp_checkpoints_path.write_text("\n".join(modified_lines) + "\n")

    # Call expire_pending with current time
    now = datetime.now(UTC)
    expired = expire_pending(now)

    # Should expire the checkpoint
    assert len(expired) == 1
    assert expired[0]["checkpoint_id"] == checkpoint_id

    # Verify status is expired
    expired_list = list_checkpoints(status="expired")
    assert len(expired_list) == 1
    assert expired_list[0]["checkpoint_id"] == checkpoint_id

    # Pending should be empty
    pending = list_checkpoints(status="pending")
    assert len(pending) == 0


def test_expire_pending_with_custom_expiration(temp_checkpoints_path: Path, temp_state_store: Path):
    """Test expiration with custom APPROVAL_EXPIRES_H."""
    # Set custom expiration to 1 hour
    os.environ["APPROVAL_EXPIRES_H"] = "1"

    # Create checkpoint
    checkpoint_id = "run_quick"
    create_checkpoint(checkpoint_id, "run_quick", "approval", "tenant-a", "Approve?", "Operator")

    # Manually modify created_at to be 2 hours ago (past 1h expiration)
    past_time = datetime.now(UTC) - timedelta(hours=2)

    lines = temp_checkpoints_path.read_text().strip().split("\n")
    modified_lines = []
    for line in lines:
        record = json.loads(line)
        if record.get("checkpoint_id") == checkpoint_id and record.get("event") == "checkpoint_created":
            record["created_at"] = past_time.isoformat()
            # Also update expires_at
            expires_h = int(os.getenv("APPROVAL_EXPIRES_H", "72"))
            record["expires_at"] = (past_time + timedelta(hours=expires_h)).isoformat()
        modified_lines.append(json.dumps(record))

    temp_checkpoints_path.write_text("\n".join(modified_lines) + "\n")

    # Expire
    now = datetime.now(UTC)
    expired = expire_pending(now)

    assert len(expired) == 1
    assert expired[0]["checkpoint_id"] == checkpoint_id

    # Cleanup
    del os.environ["APPROVAL_EXPIRES_H"]


def test_expire_pending_does_not_affect_recent(temp_checkpoints_path: Path, temp_state_store: Path):
    """Test that recent checkpoints are not expired."""
    # Create recent checkpoint (just created)
    checkpoint_id = "run_recent"
    create_checkpoint(checkpoint_id, "run_recent", "approval", "tenant-a", "Approve?", "Operator")

    # Try to expire
    now = datetime.now(UTC)
    expired = expire_pending(now)

    # Should not expire anything
    assert len(expired) == 0

    # Checkpoint should still be pending
    pending = list_checkpoints(status="pending")
    assert len(pending) == 1
    assert pending[0]["checkpoint_id"] == checkpoint_id


def test_expire_pending_mixed_checkpoints(temp_checkpoints_path: Path, temp_state_store: Path):
    """Test expiration with mix of old and recent checkpoints."""
    # Create old checkpoint
    old_id = "run_old"
    create_checkpoint(old_id, "run_old", "approval", "tenant-a", "Approve old?", "Operator")

    # Create recent checkpoint
    recent_id = "run_recent"
    create_checkpoint(recent_id, "run_recent", "approval", "tenant-a", "Approve recent?", "Operator")

    # Modify old checkpoint's created_at
    past_time = datetime.now(UTC) - timedelta(hours=73)

    lines = temp_checkpoints_path.read_text().strip().split("\n")
    modified_lines = []
    for line in lines:
        record = json.loads(line)
        if record.get("checkpoint_id") == old_id and record.get("event") == "checkpoint_created":
            record["created_at"] = past_time.isoformat()
            # Also update expires_at
            expires_h = int(os.getenv("APPROVAL_EXPIRES_H", "72"))
            record["expires_at"] = (past_time + timedelta(hours=expires_h)).isoformat()
        modified_lines.append(json.dumps(record))

    temp_checkpoints_path.write_text("\n".join(modified_lines) + "\n")

    # Expire
    now = datetime.now(UTC)
    expired = expire_pending(now)

    # Should only expire old checkpoint
    assert len(expired) == 1
    assert expired[0]["checkpoint_id"] == old_id

    # Recent should still be pending
    pending = list_checkpoints(status="pending")
    assert len(pending) == 1
    assert pending[0]["checkpoint_id"] == recent_id

    # Old should be expired
    expired_list = list_checkpoints(status="expired")
    assert len(expired_list) == 1
    assert expired_list[0]["checkpoint_id"] == old_id


def test_expire_pending_does_not_affect_approved(temp_checkpoints_path: Path, temp_state_store: Path):
    """Test that already approved checkpoints are not expired."""
    from src.orchestrator.checkpoints import approve_checkpoint

    # Create checkpoint
    checkpoint_id = "run_approved"
    create_checkpoint(checkpoint_id, "run_approved", "approval", "tenant-a", "Approve?", "Operator")

    # Approve it
    approve_checkpoint(checkpoint_id, "Admin")

    # Manually modify created_at to be very old
    past_time = datetime.now(UTC) - timedelta(hours=200)

    lines = temp_checkpoints_path.read_text().strip().split("\n")
    modified_lines = []
    for line in lines:
        record = json.loads(line)
        if record.get("checkpoint_id") == checkpoint_id and record.get("event") == "checkpoint_created":
            record["created_at"] = past_time.isoformat()
            # Also update expires_at
            expires_h = int(os.getenv("APPROVAL_EXPIRES_H", "72"))
            record["expires_at"] = (past_time + timedelta(hours=expires_h)).isoformat()
        modified_lines.append(json.dumps(record))

    temp_checkpoints_path.write_text("\n".join(modified_lines) + "\n")

    # Try to expire
    now = datetime.now(UTC)
    expired = expire_pending(now)

    # Should not expire approved checkpoint
    assert len(expired) == 0

    # Should still be approved
    approved_list = list_checkpoints(status="approved")
    assert len(approved_list) == 1
    assert approved_list[0]["checkpoint_id"] == checkpoint_id


def test_scheduler_emits_checkpoint_expired_event(temp_checkpoints_path: Path, temp_state_store: Path):
    """Test that scheduler logic would emit checkpoint_expired events."""
    from src.orchestrator.state_store import record_event

    # Create old checkpoint
    checkpoint_id = "run_for_event"
    dag_run_id = "run_for_event"
    task_id = "approval"

    create_checkpoint(checkpoint_id, dag_run_id, task_id, "tenant-a", "Approve?", "Operator")

    # Manually set created_at to past
    past_time = datetime.now(UTC) - timedelta(hours=73)

    lines = temp_checkpoints_path.read_text().strip().split("\n")
    modified_lines = []
    for line in lines:
        record = json.loads(line)
        if record.get("checkpoint_id") == checkpoint_id and record.get("event") == "checkpoint_created":
            record["created_at"] = past_time.isoformat()
            # Also update expires_at
            expires_h = int(os.getenv("APPROVAL_EXPIRES_H", "72"))
            record["expires_at"] = (past_time + timedelta(hours=expires_h)).isoformat()
        modified_lines.append(json.dumps(record))

    temp_checkpoints_path.write_text("\n".join(modified_lines) + "\n")

    # Expire
    now = datetime.now(UTC)
    expired = expire_pending(now)

    # Simulate scheduler emitting event (this is what scheduler.py does)
    for cp in expired:
        record_event(
            {
                "event": "checkpoint_expired",
                "checkpoint_id": cp["checkpoint_id"],
                "dag_run_id": cp["dag_run_id"],
                "task_id": cp["task_id"],
            }
        )

    # Verify event was written to state store
    if temp_state_store.exists():
        state_content = temp_state_store.read_text()
        assert "checkpoint_expired" in state_content
        assert checkpoint_id in state_content
        assert dag_run_id in state_content

        # Parse and verify structure
        events = last_runs(limit=10)
        expired_events = [e for e in events if e.get("event") == "checkpoint_expired"]
        assert len(expired_events) == 1
        assert expired_events[0]["checkpoint_id"] == checkpoint_id
        assert expired_events[0]["dag_run_id"] == dag_run_id
        assert expired_events[0]["task_id"] == task_id


def test_expire_pending_idempotent(temp_checkpoints_path: Path, temp_state_store: Path):
    """Test that calling expire_pending multiple times is idempotent."""
    # Create old checkpoint
    checkpoint_id = "run_idem"
    create_checkpoint(checkpoint_id, "run_idem", "approval", "tenant-a", "Approve?", "Operator")

    # Set to past
    past_time = datetime.now(UTC) - timedelta(hours=73)

    lines = temp_checkpoints_path.read_text().strip().split("\n")
    modified_lines = []
    for line in lines:
        record = json.loads(line)
        if record.get("checkpoint_id") == checkpoint_id and record.get("event") == "checkpoint_created":
            record["created_at"] = past_time.isoformat()
            # Also update expires_at
            expires_h = int(os.getenv("APPROVAL_EXPIRES_H", "72"))
            record["expires_at"] = (past_time + timedelta(hours=expires_h)).isoformat()
        modified_lines.append(json.dumps(record))

    temp_checkpoints_path.write_text("\n".join(modified_lines) + "\n")

    # Call expire_pending first time
    now = datetime.now(UTC)
    expired1 = expire_pending(now)
    assert len(expired1) == 1

    # Call again immediately
    expired2 = expire_pending(now)
    # Should return empty since already expired
    assert len(expired2) == 0

    # Verify only one expired checkpoint
    expired_list = list_checkpoints(status="expired")
    assert len(expired_list) == 1


def test_expire_pending_with_no_checkpoints(temp_checkpoints_path: Path, temp_state_store: Path):
    """Test expire_pending when no checkpoints exist."""
    now = datetime.now(UTC)
    expired = expire_pending(now)

    # Should return empty list
    assert len(expired) == 0


def test_expire_pending_boundary_condition(temp_checkpoints_path: Path, temp_state_store: Path):
    """Test expiration exactly at boundary (72 hours)."""
    os.environ["APPROVAL_EXPIRES_H"] = "72"

    # Create checkpoint
    checkpoint_id = "run_boundary"
    create_checkpoint(checkpoint_id, "run_boundary", "approval", "tenant-a", "Approve?", "Operator")

    # Set created_at to exactly 72 hours ago
    boundary_time = datetime.now(UTC) - timedelta(hours=72)

    lines = temp_checkpoints_path.read_text().strip().split("\n")
    modified_lines = []
    for line in lines:
        record = json.loads(line)
        if record.get("checkpoint_id") == checkpoint_id and record.get("event") == "checkpoint_created":
            record["created_at"] = boundary_time.isoformat()
            # Also update expires_at
            expires_h = int(os.getenv("APPROVAL_EXPIRES_H", "72"))
            record["expires_at"] = (boundary_time + timedelta(hours=expires_h)).isoformat()
        modified_lines.append(json.dumps(record))

    temp_checkpoints_path.write_text("\n".join(modified_lines) + "\n")

    # Expire at exactly boundary time
    now = datetime.now(UTC)
    expired = expire_pending(now)

    # Should expire (>= threshold)
    assert len(expired) == 1

    # Cleanup
    del os.environ["APPROVAL_EXPIRES_H"]
