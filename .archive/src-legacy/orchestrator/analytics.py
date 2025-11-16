"""
Analytics Helpers for Orchestrator Observability (Sprint 27C)

Pure Python functions for parsing and aggregating orchestrator JSONL logs.
No UI/Streamlit dependencies - testable helpers only.
"""

import json
import os
import statistics
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any


def get_events_path() -> Path:
    """Get path to orchestrator events log."""
    return Path(os.getenv("ORCH_EVENTS_PATH", "logs/orchestrator_events.jsonl"))


def get_state_path() -> Path:
    """Get path to state store log."""
    return Path(os.getenv("STATE_STORE_PATH", "logs/orchestrator_state.jsonl"))


def load_events(path: str | Path, limit: int = 5000) -> list[dict[str, Any]]:
    """
    Load events from JSONL file, skipping corrupted lines.

    Args:
        path: Path to JSONL file
        limit: Maximum number of events to load (from end)

    Returns:
        List of event dictionaries (most recent first)
    """
    path = Path(path)
    if not path.exists():
        return []

    events = []
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        events.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass  # Skip corrupted lines
    except Exception:
        return []

    # Return last N events, most recent first
    return events[-limit:][::-1]


def summarize_tasks(events: list[dict[str, Any]], window_hours: int = 24) -> dict[str, Any]:
    """
    Summarize task execution stats.

    Args:
        events: List of orchestrator events
        window_hours: Time window for recent stats

    Returns:
        Dict with totals and recent stats
    """
    cutoff = datetime.now(UTC) - timedelta(hours=window_hours)
    cutoff_iso = cutoff.isoformat()

    tasks_started = 0
    tasks_ok = 0
    tasks_fail = 0
    tasks_retry = 0
    durations = []

    recent_started = 0
    recent_ok = 0
    recent_fail = 0
    recent_durations = []

    for event in events:
        event_type = event.get("event")
        timestamp = event.get("timestamp", "")

        if event_type == "task_start":
            tasks_started += 1
            if timestamp >= cutoff_iso:
                recent_started += 1

        elif event_type == "task_ok":
            tasks_ok += 1
            if timestamp >= cutoff_iso:
                recent_ok += 1

        elif event_type == "task_fail":
            tasks_fail += 1
            if timestamp >= cutoff_iso:
                recent_fail += 1

        elif event_type == "task_retry":
            tasks_retry += 1

    # Calculate p95 duration if we have duration data
    # Note: Duration tracking would need to be added to runner events
    # For now, return placeholder
    avg_duration = statistics.mean(durations) if durations else 0
    p95_duration = statistics.quantiles(durations, n=20)[18] if len(durations) >= 20 else avg_duration

    recent_avg = statistics.mean(recent_durations) if recent_durations else 0
    recent_p95 = statistics.quantiles(recent_durations, n=20)[18] if len(recent_durations) >= 20 else recent_avg

    return {
        "all_time": {
            "tasks_started": tasks_started,
            "tasks_ok": tasks_ok,
            "tasks_fail": tasks_fail,
            "tasks_retry": tasks_retry,
            "avg_duration": avg_duration,
            "p95_duration": p95_duration,
        },
        f"last_{window_hours}h": {
            "tasks_started": recent_started,
            "tasks_ok": recent_ok,
            "tasks_fail": recent_fail,
            "avg_duration": recent_avg,
            "p95_duration": recent_p95,
            "error_rate": (recent_fail / recent_started if recent_started > 0 else 0.0),
        },
    }


