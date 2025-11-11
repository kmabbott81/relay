"""Tests for idempotency store (Sprint 29)."""

import os
from datetime import UTC, datetime, timedelta

from relay_ai.orchestrator.idempotency import already_processed, mark_processed, purge_expired


def test_idempotency_not_processed_initially(tmp_path):
    """Test run_id not processed initially."""
    os.environ["IDEMP_STORE_PATH"] = str(tmp_path / "idemp.jsonl")

    assert already_processed("run-1") is False


def test_idempotency_mark_and_check(tmp_path):
    """Test marking and checking run_id."""
    os.environ["IDEMP_STORE_PATH"] = str(tmp_path / "idemp.jsonl")

    mark_processed("run-1")

    assert already_processed("run-1") is True
    assert already_processed("run-2") is False


def test_idempotency_ttl_honored(tmp_path):
    """Test run_id expires after TTL."""
    os.environ["IDEMP_STORE_PATH"] = str(tmp_path / "idemp.jsonl")
    os.environ["IDEMP_TTL_HOURS"] = "1"  # 1 hour TTL

    # Manually write old entry
    old_timestamp = (datetime.now(UTC) - timedelta(hours=2)).isoformat()

    with open(tmp_path / "idemp.jsonl", "w") as f:
        f.write(f'{{"timestamp": "{old_timestamp}", "run_id": "old-run"}}\\n')

    # Should not be processed (expired)
    assert already_processed("old-run") is False


def test_idempotency_purge(tmp_path):
    """Test purging expired entries."""
    import json as jsonlib

    store_path = tmp_path / "idemp.jsonl"
    os.environ["IDEMP_STORE_PATH"] = str(store_path)
    os.environ["IDEMP_TTL_HOURS"] = "1"

    # Add old and recent entries
    old_timestamp = (datetime.now(UTC) - timedelta(hours=2)).isoformat()
    recent_timestamp = datetime.now(UTC).isoformat()

    with open(store_path, "w") as f:
        f.write(jsonlib.dumps({"timestamp": old_timestamp, "run_id": "old-run"}) + "\n")
        f.write(jsonlib.dumps({"timestamp": recent_timestamp, "run_id": "recent-run"}) + "\n")

    # Purge should remove old entry
    purged = purge_expired()

    assert purged == 1  # One entry removed

    # Verify file has one entry
    with open(store_path) as f:
        lines = [line.strip() for line in f if line.strip()]
        assert len(lines) == 1


def test_idempotency_empty_run_id(tmp_path):
    """Test empty run_id handled gracefully."""
    os.environ["IDEMP_STORE_PATH"] = str(tmp_path / "idemp.jsonl")

    assert already_processed("") is False
    assert already_processed(None) is False

    mark_processed("")  # Should not crash
    mark_processed(None)  # Should not crash
