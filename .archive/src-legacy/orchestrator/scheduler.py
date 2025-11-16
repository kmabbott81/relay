"""
Lightweight Scheduler (Sprint 27B + Sprint 28 update)

Cron-like scheduler for DAG execution with persistent queue backend.
Uses pluggable queue backend (memory/Redis) for durable job storage.
"""

import argparse
import os
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from ..queue.backends.memory import MemoryQueue
from ..queue.persistent_queue import Job, JobStatus, PersistentQueue
from .graph import DAG, Task
from .runner import run_dag
from .state_store import record_event


def parse_cron(expr: str) -> callable:
    """
    Parse minimal cron expression and return matcher function.

    Supports:
    - */n for every n minutes (*/5 = every 5 minutes)
    - * for any value

    Args:
        expr: Cron expression (minute hour day month weekday format)

    Returns:
        Function that takes datetime and returns bool

    Example:
        >>> matcher = parse_cron("*/5 * * * *")
        >>> matcher(datetime(2025, 10, 3, 14, 5))  # minute % 5 == 0
        True
    """
    parts = expr.split()
    if len(parts) != 5:
        raise ValueError(f"Invalid cron expression: {expr} (expected 5 fields)")

    minute, hour, day, month, weekday = parts

    def matches(now: datetime) -> bool:
        # Minute field
        if minute.startswith("*/"):
            interval = int(minute[2:])
            if now.minute % interval != 0:
                return False
        elif minute != "*":
            if now.minute != int(minute):
                return False

        # Hour field
        if hour != "*":
            if now.hour != int(hour):
                return False

        # Day field
        if day != "*":
            if now.day != int(day):
                return False

        # Month field
        if month != "*":
            if now.month != int(month):
                return False

        # Weekday field (0=Monday, 6=Sunday)
        if weekday != "*":
            if now.weekday() != int(weekday):
                return False

        return True

    return matches


def load_schedules(schedules_dir: str) -> list[dict[str, Any]]:
    """
    Load all schedule YAML files from a directory.

    Args:
        schedules_dir: Path to schedules directory

    Returns:
        List of schedule configuration dictionaries
    """
    schedules = []
    schedules_path = Path(schedules_dir)

    if not schedules_path.exists():
        return []

    for yaml_file in schedules_path.glob("*.yaml"):
        try:
            with open(yaml_file, encoding="utf-8") as f:
                config = yaml.safe_load(f)
                if isinstance(config, list):
                    schedules.extend(config)
                elif isinstance(config, dict):
                    schedules.append(config)
        except Exception as e:
            print(f"Warning: Failed to load {yaml_file}: {e}")

    return schedules


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


def tick_once(now: datetime, schedules: list[dict[str, Any]], queue: PersistentQueue, dedup_cache: set) -> int:
    """
    Process one scheduler tick.

    Enqueues jobs for any schedules matching the current time.
    De-duplicates by {schedule_id, minute} to prevent double-enqueue.

    Args:
        now: Current datetime
        schedules: List of schedule configurations
        queue: Persistent queue to enqueue jobs
        dedup_cache: Set of (schedule_id, minute) keys to prevent double-enqueue

    Returns:
        Number of jobs enqueued
    """
    current_minute = now.strftime("%Y-%m-%d %H:%M")
    enqueued_count = 0

    for schedule in schedules:
        if not schedule.get("enabled", True):
            continue

        schedule_id = schedule["id"]
        cron_expr = schedule["cron"]

        try:
            matcher = parse_cron(cron_expr)
            if matcher(now):
                key = (schedule_id, current_minute)
                if key not in dedup_cache:
                    # Create job
                    job = Job(
                        id=str(uuid.uuid4()),
                        dag_path=schedule["dag"],
                        tenant_id=schedule.get("tenant", "local-dev"),
                        schedule_id=schedule_id,
                        status=JobStatus.PENDING,
                        enqueued_at=now.isoformat(),
                        max_retries=schedule.get("max_retries", 0),
                    )

                    # Enqueue
                    queue.enqueue(job)
                    dedup_cache.add(key)
                    enqueued_count += 1

                    record_event(
                        {
                            "event": "schedule_enqueued",
                            "schedule_id": schedule_id,
                            "job_id": job.id,
                            "dag_path": schedule["dag"],
                            "tenant": job.tenant_id,
                            "minute": current_minute,
                        }
                    )

        except Exception as e:
            print(f"Warning: Failed to process schedule {schedule_id}: {e}")

    return enqueued_count


