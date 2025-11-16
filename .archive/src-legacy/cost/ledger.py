"""
Cost Ledger (Sprint 30)

Reads and aggregates cost events from Sprint 25 adapter telemetry.
Provides rolling windows, rollups, and sums for budget enforcement.
"""

import json
import os
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any


def get_cost_events_path() -> Path:
    """Get cost events log path."""
    return Path(os.getenv("COST_EVENTS_PATH", "logs/cost_events.jsonl"))


def load_cost_events(path: str | Path | None = None, window_days: int = 31) -> list[dict[str, Any]]:
    """
    Load cost events from JSONL file.

    Args:
        path: Path to cost events file (defaults to COST_EVENTS_PATH)
        window_days: Only load events from last N days

    Returns:
        List of cost event dictionaries
    """
    if path is None:
        path = get_cost_events_path()

    path = Path(path)

    if not path.exists():
        return []

    cutoff = datetime.now(UTC) - timedelta(days=window_days)
    cutoff_iso = cutoff.isoformat()

    events = []

    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        event = json.loads(line)
                        timestamp = event.get("timestamp", "")
                        if timestamp >= cutoff_iso:
                            events.append(event)
                    except json.JSONDecodeError:
                        pass  # Skip corrupted lines
    except Exception:
        return []

    return events


def rollup(events: list[dict[str, Any]], by: tuple[str, ...] = ("tenant",)) -> list[dict[str, Any]]:
    """
    Rollup cost events by specified dimensions.

    Args:
        events: List of cost events
        by: Tuple of fields to group by (tenant, model, day, etc.)

    Returns:
        List of aggregated records
    """
    groups: dict[tuple, dict[str, Any]] = defaultdict(lambda: {"cost": 0.0, "count": 0})

    for event in events:
        # Build group key
        key_parts = []
        for field in by:
            if field == "day":
                # Extract day from timestamp
                timestamp = event.get("timestamp", "")
                day = timestamp[:10] if timestamp else "unknown"
                key_parts.append(day)
            else:
                key_parts.append(event.get(field, "unknown"))

        key = tuple(key_parts)

        # Aggregate
        groups[key]["cost"] += event.get("cost_estimate", 0.0)
        groups[key]["count"] += 1

    # Convert to list
    result = []
    for key, agg in groups.items():
        record = dict(zip(by, key))
        record["cost"] = agg["cost"]
        record["count"] = agg["count"]
        result.append(record)

    # Sort by cost descending
    result.sort(key=lambda x: x["cost"], reverse=True)

    return result


def window_sum(
    events: list[dict[str, Any]], tenant: str | None = None, team_id: str | None = None, days: int = 1
) -> float:
    """
    Sum costs in rolling window.

    Args:
        events: List of cost events
        tenant: Filter by tenant (None for global)
        team_id: Filter by team (Sprint 34A)
        days: Window size in days (1=today, 30=last 30 days)

    Returns:
        Total cost in window
    """
    cutoff = datetime.now(UTC) - timedelta(days=days)
    cutoff_iso = cutoff.isoformat()

    total = 0.0

    for event in events:
        timestamp = event.get("timestamp", "")
        if timestamp < cutoff_iso:
            continue

        # Filter by team if specified (Sprint 34A)
        if team_id and event.get("team_id") != team_id:
            continue

        # Filter by tenant if specified
        if tenant and event.get("tenant") != tenant:
            continue

        total += event.get("cost_estimate", 0.0)

    return total
