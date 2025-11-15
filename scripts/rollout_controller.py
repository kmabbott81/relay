#!/usr/bin/env python3
"""Automated rollout controller for Gmail feature.

Sprint 54: SLO-based automated promotion and rollback.

This script runs on a schedule (every 10 minutes) and:
1. Queries Prometheus for Gmail SLO metrics (error rate, latency, OAuth failures)
2. Gets current rollout percentage from Redis
3. Calls gmail_policy() to get recommendation
4. Updates Redis if recommendation differs (with safety guards)
5. Logs decision to audit trail

Safety guards:
- Min dwell time: 15 minutes between any change
- Cooldown after rollback: 1 hour hold before next promotion
- Manual pause: Set flags:google:paused=true to stop controller
- Prometheus unreachable: Hold at current level, exit non-zero
- Redis write failure: Exit non-zero (surfaces in GitHub Actions)

Observability:
- Emits telemetry to Pushgateway (optional):
  - rollout_controller_changes_total{feature,result}: promote/rollback/hold decisions
  - rollout_controller_percent{feature}: Current rollout percentage
  - rollout_controller_runs_total{status}: Controller health (ok/prom_unreachable/redis_error)

Usage:
    # Run once (manual)
    python scripts/rollout_controller.py

    # Run via GitHub Actions cron (every 10 minutes)
    # See .github/workflows/rollout-controller.yml

Environment variables:
    PROMETHEUS_BASE_URL: Prometheus server URL (e.g., http://localhost:9090)
    REDIS_URL: Redis connection URL
    ROLLOUT_DRY_RUN: If "true", only log recommendations (no Redis updates)
    PUSHGATEWAY_URL: Prometheus Pushgateway URL (optional, e.g., http://pushgateway:9091)
"""

import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx


def query_prometheus(prom_url: str, query: str, timeout: int = 10) -> Optional[float]:
    """Query Prometheus and return first scalar result.

    Args:
        prom_url: Prometheus base URL (e.g., http://localhost:9090)
        query: PromQL query string
        timeout: Request timeout in seconds

    Returns:
        Float result, or None if query fails or returns no data
    """
    url = f"{prom_url}/api/v1/query"
    params = {"query": query}

    try:
        response = httpx.get(url, params=params, timeout=timeout)
        response.raise_for_status()

        data = response.json()
        if data["status"] != "success":
            print(f"[ERROR] Prometheus query failed: {data}")
            return None

        result = data.get("data", {}).get("result", [])
        if not result:
            # No data points (e.g., no Gmail traffic yet)
            return 0.0

        # Return first scalar value
        value = result[0].get("value", [None, None])[1]
        return float(value) if value is not None else None

    except Exception as e:
        print(f"[ERROR] Failed to query Prometheus: {e}")
        return None


def get_metrics(prom_url: str) -> dict:
    """Fetch Gmail SLO metrics from Prometheus.

    Args:
        prom_url: Prometheus base URL

    Returns:
        Dict with keys:
        - error_rate_5m: Error rate over last 5 minutes (0.0-1.0)
        - latency_p95_5m: P95 latency in seconds (float)
        - oauth_refresh_failures_15m: Count of refresh failures (int)
    """
    metrics = {}

    # Error rate: action_error_total / action_exec_total
    error_query = """
        (
            increase(action_error_total{provider="google",action="gmail.send"}[5m])
                /
            increase(action_exec_total{provider="google",action="gmail.send"}[5m])
        )
    """
    error_rate = query_prometheus(prom_url, error_query)
    metrics["error_rate_5m"] = error_rate if error_rate is not None else 0.0

    # Latency P95
    latency_query = """
        histogram_quantile(
            0.95,
            sum(rate(action_latency_seconds_bucket{provider="google",action="gmail.send"}[5m])) by (le)
        )
    """
    latency = query_prometheus(prom_url, latency_query)
    metrics["latency_p95_5m"] = latency if latency is not None else 0.0

    # OAuth refresh failures
    oauth_query = 'increase(oauth_events_total{provider="google",event="refresh_failed"}[15m])'
    failures = query_prometheus(prom_url, oauth_query)
    metrics["oauth_refresh_failures_15m"] = int(failures) if failures is not None else 0

    return metrics


