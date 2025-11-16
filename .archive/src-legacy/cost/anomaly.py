"""
Cost Anomaly Detection (Sprint 30)

Simple statistical baseline: flag if today's spend > ANOMALY_SIGMA std devs over 7-day mean.
Deterministic and testable.
"""

import os
import statistics
from datetime import UTC, datetime, timedelta
from typing import Any

from .enforcer import emit_governance_event
from .ledger import load_cost_events


def compute_baseline(events: list[dict[str, Any]], tenant: str, days: int = 7) -> dict[str, float]:
    """
    Compute baseline statistics for tenant.

    Args:
        events: List of cost events
        tenant: Tenant identifier
        days: Number of days for baseline

    Returns:
        Dict with mean, std_dev, min, max
    """
    cutoff = datetime.now(UTC) - timedelta(days=days)
    cutoff_iso = cutoff.isoformat()

    # Group by day
    daily_costs: dict[str, float] = {}

    for event in events:
        timestamp = event.get("timestamp", "")
        if timestamp < cutoff_iso:
            continue

        if event.get("tenant") != tenant:
            continue

        day = timestamp[:10]
        daily_costs[day] = daily_costs.get(day, 0.0) + event.get("cost_estimate", 0.0)

    if not daily_costs:
        return {"mean": 0.0, "std_dev": 0.0, "min": 0.0, "max": 0.0, "count": 0}

    values = list(daily_costs.values())

    return {
        "mean": statistics.mean(values),
        "std_dev": statistics.stdev(values) if len(values) > 1 else 0.0,
        "min": min(values),
        "max": max(values),
        "count": len(values),
    }


def detect_anomalies(tenant: str | None = None) -> list[dict[str, Any]]:
    """
    Detect cost anomalies for tenant(s).

    Args:
        tenant: Specific tenant or None for all tenants

    Returns:
        List of anomaly records
    """
    sigma_threshold = float(os.getenv("ANOMALY_SIGMA", "3.0"))
    min_dollars = float(os.getenv("ANOMALY_MIN_DOLLARS", "3.0"))
    min_events = int(os.getenv("ANOMALY_MIN_EVENTS", "10"))

    events = load_cost_events(window_days=31)

    # Get unique tenants
    if tenant:
        tenants = [tenant]
    else:
        tenants = list({e.get("tenant") for e in events if e.get("tenant")})

    anomalies = []

    for tenant_id in tenants:
        # Compute baseline (last 7 days excluding today)
        baseline = compute_baseline(events, tenant_id, days=7)

        if baseline["count"] < min_events:
            continue  # Not enough data

        # Today's spend
        today = datetime.now(UTC).date().isoformat()
        today_spend = sum(
            e.get("cost_estimate", 0.0)
            for e in events
            if e.get("tenant") == tenant_id and e.get("timestamp", "")[:10] == today
        )

        # Check if anomalous
        threshold = baseline["mean"] + (sigma_threshold * baseline["std_dev"])

        if today_spend > threshold and today_spend >= min_dollars:
            anomaly = {
                "tenant": tenant_id,
                "today_spend": today_spend,
                "baseline_mean": baseline["mean"],
                "baseline_std_dev": baseline["std_dev"],
                "threshold": threshold,
                "sigma": sigma_threshold,
                "date": today,
            }

            anomalies.append(anomaly)

            # Emit governance event
            emit_governance_event(
                {
                    "event": "cost_anomaly",
                    "tenant": tenant_id,
                    "today_spend": today_spend,
                    "baseline_mean": baseline["mean"],
                    "threshold": threshold,
                    "sigma": sigma_threshold,
                }
            )

    return anomalies
