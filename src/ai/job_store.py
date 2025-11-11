"""In-memory job store - Sprint 58 Slice 6.

Manages job record lifecycle (create, start, finish).
Thread-safe via asyncio.Lock.
Designed to be swappable with DB implementation later.
"""

import asyncio
from datetime import UTC, datetime
from typing import Optional
from uuid import uuid4

from relay_ai.schemas.job import JobRecord, JobStatus


class JobStore:
    """In-memory job store with lifecycle management.

    Provides create, start, finish_ok, finish_err, and get operations.
    Thread-safe using asyncio.Lock for concurrent access.
    """

    def __init__(self):
        """Initialize store with empty job map."""
        self._jobs: dict[str, JobRecord] = {}
        self._lock = asyncio.Lock()

    async def create(
        self,
        user_id: str,
        action_id: str,
        plan_id: Optional[str] = None,
    ) -> JobRecord:
        """Create a new job record in PENDING state.

        Args:
            user_id: User identifier
            action_id: Action identifier (e.g., 'gmail.send')
            plan_id: Optional parent plan UUID for correlation

        Returns:
            Created JobRecord
        """
        async with self._lock:
            job = JobRecord(
                job_id=str(uuid4()),
                user_id=user_id,
                action_id=action_id,
                plan_id=plan_id,
                status=JobStatus.PENDING,
                created_at=datetime.now(UTC),
            )
            self._jobs[job.job_id] = job
            return job

    async def start(self, job_id: str) -> Optional[JobRecord]:
        """Transition job to RUNNING state.

        Args:
            job_id: Job identifier

        Returns:
            Updated JobRecord, or None if not found
        """
        async with self._lock:
            job = self._jobs.get(job_id)
            if job:
                # Create updated record with started_at timestamp
                job = JobRecord(**{**job.model_dump(), "status": JobStatus.RUNNING, "started_at": datetime.now(UTC)})
                self._jobs[job_id] = job
            return job

    async def finish_ok(self, job_id: str, result: Optional[dict] = None) -> Optional[JobRecord]:
        """Transition job to SUCCESS state with result.

        Args:
            job_id: Job identifier
            result: Execution result (will be stored as-is; redact before calling)

        Returns:
            Updated JobRecord, or None if not found
        """
        async with self._lock:
            job = self._jobs.get(job_id)
            if job:
                job = JobRecord(
                    **{
                        **job.model_dump(),
                        "status": JobStatus.SUCCESS,
                        "finished_at": datetime.now(UTC),
                        "result": result,
                    }
                )
                self._jobs[job_id] = job
            return job

    async def finish_err(self, job_id: str, error: str) -> Optional[JobRecord]:
        """Transition job to FAILED state with error message.

        Args:
            job_id: Job identifier
            error: Error message (redact PII before calling)

        Returns:
            Updated JobRecord, or None if not found
        """
        async with self._lock:
            job = self._jobs.get(job_id)
            if job:
                job = JobRecord(
                    **{
                        **job.model_dump(),
                        "status": JobStatus.FAILED,
                        "finished_at": datetime.now(UTC),
                        "error": error,
                    }
                )
                self._jobs[job_id] = job
            return job

    async def get(self, job_id: str) -> Optional[JobRecord]:
        """Retrieve job record by ID.

        Args:
            job_id: Job identifier

        Returns:
            JobRecord if found, None otherwise
        """
        async with self._lock:
            return self._jobs.get(job_id)


# Global job store singleton (lazy-initialized)
_JOB_STORE: Optional[JobStore] = None


def get_job_store() -> JobStore:
    """Get or create the global job store singleton.

    Lazy-initializes on first call. For testing, can be overridden
    by passing job_store parameter to AIOrchestrator.__init__.

    Returns:
        Global JobStore instance
    """
    global _JOB_STORE
    if _JOB_STORE is None:
        _JOB_STORE = JobStore()
    return _JOB_STORE
