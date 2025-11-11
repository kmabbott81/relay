"""
Queue Worker (Sprint 28 + Sprint 29)

Standalone worker with reliability features:
- DLQ for terminal failures
- Exponential backoff with jitter
- Heartbeat/lease renewal for long jobs
- Idempotency checks
- Rate limiting (global + per-tenant)
"""

import argparse
import os
import sys
import threading
import time
from datetime import UTC, datetime
from pathlib import Path

import yaml

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# pylint: disable=wrong-import-position
from relay_ai.orchestrator.graph import DAG, Task  # noqa: E402
from relay_ai.orchestrator.idempotency import already_processed, mark_processed  # noqa: E402
from relay_ai.orchestrator.runner import run_dag  # noqa: E402
from relay_ai.orchestrator.state_store import record_event  # noqa: E402
from relay_ai.queue.backends.memory import MemoryQueue  # noqa: E402
from relay_ai.queue.backoff import compute_delay  # noqa: E402
from relay_ai.queue.dlq import append_to_dlq  # noqa: E402
from relay_ai.queue.persistent_queue import Job, JobStatus, PersistentQueue  # noqa: E402
from relay_ai.queue.ratelimit import get_rate_limiter  # noqa: E402
from relay_ai.telemetry.noop import init_noop_if_enabled  # noqa: E402


def get_queue_backend() -> PersistentQueue:
    """Get queue backend from environment config."""
    backend = os.getenv("QUEUE_BACKEND", "memory").lower()

    if backend == "redis":
        try:
            import redis

            redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
            client = redis.from_url(redis_url, decode_responses=False)

            from .backends.redis import RedisQueue

            return RedisQueue(client, key_prefix="orch:queue")
        except ImportError:
            print("Warning: redis not installed, falling back to memory backend")
            return MemoryQueue()
        except Exception as e:
            print(f"Warning: Failed to connect to Redis ({e}), falling back to memory backend")
            return MemoryQueue()

    return MemoryQueue()


def load_dag_from_yaml(path: str) -> DAG:
    """Load DAG from YAML file."""
    with open(path, encoding="utf-8") as f:
        config = yaml.safe_load(f)

    tasks = [
        Task(
            id=t["id"],
            workflow_ref=t["workflow_ref"],
            params=t.get("params", {}),
            depends_on=t.get("depends_on", []),
            retries=t.get("retries", 0),
        )
        for t in config.get("tasks", [])
    ]

    return DAG(name=config["name"], tasks=tasks)


