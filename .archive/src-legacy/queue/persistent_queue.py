"""
Persistent Queue Abstraction (Sprint 28)

Provides pluggable backend for durable job queuing with memory and Redis implementations.
Replaces in-memory queue with persistent storage for cross-region distribution and recovery.
"""

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any


class JobStatus(Enum):
    """Job execution status."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    RETRY = "retry"


@dataclass
class Job:
    """Job model for persistent queue (Sprint 28 + Sprint 29)."""

    id: str
    dag_path: str
    tenant_id: str
    schedule_id: str | None
    status: JobStatus
    enqueued_at: str
    started_at: str | None = None
    finished_at: str | None = None
    attempts: int = 0
    max_retries: int = 0
    error: str | None = None
    result: dict[str, Any] | None = None
    # Sprint 29 additions
    first_seen_at: str | None = None  # First time job was enqueued
    failure_reason: str | None = None  # Terminal failure reason
    run_id: str | None = None  # Idempotency key

    def to_dict(self) -> dict[str, Any]:
        """Convert job to dictionary."""
        data = asdict(self)
        data["status"] = self.status.value
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Job":
        """Create job from dictionary."""
        data["status"] = JobStatus(data["status"])
        return cls(**data)


class PersistentQueue(ABC):
    """Abstract base class for persistent queue backends."""

    @abstractmethod
    def enqueue(self, job: Job) -> None:
        """
        Add job to queue.

        Args:
            job: Job to enqueue
        """
        pass

    @abstractmethod
    def dequeue(self) -> Job | None:
        """
        Get next job from queue (FIFO).

        Returns:
            Next job or None if queue is empty
        """
        pass

    @abstractmethod
    def update_status(
        self,
        job_id: str,
        status: JobStatus,
        error: str | None = None,
        result: dict[str, Any] | None = None,
    ) -> None:
        """
        Update job status.

        Args:
            job_id: Job identifier
            status: New status
            error: Error message if failed
            result: Result data if successful
        """
        pass

    @abstractmethod
    def get_job(self, job_id: str) -> Job | None:
        """
        Get job by ID.

        Args:
            job_id: Job identifier

        Returns:
            Job or None if not found
        """
        pass

    @abstractmethod
    def list_jobs(self, status: JobStatus | None = None, limit: int = 100) -> list[Job]:
        """
        List jobs with optional status filter.

        Args:
            status: Filter by status (None for all)
            limit: Maximum number of jobs to return

        Returns:
            List of jobs
        """
        pass

    @abstractmethod
    def count(self, status: JobStatus | None = None) -> int:
        """
        Count jobs with optional status filter.

        Args:
            status: Filter by status (None for all)

        Returns:
            Number of jobs matching criteria
        """
        pass

    @abstractmethod
    def purge(self, older_than_hours: int = 24) -> int:
        """
        Remove completed/failed jobs older than threshold.

        Args:
            older_than_hours: Age threshold in hours

        Returns:
            Number of jobs purged
        """
        pass
