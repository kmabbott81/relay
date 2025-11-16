"""Job telemetry metrics - Sprint 58 Slice 6.

Prometheus metrics for job execution tracking:
- relay_jobs_total: counter by status (success/failed)
- relay_jobs_per_provider_total: counter by provider + status (bounded cardinality)
- relay_job_latency_seconds: histogram of job duration by provider (bounded)
"""

import re

from prometheus_client import Counter, Histogram

# Counters
relay_jobs_total = Counter(
    "relay_jobs_total",
    "Total jobs completed",
    labelnames=["status"],
)

relay_jobs_per_provider_total = Counter(
    "relay_jobs_per_provider_total",
    "Total jobs per provider (bounded cardinality)",
    labelnames=["provider", "status"],
)

# Histogram (10 buckets: 0.01s to 100s)
relay_job_latency_seconds = Histogram(
    "relay_job_latency_seconds",
    "Job execution latency in seconds by provider (bounded cardinality)",
    labelnames=["provider"],
    buckets=(0.01, 0.05, 0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 25.0, 100.0),
)


def inc_job(status: str) -> None:
    """Increment total job counter.

    Args:
        status: 'success' or 'failed'
    """
    relay_jobs_total.labels(status=status).inc()


def _provider_from_action_id(action_id: str) -> str:
    """Extract provider from action ID (bounded cardinality).

    Args:
        action_id: Canonical action ID (provider.action format)

    Returns:
        Provider name (first component before dot)

    Raises:
        ValueError: If action_id format is invalid
    """
    if not action_id or "." not in action_id:
        raise ValueError(f"Invalid action_id format: {action_id}")

    provider = action_id.split(".")[0]

    # Validate provider matches expected pattern [a-z0-9_]+
    if not re.match(r"^[a-z][a-z0-9_]*$", provider):
        raise ValueError(f"Invalid provider in action_id: {provider}")

    return provider


def inc_job_by_provider(provider: str, status: str) -> None:
    """Increment per-provider job counter.

    Args:
        provider: Provider name (bounded label)
        status: 'success' or 'failed'
    """
    relay_jobs_per_provider_total.labels(provider=provider, status=status).inc()


def observe_job_latency(provider: str, seconds: float) -> None:
    """Record job latency histogram by provider.

    Args:
        provider: Provider name (bounded label)
        seconds: Execution time in seconds (non-negative)
    """
    relay_job_latency_seconds.labels(provider=provider).observe(seconds)
