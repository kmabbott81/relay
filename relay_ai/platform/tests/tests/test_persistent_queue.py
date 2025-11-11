"""Tests for persistent queue (Sprint 28)."""

from datetime import UTC, datetime

from relay_ai.queue.backends.memory import MemoryQueue
from relay_ai.queue.persistent_queue import Job, JobStatus


def test_memory_queue_enqueue_dequeue():
    """Test basic enqueue/dequeue operations."""
    queue = MemoryQueue()

    job = Job(
        id="job-1",
        dag_path="test.yaml",
        tenant_id="tenant-1",
        schedule_id="schedule-1",
        status=JobStatus.PENDING,
        enqueued_at=datetime.now(UTC).isoformat(),
    )

    queue.enqueue(job)

    # Dequeue should return the job
    dequeued = queue.dequeue()
    assert dequeued is not None
    assert dequeued.id == "job-1"
    assert dequeued.status == JobStatus.RUNNING  # Status changed to RUNNING


def test_memory_queue_empty_dequeue():
    """Test dequeue from empty queue returns None."""
    queue = MemoryQueue()

    result = queue.dequeue()
    assert result is None


def test_memory_queue_multiple_jobs():
    """Test FIFO ordering of jobs."""
    queue = MemoryQueue()

    job1 = Job(
        id="job-1",
        dag_path="test1.yaml",
        tenant_id="tenant-1",
        schedule_id=None,
        status=JobStatus.PENDING,
        enqueued_at=datetime.now(UTC).isoformat(),
    )

    job2 = Job(
        id="job-2",
        dag_path="test2.yaml",
        tenant_id="tenant-1",
        schedule_id=None,
        status=JobStatus.PENDING,
        enqueued_at=datetime.now(UTC).isoformat(),
    )

    queue.enqueue(job1)
    queue.enqueue(job2)

    # Should dequeue in FIFO order
    first = queue.dequeue()
    assert first.id == "job-1"

    second = queue.dequeue()
    assert second.id == "job-2"


def test_memory_queue_update_status():
    """Test updating job status."""
    queue = MemoryQueue()

    job = Job(
        id="job-1",
        dag_path="test.yaml",
        tenant_id="tenant-1",
        schedule_id=None,
        status=JobStatus.PENDING,
        enqueued_at=datetime.now(UTC).isoformat(),
    )

    queue.enqueue(job)
    queue.update_status("job-1", JobStatus.SUCCESS, result={"output": "done"})

    # Get job and verify status
    updated = queue.get_job("job-1")
    assert updated.status == JobStatus.SUCCESS
    assert updated.result == {"output": "done"}
    assert updated.finished_at is not None


def test_memory_queue_update_status_with_error():
    """Test updating job status with error."""
    queue = MemoryQueue()

    job = Job(
        id="job-1",
        dag_path="test.yaml",
        tenant_id="tenant-1",
        schedule_id=None,
        status=JobStatus.PENDING,
        enqueued_at=datetime.now(UTC).isoformat(),
    )

    queue.enqueue(job)
    queue.dequeue()  # Mark as RUNNING
    queue.update_status("job-1", JobStatus.FAILED, error="Something went wrong")

    updated = queue.get_job("job-1")
    assert updated.status == JobStatus.FAILED
    assert updated.error == "Something went wrong"
    assert updated.finished_at is not None


def test_memory_queue_retry():
    """Test job retry re-enqueues the job."""
    queue = MemoryQueue()

    job = Job(
        id="job-1",
        dag_path="test.yaml",
        tenant_id="tenant-1",
        schedule_id=None,
        status=JobStatus.PENDING,
        enqueued_at=datetime.now(UTC).isoformat(),
        max_retries=2,
    )

    queue.enqueue(job)
    queue.dequeue()  # Mark as RUNNING

    # Update status to RETRY
    queue.update_status("job-1", JobStatus.RETRY)

    # Job should be re-enqueued
    retrieved = queue.get_job("job-1")
    assert retrieved.status == JobStatus.PENDING
    assert retrieved.attempts == 1

    # Should be able to dequeue again
    dequeued_again = queue.dequeue()
    assert dequeued_again.id == "job-1"
    assert dequeued_again.status == JobStatus.RUNNING


def test_memory_queue_get_job():
    """Test getting job by ID."""
    queue = MemoryQueue()

    job = Job(
        id="job-1",
        dag_path="test.yaml",
        tenant_id="tenant-1",
        schedule_id=None,
        status=JobStatus.PENDING,
        enqueued_at=datetime.now(UTC).isoformat(),
    )

    queue.enqueue(job)

    retrieved = queue.get_job("job-1")
    assert retrieved is not None
    assert retrieved.id == "job-1"

    # Non-existent job
    not_found = queue.get_job("job-999")
    assert not_found is None


