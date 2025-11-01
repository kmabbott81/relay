"""Tests for Sprint 60 Phase 3 backfill script.

Tests backfill old→new Redis key migration with fakeredis.
"""

import time
from unittest.mock import patch

import fakeredis
import pytest

from scripts.backfill_redis_keys import backfill_keys


@pytest.fixture
def redis_client():
    """Provide FakeRedis client for testing."""
    return fakeredis.FakeStrictRedis(decode_responses=True)


@pytest.fixture
def redis_url_with_fake(redis_client):
    """Provide fake Redis URL with patched redis.from_url."""
    with patch("redis.from_url", return_value=redis_client):
        yield "redis://fake:6379"


def _create_old_job(client, job_id: str, workspace_id: str, status: str = "pending") -> None:
    """Helper to create job in old schema."""
    key = f"ai:jobs:{job_id}"
    client.hset(
        key,
        mapping={
            "job_id": job_id,
            "status": status,
            "action_provider": "google",
            "action_name": "gmail.send",
            "params": '{"to":"test@example.com"}',
            "workspace_id": workspace_id,
            "actor_id": "user-123",
            "result": "null",
            "enqueued_at": "2025-01-01T00:00:00Z",
        },
    )


def _job_exists_in_new_schema(client, job_id: str, workspace_id: str) -> bool:
    """Helper to check if job exists in new schema."""
    new_key = f"ai:job:{workspace_id}:{job_id}"
    return client.exists(new_key)


class TestDryRunMode:
    """Tests for --dry-run mode."""

    def test_dry_run_no_writes_but_counts_increment(self, redis_client, redis_url_with_fake):
        """Dry-run mode counts migrations without writing to new schema."""
        # Create 3 jobs in old schema
        _create_old_job(redis_client, "job-001", "workspace-123")
        _create_old_job(redis_client, "job-002", "workspace-123")
        _create_old_job(redis_client, "job-003", "workspace-456")

        # Run backfill in dry-run mode
        stats = backfill_keys(
            redis_url=redis_url_with_fake,
            dry_run=True,
            rps=1000,
            batch=10,
            cursor="0",
            max_keys=None,
            workspace_filter=None,
            progress_key_prefix="ai:backfill:test",
        )

        # Verify stats
        assert stats["scanned"] == 3
        assert stats["migrated"] == 3  # Counted but not written
        assert stats["skipped_exists"] == 0
        assert stats["skipped_invalid"] == 0
        assert stats["errors"] == 0

        # Verify NO writes to new schema
        assert not _job_exists_in_new_schema(redis_client, "job-001", "workspace-123")
        assert not _job_exists_in_new_schema(redis_client, "job-002", "workspace-123")
        assert not _job_exists_in_new_schema(redis_client, "job-003", "workspace-456")

        # Verify no progress keys stored in dry-run
        assert not redis_client.exists("ai:backfill:test:cursor")
        assert not redis_client.exists("ai:backfill:test:last_job")


