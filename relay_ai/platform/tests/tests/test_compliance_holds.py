"""
Tests for Legal Hold Store - Sprint 33A

Covers apply/release/list legal holds with JSONL integrity.
"""

import pytest

from relay_ai.compliance.holds import (
    apply_legal_hold,
    current_holds,
    is_on_hold,
    release_legal_hold,
)


def test_apply_legal_hold(tmp_path, monkeypatch):
    """Test applying legal hold to tenant."""
    holds_path = tmp_path / "legal_holds.jsonl"
    monkeypatch.setenv("LOGS_LEGAL_HOLDS_PATH", str(holds_path))

    event = apply_legal_hold("tenant-a", "Litigation hold")

    assert event["event"] == "hold_applied"
    assert event["tenant"] == "tenant-a"
    assert event["reason"] == "Litigation hold"
    assert "timestamp" in event


def test_apply_hold_requires_reason(tmp_path, monkeypatch):
    """Test that hold requires non-empty reason."""
    holds_path = tmp_path / "legal_holds.jsonl"
    monkeypatch.setenv("LOGS_LEGAL_HOLDS_PATH", str(holds_path))

    with pytest.raises(ValueError, match="reason is required"):
        apply_legal_hold("tenant-a", "")


def test_is_on_hold_after_apply(tmp_path, monkeypatch):
    """Test that is_on_hold returns True after apply."""
    holds_path = tmp_path / "legal_holds.jsonl"
    monkeypatch.setenv("LOGS_LEGAL_HOLDS_PATH", str(holds_path))

    apply_legal_hold("tenant-a", "Litigation")
    assert is_on_hold("tenant-a")


def test_is_on_hold_false_by_default(tmp_path, monkeypatch):
    """Test that is_on_hold returns False for tenant without hold."""
    holds_path = tmp_path / "legal_holds.jsonl"
    monkeypatch.setenv("LOGS_LEGAL_HOLDS_PATH", str(holds_path))

    assert not is_on_hold("tenant-a")


def test_release_legal_hold(tmp_path, monkeypatch):
    """Test releasing legal hold."""
    holds_path = tmp_path / "legal_holds.jsonl"
    monkeypatch.setenv("LOGS_LEGAL_HOLDS_PATH", str(holds_path))

    apply_legal_hold("tenant-a", "Litigation")
    event = release_legal_hold("tenant-a")

    assert event["event"] == "hold_released"
    assert event["tenant"] == "tenant-a"
    assert not is_on_hold("tenant-a")


def test_release_hold_fails_without_active_hold(tmp_path, monkeypatch):
    """Test that release fails if no active hold."""
    holds_path = tmp_path / "legal_holds.jsonl"
    monkeypatch.setenv("LOGS_LEGAL_HOLDS_PATH", str(holds_path))

    with pytest.raises(ValueError, match="No active legal hold"):
        release_legal_hold("tenant-a")


def test_multiple_holds_same_tenant(tmp_path, monkeypatch):
    """Test multiple apply/release cycles for same tenant."""
    holds_path = tmp_path / "legal_holds.jsonl"
    monkeypatch.setenv("LOGS_LEGAL_HOLDS_PATH", str(holds_path))

    # First hold
    apply_legal_hold("tenant-a", "Case 1")
    assert is_on_hold("tenant-a")
    release_legal_hold("tenant-a")
    assert not is_on_hold("tenant-a")

    # Second hold
    apply_legal_hold("tenant-a", "Case 2")
    assert is_on_hold("tenant-a")
    release_legal_hold("tenant-a")
    assert not is_on_hold("tenant-a")


def test_current_holds_empty_by_default(tmp_path, monkeypatch):
    """Test that current_holds returns empty list initially."""
    holds_path = tmp_path / "legal_holds.jsonl"
    monkeypatch.setenv("LOGS_LEGAL_HOLDS_PATH", str(holds_path))

    holds = current_holds()
    assert holds == []


def test_current_holds_lists_active(tmp_path, monkeypatch):
    """Test that current_holds lists active holds."""
    holds_path = tmp_path / "legal_holds.jsonl"
    monkeypatch.setenv("LOGS_LEGAL_HOLDS_PATH", str(holds_path))

    apply_legal_hold("tenant-a", "Case 1")
    apply_legal_hold("tenant-b", "Case 2")

    holds = current_holds()
    assert len(holds) == 2

    tenants = {h["tenant"] for h in holds}
    assert tenants == {"tenant-a", "tenant-b"}


def test_current_holds_excludes_released(tmp_path, monkeypatch):
    """Test that released holds are not in current_holds."""
    holds_path = tmp_path / "legal_holds.jsonl"
    monkeypatch.setenv("LOGS_LEGAL_HOLDS_PATH", str(holds_path))

    apply_legal_hold("tenant-a", "Case 1")
    apply_legal_hold("tenant-b", "Case 2")
    release_legal_hold("tenant-a")

    holds = current_holds()
    assert len(holds) == 1
    assert holds[0]["tenant"] == "tenant-b"


def test_holds_survive_malformed_lines(tmp_path, monkeypatch):
    """Test that malformed JSONL lines don't crash hold tracking."""
    holds_path = tmp_path / "legal_holds.jsonl"
    monkeypatch.setenv("LOGS_LEGAL_HOLDS_PATH", str(holds_path))

    apply_legal_hold("tenant-a", "Case 1")

    # Inject malformed line
    with open(holds_path, "a") as f:
        f.write("not valid json\n")
        f.write("{}\n")

    # Should still work
    assert is_on_hold("tenant-a")
    holds = current_holds()
    assert len(holds) == 1


def test_idempotent_hold_application(tmp_path, monkeypatch):
    """Test that applying hold twice doesn't break state."""
    holds_path = tmp_path / "legal_holds.jsonl"
    monkeypatch.setenv("LOGS_LEGAL_HOLDS_PATH", str(holds_path))

    apply_legal_hold("tenant-a", "Case 1")
    apply_legal_hold("tenant-a", "Case 1 - Updated")

    # Should have 2 apply events but still be on hold
    assert is_on_hold("tenant-a")

    # Need to release twice (once per apply)
    release_legal_hold("tenant-a")
    assert is_on_hold("tenant-a")  # Still on hold after first release
    release_legal_hold("tenant-a")
    assert not is_on_hold("tenant-a")  # Released after second
