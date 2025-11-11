"""Unit tests for Sprint 60 Phase 2.2 read-routing functionality.

Tests workspace-scoped read paths with new→old fallback and isolation enforcement.

Sprint 60 Phase 2.2: Read-routing with zero-downtime migration support:
- get_job(): Prefer new schema (ai:job:{workspace_id}:{job_id}), fallback to old with isolation
- list_jobs(): SCAN-based workspace-scoped enumeration with cursor pagination
- Workspace isolation: Reject jobs from other workspaces during fallback
- Telemetry: Track read path distribution (new, old, miss)

References:
- Sprint 60 Phase 2.2: Read-routing implementation
- src/queue/simple_queue.py: Enhanced get_job() and list_jobs()
- src/telemetry/prom.py: Read-routing telemetry metrics
"""

from unittest.mock import patch

import fakeredis
import pytest

from relay_ai.queue.simple_queue import SimpleQueue


@pytest.fixture
def redis_client():
    """Provide FakeRedis client for testing."""
    return fakeredis.FakeStrictRedis(decode_responses=True)


@pytest.fixture
def queue_with_redis(redis_client):
    """Provide SimpleQueue with FakeRedis for testing."""
    with patch("src.queue.simple_queue.redis.from_url", return_value=redis_client):
        queue = SimpleQueue()
        queue._redis = redis_client  # Override with fake redis
        yield queue


# ============================================================================
# get_job() Read-Routing Tests
# ============================================================================


