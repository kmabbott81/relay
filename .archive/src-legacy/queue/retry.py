"""Retry policy with exponential backoff and jitter.

Provides idempotent retry logic for failed jobs with configurable backoff.

Environment Variables:
    MAX_RETRIES: Maximum retry attempts (default: 3)
    RETRY_BASE_MS: Base retry delay in milliseconds (default: 400)
    RETRY_JITTER_PCT: Jitter percentage 0.0-1.0 (default: 0.2)
"""

import os
import random
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Optional


@dataclass
class RetryConfig:
    """Retry policy configuration."""

    max_retries: int
    base_delay_ms: int
    jitter_pct: float

    @classmethod
    def from_env(cls) -> "RetryConfig":
        """Load retry config from environment variables."""
        return cls(
            max_retries=int(os.getenv("MAX_RETRIES", "3")),
            base_delay_ms=int(os.getenv("RETRY_BASE_MS", "400")),
            jitter_pct=float(os.getenv("RETRY_JITTER_PCT", "0.2")),
        )


@dataclass
class RetryState:
    """State for retry tracking."""

    job_id: str
    attempt: int
    max_attempts: int
    last_error: Optional[str] = None
    next_retry_at: Optional[datetime] = None


def calculate_backoff_ms(attempt: int, config: RetryConfig) -> int:
    """
    Calculate exponential backoff with jitter.

    Args:
        attempt: Current attempt number (0-indexed)
        config: Retry configuration

    Returns:
        Delay in milliseconds before next retry
    """
    # Exponential backoff: base * 2^attempt
    base_delay = config.base_delay_ms * (2**attempt)

    # Add jitter: +/- jitter_pct
    jitter_range = base_delay * config.jitter_pct
    jitter = random.uniform(-jitter_range, jitter_range)

    return int(base_delay + jitter)


def should_retry(state: RetryState, config: RetryConfig) -> bool:
    """
    Determine if job should be retried.

    Args:
        state: Current retry state
        config: Retry configuration

    Returns:
        True if should retry, False if exhausted
    """
    return state.attempt < config.max_retries


def retry_with_backoff(
    job_id: str,
    task: Callable,
    args: tuple = (),
    kwargs: Optional[dict] = None,
    config: Optional[RetryConfig] = None,
) -> tuple[bool, Optional[Exception]]:
    """
    Execute task with retry and exponential backoff.

    Args:
        job_id: Unique job identifier (for idempotency)
        task: Callable to execute
        args: Positional arguments
        kwargs: Keyword arguments
        config: Retry configuration (loads from env if None)

    Returns:
        Tuple of (success: bool, last_error: Optional[Exception])
    """
    if kwargs is None:
        kwargs = {}

    if config is None:
        config = RetryConfig.from_env()

    last_error: Optional[Exception] = None

    for attempt in range(config.max_retries + 1):
        try:
            task(*args, **kwargs)
            return (True, None)

        except Exception as e:
            last_error = e
            print(f"Job {job_id} attempt {attempt + 1}/{config.max_retries + 1} failed: {e}")

            # Don't sleep after final attempt
            if attempt < config.max_retries:
                backoff_ms = calculate_backoff_ms(attempt, config)
                time.sleep(backoff_ms / 1000.0)

    return (False, last_error)


class IdempotencyTracker:
    """Track job IDs to prevent duplicate execution."""

    def __init__(self):
        """Initialize tracker."""
        self.seen_jobs: set[str] = set()
        self.lock = __import__("threading").Lock()

    def is_duplicate(self, job_id: str) -> bool:
        """
        Check if job has been seen before.

        Args:
            job_id: Job identifier

        Returns:
            True if duplicate, False if first time
        """
        with self.lock:
            if job_id in self.seen_jobs:
                return True
            self.seen_jobs.add(job_id)
            return False

    def mark_completed(self, job_id: str):
        """
        Mark job as completed.

        Args:
            job_id: Job identifier
        """
        # Keep in seen set to prevent re-execution
        pass

    def clear(self):
        """Clear all tracked jobs."""
        with self.lock:
            self.seen_jobs.clear()
