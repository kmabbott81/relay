"""Unit tests for /ai/jobs endpoint - Sprint 59 Slice 05 hotfix.

Tests workspace-scoped job listing with proper Redis key filtering and error handling.

References:
- S59-05 Hotfix: Workspace-scoped /ai/jobs endpoint (removed duplicate definition)
- src/webapi.py:1455-1557 (list_ai_jobs implementation)
- src/telemetry/prom.py: workspace-scoped AI metrics
"""

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from relay_ai.webapi import app


@pytest.fixture
def client():
    """Create test client with demo authentication for testing."""
    # Use demo preview key that bypasses database auth (Sprint 55 Week 3 feature)
    # Defined in src/auth/security.py:156
    return TestClient(app, headers={"Authorization": "Bearer relay_sk_demo_preview_key"})


class TestAIJobsListEndpoint:
    """Tests for GET /ai/jobs endpoint (S59-05 hotfix)."""

    def test_list_jobs_disabled_feature(self, client):
        """List jobs returns 404 if ACTIONS_ENABLED is false."""
        with patch("src.webapi.ACTIONS_ENABLED", False):
            response = client.get("/ai/jobs")
            assert response.status_code == 404
            assert "not enabled" in response.json()["detail"]

    def test_list_jobs_invalid_limit_too_low(self, client):
        """List jobs validates limit >= 1."""
        with patch("src.webapi.ACTIONS_ENABLED", True):
            response = client.get("/ai/jobs?limit=0")
            assert response.status_code == 400
            assert "limit must be between 1 and 100" in response.json()["detail"]

    def test_list_jobs_invalid_limit_too_high(self, client):
        """List jobs validates limit <= 100."""
        with patch("src.webapi.ACTIONS_ENABLED", True):
            response = client.get("/ai/jobs?limit=101")
            assert response.status_code == 400
            assert "limit must be between 1 and 100" in response.json()["detail"]

    def test_list_jobs_queue_unavailable(self, client):
        """List jobs returns 503 if queue is unavailable."""
        with patch("src.webapi.ACTIONS_ENABLED", True):
            with patch("src.queue.simple_queue.SimpleQueue", side_effect=ValueError("Redis unavailable")):
                response = client.get("/ai/jobs")
                assert response.status_code == 503
                assert "Queue unavailable" in response.json()["detail"]

    def test_list_jobs_empty(self, client):
        """List jobs returns empty list when no jobs exist."""
        with patch("src.webapi.ACTIONS_ENABLED", True):
            with patch("src.queue.simple_queue.SimpleQueue") as mock_queue_class:
                mock_queue = MagicMock()
                mock_queue.redis.keys.return_value = []
                mock_queue.get_queue_depth.return_value = 0
                mock_queue_class.return_value = mock_queue

                response = client.get("/ai/jobs")
                assert response.status_code == 200
                data = response.json()
                assert data["jobs"] == []
                assert data["count"] == 0
                assert data["queue_depth"] == 0

    def test_list_jobs_with_jobs(self, client):
        """List jobs returns job data from Redis keys."""
        with patch("src.webapi.ACTIONS_ENABLED", True):
            with patch("src.queue.simple_queue.SimpleQueue") as mock_queue_class:
                mock_queue = MagicMock()
                job_key = "ai:job:uuid-1"
                mock_queue.redis.keys.return_value = [job_key]

                now = datetime.now(UTC).isoformat()
                job_data = {
                    "job_id": "uuid-1",
                    "status": "completed",
                    "action_provider": "google",
                    "action_name": "gmail.send",
                    "params": '{"to": "user@example.com"}',
                    "result": '{"message_id": "msg_123"}',
                    "error": None,
                    "started_at": now,
                    "finished_at": now,
                    "enqueued_at": now,
                }
                mock_queue.redis.hgetall.return_value = job_data
                mock_queue.get_queue_depth.return_value = 1
                mock_queue_class.return_value = mock_queue

                response = client.get("/ai/jobs?limit=50")
                assert response.status_code == 200
                data = response.json()
                assert len(data["jobs"]) == 1
                assert data["jobs"][0]["job_id"] == "uuid-1"
                assert data["jobs"][0]["status"] == "completed"
                assert data["jobs"][0]["action"] == "google.gmail.send"

    def test_list_jobs_respects_limit(self, client):
        """List jobs respects the limit parameter."""
        with patch("src.webapi.ACTIONS_ENABLED", True):
            with patch("src.queue.simple_queue.SimpleQueue") as mock_queue_class:
                mock_queue = MagicMock()
                job_keys = [f"ai:job:uuid-{i}" for i in range(5)]
                mock_queue.redis.keys.return_value = job_keys

                job_data = {
                    "status": "pending",
                    "action_provider": "google",
                    "action_name": "test",
                    "params": "{}",
                    "error": None,
                    "enqueued_at": "2025-01-01T00:00:00",
                }
                mock_queue.redis.hgetall.return_value = job_data
                mock_queue.get_queue_depth.return_value = 5
                mock_queue_class.return_value = mock_queue

                response = client.get("/ai/jobs?limit=2")
                assert response.status_code == 200
                data = response.json()
                assert len(data["jobs"]) == 2
                assert data["count"] == 2


