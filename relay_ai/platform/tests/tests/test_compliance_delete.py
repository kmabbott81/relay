"""
Tests for Compliance Delete - Sprint 33A

Covers tenant data deletion with dry-run, legal hold, and RBAC enforcement.
"""

import json

import pytest

from relay_ai.compliance.api import delete_tenant
from relay_ai.compliance.holds import apply_legal_hold


@pytest.fixture
def temp_data_store(tmp_path, monkeypatch):
    """Setup temporary data stores with sample tenant data."""
    # Create sample event logs
    orch_events = tmp_path / "orch_events.jsonl"
    with open(orch_events, "w") as f:
        f.write(json.dumps({"event": "dag_start", "tenant": "tenant-a"}) + "\n")
        f.write(json.dumps({"event": "dag_start", "tenant": "tenant-b"}) + "\n")
        f.write(json.dumps({"event": "dag_done", "tenant": "tenant-a"}) + "\n")

    queue_events = tmp_path / "queue_events.jsonl"
    with open(queue_events, "w") as f:
        f.write(json.dumps({"event": "job_queued", "tenant": "tenant-a"}) + "\n")
        f.write(json.dumps({"event": "job_queued", "tenant": "tenant-b"}) + "\n")

    cost_events = tmp_path / "cost_events.jsonl"
    with open(cost_events, "w") as f:
        f.write(json.dumps({"tenant": "tenant-a", "cost_usd": 0.05}) + "\n")

    # Set environment variables
    monkeypatch.setenv("ORCH_EVENTS_PATH", str(orch_events))
    monkeypatch.setenv("QUEUE_EVENTS_PATH", str(queue_events))
    monkeypatch.setenv("COST_LOG_PATH", str(cost_events))
    monkeypatch.setenv("APPROVALS_LOG_PATH", str(tmp_path / "approvals.jsonl"))
    monkeypatch.setenv("GOV_EVENTS_PATH", str(tmp_path / "gov_events.jsonl"))
    monkeypatch.setenv("STORAGE_BASE_PATH", str(tmp_path / "artifacts"))
    monkeypatch.setenv("LOGS_LEGAL_HOLDS_PATH", str(tmp_path / "legal_holds.jsonl"))
    monkeypatch.setenv("USER_RBAC_ROLE", "Compliance")

    # Create artifacts
    (tmp_path / "artifacts" / "hot" / "tenant-a").mkdir(parents=True, exist_ok=True)
    (tmp_path / "artifacts" / "hot" / "tenant-a" / "test.md").write_text("test")

    return tmp_path


def test_delete_tenant_dry_run(temp_data_store):
    """Test dry-run shows what would be deleted without deleting."""
    result = delete_tenant("tenant-a", dry_run=True)

    assert result["dry_run"] is True
    assert result["tenant"] == "tenant-a"
    assert result["deleted_at"] is None
    assert result["counts"]["orch_events"] == 2
    assert result["counts"]["queue_events"] == 1

    # Verify data still exists
    orch_path = temp_data_store / "orch_events.jsonl"
    with open(orch_path) as f:
        lines = f.readlines()
    assert len(lines) == 3  # Still 3 events


def test_delete_tenant_live(temp_data_store):
    """Test live deletion removes tenant data."""
    result = delete_tenant("tenant-a", dry_run=False)

    assert result["dry_run"] is False
    assert "deleted_at" in result
    assert result["counts"]["orch_events"] == 2

    # Verify data removed
    orch_path = temp_data_store / "orch_events.jsonl"
    with open(orch_path) as f:
        events = [json.loads(line) for line in f if line.strip()]

    # Should only have tenant-b event
    assert len(events) == 1
    assert events[0]["tenant"] == "tenant-b"


def test_delete_respects_legal_hold(temp_data_store):
    """Test that deletion is blocked if legal hold active."""
    apply_legal_hold("tenant-a", "Litigation")

    with pytest.raises(ValueError, match="active legal hold"):
        delete_tenant("tenant-a")


def test_delete_ignores_legal_hold_with_flag(temp_data_store):
    """Test that deletion can override legal hold if specified."""
    apply_legal_hold("tenant-a", "Litigation")

    # Should succeed with respect_legal_hold=False
    result = delete_tenant("tenant-a", respect_legal_hold=False)
    assert result["tenant"] == "tenant-a"


def test_delete_rbac_compliance_allowed(temp_data_store, monkeypatch):
    """Test that Compliance role can delete."""
    monkeypatch.setenv("USER_RBAC_ROLE", "Compliance")

    result = delete_tenant("tenant-a", dry_run=True)
    assert result["tenant"] == "tenant-a"


def test_delete_rbac_auditor_denied(temp_data_store, monkeypatch):
    """Test that Auditor role cannot delete."""
    monkeypatch.setenv("USER_RBAC_ROLE", "Auditor")

    with pytest.raises(PermissionError, match="requires Compliance"):
        delete_tenant("tenant-a", dry_run=True)


def test_delete_rbac_admin_allowed(temp_data_store, monkeypatch):
    """Test that Admin role can delete."""
    monkeypatch.setenv("USER_RBAC_ROLE", "Admin")

    result = delete_tenant("tenant-a", dry_run=True)
    assert result["tenant"] == "tenant-a"


def test_delete_preserves_other_tenants(temp_data_store):
    """Test that deletion doesn't affect other tenants."""
    delete_tenant("tenant-a", dry_run=False)

    # Check tenant-b data still exists
    queue_path = temp_data_store / "queue_events.jsonl"
    with open(queue_path) as f:
        events = [json.loads(line) for line in f if line.strip()]

    assert len(events) == 1
    assert events[0]["tenant"] == "tenant-b"


def test_delete_empty_tenant(temp_data_store):
    """Test deleting tenant with no data."""
    result = delete_tenant("tenant-nonexistent")

    assert result["counts"]["orch_events"] == 0
    assert result["total_items"] == 0


def test_delete_idempotent(temp_data_store):
    """Test that deleting twice doesn't error."""
    delete_tenant("tenant-a")
    result = delete_tenant("tenant-a")  # Second deletion

    assert result["total_items"] == 0  # Nothing left to delete


def test_delete_counts_accurate(temp_data_store):
    """Test that deletion counts match actual items."""
    result = delete_tenant("tenant-a", dry_run=False)

    # Verify counts
    assert result["counts"]["orch_events"] == 2
    assert result["counts"]["queue_events"] == 1
    assert result["counts"]["cost_events"] == 1
    # Total includes artifacts (1 file created in fixture)
    assert result["total_items"] >= 4
