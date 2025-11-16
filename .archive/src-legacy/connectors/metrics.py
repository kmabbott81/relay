"""Connector metrics and health monitoring.

Records connector operations and computes health status based on thresholds.
"""

import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional


def get_metrics_path() -> Path:
    """Get metrics JSONL path from environment."""
    return Path(os.environ.get("CONNECTOR_METRICS_PATH", "logs/connectors/metrics.jsonl"))


def record_call(
    connector_id: str,
    operation: str,
    status: str,
    duration_ms: float,
    error: Optional[str] = None,
) -> None:
    """Record connector operation metrics.

    Args:
        connector_id: Connector identifier
        operation: Operation name (connect, list_resources, etc.)
        status: Result status (success, error, denied)
        duration_ms: Operation duration in milliseconds
        error: Error message if failed
    """
    metrics_path = get_metrics_path()
    metrics_path.parent.mkdir(parents=True, exist_ok=True)

    # Clamp negative durations to 0
    duration_ms = max(0.0, duration_ms)

    entry = {
        "connector_id": connector_id,
        "operation": operation,
        "status": status,
        "duration_ms": duration_ms,
        "error": error,
        "timestamp": datetime.now().isoformat(),
    }

    with open(metrics_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def summarize(connector_id: str, window_minutes: int = 60) -> dict:
    """Summarize connector metrics over time window.

    Args:
        connector_id: Connector to summarize
        window_minutes: Time window in minutes (default: 60)

    Returns:
        Dict with total_calls, error_rate, p50_ms, p95_ms, p99_ms
    """
    metrics_path = get_metrics_path()
    if not metrics_path.exists():
        return {
            "total_calls": 0,
            "error_rate": 0.0,
            "p50_ms": 0.0,
            "p95_ms": 0.0,
            "p99_ms": 0.0,
        }

    cutoff = datetime.now() - timedelta(minutes=window_minutes)
    durations = []
    errors = 0
    total = 0

    try:
        with open(metrics_path, encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue

                try:
                    entry = json.loads(line.strip())
                except json.JSONDecodeError:
                    # Skip corrupt lines
                    continue

                if entry.get("connector_id") != connector_id:
                    continue

                # Parse timestamp with error handling
                try:
                    timestamp = datetime.fromisoformat(entry["timestamp"])
                except (ValueError, KeyError):
                    continue

                if timestamp < cutoff:
                    continue

                total += 1

                # Clamp duration
                duration = max(0.0, entry.get("duration_ms", 0.0))
                durations.append(duration)

                if entry.get("status") == "error":
                    errors += 1
    except OSError:
        # File read error
        pass

    if total == 0:
        return {
            "total_calls": 0,
            "error_rate": 0.0,
            "p50_ms": 0.0,
            "p95_ms": 0.0,
            "p99_ms": 0.0,
        }

    durations.sort()
    error_rate = errors / total

    def percentile(p: float) -> float:
        idx = int(len(durations) * p)
        return durations[min(idx, len(durations) - 1)]

    return {
        "total_calls": total,
        "error_rate": error_rate,
        "p50_ms": percentile(0.50),
        "p95_ms": percentile(0.95),
        "p99_ms": percentile(0.99),
    }


def health_status(connector_id: str, window_minutes: int = 60) -> dict:
    """Compute health status based on thresholds.

    Args:
        connector_id: Connector to check
        window_minutes: Time window for metrics

    Returns:
        Dict with status (healthy/degraded/down), reason, metrics
    """
    p95_threshold_ms = float(os.environ.get("CONNECTOR_HEALTH_P95_MS", "2000"))
    error_rate_threshold = float(os.environ.get("CONNECTOR_HEALTH_ERROR_RATE", "0.10"))

    metrics = summarize(connector_id, window_minutes)

    if metrics["total_calls"] == 0:
        return {
            "status": "unknown",
            "reason": "No metrics available",
            "metrics": metrics,
        }

    # Check thresholds
    issues = []

    if metrics["p95_ms"] > p95_threshold_ms:
        issues.append(f"p95 latency {metrics['p95_ms']:.0f}ms exceeds {p95_threshold_ms:.0f}ms")

    if metrics["error_rate"] > error_rate_threshold:
        issues.append(f"error rate {metrics['error_rate']:.1%} exceeds {error_rate_threshold:.1%}")

    if not issues:
        return {
            "status": "healthy",
            "reason": "All metrics within thresholds",
            "metrics": metrics,
        }
    elif metrics["error_rate"] > 0.5:
        return {
            "status": "down",
            "reason": "; ".join(issues),
            "metrics": metrics,
        }
    else:
        return {
            "status": "degraded",
            "reason": "; ".join(issues),
            "metrics": metrics,
        }
