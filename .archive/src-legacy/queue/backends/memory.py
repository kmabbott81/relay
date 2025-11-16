"""
In-Memory Queue Backend (Sprint 28)

Thread-safe in-memory implementation for testing and development.
"""

import threading
from collections import deque
from datetime import UTC, datetime, timedelta

from ..persistent_queue import Job, JobStatus, PersistentQueue


class MemoryQueue(PersistentQueue):
    """Thread-safe in-memory queue implementation."""

    def __init__(self):
        """Initialize memory queue."""
        self._queue: deque[str] = deque()  # Job IDs in FIFO order
        self._jobs: dict[str, Job] = {}  # Job storage by ID
        self._lock = threading.Lock()

    def enqueue(self, job: Job) -> None:
        """Add job to queue."""
        with self._lock:
            self._jobs[job.id] = job
            self._queue.append(job.id)

    def dequeue(self) -> Job | None:
        """Get next pending job from queue."""
        with self._lock:
            while self._queue:
                job_id = self._queue.popleft()
                job = self._jobs.get(job_id)

                if job and job.status == JobStatus.PENDING:
                    # Mark as running
                    job.status = JobStatus.RUNNING
                    job.started_at = datetime.now(UTC).isoformat()
                    return job

            return None

    def update_status(
        self,
        job_id: str,
        status: JobStatus,
        error: str | None = None,
        result: dict | None = None,
    ) -> None:
        """Update job status."""
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return

            job.status = status
            job.error = error
            job.result = result

            if status in (JobStatus.SUCCESS, JobStatus.FAILED):
                job.finished_at = datetime.now(UTC).isoformat()

            # Re-enqueue for retry
            if status == JobStatus.RETRY:
                job.attempts += 1
                job.status = JobStatus.PENDING
                self._queue.append(job_id)

    def get_job(self, job_id: str) -> Job | None:
        """Get job by ID."""
        with self._lock:
            return self._jobs.get(job_id)

    def list_jobs(self, status: JobStatus | None = None, limit: int = 100) -> list[Job]:
        """List jobs with optional status filter."""
        with self._lock:
            jobs = list(self._jobs.values())

            if status:
                jobs = [j for j in jobs if j.status == status]

            # Sort by enqueued time (most recent first)
            jobs.sort(key=lambda j: j.enqueued_at, reverse=True)

            return jobs[:limit]

    def count(self, status: JobStatus | None = None) -> int:
        """Count jobs with optional status filter."""
        with self._lock:
            if status is None:
                return len(self._jobs)

            return sum(1 for j in self._jobs.values() if j.status == status)

    def purge(self, older_than_hours: int = 24) -> int:
        """Remove completed/failed jobs older than threshold."""
        cutoff = datetime.now(UTC) - timedelta(hours=older_than_hours)
        cutoff_iso = cutoff.isoformat()

        with self._lock:
            to_remove = []

            for job_id, job in self._jobs.items():
                if job.status in (JobStatus.SUCCESS, JobStatus.FAILED):
                    if job.finished_at and job.finished_at < cutoff_iso:
                        to_remove.append(job_id)

            for job_id in to_remove:
                del self._jobs[job_id]

            return len(to_remove)
