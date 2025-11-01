"""Unit tests for AI Orchestrator queue with idempotency.

Sprint 55 Week 3: Test job queuing, dequeuing, and idempotency.
"""

import json
from unittest.mock import patch

from src.queue.simple_queue import SimpleQueue


class TestSimpleQueueEnqueue:
    """Tests for queue enqueue operation."""

    def test_enqueue_creates_job(self, mock_redis):
        """Enqueuing creates job data and adds to queue."""
        with patch("redis.from_url", return_value=mock_redis):
            os_env_patch = {"REDIS_URL": "redis://localhost"}
            with patch.dict("os.environ", os_env_patch):
                queue = SimpleQueue()

        result = queue.enqueue(
            job_id="job-001",
            action_provider="google",
            action_name="gmail.send",
            params={"to": "test@example.com"},
            workspace_id="ws-001",
            actor_id="user-001",
        )

        assert result is True
        mock_redis.hset.assert_called_once()
        mock_redis.rpush.assert_called_once()

    def test_idempotency_blocks_duplicate(self, mock_redis):
        """Idempotency key blocks duplicate enqueue."""
        # First request: SETNX returns True (key set successfully)
        mock_redis.set.return_value = True

        with patch("redis.from_url", return_value=mock_redis):
            os_env_patch = {"REDIS_URL": "redis://localhost"}
            with patch.dict("os.environ", os_env_patch):
                queue = SimpleQueue()

        result1 = queue.enqueue(
            job_id="job-001",
            action_provider="google",
            action_name="gmail.send",
            params={"to": "test@example.com"},
            workspace_id="ws-001",
            actor_id="user-001",
            client_request_id="req-123",
        )

        assert result1 is True

        # Second request: SETNX returns False (key already exists)
        mock_redis.set.return_value = False

        result2 = queue.enqueue(
            job_id="job-002",
            action_provider="google",
            action_name="gmail.send",
            params={"to": "test@example.com"},
            workspace_id="ws-001",
            actor_id="user-001",
            client_request_id="req-123",  # Same idempotency key
        )

        assert result2 is False  # Duplicate blocked

    def test_no_idempotency_key_always_enqueues(self, mock_redis):
        """Without idempotency key, all requests enqueue."""
        mock_redis.set.return_value = True

        with patch("redis.from_url", return_value=mock_redis):
            os_env_patch = {"REDIS_URL": "redis://localhost"}
            with patch.dict("os.environ", os_env_patch):
                queue = SimpleQueue()

        # Both requests without client_request_id should succeed
        result1 = queue.enqueue(
            job_id="job-001",
            action_provider="google",
            action_name="gmail.send",
            params={"to": "test@example.com"},
            workspace_id="ws-001",
            actor_id="user-001",
        )

        result2 = queue.enqueue(
            job_id="job-002",
            action_provider="google",
            action_name="gmail.send",
            params={"to": "test@example.com"},
            workspace_id="ws-001",
            actor_id="user-001",
        )

        assert result1 is True
        assert result2 is True


class TestSimpleQueueGet:
    """Tests for getting job data."""

    def test_get_job_returns_data(self, mock_redis):
        """Getting job returns deserialized data."""
        mock_redis.hgetall.return_value = {
            "job_id": "job-001",
            "status": "pending",
            "action_provider": "google",
            "action_name": "gmail.send",
            "params": json.dumps({"to": "test@example.com"}),
            "result": None,
            "enqueued_at": "2025-01-10T12:00:00",
        }

        with patch("redis.from_url", return_value=mock_redis):
            os_env_patch = {"REDIS_URL": "redis://localhost"}
            with patch.dict("os.environ", os_env_patch):
                queue = SimpleQueue()

        job = queue.get_job("job-001")

        assert job["job_id"] == "job-001"
        assert job["status"] == "pending"
        assert job["params"]["to"] == "test@example.com"  # Deserialized

    def test_get_nonexistent_job_returns_none(self, mock_redis):
        """Getting nonexistent job returns None."""
        mock_redis.hgetall.return_value = {}

        with patch("redis.from_url", return_value=mock_redis):
            os_env_patch = {"REDIS_URL": "redis://localhost"}
            with patch.dict("os.environ", os_env_patch):
                queue = SimpleQueue()

        job = queue.get_job("nonexistent")

        assert job is None


class TestSimpleQueueStatus:
    """Tests for status updates."""

    def test_update_status_to_running(self, mock_redis):
        """Updating to running sets started_at."""
        with patch("redis.from_url", return_value=mock_redis):
            os_env_patch = {"REDIS_URL": "redis://localhost"}
            with patch.dict("os.environ", os_env_patch):
                queue = SimpleQueue()

        queue.update_status("job-001", "running")

        # Verify hset was called with status and started_at
        call_args = mock_redis.hset.call_args
        updates = call_args[1]["mapping"]

        assert updates["status"] == "running"
        assert "started_at" in updates

    def test_update_status_to_completed(self, mock_redis):
        """Updating to completed sets finished_at."""
        with patch("redis.from_url", return_value=mock_redis):
            os_env_patch = {"REDIS_URL": "redis://localhost"}
            with patch.dict("os.environ", os_env_patch):
                queue = SimpleQueue()

        result_data = {"status": "sent", "message_id": "msg-123"}
        queue.update_status("job-001", "completed", result=result_data)

        call_args = mock_redis.hset.call_args
        updates = call_args[1]["mapping"]

        assert updates["status"] == "completed"
        assert "finished_at" in updates
        assert json.loads(updates["result"]) == result_data


class TestQueueDepth:
    """Tests for queue depth monitoring."""

    def test_get_queue_depth(self, mock_redis):
        """Queue depth returns length of pending list."""
        mock_redis.llen.return_value = 42

        with patch("redis.from_url", return_value=mock_redis):
            os_env_patch = {"REDIS_URL": "redis://localhost"}
            with patch.dict("os.environ", os_env_patch):
                queue = SimpleQueue()

        depth = queue.get_queue_depth()

        assert depth == 42
        mock_redis.llen.assert_called_once()
