"""
Tests for scripts/approvals.py CLI

Covers:
- List pending checkpoints
- Approve with RBAC checks
- Reject with reason
- Command-line argument parsing
"""

import json
import os
from pathlib import Path

import pytest

from scripts.approvals import approve_command, list_command, reject_command
from relay_ai.orchestrator.checkpoints import create_checkpoint


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
def sample_checkpoints(temp_checkpoints_path: Path, temp_state_store: Path):
    """Create sample checkpoints for testing."""
    create_checkpoint(
        checkpoint_id="run1_approval",
        dag_run_id="run1",
        task_id="approval",
        tenant="tenant-a",
        prompt="Approve weekly report?",
        required_role="Operator",
        inputs={"signoff": {"type": "string", "required": True}},
    )

    create_checkpoint(
        checkpoint_id="run2_approval",
        dag_run_id="run2",
        task_id="approval",
        tenant="tenant-b",
        prompt="Approve budget allocation?",
        required_role="Admin",
    )


def test_list_command_shows_pending(
    capsys,
    sample_checkpoints,
    temp_checkpoints_path: Path,
    temp_state_store: Path,
):
    """Test that list command shows pending checkpoints."""
    exit_code = list_command()

    assert exit_code == 0

    # Capture output
    captured = capsys.readouterr()
    output = captured.out

    # Should show checkpoint IDs
    assert "run1_approval" in output
    assert "run2_approval" in output

    # Should show prompts
    assert "Approve weekly report?" in output
    assert "Approve budget allocation?" in output

    # Should show roles
    assert "Operator" in output
    assert "Admin" in output


def test_list_command_with_tenant_filter(
    capsys,
    sample_checkpoints,
    temp_checkpoints_path: Path,
    temp_state_store: Path,
):
    """Test list command with tenant filter."""
    exit_code = list_command(tenant="tenant-a")

    assert exit_code == 0

    captured = capsys.readouterr()
    output = captured.out

    # Should show tenant-a checkpoint
    assert "run1_approval" in output

    # Should NOT show tenant-b checkpoint
    assert "run2_approval" not in output


def test_list_command_no_pending(
    capsys,
    temp_checkpoints_path: Path,
    temp_state_store: Path,
):
    """Test list command when no pending checkpoints."""
    exit_code = list_command()

    assert exit_code == 0

    captured = capsys.readouterr()
    output = captured.out

    # Should indicate no pending checkpoints
    assert "No pending checkpoints" in output or "0 pending" in output


def test_approve_command_success(
    capsys,
    sample_checkpoints,
    temp_checkpoints_path: Path,
    temp_state_store: Path,
):
    """Test approve command with sufficient role."""
    # Set user role to Operator (can approve Operator checkpoints)
    os.environ["USER_RBAC_ROLE"] = "Operator"

    exit_code = approve_command(checkpoint_id="run1_approval", kv={"signoff": "Approved by manager"})

    assert exit_code == 0

    captured = capsys.readouterr()
    output = captured.out

    # Should confirm approval
    assert "approved" in output.lower() or "success" in output.lower()

    # Verify checkpoint is actually approved
    lines = temp_checkpoints_path.read_text().strip().split("\n")
    events = [json.loads(line) for line in lines]
    approved_events = [
        e for e in events if e.get("event") == "checkpoint_approved" and e.get("checkpoint_id") == "run1_approval"
    ]
    assert len(approved_events) == 1
    assert approved_events[0]["approval_data"]["signoff"] == "Approved by manager"

    # Cleanup
    del os.environ["USER_RBAC_ROLE"]


def test_approve_command_insufficient_role(
    capsys,
    sample_checkpoints,
    temp_checkpoints_path: Path,
    temp_state_store: Path,
):
    """Test approve command with insufficient role."""
    # Set user role to Viewer (cannot approve Operator checkpoints)
    os.environ["USER_RBAC_ROLE"] = "Viewer"

    exit_code = approve_command(checkpoint_id="run1_approval")

    assert exit_code == 1  # Should fail

    captured = capsys.readouterr()
    output = captured.out + captured.err

    # Should indicate insufficient permissions
    assert "cannot approve" in output.lower() or "permission" in output.lower() or "role" in output.lower()

    # Verify checkpoint is still pending
    lines = temp_checkpoints_path.read_text().strip().split("\n")
    events = [json.loads(line) for line in lines]
    approved_events = [
        e for e in events if e.get("event") == "checkpoint_approved" and e.get("checkpoint_id") == "run1_approval"
    ]
    assert len(approved_events) == 0

    # Cleanup
    del os.environ["USER_RBAC_ROLE"]