def summarize_dags(events: list[dict[str, Any]], limit: int = 20) -> list[dict[str, Any]]:
    """
    Summarize recent DAG runs.

    Args:
        events: List of orchestrator events
        limit: Maximum number of DAG runs to return

    Returns:
        List of DAG run summaries (most recent first)
    """
    dag_runs = {}

    for event in events:
        event_type = event.get("event")
        dag_name = event.get("dag_name")

        if not dag_name:
            continue

        if event_type == "dag_start":
            if dag_name not in dag_runs:
                dag_runs[dag_name] = {
                    "dag_name": dag_name,
                    "status": "running",
                    "start": event.get("timestamp", ""),
                    "tasks_ok": 0,
                    "tasks_fail": 0,
                }

        elif event_type == "task_ok":
            if dag_name in dag_runs:
                dag_runs[dag_name]["tasks_ok"] += 1

        elif event_type == "task_fail":
            if dag_name in dag_runs:
                dag_runs[dag_name]["tasks_fail"] += 1

        elif event_type == "dag_done":
            if dag_name in dag_runs:
                dag_runs[dag_name]["status"] = "completed"
                dag_runs[dag_name]["duration"] = event.get("duration_seconds", 0)
                dag_runs[dag_name]["end"] = event.get("timestamp", "")

    # Convert to list and sort by start time
    runs_list = list(dag_runs.values())
    runs_list.sort(key=lambda x: x.get("start", ""), reverse=True)

    return runs_list[:limit]


def summarize_schedules(state_events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Summarize schedule status and recent runs.

    Args:
        state_events: List of state store events

    Returns:
        List of schedule summaries
    """
    schedules = {}

    for event in state_events:
        event_type = event.get("event")
        schedule_id = event.get("schedule_id")

        if not schedule_id:
            continue

        if schedule_id not in schedules:
            schedules[schedule_id] = {
                "schedule_id": schedule_id,
                "last_run": None,
                "last_status": None,
                "enqueued_count": 0,
                "started_count": 0,
                "finished_count": 0,
                "success_count": 0,
                "failed_count": 0,
            }

        if event_type == "schedule_enqueued":
            schedules[schedule_id]["enqueued_count"] += 1

        elif event_type == "run_started":
            schedules[schedule_id]["started_count"] += 1
            schedules[schedule_id]["last_run"] = event.get("timestamp", "")

        elif event_type == "run_finished":
            schedules[schedule_id]["finished_count"] += 1
            status = event.get("status")
            schedules[schedule_id]["last_status"] = status

            if status == "success":
                schedules[schedule_id]["success_count"] += 1
            elif status == "failed":
                schedules[schedule_id]["failed_count"] += 1

    return list(schedules.values())


def per_tenant_load(events: list[dict[str, Any]], window_hours: int = 24) -> list[dict[str, Any]]:
    """
    Calculate per-tenant load statistics.

    Args:
        events: List of orchestrator events
        window_hours: Time window for recent stats

    Returns:
        List of per-tenant summaries
    """
    cutoff = datetime.now(UTC) - timedelta(hours=window_hours)
    cutoff_iso = cutoff.isoformat()

    tenants = {}

    for event in events:
        timestamp = event.get("timestamp", "")
        if timestamp < cutoff_iso:
            continue

        tenant = event.get("tenant")
        if not tenant:
            continue

        if tenant not in tenants:
            tenants[tenant] = {
                "tenant": tenant,
                "runs": 0,
                "tasks": 0,
                "errors": 0,
                "durations": [],
            }

        event_type = event.get("event")

        if event_type == "dag_start":
            tenants[tenant]["runs"] += 1

        elif event_type in ("task_ok", "task_fail"):
            tenants[tenant]["tasks"] += 1
            if event_type == "task_fail":
                tenants[tenant]["errors"] += 1

    # Calculate final stats
    result = []
    for tenant_id, data in tenants.items():
        avg_latency = statistics.mean(data["durations"]) if data["durations"] else 0.0
        error_rate = data["errors"] / data["tasks"] if data["tasks"] > 0 else 0.0

        result.append(
            {
                "tenant": tenant_id,
                "runs": data["runs"],
                "tasks": data["tasks"],
                "avg_latency": avg_latency,
                "error_rate": error_rate,
            }
        )

    # Sort by run count descending
    result.sort(key=lambda x: x["runs"], reverse=True)

    return result
