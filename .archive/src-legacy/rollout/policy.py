"""Rollout policy decision logic.

Sprint 54: SLO-based rollout promotion and rollback policies.

This module encodes the thresholds and decision logic for automated
rollout. Today it returns recommendations; later the controller script
will execute them.

Tuning strategy:
- Start with conservative thresholds during manual rollout
- Observe false positives and adjust based on real data
- Document threshold changes in rollout_log.md
"""

from dataclasses import dataclass


@dataclass
class Recommendation:
    """Rollout recommendation from policy evaluation.

    Attributes:
        target_percent: Recommended rollout percentage (0-100)
        reason: Human-readable explanation for the decision
    """

    target_percent: int
    reason: str


def gmail_policy(metrics: dict, current_percent: int) -> Recommendation:
    """Gmail rollout policy based on SLO metrics.

    Evaluates current metrics against SLO thresholds and recommends
    rollout percentage changes.

    SLO Thresholds (tune during manual rollout):
    - Error rate: ≤1% (action_error_total / action_exec_total)
    - P95 latency: ≤500ms (action_latency_seconds)
    - OAuth refresh failures: ≤5 per 15 minutes

    Rollout stages:
    - 0% → 10%: Initial canary (internal users)
    - 10% → 50%: Ramp if SLOs green
    - 50% → 100%: Full rollout if stable
    - Any → 0% or 10%: Rollback if SLO violated

    Args:
        metrics: Dict with keys:
            - error_rate_5m: Error rate over last 5 minutes (0.0-1.0)
            - latency_p95_5m: P95 latency in seconds (float)
            - oauth_refresh_failures_15m: Count of refresh failures (int)
        current_percent: Current rollout percentage (0-100)

    Returns:
        Recommendation with target_percent and reason

    Example:
        metrics = {
            "error_rate_5m": 0.005,  # 0.5% error rate (good)
            "latency_p95_5m": 0.35,  # 350ms P95 (good)
            "oauth_refresh_failures_15m": 2  # 2 failures (good)
        }
        rec = gmail_policy(metrics, current_percent=10)
        # rec.target_percent = 50, rec.reason = "Healthy → ramp"
    """
    # SLO guard: Check for violations
    error_rate = metrics.get("error_rate_5m", 0.0)
    latency_p95 = metrics.get("latency_p95_5m", 0.0)
    oauth_failures = metrics.get("oauth_refresh_failures_15m", 0)

    # Rollback logic: If any SLO violated, reduce to safe level
    if error_rate > 0.01:
        return Recommendation(
            target_percent=max(0, min(current_percent, 10)),
            reason=f"SLO violated: error_rate={error_rate:.1%} > 1% → reduce/hold",
        )

    if latency_p95 > 0.5:
        return Recommendation(
            target_percent=max(0, min(current_percent, 10)),
            reason=f"SLO violated: P95 latency={latency_p95:.3f}s > 0.5s → reduce/hold",
        )

    if oauth_failures > 5:
        return Recommendation(
            target_percent=max(0, min(current_percent, 10)),
            reason=f"SLO violated: OAuth refresh failures={oauth_failures} > 5 → reduce/hold",
        )

    # Promotion logic: If SLOs green, advance through stages
    if current_percent == 0:
        return Recommendation(target_percent=10, reason="Initial canary (internal users)")

    if current_percent == 10:
        return Recommendation(target_percent=50, reason="Healthy → ramp to 50%")

    if current_percent == 50:
        return Recommendation(target_percent=100, reason="Healthy → full rollout")

    # Hold at current level if no action needed
    return Recommendation(target_percent=current_percent, reason="Hold at current level")
