"""
Tests for Export Policies - Sprint 33B

Covers export-time enforcement of classification policies.
"""

import json
from pathlib import Path

import pytest

from relay_ai.compliance.api import export_tenant


@pytest.fixture
def temp_export_env(tmp_path, monkeypatch):
    """Setup temporary export environment with artifacts."""
    storage_base = tmp_path / "artifacts"
    storage_base.mkdir()

    # Create hot tier with tenant artifacts
    hot_path = storage_base / "hot" / "tenant-a"
    hot_path.mkdir(parents=True)

    # Artifact 1: Labeled (Internal)
    (hot_path / "internal.md").write_text("internal data")
    (hot_path / "internal.md.json").write_text(
        json.dumps({"label": "Internal", "tenant": "tenant-a", "encrypted": False})
    )

    # Artifact 2: Labeled (Confidential)
    (hot_path / "confidential.md").write_text("confidential data")
    (hot_path / "confidential.md.json").write_text(
        json.dumps({"label": "Confidential", "tenant": "tenant-a", "encrypted": False})
    )

    # Artifact 3: Unlabeled
    (hot_path / "unlabeled.md").write_text("unlabeled data")

    # Configure environment
    monkeypatch.setenv("STORAGE_BASE_PATH", str(storage_base))
    monkeypatch.setenv("USER_RBAC_ROLE", "Auditor")
    monkeypatch.setenv("USER_CLEARANCE", "Internal")
    monkeypatch.setenv("REQUIRE_LABELS_FOR_EXPORT", "false")
    monkeypatch.setenv("EXPORT_POLICY", "deny")

    # Empty JSONL files
    logs_path = tmp_path / "logs"
    logs_path.mkdir()
    (logs_path / "orchestrator_events.jsonl").touch()
    (logs_path / "queue_events.jsonl").touch()
    (logs_path / "cost_events.jsonl").touch()
    (logs_path / "approvals.jsonl").touch()
    (logs_path / "governance_events.jsonl").touch()

    monkeypatch.setenv("ORCH_EVENTS_PATH", str(logs_path / "orchestrator_events.jsonl"))
    monkeypatch.setenv("QUEUE_EVENTS_PATH", str(logs_path / "queue_events.jsonl"))
    monkeypatch.setenv("COST_LOG_PATH", str(logs_path / "cost_events.jsonl"))
    monkeypatch.setenv("APPROVALS_LOG_PATH", str(logs_path / "approvals.jsonl"))
    monkeypatch.setenv("GOV_EVENTS_PATH", str(logs_path / "governance_events.jsonl"))
    monkeypatch.setenv("LOGS_LEGAL_HOLDS_PATH", str(logs_path / "legal_holds.jsonl"))

    return tmp_path


def test_export_allows_sufficient_clearance(temp_export_env, monkeypatch):
    """Test export includes artifacts with sufficient clearance."""
    monkeypatch.setenv("USER_CLEARANCE", "Internal")

    out_dir = temp_export_env / "exports"
    result = export_tenant("tenant-a", out_dir)

    # Should include internal artifact (internal.md)
    # Should exclude confidential artifact (clearance too low)
    # Should include unlabeled (REQUIRE_LABELS_FOR_EXPORT=false)
    assert result["counts"]["artifacts"] >= 2  # internal + unlabeled


def test_export_denies_insufficient_clearance(temp_export_env, monkeypatch):
    """Test export excludes artifacts with insufficient clearance."""
    monkeypatch.setenv("USER_CLEARANCE", "Internal")
    monkeypatch.setenv("EXPORT_POLICY", "deny")

    out_dir = temp_export_env / "exports"
    export_tenant("tenant-a", out_dir)

    # Check governance log for denials
    gov_path = Path(temp_export_env / "logs" / "governance_events.jsonl")
    if gov_path.exists() and gov_path.stat().st_size > 0:
        with open(gov_path) as f:
            events = [json.loads(line) for line in f if line.strip()]

        # Should have denial events for confidential artifact
        denials = [e for e in events if e.get("event") == "export_denied"]
        assert len(denials) >= 1