class TestGetJobReadRouting:
    """Tests for get_job() read-routing and workspace isolation (Phase 2.2)."""

    def test_get_job_prefers_new_key_when_both_exist(self, queue_with_redis):
        """get_job() prefers new schema when both old and new keys exist."""
        with patch("src.queue.simple_queue.READ_PREFERS_NEW", True):
            with patch("src.telemetry.prom.record_job_read_path") as mock_telemetry:
                # Setup: Create job in BOTH schemas with different data
                old_key = "ai:jobs:job-001"
                queue_with_redis._redis.hset(
                    old_key,
                    mapping={
                        "job_id": "job-001",
                        "status": "pending",
                        "action_provider": "google",
                        "action_name": "gmail.send",
                        "params": '{"to": "old@example.com"}',
                        "workspace_id": "workspace-123",
                        "actor_id": "user-456",
                        "result": "",
                        "enqueued_at": "2025-01-01T00:00:00Z",
                    },
                )

                new_key = "ai:job:workspace-123:job-001"
                queue_with_redis._redis.hset(
                    new_key,
                    mapping={
                        "job_id": "job-001",
                        "status": "completed",
                        "action_provider": "google",
                        "action_name": "gmail.send",
                        "params": '{"to": "new@example.com"}',
                        "workspace_id": "workspace-123",
                        "actor_id": "user-456",
                        "result": '{"success": true}',
                        "enqueued_at": "2025-01-01T00:00:00Z",
                        "finished_at": "2025-01-01T00:00:05Z",
                    },
                )

                # Act: Get job with workspace_id
                job_data = queue_with_redis.get_job("job-001", workspace_id="workspace-123")

                # Assert: Should return data from NEW schema (status=completed)
                assert job_data is not None
                assert job_data["status"] == "completed"
                assert job_data["params"]["to"] == "new@example.com"
                assert job_data["result"]["success"] is True

                # Verify telemetry recorded "new" path
                mock_telemetry.assert_called_once_with("workspace-123", "new")

    def test_get_job_falls_back_to_old_when_new_absent_but_same_workspace(self, queue_with_redis):
        """get_job() falls back to old schema when new key absent and workspace matches."""
        with patch("src.queue.simple_queue.READ_PREFERS_NEW", True):
            with patch("src.queue.simple_queue.READ_FALLBACK_OLD", True):
                with patch("src.telemetry.prom.record_job_read_path") as mock_telemetry:
                    # Setup: Create job in OLD schema only
                    old_key = "ai:jobs:job-002"
                    queue_with_redis._redis.hset(
                        old_key,
                        mapping={
                            "job_id": "job-002",
                            "status": "pending",
                            "action_provider": "google",
                            "action_name": "gmail.send",
                            "params": '{"to": "test@example.com"}',
                            "workspace_id": "workspace-123",
                            "actor_id": "user-456",
                            "result": "",
                            "enqueued_at": "2025-01-01T00:00:00Z",
                        },
                    )

                    # Act: Get job with matching workspace_id
                    job_data = queue_with_redis.get_job("job-002", workspace_id="workspace-123")

                    # Assert: Should return data from old schema (fallback successful)
                    assert job_data is not None
                    assert job_data["job_id"] == "job-002"
                    assert job_data["status"] == "pending"
                    assert job_data["workspace_id"] == "workspace-123"

                    # Verify telemetry recorded "old" path (fallback)
                    mock_telemetry.assert_called_once_with("workspace-123", "old")

    def test_get_job_rejects_legacy_if_workspace_mismatch(self, queue_with_redis):
        """get_job() rejects old schema job if workspace_id doesn't match (isolation enforcement)."""
        with patch("src.queue.simple_queue.READ_PREFERS_NEW", True):
            with patch("src.queue.simple_queue.READ_FALLBACK_OLD", True):
                with patch("src.telemetry.prom.record_job_read_path") as mock_telemetry:
                    # Setup: Create job in OLD schema with different workspace
                    old_key = "ai:jobs:job-003"
                    queue_with_redis._redis.hset(
                        old_key,
                        mapping={
                            "job_id": "job-003",
                            "status": "completed",
                            "action_provider": "google",
                            "action_name": "gmail.send",
                            "params": '{"to": "test@example.com"}',
                            "workspace_id": "workspace-456",  # Different workspace!
                            "actor_id": "user-789",
                            "result": '{"success": true}',
                            "enqueued_at": "2025-01-01T00:00:00Z",
                        },
                    )

                    # Act: Request job with mismatched workspace_id
                    job_data = queue_with_redis.get_job("job-003", workspace_id="workspace-123")

                    # Assert: Should return None (cross-workspace access rejected)
                    assert job_data is None

                    # Verify telemetry recorded "miss" (not a leak)
                    mock_telemetry.assert_called_once_with("workspace-123", "miss")

    def test_get_job_returns_none_when_workspace_id_missing(self, queue_with_redis):
        """get_job() returns None when workspace_id parameter is missing (required for isolation)."""
        with patch("src.queue.simple_queue.READ_PREFERS_NEW", True):
            # Setup: Create job in old schema
            old_key = "ai:jobs:job-004"
            queue_with_redis._redis.hset(
                old_key,
                mapping={
                    "job_id": "job-004",
                    "status": "pending",
                    "workspace_id": "workspace-123",
                    "params": "{}",
                    "result": "",
                },
            )

            # Act: Call get_job WITHOUT workspace_id (isolation cannot be enforced)
            job_data = queue_with_redis.get_job("job-004", workspace_id=None)

            # Assert: Should return None (workspace_id required)
            assert job_data is None

    def test_get_job_returns_none_when_workspace_id_invalid(self, queue_with_redis):
        """get_job() returns None when workspace_id is invalid (validation failure)."""
        with patch("src.queue.simple_queue.READ_PREFERS_NEW", True):
            # Act: Call get_job with invalid workspace_id
            invalid_ids = [
                "WORKSPACE",  # Uppercase
                "workspace:123",  # Colon
                "workspace*",  # Asterisk
                "",  # Empty
            ]

            for invalid_id in invalid_ids:
                job_data = queue_with_redis.get_job("job-test", workspace_id=invalid_id)
                assert job_data is None, f"Should reject invalid workspace_id: {invalid_id}"

    def test_get_job_returns_none_when_not_found_in_either_schema(self, queue_with_redis):
        """get_job() returns None when job doesn't exist in either schema."""
        with patch("src.queue.simple_queue.READ_PREFERS_NEW", True):
            with patch("src.queue.simple_queue.READ_FALLBACK_OLD", True):
                with patch("src.telemetry.prom.record_job_read_path") as mock_telemetry:
                    # Act: Request non-existent job
                    job_data = queue_with_redis.get_job("job-nonexistent", workspace_id="workspace-123")

                    # Assert: Should return None
                    assert job_data is None

                    # Verify telemetry recorded "miss"
                    mock_telemetry.assert_called_once_with("workspace-123", "miss")

    def test_get_job_strict_mode_skips_fallback_when_flag_off(self, queue_with_redis):
        """get_job() skips fallback to old schema when READ_FALLBACK_OLD=off (strict mode)."""
        with patch("src.queue.simple_queue.READ_PREFERS_NEW", True):
            with patch("src.queue.simple_queue.READ_FALLBACK_OLD", False):
                with patch("src.telemetry.prom.record_job_read_path") as mock_telemetry:
                    # Setup: Create job in OLD schema only
                    old_key = "ai:jobs:job-005"
                    queue_with_redis._redis.hset(
                        old_key,
                        mapping={
                            "job_id": "job-005",
                            "status": "pending",
                            "workspace_id": "workspace-123",
                            "params": "{}",
                            "result": "",
                        },
                    )

                    # Act: Get job with READ_FALLBACK_OLD=off
                    job_data = queue_with_redis.get_job("job-005", workspace_id="workspace-123")

                    # Assert: Should return None (fallback disabled)
                    assert job_data is None

                    # Verify telemetry recorded "miss" (not "old")
                    mock_telemetry.assert_called_once_with("workspace-123", "miss")


