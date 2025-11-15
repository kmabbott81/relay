"""AI Orchestrator v0.1 Worker - Background job processor.

Sprint 55 Week 3: Worker daemon for async action execution.

Usage:
    python scripts/worker_actions.py
"""

import asyncio
import os
import sys
import time
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


async def process_job(job_data: dict) -> None:
    """Process a single job.

    Args:
        job_data: Job data from queue
    """
    from relay_ai.actions.runner import run_action
    from relay_ai.queue.simple_queue import SimpleQueue
    from relay_ai.telemetry.prom import ai_job_latency_seconds, ai_jobs_total

    queue = SimpleQueue()
    job_id = job_data["job_id"]

    print(f"[INFO] Processing job {job_id}: {job_data['action_provider']}.{job_data['action_name']}")

    # Mark as running
    queue.update_status(job_id, "running")

    # Execute action
    start = time.perf_counter()
    try:
        result = await run_action(
            action_provider=job_data["action_provider"],
            action_name=job_data["action_name"],
            params=job_data["params"],
            workspace_id=job_data["workspace_id"],
            actor_id=job_data["actor_id"],
        )

        # Mark as completed
        queue.update_status(
            job_id,
            "completed",
            result=result,
        )

        # Record metrics
        duration = time.perf_counter() - start
        ai_job_latency_seconds.observe(duration)
        ai_jobs_total.labels(status="completed").inc()

        print(f"[OK] Job {job_id} completed in {duration:.2f}s")

    except Exception as e:
        # Mark as error
        queue.update_status(
            job_id,
            "error",
            error=str(e),
        )

        # Record metrics
        duration = time.perf_counter() - start
        ai_job_latency_seconds.observe(duration)
        ai_jobs_total.labels(status="error").inc()

        print(f"[ERROR] Job {job_id} failed: {e}")


async def worker_loop():
    """Main worker loop."""
    from relay_ai.queue.simple_queue import SimpleQueue
    from relay_ai.telemetry.prom import ai_queue_depth

    print("[INFO] AI Orchestrator worker starting...")
    print(f"[INFO] REDIS_URL: {os.getenv('REDIS_URL', 'NOT SET')}")

    # Initialize queue
    try:
        queue = SimpleQueue()
        print("[OK] Connected to Redis queue")
    except Exception as e:
        print(f"[ERROR] Failed to connect to queue: {e}")
        sys.exit(1)

    # Worker loop
    while True:
        try:
            # Update queue depth metric
            depth = queue.get_queue_depth()
            ai_queue_depth.set(depth)

            if depth > 0:
                print(f"[INFO] Queue depth: {depth}")

            # Dequeue next job (blocks for 1 second)
            job_data = queue.dequeue()

            if job_data:
                await process_job(job_data)
            else:
                # No jobs - sleep briefly
                await asyncio.sleep(0.1)

        except KeyboardInterrupt:
            print("\n[INFO] Worker shutting down...")
            break
        except Exception as e:
            print(f"[ERROR] Worker error: {e}")
            await asyncio.sleep(1)


if __name__ == "__main__":
    # Initialize telemetry
    from relay_ai.telemetry import init_telemetry

    init_telemetry()
    print("[OK] Telemetry initialized")

    # Run worker
    asyncio.run(worker_loop())