class TestExecuteMode:
    """Tests for --execute mode."""

    def test_execute_migrates_missing_new_key(self, redis_client, redis_url_with_fake):
        """Execute mode writes jobs to new schema when missing."""
        # Create job in old schema only
        _create_old_job(redis_client, "job-001", "workspace-123", "completed")

        # Run backfill in execute mode
        stats = backfill_keys(
            redis_url=redis_url_with_fake,
            dry_run=False,
            rps=1000,
            batch=10,
            cursor="0",
            max_keys=None,
            workspace_filter=None,
            progress_key_prefix="ai:backfill:test",
        )

        # Verify migration succeeded
        assert stats["scanned"] == 1
        assert stats["migrated"] == 1
        assert stats["skipped_exists"] == 0
        assert stats["errors"] == 0

        # Verify new key exists with correct data
        assert _job_exists_in_new_schema(redis_client, "job-001", "workspace-123")
        new_key = "ai:job:workspace-123:job-001"
        new_data = redis_client.hgetall(new_key)
        assert new_data["job_id"] == "job-001"
        assert new_data["workspace_id"] == "workspace-123"
        assert new_data["status"] == "completed"

    def test_execute_idempotent_on_second_run(self, redis_client, redis_url_with_fake):
        """Second run skips existing keys (idempotency)."""
        # Create job in old schema
        _create_old_job(redis_client, "job-001", "workspace-123")

        # First run - should migrate
        stats1 = backfill_keys(
            redis_url=redis_url_with_fake,
            dry_run=False,
            rps=1000,
            batch=10,
            cursor="0",
            max_keys=None,
            workspace_filter=None,
            progress_key_prefix="ai:backfill:test",
        )

        assert stats1["migrated"] == 1
        assert stats1["skipped_exists"] == 0

        # Second run - should skip (already exists)
        stats2 = backfill_keys(
            redis_url=redis_url_with_fake,
            dry_run=False,
            rps=1000,
            batch=10,
            cursor="0",
            max_keys=None,
            workspace_filter=None,
            progress_key_prefix="ai:backfill:test",
        )

        assert stats2["migrated"] == 0
        assert stats2["skipped_exists"] == 1  # Skipped because exists

    def test_execute_workspace_filter(self, redis_client, redis_url_with_fake):
        """Workspace filter restricts migration to one workspace."""
        # Create jobs in two workspaces
        _create_old_job(redis_client, "job-001", "workspace-123")
        _create_old_job(redis_client, "job-002", "workspace-456")

        # Run backfill filtered to workspace-123
        stats = backfill_keys(
            redis_url=redis_url_with_fake,
            dry_run=False,
            rps=1000,
            batch=10,
            cursor="0",
            max_keys=None,
            workspace_filter="workspace-123",
            progress_key_prefix="ai:backfill:test",
        )

        # Only job-001 should be migrated
        assert stats["scanned"] == 2  # Both scanned
        assert stats["migrated"] == 1  # Only one migrated
        assert _job_exists_in_new_schema(redis_client, "job-001", "workspace-123")
        assert not _job_exists_in_new_schema(redis_client, "job-002", "workspace-456")


class TestResumability:
    """Tests for resumable backfill with progress tracking."""

    def test_resume_from_stored_cursor_picks_up_where_left_off(self, redis_client, redis_url_with_fake):
        """Backfill resumes from stored cursor on restart."""
        # Create 5 jobs in old schema
        for i in range(5):
            _create_old_job(redis_client, f"job-{i:03d}", "workspace-123")

        # First run - process only 2 jobs (max_keys=2)
        stats1 = backfill_keys(
            redis_url=redis_url_with_fake,
            dry_run=False,
            rps=1000,
            batch=2,
            cursor="0",
            max_keys=2,
            workspace_filter=None,
            progress_key_prefix="ai:backfill:test",
        )

        assert stats1["scanned"] == 2
        assert stats1["migrated"] == 2

        # Verify progress keys stored
        assert redis_client.exists("ai:backfill:test:cursor")
        assert redis_client.exists("ai:backfill:test:last_job")

        # Second run - resume from stored cursor (no max_keys)
        stats2 = backfill_keys(
            redis_url=redis_url_with_fake,
            dry_run=False,
            rps=1000,
            batch=10,
            cursor="0",  # Will be overridden by stored cursor
            max_keys=None,
            workspace_filter=None,
            progress_key_prefix="ai:backfill:test",
        )

        # Should process remaining 3 jobs
        assert stats2["scanned"] >= 3  # May scan more due to SCAN behavior
        assert stats2["migrated"] + stats2["skipped_exists"] >= 3


