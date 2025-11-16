"""
Idempotency Store (Sprint 29)

JSONL-based store for tracking completed run_ids with TTL window.
Prevents duplicate DAG executions within configurable time window.
"""

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any


def get_idemp_store_path() -> Path:
    """Get idempotency store path from environment."""
    return Path(os.getenv("IDEMP_STORE_PATH", "logs/idempotency.jsonl"))


def get_idemp_ttl_hours() -> int:
    """Get idempotency TTL in hours."""
    return int(os.getenv("IDEMP_TTL_HOURS", "24"))


def already_processed(run_id: str) -> bool:
    """
    Check if run_id has been processed within TTL window.

    Args:
        run_id: Unique run identifier

    Returns:
        True if run was processed within TTL window
    """
    if not run_id:
        return False

    store_path = get_idemp_store_path()

    if not store_path.exists():
        return False

    ttl_hours = get_idemp_ttl_hours()
    cutoff = datetime.now(UTC) - timedelta(hours=ttl_hours)
    cutoff_iso = cutoff.isoformat()

    try:
        with open(store_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entry = json.loads(line)
                        if entry.get("run_id") == run_id:
                            timestamp = entry.get("timestamp", "")
                            if timestamp >= cutoff_iso:
                                return True
                    except json.JSONDecodeError:
                        pass  # Skip corrupted lines
    except Exception:
        return False

    return False


def mark_processed(run_id: str, metadata: dict[str, Any] | None = None) -> None:
    """
    Mark run_id as processed.

    Args:
        run_id: Unique run identifier
        metadata: Optional metadata to store with entry
    """
    if not run_id:
        return

    store_path = get_idemp_store_path()
    store_path.parent.mkdir(parents=True, exist_ok=True)

    entry = {
        "timestamp": datetime.now(UTC).isoformat(),
        "run_id": run_id,
        "metadata": metadata or {},
    }

    with open(store_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def purge_expired() -> int:
    """
    Remove entries older than TTL.

    Returns:
        Number of entries removed
    """
    store_path = get_idemp_store_path()

    if not store_path.exists():
        return 0

    ttl_hours = get_idemp_ttl_hours()
    cutoff = datetime.now(UTC) - timedelta(hours=ttl_hours)
    cutoff_iso = cutoff.isoformat()

    all_entries = []
    valid_entries = []

    try:
        with open(store_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entry = json.loads(line)
                        all_entries.append(entry)
                        timestamp = entry.get("timestamp", "")
                        if timestamp >= cutoff_iso:
                            valid_entries.append(entry)
                    except json.JSONDecodeError:
                        pass  # Skip corrupted lines
    except Exception:
        return 0

    removed_count = len(all_entries) - len(valid_entries)

    # Rewrite file with valid entries only
    try:
        with open(store_path, "w", encoding="utf-8") as f:
            for entry in valid_entries:
                f.write(json.dumps(entry) + "\n")
    except Exception:
        return 0

    return removed_count
