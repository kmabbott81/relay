"""Unit tests for job tracking - Sprint 58 Slice 6.

Tests JobStore lifecycle (create → start → finish_ok/err)
and status transitions with timestamps.
"""

from datetime import UTC, datetime

import pytest

from src.ai.job_store import JobStore
from src.schemas.job import JobRecord, JobStatus


class TestJobStore:
    """Tests for in-memory job store."""

    @pytest.fixture
    def store(self):
        """Create fresh store for each test."""
        return JobStore()

    @pytest.mark.asyncio
    @pytest.mark.anyio
    async def test_create_job(self, store):
        """Create job starts in PENDING state with creation timestamp."""
        job = await store.create(user_id="user_123", action_id="gmail.send", plan_id="plan_456")

        assert job.job_id is not None
        assert job.user_id == "user_123"
        assert job.action_id == "gmail.send"
        assert job.plan_id == "plan_456"
        assert job.status == JobStatus.PENDING
        assert job.created_at is not None
        assert job.started_at is None
        assert job.finished_at is None
        assert job.result is None
        assert job.error is None

    @pytest.mark.asyncio
    @pytest.mark.anyio
    async def test_lifecycle_success(self, store):
        """Job lifecycle: PENDING → RUNNING → SUCCESS."""
        # Create
        job = await store.create(user_id="user_123", action_id="gmail.send")
        assert job.status == JobStatus.PENDING

        # Start
        job = await store.start(job.job_id)
        assert job is not None
        assert job.status == JobStatus.RUNNING
        assert job.started_at is not None

        # Finish success
        result_data = {"message_id": "msg_789"}
        job = await store.finish_ok(job.job_id, result=result_data)
        assert job is not None
        assert job.status == JobStatus.SUCCESS
        assert job.finished_at is not None
        assert job.result == result_data
        assert job.error is None

    @pytest.mark.asyncio
    @pytest.mark.anyio
    async def test_lifecycle_failure(self, store):
        """Job lifecycle: PENDING → RUNNING → FAILED."""
        # Create
        job = await store.create(user_id="user_123", action_id="gmail.send")
        assert job.status == JobStatus.PENDING

        # Start
        job = await store.start(job.job_id)
        assert job.status == JobStatus.RUNNING

        # Finish failure
        job = await store.finish_err(job.job_id, error="Authentication failed")
        assert job is not None
        assert job.status == JobStatus.FAILED
        assert job.finished_at is not None
        assert job.error == "Authentication failed"
        assert job.result is None

    @pytest.mark.asyncio
    @pytest.mark.anyio
    async def test_get_job(self, store):
        """Retrieve job by ID."""
        job = await store.create(user_id="user_123", action_id="gmail.send")
        job_id = job.job_id

        retrieved = await store.get(job_id)
        assert retrieved is not None
        assert retrieved.job_id == job_id
        assert retrieved.status == JobStatus.PENDING

    @pytest.mark.asyncio
    @pytest.mark.anyio
    async def test_get_nonexistent_job(self, store):
        """Get nonexistent job returns None."""
        retrieved = await store.get("nonexistent_id")
        assert retrieved is None

    @pytest.mark.asyncio
    @pytest.mark.anyio
    async def test_start_nonexistent_job(self, store):
        """Start nonexistent job returns None."""
        result = await store.start("nonexistent_id")
        assert result is None

    @pytest.mark.asyncio
    @pytest.mark.anyio
    async def test_finish_ok_nonexistent_job(self, store):
        """Finish success on nonexistent job returns None."""
        result = await store.finish_ok("nonexistent_id")
        assert result is None

    @pytest.mark.asyncio
    @pytest.mark.anyio
    async def test_finish_err_nonexistent_job(self, store):
        """Finish error on nonexistent job returns None."""
        result = await store.finish_err("nonexistent_id", error="Test error")
        assert result is None

    @pytest.mark.asyncio
    @pytest.mark.anyio
    async def test_extra_forbid_on_job_record(self):
        """Extra fields are rejected on JobRecord."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            JobRecord(
                job_id="job_123",
                user_id="user_123",
                action_id="gmail.send",
                status=JobStatus.PENDING,
                created_at=datetime.now(UTC),
                extra_field="should_fail",  # type: ignore
            )

    @pytest.mark.asyncio
    @pytest.mark.anyio
    async def test_concurrent_create_and_get(self, store):
        """Multiple concurrent create/get operations (basic concurrency test)."""
        import asyncio

        jobs = await asyncio.gather(
            store.create(user_id="user_1", action_id="gmail.send"),
            store.create(user_id="user_2", action_id="calendar.create"),
            store.create(user_id="user_3", action_id="gmail.send"),
        )

        retrieved = await asyncio.gather(
            store.get(jobs[0].job_id),
            store.get(jobs[1].job_id),
            store.get(jobs[2].job_id),
        )

        assert len([j for j in retrieved if j is not None]) == 3
