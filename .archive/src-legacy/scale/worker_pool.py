"""Worker pool with graceful scaling and region awareness.

Manages a pool of background worker threads that process jobs from a queue.
Supports graceful drain on scale-down and region-aware job routing.

Environment Variables:
    CURRENT_REGION: Current region identifier
    WORKER_SHUTDOWN_TIMEOUT_S: Graceful shutdown timeout (default: 30)
"""

import os
import queue
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Optional


@dataclass
class Job:
    """Background job to be executed."""

    job_id: str
    task: Callable
    args: tuple
    kwargs: dict
    region: Optional[str] = None
    submitted_at: Optional[datetime] = None
    retries: int = 0


@dataclass
class WorkerStats:
    """Statistics for worker pool."""

    total_workers: int
    active_workers: int
    idle_workers: int
    queue_depth: int
    jobs_completed: int
    jobs_failed: int


class WorkerPool:
    """Thread-based worker pool with graceful scaling."""

    def __init__(self, initial_workers: int = 1, region: Optional[str] = None):
        """
        Initialize worker pool.

        Args:
            initial_workers: Initial number of workers
            region: Region identifier for this pool
        """
        self.region = region or os.getenv("CURRENT_REGION", "default")
        self.job_queue: queue.Queue[Optional[Job]] = queue.Queue()
        self.workers: list[threading.Thread] = []
        self.active_jobs: dict[str, Job] = {}
        self.stats = {
            "completed": 0,
            "failed": 0,
        }
        self.shutdown_event = threading.Event()
        self.lock = threading.Lock()

        # Start initial workers
        for _ in range(initial_workers):
            self._spawn_worker()

    def _spawn_worker(self):
        """Spawn a new worker thread."""
        worker = threading.Thread(target=self._worker_loop, daemon=True, name=f"Worker-{self.region}-{len(self.workers)}")
        worker.start()
        self.workers.append(worker)

    def _worker_loop(self):
        """Main worker loop - processes jobs from queue."""
        while not self.shutdown_event.is_set():
            try:
                # Get job with timeout to check shutdown periodically
                job = self.job_queue.get(timeout=1.0)

                # None is poison pill for graceful shutdown
                if job is None:
                    break

                # Mark job as active
                with self.lock:
                    self.active_jobs[job.job_id] = job

                # Execute job
                try:
                    job.task(*job.args, **job.kwargs)
                    with self.lock:
                        self.stats["completed"] += 1
                except Exception as e:
                    print(f"Job {job.job_id} failed: {e}")
                    with self.lock:
                        self.stats["failed"] += 1
                finally:
                    # Remove from active jobs
                    with self.lock:
                        self.active_jobs.pop(job.job_id, None)
                    self.job_queue.task_done()

            except queue.Empty:
                # No job available, loop back to check shutdown
                continue

    def submit_job(self, job: Job):
        """
        Submit a job to the pool.

        Args:
            job: Job to execute
        """
        if not job.submitted_at:
            job.submitted_at = datetime.utcnow()

        self.job_queue.put(job)

    def scale_to(self, desired_workers: int) -> bool:
        """
        Scale pool to desired worker count.

        Args:
            desired_workers: Target number of workers

        Returns:
            True if scaling succeeded, False otherwise
        """
        current = len([w for w in self.workers if w.is_alive()])

        if desired_workers == current:
            return True

        if desired_workers > current:
            # Scale up: spawn new workers
            to_add = desired_workers - current
            for _ in range(to_add):
                self._spawn_worker()
            return True

        # Scale down: send poison pills
        to_remove = current - desired_workers
        for _ in range(to_remove):
            self.job_queue.put(None)  # Poison pill

        # Wait for workers to drain (with timeout)
        timeout_s = int(os.getenv("WORKER_SHUTDOWN_TIMEOUT_S", "30"))
        deadline = time.time() + timeout_s

        while time.time() < deadline:
            alive = len([w for w in self.workers if w.is_alive()])
            if alive <= desired_workers:
                # Clean up dead threads
                self.workers = [w for w in self.workers if w.is_alive()]
                return True
            time.sleep(0.5)

        # Timeout - force cleanup
        self.workers = [w for w in self.workers if w.is_alive()]
        return len(self.workers) == desired_workers

    def get_stats(self) -> WorkerStats:
        """
        Get current worker pool statistics.

        Returns:
            WorkerStats with current state
        """
        with self.lock:
            total = len([w for w in self.workers if w.is_alive()])
            active = len(self.active_jobs)

            return WorkerStats(
                total_workers=total,
                active_workers=active,
                idle_workers=total - active,
                queue_depth=self.job_queue.qsize(),
                jobs_completed=self.stats["completed"],
                jobs_failed=self.stats["failed"],
            )

    def shutdown(self, timeout_s: Optional[int] = None):
        """
        Gracefully shutdown the pool.

        Args:
            timeout_s: Timeout in seconds (default: WORKER_SHUTDOWN_TIMEOUT_S env)
        """
        if timeout_s is None:
            timeout_s = int(os.getenv("WORKER_SHUTDOWN_TIMEOUT_S", "30"))

        # Wait for queue to drain first (with timeout)
        deadline = time.time() + timeout_s
        while not self.job_queue.empty() and time.time() < deadline:
            time.sleep(0.1)

        # Signal shutdown
        self.shutdown_event.set()

        # Send poison pills to all workers
        for _ in self.workers:
            self.job_queue.put(None)

        # Wait for workers to finish
        remaining = deadline - time.time()
        for worker in self.workers:
            if remaining > 0:
                worker.join(timeout=remaining)
                remaining = deadline - time.time()

        self.workers.clear()
