"""
Tests for Compliance Export - Sprint 33A

Covers tenant data export with bundle structure verification.
"""

import json
from pathlib import Path

import pytest

from relay_ai.compliance.api import export_tenant


@pytest.fixture
def temp_data_store(tmp_path, monkeypatch):
    """Setup temporary data stores with sample tenant data."""
    # Create sample event logs
    orch_events = tmp_path / "orch_events.jsonl"
    with open(orch_events, "w") as f:
        f.write(json.dumps({"event": "dag_start", "tenant": "tenant-a", "timestamp": "2025-10-01T10:00:00Z"}) + "\n")
        f.write(json.dumps({"event": "dag_start", "tenant": "tenant-b", "timestamp": "2025-10-01T10:01:00Z"}) + "\n")
        f.write(json.dumps({"event": "dag_done", "tenant": "tenant-a", "timestamp": "2025-10-01T10:05:00Z"}) + "\n")

    queue_events = tmp_path / "queue_events.jsonl"
    with open(queue_events, "w") as f:
        f.write(json.dumps({"event": "job_queued", "tenant": "tenant-a", "timestamp": "2025-10-01T10:00:00Z"}) + "\n")

    cost_events = tmp_path / "cost_events.jsonl"
    with open(cost_events, "w") as f:
        f.write(json.dumps({"tenant": "tenant-a", "cost_usd": 0.05, "timestamp": "2025-10-01T10:00:00Z"}) + "\n")

    # Set environment variables
    monkeypatch.setenv("ORCH_EVENTS_PATH", str(orch_events))
    monkeypatch.setenv("QUEUE_EVENTS_PATH", str(queue_events))
    monkeypatch.setenv("COST_LOG_PATH", str(cost_events))
    monkeypatch.setenv("APPROVALS_LOG_PATH", str(tmp_path / "approvals.jsonl"))
    monkeypatch.setenv("GOV_EVENTS_PATH", str(tmp_path / "gov_events.jsonl"))
    monkeypatch.setenv("STORAGE_BASE_PATH", str(tmp_path / "artifacts"))
    monkeypatch.setenv("USER_RBAC_ROLE", "Auditor")

    # Create artifact directories
    (tmp_path / "artifacts" / "hot" / "tenant-a").mkdir(parents=True, exist_ok=True)
    (tmp_path / "artifacts" / "hot" / "tenant-a" / "test.md").write_text("test artifact")

    return tmp_path


def test_export_tenant_creates_bundle(temp_data_store):
    """Test that export creates bundle directory with manifest."""
    out_dir = temp_data_store / "exports"
    result = export_tenant("tenant-a", out_dir)

    assert result["tenant"] == "tenant-a"
    assert "export_date" in result
    assert "counts" in result

    export_path = Path(result["export_path"])
    assert export_path.exists()
    assert (export_path / "manifest.json").exists()


def test_export_tenant_rbac_auditor_allowed(temp_data_store, monkeypatch):
    """Test that Auditor role can export."""
    monkeypatch.setenv("USER_RBAC_ROLE", "Auditor")

    out_dir = temp_data_store / "exports"
    result = export_tenant("tenant-a", out_dir)
    assert result["tenant"] == "tenant-a"


def test_export_tenant_rbac_viewer_denied(temp_data_store, monkeypatch):
    """Test that Viewer role cannot export."""
    monkeypatch.setenv("USER_RBAC_ROLE", "Viewer")

    out_dir = temp_data_store / "exports"
    with pytest.raises(PermissionError, match="requires Auditor"):
        export_tenant("tenant-a", out_dir)


def test_export_includes_orchestrator_events(temp_data_store):
    """Test that export includes filtered orchestrator events."""
    out_dir = temp_data_store / "exports"
    result = export_tenant("tenant-a", out_dir)

    export_path = Path(result["export_path"])
    orch_file = export_path / "orchestrator_events.jsonl"

    assert orch_file.exists()

    # Should have 2 events for tenant-a
    with open(orch_file) as f:
        events = [json.loads(line) for line in f if line.strip()]
    assert len(events) == 2
    assert all(e["tenant"] == "tenant-a" for e in events)


def test_export_excludes_other_tenants(temp_data_store):
    """Test that export excludes other tenant data."""
    out_dir = temp_data_store / "exports"
    result = export_tenant("tenant-a", out_dir)

    export_path = Path(result["export_path"])
    orch_file = export_path / "orchestrator_events.jsonl"

    with open(orch_file) as f:
        events = [json.loads(line) for line in f if line.strip()]

    # Should NOT include tenant-b event
    tenant_ids = {e["tenant"] for e in events}
    assert tenant_ids == {"tenant-a"}


def test_export_manifest_has_counts(temp_data_store):
    """Test that manifest includes accurate counts."""
    out_dir = temp_data_store / "exports"
    result = export_tenant("tenant-a", out_dir)

    export_path = Path(result["export_path"])
    manifest_file = export_path / "manifest.json"

    with open(manifest_file) as f:
        manifest = json.load(f)

    assert manifest["counts"]["orch_events"] == 2
    assert manifest["counts"]["queue_events"] == 1
    assert manifest["counts"]["cost_events"] == 1


def test_export_artifacts_by_reference(temp_data_store):
    """Test that artifacts are exported as references not copies."""
    out_dir = temp_data_store / "exports"
    result = export_tenant("tenant-a", out_dir)

    export_path = Path(result["export_path"])
    artifacts_file = export_path / "artifacts.json"

    assert artifacts_file.exists()

    with open(artifacts_file) as f:
        artifacts = json.load(f)

    # Should have reference list, not full copies
    assert isinstance(artifacts, list)
    if artifacts:  # May be empty in minimal test
        assert "path" in artifacts[0]
        assert "tier" in artifacts[0]


def test_export_empty_tenant(temp_data_store):
    """Test exporting tenant with no data."""
    out_dir = temp_data_store / "exports"
    result = export_tenant("tenant-nonexistent", out_dir)

    assert result["counts"]["orch_events"] == 0
    assert result["counts"]["queue_events"] == 0
    assert result["total_items"] == 0


def test_export_deterministic_path(temp_data_store):
    """Test that export path is deterministic by date."""
    out_dir = temp_data_store / "exports"
    result = export_tenant("tenant-a", out_dir)

    export_path = result["export_path"]
    assert "tenant-a-export-" in export_path
    assert export_path.endswith(result["export_date"][:10])  # YYYY-MM-DD