class TestInvalidData:
    """Tests for handling invalid workspace IDs."""

    def test_invalid_workspace_is_skipped_and_counted(self, redis_client, redis_url_with_fake):
        """Jobs with invalid workspace_id are skipped."""
        # Create jobs with invalid workspace IDs
        _create_old_job(redis_client, "job-001", "WORKSPACE-UPPERCASE")  # Invalid: uppercase
        _create_old_job(redis_client, "job-002", "workspace:colon")  # Invalid: colon
        _create_old_job(redis_client, "job-003", "")  # Invalid: empty
        _create_old_job(redis_client, "job-004", "workspace-123")  # Valid

        # Run backfill
        stats = backfill_keys(
            redis_url=redis_url_with_fake,
            dry_run=False,
            rps=1000,
            batch=10,
            cursor="0",
            max_keys=None,
            workspace_filter=None,
            progress_key_prefix="ai:backfill:test",
        )

        # 4 jobs scanned, 3 invalid, 1 migrated
        assert stats["scanned"] == 4
        assert stats["skipped_invalid"] == 3
        assert stats["migrated"] == 1
        assert stats["errors"] == 0

        # Only valid job migrated
        assert _job_exists_in_new_schema(redis_client, "job-004", "workspace-123")
        assert not _job_exists_in_new_schema(redis_client, "job-001", "WORKSPACE-UPPERCASE")


class TestTelemetry:
    """Tests for telemetry recording."""

    def test_telemetry_counters_increment_correctly(self, redis_client, redis_url_with_fake):
        """Telemetry metrics are recorded for each operation."""
        # Create jobs
        _create_old_job(redis_client, "job-001", "workspace-123")
        _create_old_job(redis_client, "job-002", "INVALID-WS")  # Invalid

        with patch("scripts.backfill_redis_keys._record_telemetry") as mock_telemetry:
            # Run backfill
            stats = backfill_keys(
                redis_url=redis_url_with_fake,
                dry_run=False,
                rps=1000,
                batch=10,
                cursor="0",
                max_keys=None,
                workspace_filter=None,
                progress_key_prefix="ai:backfill:test",
            )

            # Verify telemetry calls
            assert stats["scanned"] == 2
            assert stats["migrated"] == 1
            assert stats["skipped_invalid"] == 1

            # Check telemetry was called (calls may vary due to skip timing)
            assert mock_telemetry.call_count >= 2  # At least scanned + migrated/skipped


class TestRateLimiting:
    """Tests for rate limiting."""

    def test_rps_cap_is_respected(self, redis_client, redis_url_with_fake):
        """Rate limiting enforces rps cap."""
        # Create 5 jobs
        for i in range(5):
            _create_old_job(redis_client, f"job-{i:03d}", "workspace-123")

        # Run backfill with rps=10 (sleep 0.1s per job)
        start_time = time.time()
        stats = backfill_keys(
            redis_url=redis_url_with_fake,
            dry_run=False,
            rps=10,  # 10 requests per second = 0.1s per job
            batch=10,
            cursor="0",
            max_keys=None,
            workspace_filter=None,
            progress_key_prefix="ai:backfill:test",
        )
        elapsed = time.time() - start_time

        assert stats["scanned"] == 5

        # Should take at least 0.5 seconds (5 jobs * 0.1s each)
        # Allow some variance for test execution overhead
        assert elapsed >= 0.4  # Slightly under to account for test overhead


class TestMaxKeys:
    """Tests for max_keys limit."""

    def test_max_keys_stops_at_limit(self, redis_client, redis_url_with_fake):
        """max_keys parameter limits migration count."""
        # Create 10 jobs
        for i in range(10):
            _create_old_job(redis_client, f"job-{i:03d}", "workspace-123")

        # Run backfill with max_keys=3
        stats = backfill_keys(
            redis_url=redis_url_with_fake,
            dry_run=False,
            rps=1000,
            batch=10,
            cursor="0",
            max_keys=3,
            workspace_filter=None,
            progress_key_prefix="ai:backfill:test",
        )

        # Should stop after 3 jobs
        assert stats["scanned"] == 3
        assert stats["migrated"] == 3