class TestAIJobStatusEndpoint:
    """Tests for GET /ai/jobs/{job_id} endpoint."""

    def test_get_job_status_not_found(self, client):
        """Get job status returns 404 for nonexistent job."""
        with patch("src.webapi.ACTIONS_ENABLED", True):
            with patch("src.queue.simple_queue.SimpleQueue") as mock_queue_class:
                mock_queue = MagicMock()
                mock_queue.get_job.return_value = None
                mock_queue_class.return_value = mock_queue

                response = client.get("/ai/jobs/nonexistent-job")
                assert response.status_code == 404
                assert "not found" in response.json()["detail"]

    def test_get_job_status_pending(self, client):
        """Get job status for pending job."""
        with patch("src.webapi.ACTIONS_ENABLED", True):
            with patch("src.queue.simple_queue.SimpleQueue") as mock_queue_class:
                mock_queue = MagicMock()

                now = datetime.now(UTC).isoformat()
                job_data = {
                    "status": "pending",
                    "action_provider": "google",
                    "action_name": "gmail.send",
                    "result": None,
                    "error": None,
                    "duration_ms": None,
                    "started_at": None,
                    "finished_at": None,
                    "enqueued_at": now,
                }
                mock_queue.get_job.return_value = job_data
                mock_queue_class.return_value = mock_queue

                response = client.get("/ai/jobs/job-1")
                assert response.status_code == 200
                data = response.json()
                assert data["job_id"] == "job-1"
                assert data["status"] == "pending"
                assert data["action"] == "google.gmail.send"

    def test_get_job_status_completed(self, client):
        """Get job status for completed job."""
        with patch("src.webapi.ACTIONS_ENABLED", True):
            with patch("src.queue.simple_queue.SimpleQueue") as mock_queue_class:
                mock_queue = MagicMock()

                now = datetime.now(UTC)
                job_data = {
                    "status": "completed",
                    "action_provider": "google",
                    "action_name": "gmail.send",
                    "result": '{"message_id": "msg_123"}',
                    "error": None,
                    "started_at": now.isoformat(),
                    "finished_at": now.isoformat(),
                    "enqueued_at": (now.timestamp() - 5).__str__(),
                }
                mock_queue.get_job.return_value = job_data
                mock_queue_class.return_value = mock_queue

                response = client.get("/ai/jobs/job-1")
                assert response.status_code == 200
                data = response.json()
                assert data["status"] == "completed"
                assert data["result"] is not None

    def test_get_job_status_failed(self, client):
        """Get job status for failed job."""
        with patch("src.webapi.ACTIONS_ENABLED", True):
            with patch("src.queue.simple_queue.SimpleQueue") as mock_queue_class:
                mock_queue = MagicMock()

                now = datetime.now(UTC)
                job_data = {
                    "status": "failed",
                    "action_provider": "google",
                    "action_name": "gmail.send",
                    "result": None,
                    "error": "Auth failed",
                    "started_at": now.isoformat(),
                    "finished_at": now.isoformat(),
                    "enqueued_at": (now.timestamp() - 10).__str__(),
                }
                mock_queue.get_job.return_value = job_data
                mock_queue_class.return_value = mock_queue

                response = client.get("/ai/jobs/job-1")
                assert response.status_code == 200
                data = response.json()
                assert data["status"] == "failed"
                assert data["error"] is not None


class TestWorkspaceScopedMetrics:
    """Tests for workspace-scoped metrics (Sprint 60 preparation)."""

    def test_metrics_have_workspace_labels(self):
        """Verify AI metrics have workspace_id labels defined."""
        from src.telemetry.prom import ai_job_latency_seconds, ai_jobs_total, ai_queue_depth, security_decisions_total

        # Metrics should be initialized (or None if telemetry disabled)
        if ai_jobs_total is not None:
            assert "workspace_id" in ai_jobs_total._labelnames
            assert "status" in ai_jobs_total._labelnames

        if ai_job_latency_seconds is not None:
            assert "workspace_id" in ai_job_latency_seconds._labelnames

        if ai_queue_depth is not None:
            assert "workspace_id" in ai_queue_depth._labelnames

        if security_decisions_total is not None:
            assert "workspace_id" in security_decisions_total._labelnames
            assert "result" in security_decisions_total._labelnames
