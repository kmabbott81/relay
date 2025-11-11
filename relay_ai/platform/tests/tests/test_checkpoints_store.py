"""
Tests for src/orchestrator/checkpoints.py

Covers:
- Checkpoint creation and listing
- Approve/reject flows
- Expiration logic
- JSONL persistence
- RBAC enforcement
"""

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from relay_ai.orchestrator.checkpoints import (
    approve_checkpoint,
    create_checkpoint,
    expire_pending,
    get_checkpoint,
    list_checkpoints,
    reject_checkpoint,
)
from relay_ai.security.rbac_check import can_approve


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


def test_create_and_list_checkpoint(temp_checkpoints_path: Path, temp_state_store: Path):
    """Test creating a checkpoint and listing it."""
    checkpoint_id = "run123_approval"
    dag_run_id = "run123"
    task_id = "approval"
    tenant = "tenant-a"
    prompt = "Approve weekly report?"

    # Create checkpoint
    checkpoint = create_checkpoint(
        checkpoint_id=checkpoint_id,
        dag_run_id=dag_run_id,
        task_id=task_id,
        tenant=tenant,
        prompt=prompt,
        required_role="Operator",
        inputs={"signoff": {"type": "string", "required": True}},
    )

    assert checkpoint["checkpoint_id"] == checkpoint_id
    assert checkpoint["status"] == "pending"
    assert checkpoint["prompt"] == prompt
    assert checkpoint["required_role"] == "Operator"

    # List pending checkpoints
    pending = list_checkpoints(status="pending")
    assert len(pending) == 1
    assert pending[0]["checkpoint_id"] == checkpoint_id

    # List by tenant
    tenant_checkpoints = list_checkpoints(tenant=tenant)
    assert len(tenant_checkpoints) == 1

    # List by different tenant (should be empty)
    other_tenant = list_checkpoints(tenant="tenant-b")
    assert len(other_tenant) == 0

    # Verify JSONL file exists and has content
    assert temp_checkpoints_path.exists()
    content = temp_checkpoints_path.read_text()
    assert checkpoint_id in content
    assert "pending" in content


def test_approve_checkpoint(temp_checkpoints_path: Path, temp_state_store: Path):
    """Test approving a checkpoint."""
    checkpoint_id = "run456_approval"

    # Create checkpoint
    create_checkpoint(
        checkpoint_id=checkpoint_id,
        dag_run_id="run456",
        task_id="approval",
        tenant="tenant-a",
        prompt="Approve?",
        required_role="Operator",
    )

    # Approve with data
    approval_data = {"signoff_text": "Approved by manager", "priority": "high"}
    approved = approve_checkpoint(checkpoint_id=checkpoint_id, approved_by="Admin", approval_data=approval_data)

    assert approved["status"] == "approved"
    assert approved["approved_by"] == "Admin"
    assert approved["approval_data"] == approval_data
    assert "approved_at" in approved

    # Verify listing
    approved_list = list_checkpoints(status="approved")
    assert len(approved_list) == 1
    assert approved_list[0]["checkpoint_id"] == checkpoint_id

    # Pending should be empty
    pending = list_checkpoints(status="pending")
    assert len(pending) == 0

    # Get specific checkpoint
    checkpoint = get_checkpoint(checkpoint_id)
    assert checkpoint["status"] == "approved"


def test_reject_checkpoint(temp_checkpoints_path: Path, temp_state_store: Path):
    """Test rejecting a checkpoint."""
    checkpoint_id = "run789_approval"

    # Create checkpoint
    create_checkpoint(
        checkpoint_id=checkpoint_id,
        dag_run_id="run789",
        task_id="approval",
        tenant="tenant-a",
        prompt="Approve?",
        required_role="Operator",
    )

    # Reject with reason
    rejected = reject_checkpoint(checkpoint_id=checkpoint_id, rejected_by="Admin", reason="Budget concerns")

    assert rejected["status"] == "rejected"
    assert rejected["rejected_by"] == "Admin"
    assert rejected["reject_reason"] == "Budget concerns"
    assert "rejected_at" in rejected

    # Verify listing
    rejected_list = list_checkpoints(status="rejected")
    assert len(rejected_list) == 1

    # Pending should be empty
    pending = list_checkpoints(status="pending")
    assert len(pending) == 0


