"""Tests for DLQ (Sprint 29)."""

import os

from relay_ai.queue.dlq import append_to_dlq, list_dlq, replay_job


def test_dlq_append_and_list(tmp_path):
    """Test appending to and listing from DLQ."""
    os.environ["DLQ_PATH"] = str(tmp_path / "test_dlq.jsonl")

    job_dict = {
        "id": "job-1",
        "dag_path": "test.yaml",
        "tenant_id": "tenant-1",
        "status": "failed",
    }

    append_to_dlq(job_dict, reason="max_retries")

    entries = list_dlq(limit=10)

    assert len(entries) == 1
    assert entries[0]["reason"] == "max_retries"
    assert entries[0]["job"]["id"] == "job-1"


def test_dlq_list_empty():
    """Test listing from empty DLQ."""
    os.environ["DLQ_PATH"] = "/nonexistent/dlq.jsonl"
    entries = list_dlq(limit=10)
    assert entries == []


def test_dlq_list_respects_limit(tmp_path):
    """Test list_dlq respects limit."""
    os.environ["DLQ_PATH"] = str(tmp_path / "test_dlq.jsonl")

    # Add 10 jobs
    for i in range(10):
        job_dict = {"id": f"job-{i}", "dag_path": "test.yaml"}
        append_to_dlq(job_dict, reason="max_retries")

    entries = list_dlq(limit=5)

    assert len(entries) == 5
    # Most recent first
    assert entries[0]["job"]["id"] == "job-9"


def test_dlq_replay_job(tmp_path):
    """Test replaying job from DLQ."""
    os.environ["DLQ_PATH"] = str(tmp_path / "test_dlq.jsonl")

    job_dict = {
        "id": "job-replay",
        "dag_path": "test.yaml",
        "tenant_id": "tenant-1",
        "status": "failed",
    }

    append_to_dlq(job_dict, reason="max_retries")

    replayed = replay_job("job-replay")

    assert replayed is not None
    assert replayed["id"] == "job-replay"


def test_dlq_replay_nonexistent(tmp_path):
    """Test replaying nonexistent job returns None."""
    os.environ["DLQ_PATH"] = str(tmp_path / "test_dlq.jsonl")

    replayed = replay_job("nonexistent")
    assert replayed is None