def get_last_change_time(redis_client) -> Optional[datetime]:
    """Get timestamp of last rollout change from Redis.

    Args:
        redis_client: Redis client instance

    Returns:
        Datetime of last change, or None if no previous change

    Raises:
        ValueError: If timestamp is corrupted (fail-fast to prevent bypassing dwell/cooldown)
    """
    timestamp_str = redis_client.get("flags:google:last_change_time")
    if not timestamp_str:
        return None

    try:
        return datetime.fromisoformat(timestamp_str)
    except Exception as e:
        # Fail-fast on corrupted timestamp - prevents bypassing dwell/cooldown safety guards
        print(f"[ERROR] REDIS_TIMESTAMP_CORRUPT: Unable to parse timestamp '{timestamp_str}': {e}")
        print("[ERROR] Failing fast to prevent bypassing rollout safety guards (dwell time, cooldown)")
        raise ValueError(f"Corrupted Redis timestamp: {timestamp_str}") from e


def set_last_change_time(redis_client, dt: datetime):
    """Set timestamp of last rollout change in Redis.

    Args:
        redis_client: Redis client instance
        dt: Datetime to store
    """
    redis_client.set("flags:google:last_change_time", dt.isoformat())


def is_paused(redis_client) -> bool:
    """Check if controller is manually paused.

    Args:
        redis_client: Redis client instance

    Returns:
        True if paused (flags:google:paused=true)
    """
    paused = redis_client.get("flags:google:paused")
    return paused is not None and paused.lower() == "true"


def push_gateway(feature: str = "google", result: str = "hold", percent: Optional[int] = None, status: str = "ok"):
    """Push controller telemetry to Prometheus Pushgateway.

    Emits metrics for monitoring controller health and decisions:
    - rollout_controller_changes_total: Counter of decisions (promote/rollback/hold)
    - rollout_controller_percent: Current rollout percentage
    - rollout_controller_runs_total: Counter of controller runs by status

    Args:
        feature: Feature name (e.g., "google")
        result: Decision result (promote, rollback, hold)
        percent: Current rollout percentage (optional)
        status: Run status (ok, prom_unreachable, redis_error)
    """
    pushgateway_url = os.getenv("PUSHGATEWAY_URL")
    if not pushgateway_url:
        return  # Telemetry disabled

    job = "rollout_controller"
    instance = os.getenv("HOSTNAME", "gha")

    # Build OpenMetrics exposition format
    lines = [
        "# TYPE rollout_controller_changes_total counter",
        f'rollout_controller_changes_total{{feature="{feature}",result="{result}"}} 1',
        "# TYPE rollout_controller_runs_total counter",
        f'rollout_controller_runs_total{{status="{status}"}} 1',
    ]

    if percent is not None:
        lines += [
            "# TYPE rollout_controller_percent gauge",
            f'rollout_controller_percent{{feature="{feature}"}} {percent}',
        ]

    body = "\n".join(lines) + "\n"
    url = f"{pushgateway_url}/metrics/job/{job}/instance/{instance}"

    try:
        httpx.put(url, content=body, timeout=5)
    except Exception as e:
        print(f"[WARN] Failed to push metrics to Pushgateway: {e}")