def test_expire_pending_checkpoints(temp_checkpoints_path: Path, temp_state_store: Path):
    """Test expiring old pending checkpoints."""
    # Create checkpoint with past created_at
    checkpoint_id = "run_old_approval"
    past_time = datetime.now(UTC) - timedelta(hours=73)  # Past default 72h expiration

    # Create checkpoint normally first
    create_checkpoint(
        checkpoint_id=checkpoint_id,
        dag_run_id="run_old",
        task_id="approval",
        tenant="tenant-a",
        prompt="Approve?",
        required_role="Operator",
    )

    # Manually modify created_at and expires_at in JSONL to be in the past
    lines = temp_checkpoints_path.read_text().strip().split("\n")

    modified_lines = []
    for line in lines:
        record = json.loads(line)
        if record.get("checkpoint_id") == checkpoint_id and record.get("event") == "checkpoint_created":
            record["created_at"] = past_time.isoformat()
            # Also update expires_at since it's based on created_at
            expires_h = int(os.getenv("APPROVAL_EXPIRES_H", "72"))
            record["expires_at"] = (past_time + timedelta(hours=expires_h)).isoformat()
        modified_lines.append(json.dumps(record))

    temp_checkpoints_path.write_text("\n".join(modified_lines) + "\n")

    # Now expire
    now = datetime.now(UTC)
    expired = expire_pending(now)

    assert len(expired) == 1
    assert expired[0]["checkpoint_id"] == checkpoint_id

    # Verify status updated to expired
    checkpoint = get_checkpoint(checkpoint_id)
    assert checkpoint["status"] == "expired"
    assert "expired_at" in checkpoint

    # Pending should be empty
    pending = list_checkpoints(status="pending")
    assert len(pending) == 0


def test_rbac_approval_authorization():
    """Test RBAC role hierarchy for approvals."""
    # Viewer cannot approve Operator checkpoints
    assert not can_approve("Viewer", "Operator")

    # Operator can approve Operator checkpoints
    assert can_approve("Operator", "Operator")

    # Admin can approve Operator checkpoints
    assert can_approve("Admin", "Operator")

    # Admin can approve Admin checkpoints
    assert can_approve("Admin", "Admin")

    # Operator cannot approve Admin checkpoints
    assert not can_approve("Operator", "Admin")


def test_multiple_checkpoints(temp_checkpoints_path: Path, temp_state_store: Path):
    """Test handling multiple checkpoints with different statuses."""
    # Create 3 checkpoints
    create_checkpoint("run1_cp", "run1", "cp", "tenant-a", "Approve 1?", "Operator")
    create_checkpoint("run2_cp", "run2", "cp", "tenant-a", "Approve 2?", "Operator")
    create_checkpoint("run3_cp", "run3", "cp", "tenant-b", "Approve 3?", "Admin")

    # All pending
    pending = list_checkpoints(status="pending")
    assert len(pending) == 3

    # Approve one
    approve_checkpoint("run1_cp", "Admin")

    # Reject one
    reject_checkpoint("run2_cp", "Admin", "Not ready")

    # Check counts
    pending = list_checkpoints(status="pending")
    assert len(pending) == 1
    assert pending[0]["checkpoint_id"] == "run3_cp"

    approved = list_checkpoints(status="approved")
    assert len(approved) == 1

    rejected = list_checkpoints(status="rejected")
    assert len(rejected) == 1

    # Filter by tenant
    tenant_a = list_checkpoints(tenant="tenant-a")
    assert len(tenant_a) == 2  # run1 (approved) and run2 (rejected)

    tenant_b = list_checkpoints(tenant="tenant-b")
    assert len(tenant_b) == 1  # run3 (pending)


def test_jsonl_integrity(temp_checkpoints_path: Path, temp_state_store: Path):
    """Test that JSONL file maintains integrity across operations."""
    checkpoint_id = "run_integrity"

    # Create
    create_checkpoint(checkpoint_id, "run_integrity", "cp", "tenant-a", "Approve?", "Operator")

    # Verify file has 1 line
    lines = temp_checkpoints_path.read_text().strip().split("\n")
    assert len(lines) == 1

    # Approve
    approve_checkpoint(checkpoint_id, "Admin")

    # Verify file has 2 lines (create + approve)
    lines = temp_checkpoints_path.read_text().strip().split("\n")
    assert len(lines) == 2

    # Verify both lines are valid JSON
    import json

    for line in lines:
        record = json.loads(line)
        assert "checkpoint_id" in record
        assert "event" in record

    # Verify events
    events = [json.loads(line)["event"] for line in lines]
    assert "checkpoint_created" in events
    assert "checkpoint_approved" in events


def test_get_nonexistent_checkpoint(temp_checkpoints_path: Path, temp_state_store: Path):
    """Test getting a checkpoint that doesn't exist."""
    checkpoint = get_checkpoint("nonexistent")
    assert checkpoint is None


def test_expire_with_no_old_checkpoints(temp_checkpoints_path: Path, temp_state_store: Path):
    """Test expiration when no checkpoints are old enough."""
    # Create recent checkpoint
    create_checkpoint("run_recent", "run_recent", "cp", "tenant-a", "Approve?", "Operator")

    # Try to expire (should return empty list)
    now = datetime.now(UTC)
    expired = expire_pending(now)

    assert len(expired) == 0

    # Checkpoint should still be pending
    pending = list_checkpoints(status="pending")
    assert len(pending) == 1
