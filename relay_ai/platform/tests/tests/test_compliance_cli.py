"""
Tests for Compliance CLI - Sprint 33A

Covers CLI commands with RBAC checks and exit codes.
"""

import json
import subprocess
import sys

import pytest


@pytest.fixture
def cli_env(tmp_path, monkeypatch):
    """Setup environment for CLI tests."""
    # Create sample data
    orch_events = tmp_path / "orch_events.jsonl"
    with open(orch_events, "w") as f:
        f.write(json.dumps({"event": "dag_start", "tenant": "tenant-a"}) + "\n")

    # Set environment
    monkeypatch.setenv("ORCH_EVENTS_PATH", str(orch_events))
    monkeypatch.setenv("QUEUE_EVENTS_PATH", str(tmp_path / "queue.jsonl"))
    monkeypatch.setenv("COST_LOG_PATH", str(tmp_path / "cost.jsonl"))
    monkeypatch.setenv("APPROVALS_LOG_PATH", str(tmp_path / "approvals.jsonl"))
    monkeypatch.setenv("GOV_EVENTS_PATH", str(tmp_path / "gov.jsonl"))
    monkeypatch.setenv("STORAGE_BASE_PATH", str(tmp_path / "artifacts"))
    monkeypatch.setenv("LOGS_LEGAL_HOLDS_PATH", str(tmp_path / "legal_holds.jsonl"))

    return tmp_path


def run_cli(cmd, env=None):
    """Run CLI command and return result."""
    full_env = {**env} if env else {}
    result = subprocess.run(
        [sys.executable, "scripts/compliance.py"] + cmd,
        capture_output=True,
        text=True,
        env={**subprocess.os.environ, **full_env},
    )
    return result


def test_cli_export_success(cli_env, monkeypatch):
    """Test export command succeeds with Auditor role."""
    out_dir = cli_env / "exports"
    out_dir.mkdir()

    result = run_cli(
        ["export", "--tenant", "tenant-a", "--out", str(out_dir)],
        env={"USER_RBAC_ROLE": "Auditor"},
    )

    assert result.returncode == 0
    output = json.loads(result.stdout)
    assert output["tenant"] == "tenant-a"


def test_cli_export_rbac_denied(cli_env):
    """Test export fails with Viewer role (exit code 2)."""
    out_dir = cli_env / "exports"
    out_dir.mkdir()

    result = run_cli(
        ["export", "--tenant", "tenant-a", "--out", str(out_dir)],
        env={"USER_RBAC_ROLE": "Viewer"},
    )

    assert result.returncode == 2
    error = json.loads(result.stderr)
    assert error["code"] == "RBAC_DENIED"


def test_cli_delete_dry_run(cli_env):
    """Test delete dry-run command."""
    result = run_cli(["delete", "--tenant", "tenant-a", "--dry-run"], env={"USER_RBAC_ROLE": "Compliance"})

    assert result.returncode == 0
    output = json.loads(result.stdout)
    assert output["dry_run"] is True


def test_cli_delete_rbac_denied(cli_env):
    """Test delete fails with Auditor role (exit code 2)."""
    result = run_cli(["delete", "--tenant", "tenant-a"], env={"USER_RBAC_ROLE": "Auditor"})

    assert result.returncode == 2
    error = json.loads(result.stderr)
    assert error["code"] == "RBAC_DENIED"


def test_cli_hold_success(cli_env):
    """Test applying legal hold succeeds."""
    result = run_cli(
        ["hold", "--tenant", "tenant-a", "--reason", "Litigation"],
        env={"USER_RBAC_ROLE": "Compliance"},
    )

    assert result.returncode == 0
    output = json.loads(result.stdout)
    assert output["event"] == "hold_applied"


def test_cli_release_success(cli_env):
    """Test releasing legal hold succeeds."""
    # First apply hold
    run_cli(["hold", "--tenant", "tenant-a", "--reason", "Test"], env={"USER_RBAC_ROLE": "Compliance"})

    # Then release
    result = run_cli(["release", "--tenant", "tenant-a"], env={"USER_RBAC_ROLE": "Compliance"})

    assert result.returncode == 0
    output = json.loads(result.stdout)
    assert output["event"] == "hold_released"


def test_cli_release_no_hold_fails(cli_env):
    """Test releasing non-existent hold fails (exit code 1)."""
    result = run_cli(["release", "--tenant", "tenant-a"], env={"USER_RBAC_ROLE": "Compliance"})

    assert result.returncode == 1


def test_cli_holds_list(cli_env):
    """Test listing active holds."""
    # Apply hold first
    run_cli(["hold", "--tenant", "tenant-a", "--reason", "Test"], env={"USER_RBAC_ROLE": "Compliance"})

    # List holds
    result = run_cli(["holds", "--list"], env={"USER_RBAC_ROLE": "Compliance"})

    assert result.returncode == 0
    output = json.loads(result.stdout)
    assert output["count"] == 1
    assert output["holds"][0]["tenant"] == "tenant-a"


def test_cli_retention_success(cli_env):
    """Test retention enforcement succeeds."""
    result = run_cli(["retention"], env={"USER_RBAC_ROLE": "Compliance"})

    assert result.returncode == 0
    output = json.loads(result.stdout)
    assert "enforced_at" in output


def test_cli_retention_rbac_denied(cli_env):
    """Test retention fails with Auditor role (exit code 2)."""
    result = run_cli(["retention"], env={"USER_RBAC_ROLE": "Auditor"})

    assert result.returncode == 2


def test_cli_delete_with_legal_hold(cli_env):
    """Test delete fails with active legal hold (exit code 3)."""
    # Apply hold
    run_cli(["hold", "--tenant", "tenant-a", "--reason", "Test"], env={"USER_RBAC_ROLE": "Compliance"})

    # Try to delete
    result = run_cli(["delete", "--tenant", "tenant-a"], env={"USER_RBAC_ROLE": "Compliance"})

    assert result.returncode == 3
    error = json.loads(result.stderr)
    assert error["code"] == "LEGAL_HOLD"


def test_cli_no_command_shows_help(cli_env):
    """Test running CLI without command shows help."""
    result = run_cli([], env={"USER_RBAC_ROLE": "Compliance"})

    assert result.returncode == 1
    assert "usage:" in result.stdout.lower() or "help" in result.stdout.lower()


def test_cli_json_output_format(cli_env):
    """Test that all CLI commands output valid JSON."""
    # Export
    out_dir = cli_env / "exports"
    out_dir.mkdir()
    result = run_cli(
        ["export", "--tenant", "tenant-a", "--out", str(out_dir)],
        env={"USER_RBAC_ROLE": "Auditor"},
    )
    assert result.returncode == 0
    json.loads(result.stdout)  # Should not raise

    # Delete dry-run
    result = run_cli(["delete", "--tenant", "tenant-a", "--dry-run"], env={"USER_RBAC_ROLE": "Compliance"})
    assert result.returncode == 0
    json.loads(result.stdout)  # Should not raise

    # Holds list
    result = run_cli(["holds", "--list"], env={"USER_RBAC_ROLE": "Compliance"})
    assert result.returncode == 0
    json.loads(result.stdout)  # Should not raise