def main():
    """Main controller loop."""
    # Check environment
    prom_url = os.getenv("PROMETHEUS_BASE_URL")
    redis_url = os.getenv("REDIS_URL")
    dry_run = os.getenv("ROLLOUT_DRY_RUN", "false").lower() == "true"

    if not prom_url:
        print("[ERROR] PROMETHEUS_BASE_URL not set")
        sys.exit(1)

    if not redis_url:
        print("[ERROR] REDIS_URL not set")
        sys.exit(1)

    # Connect to Redis
    try:
        import redis

        redis_client = redis.from_url(redis_url, decode_responses=True, socket_connect_timeout=5)
        redis_client.ping()
        print(f"[INFO] Connected to Redis: {redis_url}")
    except Exception as e:
        print(f"[ERROR] Failed to connect to Redis: {e}")
        sys.exit(1)

    # Check if paused
    if is_paused(redis_client):
        print("[INFO] Controller is paused (flags:google:paused=true). Exiting.")
        sys.exit(0)

    # Get current rollout percentage
    current_pct_str = redis_client.get("flags:google:rollout_percent")
    current_pct = int(current_pct_str) if current_pct_str else 0
    print(f"[INFO] Current rollout: {current_pct}%")

    # Fetch metrics from Prometheus
    print(f"[INFO] Querying Prometheus: {prom_url}")
    try:
        metrics = get_metrics(prom_url)
        print(f"[INFO] Metrics: {metrics}")
    except Exception as e:
        print(f"[ERROR] PROMETHEUS_UNREACHABLE: {e}")
        push_gateway(feature="google", result="hold", status="prom_unreachable")
        sys.exit(1)  # Fail loudly; no Redis updates

    # Get policy recommendation
    from relay_ai.rollout.policy import gmail_policy

    recommendation = gmail_policy(metrics, current_percent=current_pct)
    print(f"[INFO] Policy recommendation: {recommendation.target_percent}% (reason: {recommendation.reason})")

    # Check if change is needed
    if recommendation.target_percent == current_pct:
        print("[INFO] No change needed. Holding at current level.")
        push_gateway(feature="google", result="hold", percent=current_pct, status="ok")
        return

    # Safety guard: Min dwell time (15 minutes)
    try:
        last_change = get_last_change_time(redis_client)
    except ValueError as e:
        print(f"[ERROR] {e}")
        push_gateway(feature="google", result="hold", status="redis_error")
        sys.exit(1)

    if last_change:
        elapsed = datetime.now(timezone.utc) - last_change.replace(tzinfo=timezone.utc)
        min_dwell = timedelta(minutes=15)

        if elapsed < min_dwell:
            remaining = min_dwell - elapsed
            print(f"[INFO] Min dwell time not met. Wait {remaining.total_seconds():.0f}s before next change.")
            return

    # Safety guard: Cooldown after rollback (1 hour)
    # If last change was a rollback (decrease), wait 1 hour before promoting
    if last_change and recommendation.target_percent > current_pct:
        last_pct_str = redis_client.get("flags:google:last_percent")
        if last_pct_str:
            last_pct = int(last_pct_str)
            if last_pct > current_pct:  # Previous change was a rollback
                elapsed = datetime.now(timezone.utc) - last_change.replace(tzinfo=timezone.utc)
                cooldown = timedelta(hours=1)

                if elapsed < cooldown:
                    remaining = cooldown - elapsed
                    print(f"[INFO] Cooldown after rollback. Wait {remaining.total_seconds():.0f}s before promotion.")
                    return

    # Determine result type for telemetry
    if recommendation.target_percent > current_pct:
        result = "promote"
    elif recommendation.target_percent < current_pct:
        result = "rollback"
    else:
        result = "hold"

    # Apply change
    if dry_run:
        print(f"[DRY RUN] Would update rollout: {current_pct}% -> {recommendation.target_percent}%")
    else:
        print(f"[INFO] Updating rollout: {current_pct}% -> {recommendation.target_percent}%")
        try:
            redis_client.set("flags:google:rollout_percent", str(recommendation.target_percent))
            redis_client.set("flags:google:last_percent", str(current_pct))
            set_last_change_time(redis_client, datetime.now(timezone.utc))
        except Exception as e:
            print(f"[ERROR] REDIS_WRITE_FAILED: {e}")
            push_gateway(feature="google", result="hold", status="redis_error")
            sys.exit(1)  # Fail fast; surfaces in GitHub Actions

    # Log to audit trail
    from relay_ai.rollout.audit import append_rollout_log

    append_rollout_log(
        feature="google",
        old_pct=current_pct,
        new_pct=recommendation.target_percent,
        reason=recommendation.reason,
        by="controller",
    )

    # Emit telemetry
    push_gateway(feature="google", result=result, percent=recommendation.target_percent, status="ok")

    print(f"[SUCCESS] Rollout updated: {current_pct}% -> {recommendation.target_percent}%")


if __name__ == "__main__":
    main()
