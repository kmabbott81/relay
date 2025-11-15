"""
Dead Letter Queue (DLQ) - Sprint 29

Append-only JSONL storage for permanently failed jobs.
Supports list and replay operations.
"""

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def get_dlq_path() -> Path:
    """Get DLQ file path from environment."""
    return Path(os.getenv("DLQ_PATH", "logs/dlq.jsonl"))


def append_to_dlq(job_dict: dict[str, Any], reason: str) -> None:
    """
    Append failed job to DLQ.

    Args:
        job_dict: Job data dictionary
        reason: Failure reason (max_retries, rate_limited, invalid)
    """
    dlq_path = get_dlq_path()
    dlq_path.parent.mkdir(parents=True, exist_ok=True)

    entry = {
        "timestamp": datetime.now(UTC).isoformat(),
        "reason": reason,
        "job": job_dict,
    }

    with open(dlq_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def list_dlq(limit: int = 50) -> list[dict[str, Any]]:
    """
    List entries from DLQ.

    Args:
        limit: Maximum number of entries to return (most recent first)

    Returns:
        List of DLQ entries
    """
    dlq_path = get_dlq_path()

    if not dlq_path.exists():
        return []

    entries = []
    try:
        with open(dlq_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass  # Skip corrupted lines
    except Exception:
        return []

    # Return most recent first
    return entries[-limit:][::-1]


def replay_job(job_id: str) -> dict[str, Any] | None:
    """
    Find job in DLQ by ID for replay.

    Args:
        job_id: Job identifier

    Returns:
        Job dict if found, None otherwise
    """
    dlq_path = get_dlq_path()

    if not dlq_path.exists():
        return None

    try:
        with open(dlq_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entry = json.loads(line)
                        job = entry.get("job", {})
                        if job.get("id") == job_id:
                            return job
                    except json.JSONDecodeError:
                        pass
    except Exception:
        return None

    return None


def main():
    """CLI for DLQ operations."""
    parser = argparse.ArgumentParser(description="Dead Letter Queue CLI")

    subparsers = parser.add_subparsers(dest="command", help="Command")

    # List command
    list_parser = subparsers.add_parser("list", help="List DLQ entries")
    list_parser.add_argument("--limit", type=int, default=50, help="Max entries to show")

    # Replay command
    replay_parser = subparsers.add_parser("replay", help="Replay job from DLQ")
    replay_parser.add_argument("--id", required=True, help="Job ID to replay")

    args = parser.parse_args()

    if args.command == "list":
        entries = list_dlq(limit=args.limit)

        if not entries:
            print("DLQ is empty")
            return 0

        print(f"DLQ Entries (showing last {len(entries)}):\n")

        for entry in entries:
            timestamp = entry.get("timestamp", "unknown")[:19]
            reason = entry.get("reason", "unknown")
            job = entry.get("job", {})
            job_id = job.get("id", "unknown")[:16]
            dag_path = job.get("dag_path", "unknown")
            tenant = job.get("tenant_id", "unknown")[:15]

            print(f"{timestamp} | {reason:15s} | {job_id}... | {tenant:15s} | {dag_path}")

        return 0

    elif args.command == "replay":
        job = replay_job(args.id)

        if not job:
            print(f"Job {args.id} not found in DLQ")
            return 1

        # Re-enqueue job
        sys.path.insert(0, str(Path(__file__).parent.parent.parent))

        # Import here to avoid circular dependencies
        from relay_ai.queue.persistent_queue import Job  # noqa: E402

        # Reset job for replay
        job["status"] = "pending"
        job["attempts"] = 0
        job["error"] = None
        job["result"] = None
        job["started_at"] = None
        job["finished_at"] = None
        job["enqueued_at"] = datetime.now(UTC).isoformat()

        # Get queue backend
        from relay_ai.orchestrator.scheduler import get_queue_backend  # noqa: E402

        queue = get_queue_backend()
        job_obj = Job.from_dict(job)
        queue.enqueue(job_obj)

        print(f"Job {args.id} replayed successfully")
        return 0

    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