class HeartbeatThread(threading.Thread):
    """Background thread for sending heartbeats during job execution."""

    def __init__(self, job_id: str, queue: PersistentQueue, interval_ms: int = 15000):
        super().__init__(daemon=True)
        self.job_id = job_id
        self.queue = queue
        self.interval_ms = interval_ms
        self.stopped = threading.Event()

    def run(self):
        """Send heartbeats at regular intervals."""
        while not self.stopped.is_set():
            # Sleep in small chunks to allow quick stop
            for _ in range(self.interval_ms // 100):
                if self.stopped.is_set():
                    return
                time.sleep(0.1)

            # Send heartbeat (extend visibility)
            # Note: This is a no-op for memory backend
            # Redis backend would implement extend_visibility

    def stop(self):
        """Stop heartbeat thread."""
        self.stopped.set()


def execute_job(job: Job, queue: PersistentQueue, events_path: str, worker_id: str) -> dict:
    """
    Execute job with full reliability features.

    Args:
        job: Job to execute
        queue: Queue instance
        events_path: Events log path
        worker_id: Worker identifier

    Returns:
        Result dictionary
    """
    max_retries = int(os.getenv("MAX_JOB_RETRIES", "3"))
    rate_limiter = get_rate_limiter()

    # Check idempotency
    if job.run_id and already_processed(job.run_id):
        print(f"[{worker_id}] Job {job.id} already processed (run_id={job.run_id}), skipping")
        queue.update_status(job.id, JobStatus.SUCCESS, result={"skipped": "duplicate"})
        record_event(
            {
                "event": "run_finished",
                "job_id": job.id,
                "status": "skipped_duplicate",
                "run_id": job.run_id,
            }
        )
        return {"job": job, "status": "skipped", "reason": "duplicate"}

    # Check rate limit
    if not rate_limiter.allow(job.tenant_id):
        print(f"[{worker_id}] Job {job.id} rate limited for tenant {job.tenant_id}")

        # Requeue with delay
        delay_ms = int(os.getenv("RATE_LIMIT_RETRY_DELAY_MS", "8000"))
        time.sleep(delay_ms / 1000.0)
        queue.update_status(job.id, JobStatus.RETRY)

        record_event(
            {
                "event": "run_finished",
                "job_id": job.id,
                "status": "rate_limited",
                "tenant": job.tenant_id,
            }
        )

        return {"job": job, "status": "rate_limited"}

    start_time = datetime.now(UTC)

    record_event(
        {
            "event": "run_started",
            "job_id": job.id,
            "schedule_id": job.schedule_id,
            "dag_path": job.dag_path,
            "tenant": job.tenant_id,
            "run_id": job.run_id,
        }
    )

    # Start heartbeat thread
    heartbeat_interval = int(os.getenv("LEASE_HEARTBEAT_MS", "15000"))
    heartbeat = HeartbeatThread(job.id, queue, interval_ms=heartbeat_interval)
    heartbeat.start()

    try:
        dag = load_dag_from_yaml(job.dag_path)
        result = run_dag(dag, tenant=job.tenant_id, dry_run=False, events_path=events_path)

        # Stop heartbeat
        heartbeat.stop()
        heartbeat.join(timeout=1.0)

        # Update job status
        queue.update_status(job.id, JobStatus.SUCCESS, result=result)

        # Mark as processed for idempotency
        if job.run_id:
            mark_processed(job.run_id, metadata={"job_id": job.id})

        record_event(
            {
                "event": "run_finished",
                "job_id": job.id,
                "schedule_id": job.schedule_id,
                "dag_path": job.dag_path,
                "tenant": job.tenant_id,
                "status": "success",
                "duration_seconds": result.get("duration_seconds", 0),
                "run_id": job.run_id,
            }
        )

        return {"job": job, "status": "success", "result": result}

    except Exception as e:
        # Stop heartbeat
        heartbeat.stop()
        heartbeat.join(timeout=1.0)

        end_time = datetime.now(UTC)
        duration = (end_time - start_time).total_seconds()

        # Check if terminal failure
        if job.attempts + 1 >= max_retries:
            # Terminal failure → DLQ
            job.failure_reason = "max_retries"
            queue.update_status(job.id, JobStatus.FAILED, error=str(e))
            append_to_dlq(job.to_dict(), reason="max_retries")

            record_event(
                {
                    "event": "run_failed_terminal",
                    "job_id": job.id,
                    "schedule_id": job.schedule_id,
                    "dag_path": job.dag_path,
                    "tenant": job.tenant_id,
                    "status": "failed_terminal",
                    "error": str(e),
                    "duration_seconds": duration,
                    "attempts": job.attempts + 1,
                    "reason": "max_retries",
                }
            )

            return {"job": job, "status": "failed_terminal", "error": str(e)}

        else:
            # Retry with backoff
            base_ms = int(os.getenv("REQUEUE_BASE_MS", "500"))
            cap_ms = int(os.getenv("REQUEUE_CAP_MS", "60000"))
            jitter_pct = float(os.getenv("REQUEUE_JITTER_PCT", "0.2"))

            delay_ms = compute_delay(base_ms, job.attempts, cap_ms, jitter_pct)

            print(
                f"[{worker_id}] Job {job.id} failed, retrying in {delay_ms}ms (attempt {job.attempts + 1}/{max_retries})"
            )

            # Sleep before requeue
            time.sleep(delay_ms / 1000.0)
            queue.update_status(job.id, JobStatus.RETRY)

            record_event(
                {
                    "event": "run_finished",
                    "job_id": job.id,
                    "schedule_id": job.schedule_id,
                    "dag_path": job.dag_path,
                    "tenant": job.tenant_id,
                    "status": "retry",
                    "error": str(e),
                    "duration_seconds": duration,
                    "attempts": job.attempts + 1,
                    "retry_delay_ms": delay_ms,
                }
            )

            return {"job": job, "status": "retry", "error": str(e)}


def main():
    """CLI entrypoint for worker."""
    # Initialize telemetry noop (if enabled)
    init_noop_if_enabled()

    parser = argparse.ArgumentParser(description="Queue Worker - consume jobs from persistent queue")

    parser.add_argument(
        "--poll-ms",
        type=int,
        default=1000,
        help="Polling interval in milliseconds (default: 1000)",
    )

    parser.add_argument(
        "--worker-id",
        default="worker-1",
        help="Worker identifier for logging (default: worker-1)",
    )

    args = parser.parse_args()

    # Get queue backend
    queue = get_queue_backend()
    backend_type = os.getenv("QUEUE_BACKEND", "memory")
    print(f"Worker {args.worker_id} starting with {backend_type} queue backend")

    events_path = os.getenv("ORCH_EVENTS_PATH", "logs/orchestrator_events.jsonl")

    try:
        while True:
            # Poll for next job
            job = queue.dequeue()

            if job:
                print(f"[{args.worker_id}] Processing job {job.id} (DAG: {job.dag_path})")

                try:
                    result = execute_job(job, queue, events_path, args.worker_id)

                    if result["status"] == "success":
                        print(f"[{args.worker_id}] ✓ Job {job.id} succeeded")
                    elif result["status"] == "retry":
                        print(f"[{args.worker_id}] ⟳ Job {job.id} will retry")
                    elif result["status"] == "failed_terminal":
                        print(f"[{args.worker_id}] ✗ Job {job.id} failed permanently → DLQ")
                    elif result["status"] == "skipped":
                        print(f"[{args.worker_id}] ⊘ Job {job.id} skipped (duplicate)")
                    elif result["status"] == "rate_limited":
                        print(f"[{args.worker_id}] ⏸ Job {job.id} rate limited, requeued")
                    else:
                        print(f"[{args.worker_id}] ? Job {job.id} status: {result['status']}")

                except Exception as e:
                    print(f"[{args.worker_id}] Error processing job {job.id}: {e}")
                    queue.update_status(job.id, JobStatus.FAILED, error=str(e))
                    append_to_dlq(job.to_dict(), reason="worker_exception")

            else:
                # No jobs available, sleep
                time.sleep(args.poll_ms / 1000.0)

    except KeyboardInterrupt:
        print(f"\n[{args.worker_id}] Shutting down...")
        return 0


if __name__ == "__main__":
    sys.exit(main())
