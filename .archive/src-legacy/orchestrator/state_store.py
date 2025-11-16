"""
JSONL State Store for Sprint 27B

Append-only JSONL storage for DAG run metadata and scheduler events.
Simple, fast, and easy to query with standard tools.
"""

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def get_state_store_path() -> Path:
    """
    Get the path to the state store file.

    Returns:
        Path: Path to logs/orchestrator_state.jsonl
    """
    path_str = os.getenv("STATE_STORE_PATH", "logs/orchestrator_state.jsonl")
    path = Path(path_str)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def record_event(event: dict[str, Any], path: str | None = None) -> None:
    """
    Append an event to the state store.

    Args:
        event: Event dictionary to record
        path: Optional path override (defaults to STATE_STORE_PATH)
    """
    if path is None:
        store_path = get_state_store_path()
    else:
        store_path = Path(path)
        store_path.parent.mkdir(parents=True, exist_ok=True)

    # Add timestamp if not present
    if "timestamp" not in event:
        event["timestamp"] = datetime.now(UTC).isoformat()

    try:
        with open(store_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(event) + "\n")
    except Exception as e:
        # Don't fail the operation if logging fails
        print(f"Warning: Failed to record event: {e}")


def last_runs(limit: int = 20, path: str | None = None) -> list[dict[str, Any]]:
    """
    Read the last N events from the state store.

    Args:
        limit: Maximum number of events to return
        path: Optional path override

    Returns:
        List of event dictionaries (most recent first)
    """
    if path is None:
        store_path = get_state_store_path()
    else:
        store_path = Path(path)

    if not store_path.exists():
        return []

    events = []

    try:
        with open(store_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        event = json.loads(line)
                        events.append(event)
                    except json.JSONDecodeError:
                        pass  # Skip corrupted lines

        # Return most recent events first
        return events[-limit:][::-1]

    except Exception as e:
        print(f"Warning: Failed to read state store: {e}")
        return []


def index_by(field: str, limit: int = 100, path: str | None = None) -> dict[str, list[dict[str, Any]]]:
    """
    Index recent events by a specific field.

    Args:
        field: Field name to index by
        limit: Maximum number of events to process
        path: Optional path override

    Returns:
        Dictionary mapping field values to lists of events
    """
    if path is None:
        store_path = get_state_store_path()
    else:
        store_path = Path(path)

    if not store_path.exists():
        return {}

    events = []

    try:
        with open(store_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        event = json.loads(line)
                        events.append(event)
                    except json.JSONDecodeError:
                        pass

        # Take last N events
        recent = events[-limit:]

        # Index by field
        index: dict[str, list[dict[str, Any]]] = {}
        for event in recent:
            key = event.get(field)
            if key:
                if key not in index:
                    index[key] = []
                index[key].append(event)

        return index

    except Exception as e:
        print(f"Warning: Failed to index state store: {e}")
        return {}
