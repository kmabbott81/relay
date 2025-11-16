"""
Autoscaler Signals (Sprint 29)

Produces scaling metrics from queue state and event history.
Reuses Sprint 24 autoscaler infrastructure.
"""

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any


def compute_queue_signals(queue: Any) -> dict[str, Any]:
    """
    Compute queue-based scaling signals.

    Args:
        queue: Persistent queue instance

    Returns:
        Dict of scaling metrics
    """
    from ..queue.persistent_queue import JobStatus

    pending = queue.count(JobStatus.PENDING)
    running = queue.count(JobStatus.RUNNING)

    # Get oldest pending job
    oldest_age_s = 0.0
    pending_jobs = queue.list_jobs(status=JobStatus.PENDING, limit=1)
    if pending_jobs:
        oldest_job = pending_jobs[0]
        enqueued_at = datetime.fromisoformat(oldest_job.enqueued_at)
        now = datetime.now(UTC)
        oldest_age_s = (now - enqueued_at).total_seconds()

    return {
        "queue_depth": pending,
        "running_count": running,
        "oldest_job_age_s": oldest_age_s,
    }


def compute_retry_rate(events: list[dict[str, Any]], window_minutes: int = 5) -> float:
    """
    Compute retry rate from recent events.

    Args:
        events: List of orchestrator events
        window_minutes: Time window in minutes

    Returns:
        Retry rate (retries per minute)
    """
    cutoff = datetime.now(UTC) - timedelta(minutes=window_minutes)
    cutoff_iso = cutoff.isoformat()

    retry_count = 0
    total_runs = 0

    for event in events:
        timestamp = event.get("timestamp", "")
        if timestamp < cutoff_iso:
            continue

        event_type = event.get("event")
        if event_type == "run_finished":
            total_runs += 1
            if event.get("status") == "retry":
                retry_count += 1

    if window_minutes == 0:
        return 0.0

    return retry_count / window_minutes


def compute_dlq_rate(dlq_path: Path, window_hours: int = 24) -> float:
    """
    Compute DLQ rate from recent entries.

    Args:
        dlq_path: Path to DLQ file
        window_hours: Time window in hours

    Returns:
        DLQ rate (entries per hour)
    """
    if not dlq_path.exists():
        return 0.0

    cutoff = datetime.now(UTC) - timedelta(hours=window_hours)
    cutoff_iso = cutoff.isoformat()

    dlq_count = 0

    try:
        with open(dlq_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entry = json.loads(line)
                        timestamp = entry.get("timestamp", "")
                        if timestamp >= cutoff_iso:
                            dlq_count += 1
                    except json.JSONDecodeError:
                        pass
    except Exception:
        return 0.0

    if window_hours == 0:
        return 0.0

    return dlq_count / window_hours


def export_signals(queue: Any, output_path: str = "logs/scale_signals.json") -> None:
    """
    Export scaling signals to JSON file.

    Args:
        queue: Persistent queue instance
        output_path: Output file path
    """
    from ..orchestrator.analytics import get_events_path, load_events

    # Queue signals
    queue_signals = compute_queue_signals(queue)

    # Event-based signals
    events_path = get_events_path()
    events = load_events(events_path, limit=1000)

    retry_rate = compute_retry_rate(events, window_minutes=5)

    # DLQ signals
    dlq_path = Path(os.getenv("DLQ_PATH", "logs/dlq.jsonl"))
    dlq_rate = compute_dlq_rate(dlq_path, window_hours=24)

    signals = {
        "timestamp": datetime.now(UTC).isoformat(),
        "queue_depth": queue_signals["queue_depth"],
        "running_count": queue_signals["running_count"],
        "oldest_job_age_s": queue_signals["oldest_job_age_s"],
        "retry_rate_5m": retry_rate,
        "dlq_rate_24h": dlq_rate,
    }

    # Write to output
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(signals, f, indent=2)
