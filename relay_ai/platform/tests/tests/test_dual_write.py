"""Unit tests for Sprint 60 Phase 1 dual-write functionality.

Tests dual-write key migration from ai:jobs:{job_id} to ai:job:{workspace_id}:{job_id}.

References:
- Sprint 60 Phase 1: Dual-write migration for workspace-scoped keys
- src/queue/simple_queue.py: SimpleQueue with AI_JOBS_NEW_SCHEMA flag
- RECOMMENDED_PATTERNS_S60_MIGRATION.md: Dual-write pattern documentation
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


class TestDualWriteDisabled:
    """Tests for dual-write when AI_JOBS_NEW_SCHEMA is disabled (default)."""

    def test_enqueue_writes_only_old_schema_when_flag_off(self, queue_with_redis):
        """Enqueue writes only to old schema when AI_JOBS_NEW_SCHEMA=off."""
        # Ensure flag is OFF
        with patch("src.queue.simple_queue.ENABLE_NEW_SCHEMA", False):
            success = queue_with_redis.enqueue(
                job_id="job-001",
                action_provider="google",
                action_name="gmail.send",
                params={"to": "test@example.com"},
                workspace_id="workspace-123",
                actor_id="user-456",
            )

            assert success is True

            # Verify old key exists
            old_key = "ai:jobs:job-001"
            assert queue_with_redis._redis.exists(old_key)

            # Verify new key does NOT exist
            new_key = "ai:job:workspace-123:job-001"
            assert not queue_with_redis._redis.exists(new_key)

    def test_get_job_reads_from_old_schema_when_flag_off(self, queue_with_redis):
        """get_job reads from old schema when AI_JOBS_NEW_SCHEMA=off."""
        with patch("src.queue.simple_queue.ENABLE_NEW_SCHEMA", False):
            # Enqueue job (writes to old schema only)
            queue_with_redis.enqueue(
                job_id="job-002",
                action_provider="google",
                action_name="gmail.send",
                params={"to": "test@example.com"},
                workspace_id="workspace-123",
                actor_id="user-456",
            )

            # Retrieve job (should read from old schema)
            # Phase 2.2: workspace_id now required for isolation
            job_data = queue_with_redis.get_job("job-002", workspace_id="workspace-123")
            assert job_data is not None
            assert job_data["job_id"] == "job-002"
            assert job_data["workspace_id"] == "workspace-123"


class TestDualWriteEnabled:
    """Tests for dual-write when AI_JOBS_NEW_SCHEMA is enabled."""

    def test_enqueue_writes_both_schemas_when_flag_on(self, queue_with_redis):
        """Enqueue writes to BOTH old and new schemas when AI_JOBS_NEW_SCHEMA=on."""
        with patch("src.queue.simple_queue.ENABLE_NEW_SCHEMA", True):
            with patch("src.telemetry.prom.record_dual_write_attempt") as mock_telemetry:
                success = queue_with_redis.enqueue(
                    job_id="job-003",
                    action_provider="google",
                    action_name="gmail.send",
                    params={"to": "test@example.com"},
                    workspace_id="workspace-123",
                    actor_id="user-456",
                )

                assert success is True

                # Verify old key exists
                old_key = "ai:jobs:job-003"
                assert queue_with_redis._redis.exists(old_key)

                # Verify new key exists
                new_key = "ai:job:workspace-123:job-003"
                assert queue_with_redis._redis.exists(new_key)

                # Verify both keys have same data
                old_data = queue_with_redis._redis.hgetall(old_key)
                new_data = queue_with_redis._redis.hgetall(new_key)
                assert old_data["job_id"] == new_data["job_id"]
                assert old_data["workspace_id"] == new_data["workspace_id"]

                # Verify telemetry was recorded
                mock_telemetry.assert_called_once_with("workspace-123", "succeeded")

    def test_get_job_reads_new_schema_first_when_flag_on(self, queue_with_redis):
        """get_job tries new schema first, falls back to old when AI_JOBS_NEW_SCHEMA=on."""
        with patch("src.queue.simple_queue.ENABLE_NEW_SCHEMA", True):
            # Manually create job in new schema only (simulates backfill scenario)
            new_key = "ai:job:workspace-123:job-004"
            queue_with_redis._redis.hset(
                new_key,
                mapping={
                    "job_id": "job-004",
                    "status": "pending",
                    "action_provider": "google",
                    "action_name": "gmail.send",
                    "params": '{"to": "test@example.com"}',
                    "workspace_id": "workspace-123",
                    "actor_id": "user-456",
                    "result": "null",
                    "enqueued_at": "2025-01-01T00:00:00Z",
                },
            )

            # Retrieve job with workspace_id (should read from new schema)
            job_data = queue_with_redis.get_job("job-004", workspace_id="workspace-123")
            assert job_data is not None
            assert job_data["job_id"] == "job-004"
            assert job_data["workspace_id"] == "workspace-123"

    def test_update_status_writes_both_schemas_when_flag_on(self, queue_with_redis):
        """update_status writes to both schemas when AI_JOBS_NEW_SCHEMA=on."""
        with patch("src.queue.simple_queue.ENABLE_NEW_SCHEMA", True):
            with patch("src.telemetry.prom.record_dual_write_attempt"):
                # Enqueue job (writes to both schemas)
                queue_with_redis.enqueue(
                    job_id="job-005",
                    action_provider="google",
                    action_name="gmail.send",
                    params={"to": "test@example.com"},
                    workspace_id="workspace-123",
                    actor_id="user-456",
                )

                # Update status
                queue_with_redis.update_status(job_id="job-005", status="completed", workspace_id="workspace-123")

                # Verify old key has updated status
                old_key = "ai:jobs:job-005"
                old_data = queue_with_redis._redis.hgetall(old_key)
                assert old_data["status"] == "completed"

                # Verify new key has updated status
                new_key = "ai:job:workspace-123:job-005"
                new_data = queue_with_redis._redis.hgetall(new_key)
                assert new_data["status"] == "completed"


class TestAtomicityAndValidation:
    """Tests for Sprint 60 Phase 1 blocker fixes (atomicity, idempotency, validation)."""

    def test_enqueue_uses_pipeline_for_atomicity(self, queue_with_redis):
        """Enqueue uses Redis pipeline to ensure atomic dual-write."""
        with patch("src.queue.simple_queue.ENABLE_NEW_SCHEMA", True):
            with patch.object(queue_with_redis._redis, "pipeline") as mock_pipeline:
                # Setup mock pipeline
                mock_pipe = mock_pipeline.return_value
                mock_pipe.execute.return_value = [True, True, 1, True]  # hset, hset, rpush, set
                mock_pipe.hset.return_value = mock_pipe
                mock_pipe.rpush.return_value = mock_pipe
                mock_pipe.set.return_value = mock_pipe

                success = queue_with_redis.enqueue(
                    job_id="job-atomic",
                    action_provider="google",
                    action_name="gmail.send",
                    params={"to": "test@example.com"},
                    workspace_id="workspace-123",
                    actor_id="user-456",
                    client_request_id="req-001",
                )

                assert success is True
                # Verify pipeline was used
                mock_pipeline.assert_called_once()
                mock_pipe.execute.assert_called_once()

    def test_idempotency_set_after_writes_in_pipeline(self, queue_with_redis):
        """Idempotency key is set AFTER writes in same pipeline transaction (CRITICAL-1 fix)."""
        with patch("src.queue.simple_queue.ENABLE_NEW_SCHEMA", True):
            with patch.object(queue_with_redis._redis, "pipeline") as mock_pipeline:
                mock_pipe = mock_pipeline.return_value
                mock_pipe.execute.return_value = [True, True, 1, True]
                mock_pipe.hset.return_value = mock_pipe
                mock_pipe.rpush.return_value = mock_pipe
                mock_pipe.set.return_value = mock_pipe

                queue_with_redis.enqueue(
                    job_id="job-idempotent",
                    action_provider="google",
                    action_name="gmail.send",
                    params={"to": "test@example.com"},
                    workspace_id="workspace-123",
                    actor_id="user-456",
                    client_request_id="req-002",
                )

                # Verify set() was called for idempotency key (within pipeline)
                calls = [str(call) for call in mock_pipe.method_calls]
                set_calls = [c for c in calls if "set(" in c and "nx=True" in c]
                assert len(set_calls) == 1, "Idempotency SETNX should be in pipeline"

    def test_update_status_uses_pipeline_for_dual_update(self, queue_with_redis):
        """update_status uses pipeline for atomic dual-update (HIGH-2 fix)."""
        with patch("src.queue.simple_queue.ENABLE_NEW_SCHEMA", True):
            with patch("src.telemetry.prom.record_dual_write_attempt"):
                # Enqueue job first
                queue_with_redis.enqueue(
                    job_id="job-update",
                    action_provider="google",
                    action_name="gmail.send",
                    params={"to": "test@example.com"},
                    workspace_id="workspace-123",
                    actor_id="user-456",
                )

                with patch.object(queue_with_redis._redis, "pipeline") as mock_pipeline:
                    mock_pipe = mock_pipeline.return_value
                    mock_pipe.execute.return_value = [True, True, True]  # hset, exists, hset
                    mock_pipe.hset.return_value = mock_pipe
                    mock_pipe.exists.return_value = mock_pipe

                    queue_with_redis.update_status(
                        job_id="job-update",
                        status="completed",
                        workspace_id="workspace-123",
                    )

                    # Verify pipeline was used
                    mock_pipeline.assert_called_once()
                    mock_pipe.execute.assert_called_once()

    def test_workspace_id_validation_blocks_injection(self, queue_with_redis):
        """Invalid workspace_id raises ValueError to prevent key injection (HIGH-5 fix)."""
        with patch("src.queue.simple_queue.ENABLE_NEW_SCHEMA", True):
            # Test various injection attempts
            invalid_ids = [
                "workspace:123",  # Colon (key separator)
                "workspace*",  # Asterisk (glob pattern)
                "WORKSPACE",  # Uppercase
                "",  # Empty
                "a" * 33,  # Too long (>32 chars)
                "-workspace",  # Starts with hyphen
            ]

            for invalid_id in invalid_ids:
                with pytest.raises(ValueError, match="Invalid workspace_id"):
                    queue_with_redis.enqueue(
                        job_id="job-test",
                        action_provider="google",
                        action_name="gmail.send",
                        params={"to": "test@example.com"},
                        workspace_id=invalid_id,
                        actor_id="user-456",
                    )

    def test_valid_workspace_ids_accepted(self, queue_with_redis):
        """Valid workspace_ids are accepted (HIGH-5 validation boundary test)."""
        with patch("src.queue.simple_queue.ENABLE_NEW_SCHEMA", False):
            valid_ids = [
                "workspace123",
                "workspace-123",
                "workspace_123",
                "w",  # Min length (1 char)
                "a" * 32,  # Max length (32 chars)
            ]

            for idx, valid_id in enumerate(valid_ids):
                success = queue_with_redis.enqueue(
                    job_id=f"job-{idx}",
                    action_provider="google",
                    action_name="gmail.send",
                    params={"to": "test@example.com"},
                    workspace_id=valid_id,
                    actor_id="user-456",
                )
                assert success is True

    def test_no_exc_info_leak_in_error_logs(self, queue_with_redis):
        """Error logging does not include exc_info=True (HIGH-7 fix)."""
        with patch("src.queue.simple_queue.ENABLE_NEW_SCHEMA", True):
            with patch.object(queue_with_redis._redis, "pipeline") as mock_pipeline:
                # Force pipeline to fail
                mock_pipeline.return_value.execute.side_effect = Exception("Redis connection failed")

                with patch("src.queue.simple_queue._LOG") as mock_log:
                    with pytest.raises(Exception, match="Redis connection failed"):
                        queue_with_redis.enqueue(
                            job_id="job-fail",
                            action_provider="google",
                            action_name="gmail.send",
                            params={"to": "test@example.com"},
                            workspace_id="workspace-123",
                            actor_id="user-456",
                        )

                    # Verify error() was called WITHOUT exc_info=True
                    error_calls = list(mock_log.error.call_args_list)
                    for call in error_calls:
                        # Check that exc_info is not in kwargs OR is False
                        assert call.kwargs.get("exc_info") is not True