def drain_queue(queue: PersistentQueue, max_parallel: int = 3, max_jobs: int = 100) -> list[dict[str, Any]]:
    """
    Drain the persistent queue by executing pending jobs.

    Launches up to max_parallel concurrent runs using ThreadPoolExecutor.
    Records run_started and run_finished events to state store.
    Updates job status in queue.

    Args:
        queue: Persistent queue to drain
        max_parallel: Maximum concurrent runs
        max_jobs: Maximum number of jobs to drain per call

    Returns:
        List of execution results
    """
    results = []
    events_path = os.getenv("ORCH_EVENTS_PATH", "logs/orchestrator_events.jsonl")

    def execute_job(job: Job) -> dict[str, Any]:
        """Execute a single job."""
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

    # Dequeue jobs
    jobs_to_execute = []
    for _ in range(max_jobs):
        job = queue.dequeue()
        if not job:
            break
        jobs_to_execute.append(job)

    if not jobs_to_execute:
        return []

    # Execute jobs in parallel
    with ThreadPoolExecutor(max_workers=max_parallel) as executor:
        futures = {executor.submit(execute_job, job): job for job in jobs_to_execute}

        for future in as_completed(futures):
            try:
                result = future.result()
                results.append(result)
            except Exception as e:
                job = futures[future]
                print(f"Error executing job {job.id}: {e}")
                queue.update_status(job.id, JobStatus.FAILED, error=str(e))
                results.append({"job": job, "status": "error", "error": str(e)})

    return results


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

            from ..queue.backends.redis import RedisQueue

            return RedisQueue(client, key_prefix="orch:queue")
        except ImportError:
            print("Warning: redis not installed, falling back to memory backend")
            return MemoryQueue()
        except Exception as e:
            print(f"Warning: Failed to connect to Redis ({e}), falling back to memory backend")
            return MemoryQueue()

    # Default to memory backend
    return MemoryQueue()


def main():
    """CLI entrypoint for scheduler."""
    parser = argparse.ArgumentParser(description="DAG Scheduler - cron-like execution for workflows")

    parser.add_argument(
        "--dir",
        default="configs/schedules",
        help="Directory containing schedule YAML files (default: configs/schedules)",
    )

    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument("--once", action="store_true", help="Run single tick then drain queue (CI-safe)")
    mode_group.add_argument("--serve", action="store_true", help="Serve continuously until Ctrl+C")

    args = parser.parse_args()

    # Load schedules
    schedules = load_schedules(args.dir)
    if not schedules:
        print(f"No schedules found in {args.dir}")
        return 1

    print(f"Loaded {len(schedules)} schedule(s) from {args.dir}")

    # Get config
    tick_ms = int(os.getenv("SCHED_TICK_MS", "1000"))
    max_parallel = int(os.getenv("SCHED_MAX_PARALLEL", "3"))
    max_jobs_per_drain = int(os.getenv("SCHED_MAX_JOBS_PER_DRAIN", "100"))

    # Get queue backend
    queue = get_queue_backend()
    backend_type = os.getenv("QUEUE_BACKEND", "memory")
    print(f"Using {backend_type} queue backend")

    # Deduplication cache
    dedup_cache: set = set()

    if args.once:
        # Single tick mode
        print("Running single tick...")
        now = datetime.now(UTC)
        enqueued = tick_once(now, schedules, queue, dedup_cache)
        print(f"Enqueued {enqueued} job(s)")

        if enqueued > 0:
            print("Draining queue...")
            results = drain_queue(queue, max_parallel=max_parallel, max_jobs=max_jobs_per_drain)
            print(f"Completed {len(results)} job(s)")

            # Summary
            success = sum(1 for r in results if r["status"] == "success")
            failed = sum(1 for r in results if r["status"] == "failed")
            retry = sum(1 for r in results if r["status"] == "retry")
            print(f"Success: {success}, Failed: {failed}, Retry: {retry}")

        return 0

    else:
        # Serve mode
        print(f"Serving scheduler (tick={tick_ms}ms, max_parallel={max_parallel})...")
        print("Press Ctrl+C to stop")

        try:
            while True:
                now = datetime.now(UTC)
                enqueued = tick_once(now, schedules, queue, dedup_cache)

                if enqueued > 0:
                    print(f"[{now.strftime('%H:%M:%S')}] Enqueued {enqueued} job(s)")

                # Expire pending checkpoints (Sprint 31)
                try:
                    from .checkpoints import expire_pending

                    expired = expire_pending(now)
                    if expired:
                        print(f"[{now.strftime('%H:%M:%S')}] Expired {len(expired)} checkpoint(s)")
                        # Emit checkpoint_expired events
                        for cp in expired:
                            record_event(
                                {
                                    "event": "checkpoint_expired",
                                    "checkpoint_id": cp["checkpoint_id"],
                                    "dag_run_id": cp["dag_run_id"],
                                    "task_id": cp["task_id"],
                                }
                            )
                except ImportError:
                    pass  # Checkpoints module not available

                # Always try to drain (may have pending jobs from previous ticks)
                pending = queue.count(JobStatus.PENDING)
                if pending > 0:
                    print(f"[{now.strftime('%H:%M:%S')}] Draining {pending} pending job(s)...")
                    drain_queue(queue, max_parallel=max_parallel, max_jobs=max_jobs_per_drain)

                time.sleep(tick_ms / 1000.0)

        except KeyboardInterrupt:
            print("\nShutting down...")
            pending = queue.count(JobStatus.PENDING)
            if pending > 0:
                print(f"Draining final {pending} pending job(s)...")
                drain_queue(queue, max_parallel=max_parallel, max_jobs=max_jobs_per_drain)
            return 0


if __name__ == "__main__":
    sys.exit(main())