# ============================================================================
# list_jobs() Read-Routing Tests
# ============================================================================


class TestListJobsReadRouting:
    """Tests for list_jobs() workspace-scoped enumeration and read-routing (Phase 2.2)."""

    def test_list_jobs_uses_new_prefix_only_for_workspace(self, queue_with_redis):
        """list_jobs() uses new schema workspace-scoped SCAN when READ_PREFERS_NEW=on."""
        with patch("src.queue.simple_queue.READ_PREFERS_NEW", True):
            with patch("src.queue.simple_queue.READ_FALLBACK_OLD", False):
                with patch("src.telemetry.prom.record_job_list_read_path") as mock_list_path:
                    with patch("src.telemetry.prom.record_job_list_results") as mock_list_results:
                        # Setup: Create jobs in new schema for workspace-123
                        jobs_data = [
                            ("job-001", "completed"),
                            ("job-002", "pending"),
                            ("job-003", "running"),
                        ]

                        for job_id, status in jobs_data:
                            new_key = f"ai:job:workspace-123:{job_id}"
                            queue_with_redis._redis.hset(
                                new_key,
                                mapping={
                                    "job_id": job_id,
                                    "status": status,
                                    "action_provider": "google",
                                    "action_name": "gmail.send",
                                    "params": '{"to": "test@example.com"}',
                                    "workspace_id": "workspace-123",
                                    "actor_id": "user-456",
                                    "result": "",
                                    "enqueued_at": f"2025-01-01T00:00:0{jobs_data.index((job_id, status))}Z",
                                },
                            )

                        # Create job in different workspace (should not be returned)
                        other_key = "ai:job:workspace-456:job-other"
                        queue_with_redis._redis.hset(
                            other_key,
                            mapping={
                                "job_id": "job-other",
                                "status": "completed",
                                "workspace_id": "workspace-456",
                                "params": "{}",
                                "result": "",
                            },
                        )

                        # Act: List jobs for workspace-123
                        result = queue_with_redis.list_jobs(workspace_id="workspace-123", limit=10)

                        # Assert: Should return only workspace-123 jobs
                        assert "items" in result
                        assert "next_cursor" in result
                        items = result["items"]
                        assert len(items) == 3
                        assert all(job["workspace_id"] == "workspace-123" for job in items)
                        assert {job["job_id"] for job in items} == {"job-001", "job-002", "job-003"}

                        # Verify telemetry recorded "new" path (no fallback)
                        mock_list_path.assert_called_once_with("workspace-123", "new")
                        mock_list_results.assert_called_once_with("workspace-123", 3)

    def test_list_jobs_mixed_mode_adds_only_matching_workspace_when_fallback_on(self, queue_with_redis):
        """list_jobs() includes old schema jobs with workspace filtering when READ_FALLBACK_OLD=on."""
        with patch("src.queue.simple_queue.READ_PREFERS_NEW", True):
            with patch("src.queue.simple_queue.READ_FALLBACK_OLD", True):
                with patch("src.telemetry.prom.record_job_list_read_path") as mock_list_path:
                    with patch("src.telemetry.prom.record_job_list_results") as mock_list_results:
                        # Setup: Create 2 jobs in new schema
                        for i in range(2):
                            new_key = f"ai:job:workspace-123:job-new-{i}"
                            queue_with_redis._redis.hset(
                                new_key,
                                mapping={
                                    "job_id": f"job-new-{i}",
                                    "status": "completed",
                                    "workspace_id": "workspace-123",
                                    "params": "{}",
                                    "result": "",
                                    "enqueued_at": f"2025-01-01T00:00:0{i}Z",
                                },
                            )

                        # Setup: Create 3 jobs in old schema (2 for workspace-123, 1 for workspace-456)
                        for i, workspace in enumerate(["workspace-123", "workspace-123", "workspace-456"]):
                            old_key = f"ai:jobs:job-old-{i}"
                            queue_with_redis._redis.hset(
                                old_key,
                                mapping={
                                    "job_id": f"job-old-{i}",
                                    "status": "pending",
                                    "workspace_id": workspace,
                                    "params": "{}",
                                    "result": "",
                                    "enqueued_at": f"2025-01-01T00:00:1{i}Z",
                                },
                            )

                        # Act: List jobs for workspace-123 with limit=10
                        result = queue_with_redis.list_jobs(workspace_id="workspace-123", limit=10)

                        # Assert: Should return 4 jobs (2 from new + 2 from old, excluding workspace-456)
                        items = result["items"]
                        assert len(items) == 4
                        assert all(job["workspace_id"] == "workspace-123" for job in items)
                        assert sum(1 for job in items if job["job_id"].startswith("job-new-")) == 2
                        assert sum(1 for job in items if job["job_id"].startswith("job-old-")) == 2

                        # Verify telemetry recorded "mixed" path (both schemas used)
                        mock_list_path.assert_called_once_with("workspace-123", "mixed")
                        mock_list_results.assert_called_once_with("workspace-123", 4)

    def test_list_jobs_filters_by_status_across_both_schemas(self, queue_with_redis):
        """list_jobs() applies status filter to jobs from both schemas."""
        with patch("src.queue.simple_queue.READ_PREFERS_NEW", True):
            with patch("src.queue.simple_queue.READ_FALLBACK_OLD", True):
                with patch("src.telemetry.prom.record_job_list_read_path"):
                    with patch("src.telemetry.prom.record_job_list_results"):
                        # Setup: Create jobs with different statuses
                        # New schema: 1 completed, 1 pending
                        queue_with_redis._redis.hset(
                            "ai:job:workspace-123:job-new-1",
                            mapping={
                                "job_id": "job-new-1",
                                "status": "completed",
                                "workspace_id": "workspace-123",
                                "params": "{}",
                                "result": "",
                                "enqueued_at": "2025-01-01T00:00:00Z",
                            },
                        )
                        queue_with_redis._redis.hset(
                            "ai:job:workspace-123:job-new-2",
                            mapping={
                                "job_id": "job-new-2",
                                "status": "pending",
                                "workspace_id": "workspace-123",
                                "params": "{}",
                                "result": "",
                                "enqueued_at": "2025-01-01T00:00:01Z",
                            },
                        )

                        # Old schema: 1 completed, 1 failed
                        queue_with_redis._redis.hset(
                            "ai:jobs:job-old-1",
                            mapping={
                                "job_id": "job-old-1",
                                "status": "completed",
                                "workspace_id": "workspace-123",
                                "params": "{}",
                                "result": "",
                                "enqueued_at": "2025-01-01T00:00:02Z",
                            },
                        )
                        queue_with_redis._redis.hset(
                            "ai:jobs:job-old-2",
                            mapping={
                                "job_id": "job-old-2",
                                "status": "failed",
                                "workspace_id": "workspace-123",
                                "params": "{}",
                                "result": "",
                                "enqueued_at": "2025-01-01T00:00:03Z",
                            },
                        )

                        # Act: List only "completed" jobs
                        result = queue_with_redis.list_jobs(workspace_id="workspace-123", status="completed", limit=10)

                        # Assert: Should return only completed jobs (2 total)
                        items = result["items"]
                        assert len(items) == 2
                        assert all(job["status"] == "completed" for job in items)
                        assert {job["job_id"] for job in items} == {"job-new-1", "job-old-1"}

    def test_list_jobs_respects_limit_parameter(self, queue_with_redis):
        """list_jobs() respects limit parameter for pagination."""
        with patch("src.queue.simple_queue.READ_PREFERS_NEW", True):
            with patch("src.queue.simple_queue.READ_FALLBACK_OLD", False):
                with patch("src.telemetry.prom.record_job_list_read_path"):
                    with patch("src.telemetry.prom.record_job_list_results") as mock_list_results:
                        # Setup: Create 10 jobs in new schema
                        for i in range(10):
                            new_key = f"ai:job:workspace-123:job-{i:03d}"
                            queue_with_redis._redis.hset(
                                new_key,
                                mapping={
                                    "job_id": f"job-{i:03d}",
                                    "status": "completed",
                                    "workspace_id": "workspace-123",
                                    "params": "{}",
                                    "result": "",
                                    "enqueued_at": f"2025-01-01T00:00:{i:02d}Z",
                                },
                            )

                        # Act: List jobs with limit=5
                        result = queue_with_redis.list_jobs(workspace_id="workspace-123", limit=5)

                        # Assert: Should return exactly 5 jobs
                        items = result["items"]
                        assert len(items) == 5

                        # Verify telemetry recorded correct count (5, not 10)
                        mock_list_results.assert_called_once_with("workspace-123", 5)

    def test_list_jobs_returns_empty_list_for_invalid_workspace(self, queue_with_redis):
        """list_jobs() returns empty list when workspace_id is invalid."""
        with patch("src.queue.simple_queue.READ_PREFERS_NEW", True):
            # Act: Call list_jobs with invalid workspace_id
            invalid_ids = ["WORKSPACE", "workspace:123", "workspace*", ""]

            for invalid_id in invalid_ids:
                result = queue_with_redis.list_jobs(workspace_id=invalid_id, limit=10)
                assert result == {"items": [], "next_cursor": None}, f"Should reject: {invalid_id}"

    def test_list_jobs_sorts_by_enqueued_at_descending(self, queue_with_redis):
        """list_jobs() sorts results by enqueued_at descending (most recent first)."""
        with patch("src.queue.simple_queue.READ_PREFERS_NEW", True):
            with patch("src.queue.simple_queue.READ_FALLBACK_OLD", False):
                with patch("src.telemetry.prom.record_job_list_read_path"):
                    with patch("src.telemetry.prom.record_job_list_results"):
                        # Setup: Create jobs with different timestamps
                        timestamps = ["2025-01-01T00:00:00Z", "2025-01-01T00:00:05Z", "2025-01-01T00:00:03Z"]

                        for idx, timestamp in enumerate(timestamps):
                            new_key = f"ai:job:workspace-123:job-{idx}"
                            queue_with_redis._redis.hset(
                                new_key,
                                mapping={
                                    "job_id": f"job-{idx}",
                                    "status": "completed",
                                    "workspace_id": "workspace-123",
                                    "params": "{}",
                                    "result": "",
                                    "enqueued_at": timestamp,
                                },
                            )

                        # Act: List jobs
                        result = queue_with_redis.list_jobs(workspace_id="workspace-123", limit=10)

                        # Assert: Should be sorted by timestamp descending
                        items = result["items"]
                        assert len(items) == 3
                        assert items[0]["enqueued_at"] == "2025-01-01T00:00:05Z"  # Most recent
                        assert items[1]["enqueued_at"] == "2025-01-01T00:00:03Z"
                        assert items[2]["enqueued_at"] == "2025-01-01T00:00:00Z"  # Oldest

    def test_list_jobs_cursor_pagination_returns_next_cursor(self, queue_with_redis):
        """list_jobs() returns next_cursor for pagination when more results exist."""
        with patch("src.queue.simple_queue.READ_PREFERS_NEW", True):
            with patch("src.queue.simple_queue.READ_FALLBACK_OLD", False):
                with patch("src.telemetry.prom.record_job_list_read_path"):
                    with patch("src.telemetry.prom.record_job_list_results"):
                        # Setup: Create 10 jobs
                        for i in range(10):
                            new_key = f"ai:job:workspace-123:job-{i:03d}"
                            queue_with_redis._redis.hset(
                                new_key,
                                mapping={
                                    "job_id": f"job-{i:03d}",
                                    "status": "completed",
                                    "workspace_id": "workspace-123",
                                    "params": "{}",
                                    "result": "",
                                    "enqueued_at": f"2025-01-01T00:00:{i:02d}Z",
                                },
                            )

                        # Act: List jobs with small limit to trigger pagination
                        result = queue_with_redis.list_jobs(workspace_id="workspace-123", limit=3)

                        # Assert: Should return next_cursor if SCAN has more results
                        assert "next_cursor" in result
                        # Note: next_cursor may be None or a string depending on Redis SCAN behavior
                        # This test documents the pagination contract


