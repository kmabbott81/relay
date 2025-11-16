"""
Queue Worker (Sprint 28)

Standalone worker process for consuming jobs from persistent queue.
Enables horizontal scaling by running multiple workers against shared queue.
"""

import argparse
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import yaml

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# pylint: disable=wrong-import-position
from relay_ai.orchestrator.graph import DAG, Task  # noqa: E402
from relay_ai.orchestrator.runner import run_dag  # noqa: E402
from relay_ai.orchestrator.state_store import record_event  # noqa: E402
from relay_ai.queue.backends.memory import MemoryQueue  # noqa: E402
from relay_ai.queue.persistent_queue import Job, JobStatus, PersistentQueue  # noqa: E402


def get_queue_backend() -> PersistentQueue:
    """
    Get queue backend from environment config.

    Returns:
        Queue backend instance (memory or Redis)
    """
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

    # Default to memory backend
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


def execute_job(job: Job, queue: PersistentQueue, events_path: str) -> dict:
    """
    Execute a single job.

    Args:
        job: Job to execute
        queue: Queue to update status
        events_path: Path to events log

    Returns:
        Result dictionary
    """
    start_time = datetime.now(UTC)

    record_event(
        {
            "event": "run_started",
            "job_id": job.id,
            "schedule_id": job.schedule_id,
            "dag_path": job.dag_path,
            "tenant": job.tenant_id,
        }
    )

    try:
        dag = load_dag_from_yaml(job.dag_path)
        result = run_dag(dag, tenant=job.tenant_id, dry_run=False, events_path=events_path)

        # Update job status
        queue.update_status(job.id, JobStatus.SUCCESS, result=result)

        record_event(
            {
                "event": "run_finished",
                "job_id": job.id,
                "schedule_id": job.schedule_id,
                "dag_path": job.dag_path,
                "tenant": job.tenant_id,
                "status": "success",
                "duration_seconds": result.get("duration_seconds", 0),
            }
        )

        return {"job": job, "status": "success", "result": result}

    except Exception as e:
        end_time = datetime.now(UTC)
        duration = (end_time - start_time).total_seconds()

        # Check if should retry
        if job.attempts < job.max_retries:
            queue.update_status(job.id, JobStatus.RETRY)
            status = "retry"
        else:
            queue.update_status(job.id, JobStatus.FAILED, error=str(e))
            status = "failed"

        record_event(
            {
                "event": "run_finished",
                "job_id": job.id,
                "schedule_id": job.schedule_id,
                "dag_path": job.dag_path,
                "tenant": job.tenant_id,
                "status": status,
                "error": str(e),
                "duration_seconds": duration,
                "attempts": job.attempts + 1,
            }
        )

        return {"job": job, "status": status, "error": str(e)}


def main():
    """CLI entrypoint for worker."""
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
                    result = execute_job(job, queue, events_path)

                    if result["status"] == "success":
                        print(f"[{args.worker_id}] ✓ Job {job.id} succeeded")
                    elif result["status"] == "retry":
                        print(f"[{args.worker_id}] ⟳ Job {job.id} retrying (attempt {job.attempts + 1})")
                    else:
                        print(f"[{args.worker_id}] ✗ Job {job.id} failed: {result.get('error', 'Unknown error')}")

                except Exception as e:
                    print(f"[{args.worker_id}] Error processing job {job.id}: {e}")
                    queue.update_status(job.id, JobStatus.FAILED, error=str(e))

            else:
                # No jobs available, sleep
                time.sleep(args.poll_ms / 1000.0)

    except KeyboardInterrupt:
        print(f"\n[{args.worker_id}] Shutting down...")
        return 0


if __name__ == "__main__":
    sys.exit(main())