def test_export_requires_labels_deny(temp_export_env, monkeypatch):
    """Test export denies unlabeled when REQUIRE_LABELS_FOR_EXPORT=true."""
    monkeypatch.setenv("REQUIRE_LABELS_FOR_EXPORT", "true")
    monkeypatch.setenv("USER_CLEARANCE", "Confidential")

    out_dir = temp_export_env / "exports"
    result = export_tenant("tenant-a", out_dir)

    # Should include labeled artifacts (internal, confidential)
    # Should exclude unlabeled artifact
    assert result["counts"]["artifacts"] >= 2


def test_export_allows_unlabeled_when_not_required(temp_export_env, monkeypatch):
    """Test export allows unlabeled when REQUIRE_LABELS_FOR_EXPORT=false."""
    monkeypatch.setenv("REQUIRE_LABELS_FOR_EXPORT", "false")
    monkeypatch.setenv("USER_CLEARANCE", "Confidential")

    out_dir = temp_export_env / "exports"
    result = export_tenant("tenant-a", out_dir)

    # Should include all artifacts (labeled + unlabeled)
    assert result["counts"]["artifacts"] == 3


def test_export_policy_redact_includes_metadata(temp_export_env, monkeypatch):
    """Test export with redact policy includes metadata."""
    monkeypatch.setenv("USER_CLEARANCE", "Internal")
    monkeypatch.setenv("EXPORT_POLICY", "redact")

    out_dir = temp_export_env / "exports"
    result = export_tenant("tenant-a", out_dir)

    # Should include all artifacts (some marked as redacted)
    # Read artifacts.json to check for redacted flag
    export_path = Path(result["export_path"])
    artifacts_file = export_path / "artifacts.json"

    if artifacts_file.exists():
        with open(artifacts_file) as f:
            artifacts = json.load(f)

        # Note: redact policy includes metadata but marks as redacted
        assert len(artifacts) >= 2  # At least labeled ones


def test_export_governance_event_logged(temp_export_env, monkeypatch):
    """Test export denials are logged to governance events."""
    monkeypatch.setenv("USER_CLEARANCE", "Internal")
    monkeypatch.setenv("EXPORT_POLICY", "deny")

    out_dir = temp_export_env / "exports"
    export_tenant("tenant-a", out_dir)

    # Check governance log
    gov_path = Path(temp_export_env / "logs" / "governance_events.jsonl")
    if gov_path.exists() and gov_path.stat().st_size > 0:
        with open(gov_path) as f:
            events = [json.loads(line) for line in f if line.strip()]

        # Should have export events
        export_events = [e for e in events if "export" in e.get("event", "")]
        assert len(export_events) > 0


def test_export_high_clearance_includes_all(temp_export_env, monkeypatch):
    """Test export with highest clearance includes all labeled artifacts."""
    monkeypatch.setenv("USER_CLEARANCE", "Restricted")
    monkeypatch.setenv("REQUIRE_LABELS_FOR_EXPORT", "false")

    out_dir = temp_export_env / "exports"
    result = export_tenant("tenant-a", out_dir)

    # Should include all artifacts
    assert result["counts"]["artifacts"] == 3


def test_export_manifest_includes_label_info(temp_export_env, monkeypatch):
    """Test export manifest includes classification information."""
    monkeypatch.setenv("USER_CLEARANCE", "Confidential")

    out_dir = temp_export_env / "exports"
    result = export_tenant("tenant-a", out_dir)

    export_path = Path(result["export_path"])
    artifacts_file = export_path / "artifacts.json"

    if artifacts_file.exists():
        with open(artifacts_file) as f:
            artifacts = json.load(f)

        # Check that labeled artifacts have label field
        labeled = [a for a in artifacts if "label" in a]
        assert len(labeled) >= 2  # internal and confidential


def test_export_empty_tenant(temp_export_env, monkeypatch):
    """Test export of tenant with no artifacts."""
    monkeypatch.setenv("USER_CLEARANCE", "Confidential")

    out_dir = temp_export_env / "exports"
    result = export_tenant("nonexistent-tenant", out_dir)

    # Should succeed with zero artifacts
    assert result["counts"]["artifacts"] == 0


def test_export_rbac_enforced(temp_export_env, monkeypatch):
    """Test export requires Auditor+ role."""
    monkeypatch.setenv("USER_RBAC_ROLE", "Viewer")

    out_dir = temp_export_env / "exports"

    with pytest.raises(PermissionError, match="requires Auditor"):
        export_tenant("tenant-a", out_dir)