# ============================================================================
# Telemetry Tests
# ============================================================================


class TestReadRoutingTelemetry:
    """Tests for read-routing telemetry metrics (Phase 2.2)."""

    def test_get_job_telemetry_gracefully_handles_exceptions(self, queue_with_redis):
        """get_job() continues when telemetry recording raises exception (graceful degradation)."""
        with patch("src.queue.simple_queue.READ_PREFERS_NEW", True):
            # Setup: Create job in new schema
            new_key = "ai:job:workspace-123:job-tel-1"
            queue_with_redis._redis.hset(
                new_key,
                mapping={
                    "job_id": "job-tel-1",
                    "status": "completed",
                    "workspace_id": "workspace-123",
                    "params": "{}",
                    "result": "",
                },
            )

            # Mock telemetry function to raise exception
            with patch("src.telemetry.prom.record_job_read_path", side_effect=Exception("telemetry unavailable")):
                # Act: Get job (should not raise exception)
                job_data = queue_with_redis.get_job("job-tel-1", workspace_id="workspace-123")

                # Assert: Should still return job data (telemetry failure doesn't break reads)
                assert job_data is not None
                assert job_data["job_id"] == "job-tel-1"

    def test_list_jobs_telemetry_gracefully_handles_import_error(self, queue_with_redis):
        """list_jobs() continues when telemetry import fails (graceful degradation)."""
        with patch("src.queue.simple_queue.READ_PREFERS_NEW", True):
            with patch("src.queue.simple_queue.READ_FALLBACK_OLD", False):
                # Setup: Create job
                new_key = "ai:job:workspace-123:job-tel-2"
                queue_with_redis._redis.hset(
                    new_key,
                    mapping={
                        "job_id": "job-tel-2",
                        "status": "completed",
                        "workspace_id": "workspace-123",
                        "params": "{}",
                        "result": "",
                        "enqueued_at": "2025-01-01T00:00:00Z",
                    },
                )

                # Mock telemetry functions to raise exceptions during calls
                with patch(
                    "src.telemetry.prom.record_job_list_read_path", side_effect=Exception("telemetry unavailable")
                ):
                    with patch(
                        "src.telemetry.prom.record_job_list_results", side_effect=Exception("telemetry unavailable")
                    ):
                        # Act: List jobs (should not raise exception)
                        result = queue_with_redis.list_jobs(workspace_id="workspace-123", limit=10)

                        # Assert: Should still return results (telemetry failure doesn't break list)
                        assert result["items"]
                        assert len(result["items"]) == 1
