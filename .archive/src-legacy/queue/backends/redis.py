"""
Redis Queue Backend (Sprint 28)

Production-ready persistent queue using Redis for durability and cross-region distribution.
"""

import json
from datetime import UTC, datetime, timedelta
from typing import Any

from ..persistent_queue import Job, JobStatus, PersistentQueue


class RedisQueue(PersistentQueue):
    """Redis-backed persistent queue implementation."""

    def __init__(self, redis_client: Any, key_prefix: str = "orch:queue"):
        """
        Initialize Redis queue.

        Args:
            redis_client: Redis client instance (redis.Redis or compatible)
            key_prefix: Redis key prefix for namespacing
        """
        self._redis = redis_client
        self._prefix = key_prefix
        self._queue_key = f"{key_prefix}:pending"
        self._jobs_key = f"{key_prefix}:jobs"

    def enqueue(self, job: Job) -> None:
        """Add job to queue."""
        # Store job data in hash
        self._redis.hset(self._jobs_key, job.id, json.dumps(job.to_dict()))

        # Add to pending queue (FIFO)
        self._redis.rpush(self._queue_key, job.id)

    def dequeue(self) -> Job | None:
        """Get next pending job from queue."""
        # Atomic pop from queue
        job_id = self._redis.lpop(self._queue_key)

        if not job_id:
            return None

        # Decode bytes if necessary
        if isinstance(job_id, bytes):
            job_id = job_id.decode("utf-8")

        # Get job data
        job_data = self._redis.hget(self._jobs_key, job_id)

        if not job_data:
            return None

        # Decode bytes if necessary
        if isinstance(job_data, bytes):
            job_data = job_data.decode("utf-8")

        job = Job.from_dict(json.loads(job_data))

        # Mark as running
        job.status = JobStatus.RUNNING
        job.started_at = datetime.now(UTC).isoformat()

        # Update in Redis
        self._redis.hset(self._jobs_key, job.id, json.dumps(job.to_dict()))

        return job

    def update_status(
        self,
        job_id: str,
        status: JobStatus,
        error: str | None = None,
        result: dict[str, Any] | None = None,
    ) -> None:
        """Update job status."""
        job_data = self._redis.hget(self._jobs_key, job_id)

        if not job_data:
            return

        # Decode bytes if necessary
        if isinstance(job_data, bytes):
            job_data = job_data.decode("utf-8")

        job = Job.from_dict(json.loads(job_data))

        job.status = status
        job.error = error
        job.result = result

        if status in (JobStatus.SUCCESS, JobStatus.FAILED):
            job.finished_at = datetime.now(UTC).isoformat()

        # Re-enqueue for retry
        if status == JobStatus.RETRY:
            job.attempts += 1
            job.status = JobStatus.PENDING
            self._redis.rpush(self._queue_key, job_id)

        # Update in Redis
        self._redis.hset(self._jobs_key, job.id, json.dumps(job.to_dict()))

    def get_job(self, job_id: str) -> Job | None:
        """Get job by ID."""
        job_data = self._redis.hget(self._jobs_key, job_id)

        if not job_data:
            return None

        # Decode bytes if necessary
        if isinstance(job_data, bytes):
            job_data = job_data.decode("utf-8")

        return Job.from_dict(json.loads(job_data))

    def list_jobs(self, status: JobStatus | None = None, limit: int = 100) -> list[Job]:
        """List jobs with optional status filter."""
        # Get all job IDs
        job_ids = self._redis.hkeys(self._jobs_key)

        jobs = []
        for job_id in job_ids:
            # Decode bytes if necessary
            if isinstance(job_id, bytes):
                job_id = job_id.decode("utf-8")

            job = self.get_job(job_id)
            if job:
                if status is None or job.status == status:
                    jobs.append(job)

        # Sort by enqueued time (most recent first)
        jobs.sort(key=lambda j: j.enqueued_at, reverse=True)

        return jobs[:limit]

    def count(self, status: JobStatus | None = None) -> int:
        """Count jobs with optional status filter."""
        if status is None:
            return self._redis.hlen(self._jobs_key)

        # Count jobs matching status
        job_ids = self._redis.hkeys(self._jobs_key)
        count = 0

        for job_id in job_ids:
            # Decode bytes if necessary
            if isinstance(job_id, bytes):
                job_id = job_id.decode("utf-8")

            job = self.get_job(job_id)
            if job and job.status == status:
                count += 1

        return count

    def purge(self, older_than_hours: int = 24) -> int:
        """Remove completed/failed jobs older than threshold."""
        cutoff = datetime.now(UTC) - timedelta(hours=older_than_hours)
        cutoff_iso = cutoff.isoformat()

        job_ids = self._redis.hkeys(self._jobs_key)
        purged = 0

        for job_id in job_ids:
            # Decode bytes if necessary
            if isinstance(job_id, bytes):
                job_id = job_id.decode("utf-8")

            job = self.get_job(job_id)

            if job and job.status in (JobStatus.SUCCESS, JobStatus.FAILED):
                if job.finished_at and job.finished_at < cutoff_iso:
                    self._redis.hdel(self._jobs_key, job_id)
                    purged += 1

        return purged