def test_approve_command_admin_can_approve_any(
    capsys,
    sample_checkpoints,
    temp_checkpoints_path: Path,
    temp_state_store: Path,
):
    """Test that Admin can approve any checkpoint."""
    # Set user role to Admin
    os.environ["USER_RBAC_ROLE"] = "Admin"

    # Approve Admin-level checkpoint
    exit_code = approve_command(checkpoint_id="run2_approval")

    assert exit_code == 0

    captured = capsys.readouterr()
    output = captured.out

    assert "approved" in output.lower() or "success" in output.lower()

    # Cleanup
    del os.environ["USER_RBAC_ROLE"]


def test_reject_command_success(
    capsys,
    sample_checkpoints,
    temp_checkpoints_path: Path,
    temp_state_store: Path,
):
    """Test reject command."""
    # Set user role
    os.environ["USER_RBAC_ROLE"] = "Admin"

    exit_code = reject_command(checkpoint_id="run1_approval", reason="Budget concerns")

    assert exit_code == 0

    captured = capsys.readouterr()
    output = captured.out

    # Should confirm rejection
    assert "rejected" in output.lower() or "success" in output.lower()

    # Verify checkpoint is actually rejected
    lines = temp_checkpoints_path.read_text().strip().split("\n")
    events = [json.loads(line) for line in lines]
    rejected_events = [
        e for e in events if e.get("event") == "checkpoint_rejected" and e.get("checkpoint_id") == "run1_approval"
    ]
    assert len(rejected_events) == 1
    assert rejected_events[0]["reject_reason"] == "Budget concerns"

    # Cleanup
    del os.environ["USER_RBAC_ROLE"]


def test_approve_nonexistent_checkpoint(
    capsys,
    temp_checkpoints_path: Path,
    temp_state_store: Path,
):
    """Test approving a checkpoint that doesn't exist."""
    os.environ["USER_RBAC_ROLE"] = "Admin"

    exit_code = approve_command(checkpoint_id="nonexistent")

    assert exit_code == 1  # Should fail

    captured = capsys.readouterr()
    output = captured.out + captured.err

    # Should indicate not found
    assert "not found" in output.lower() or "does not exist" in output.lower()

    # Cleanup
    del os.environ["USER_RBAC_ROLE"]


def test_approve_with_multiple_kv_pairs(
    capsys,
    sample_checkpoints,
    temp_checkpoints_path: Path,
    temp_state_store: Path,
):
    """Test approve command with multiple key-value pairs."""
    os.environ["USER_RBAC_ROLE"] = "Operator"

    kv_data = {
        "signoff": "Approved by manager",
        "priority": "high",
        "notes": "Looks good",
    }

    exit_code = approve_command(checkpoint_id="run1_approval", kv=kv_data)

    assert exit_code == 0

    # Verify all key-value pairs are stored
    lines = temp_checkpoints_path.read_text().strip().split("\n")
    events = [json.loads(line) for line in lines]
    approved_events = [
        e for e in events if e.get("event") == "checkpoint_approved" and e.get("checkpoint_id") == "run1_approval"
    ]
    assert len(approved_events) == 1

    approval_data = approved_events[0]["approval_data"]
    assert approval_data["signoff"] == "Approved by manager"
    assert approval_data["priority"] == "high"
    assert approval_data["notes"] == "Looks good"

    # Cleanup
    del os.environ["USER_RBAC_ROLE"]


def test_default_role_is_viewer(
    capsys,
    sample_checkpoints,
    temp_checkpoints_path: Path,
    temp_state_store: Path,
):
    """Test that default role is Viewer when USER_RBAC_ROLE not set."""
    # Ensure USER_RBAC_ROLE is not set
    if "USER_RBAC_ROLE" in os.environ:
        del os.environ["USER_RBAC_ROLE"]

    # Viewer should not be able to approve Operator checkpoint
    exit_code = approve_command(checkpoint_id="run1_approval")

    assert exit_code == 1

    captured = capsys.readouterr()
    output = captured.out + captured.err

    # Should indicate insufficient permissions
    assert "cannot approve" in output.lower() or "viewer" in output.lower()