def test_memory_queue_list_jobs():
    """Test listing jobs."""
    queue = MemoryQueue()

    job1 = Job(
        id="job-1",
        dag_path="test1.yaml",
        tenant_id="tenant-1",
        schedule_id=None,
        status=JobStatus.PENDING,
        enqueued_at="2025-10-03T10:00:00Z",
    )

    job2 = Job(
        id="job-2",
        dag_path="test2.yaml",
        tenant_id="tenant-1",
        schedule_id=None,
        status=JobStatus.PENDING,
        enqueued_at="2025-10-03T10:01:00Z",
    )

    queue.enqueue(job1)
    queue.enqueue(job2)

    # List all jobs
    all_jobs = queue.list_jobs()
    assert len(all_jobs) == 2

    # Most recent first
    assert all_jobs[0].id == "job-2"
    assert all_jobs[1].id == "job-1"


def test_memory_queue_list_jobs_by_status():
    """Test listing jobs filtered by status."""
    queue = MemoryQueue()

    job1 = Job(
        id="job-1",
        dag_path="test1.yaml",
        tenant_id="tenant-1",
        schedule_id=None,
        status=JobStatus.PENDING,
        enqueued_at=datetime.now(UTC).isoformat(),
    )

    job2 = Job(
        id="job-2",
        dag_path="test2.yaml",
        tenant_id="tenant-1",
        schedule_id=None,
        status=JobStatus.PENDING,
        enqueued_at=datetime.now(UTC).isoformat(),
    )

    queue.enqueue(job1)
    queue.enqueue(job2)

    queue.dequeue()  # job-1 becomes RUNNING

    # Filter by status
    pending = queue.list_jobs(status=JobStatus.PENDING)
    assert len(pending) == 1
    assert pending[0].id == "job-2"

    running = queue.list_jobs(status=JobStatus.RUNNING)
    assert len(running) == 1
    assert running[0].id == "job-1"


def test_memory_queue_list_jobs_respects_limit():
    """Test that list_jobs respects limit."""
    queue = MemoryQueue()

    for i in range(10):
        job = Job(
            id=f"job-{i}",
            dag_path=f"test{i}.yaml",
            tenant_id="tenant-1",
            schedule_id=None,
            status=JobStatus.PENDING,
            enqueued_at=datetime.now(UTC).isoformat(),
        )
        queue.enqueue(job)

    jobs = queue.list_jobs(limit=5)
    assert len(jobs) == 5


def test_memory_queue_count():
    """Test counting jobs."""
    queue = MemoryQueue()

    job1 = Job(
        id="job-1",
        dag_path="test1.yaml",
        tenant_id="tenant-1",
        schedule_id=None,
        status=JobStatus.PENDING,
        enqueued_at=datetime.now(UTC).isoformat(),
    )

    job2 = Job(
        id="job-2",
        dag_path="test2.yaml",
        tenant_id="tenant-1",
        schedule_id=None,
        status=JobStatus.PENDING,
        enqueued_at=datetime.now(UTC).isoformat(),
    )

    queue.enqueue(job1)
    queue.enqueue(job2)

    # Count all
    assert queue.count() == 2

    # Count by status
    assert queue.count(JobStatus.PENDING) == 2

    queue.dequeue()  # job-1 becomes RUNNING

    assert queue.count(JobStatus.PENDING) == 1
    assert queue.count(JobStatus.RUNNING) == 1


def test_memory_queue_purge():
    """Test purging old completed jobs."""
    queue = MemoryQueue()

    # Old completed job
    old_job = Job(
        id="old-job",
        dag_path="test.yaml",
        tenant_id="tenant-1",
        schedule_id=None,
        status=JobStatus.SUCCESS,
        enqueued_at="2025-10-01T10:00:00Z",
        finished_at="2025-10-01T10:01:00Z",
    )

    # Recent completed job
    recent_job = Job(
        id="recent-job",
        dag_path="test.yaml",
        tenant_id="tenant-1",
        schedule_id=None,
        status=JobStatus.SUCCESS,
        enqueued_at=datetime.now(UTC).isoformat(),
        finished_at=datetime.now(UTC).isoformat(),
    )

    queue._jobs["old-job"] = old_job
    queue._jobs["recent-job"] = recent_job

    # Purge jobs older than 24 hours
    purged = queue.purge(older_than_hours=24)

    assert purged == 1  # Only old job purged
    assert queue.get_job("old-job") is None
    assert queue.get_job("recent-job") is not None


def test_job_to_dict_and_from_dict():
    """Test job serialization."""
    job = Job(
        id="job-1",
        dag_path="test.yaml",
        tenant_id="tenant-1",
        schedule_id="schedule-1",
        status=JobStatus.PENDING,
        enqueued_at="2025-10-03T10:00:00Z",
        max_retries=2,
    )

    # Convert to dict
    job_dict = job.to_dict()
    assert job_dict["id"] == "job-1"
    assert job_dict["status"] == "pending"

    # Convert back
    restored = Job.from_dict(job_dict)
    assert restored.id == job.id
    assert restored.status == job.status
    assert restored.max_retries == job.max_retries
