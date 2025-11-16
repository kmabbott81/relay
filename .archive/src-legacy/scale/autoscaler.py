"""Autoscaler for worker pool based on queue depth and latency.

Pure function approach: given engine state, return desired worker count.

Environment Variables:
    MIN_WORKERS: Minimum worker count (default: 1)
    MAX_WORKERS: Maximum worker count (default: 12)
    TARGET_P95_LATENCY_MS: Target P95 latency (default: 2000)
    TARGET_QUEUE_DEPTH: Target queue depth (default: 50)
    SCALE_UP_STEP: Workers to add when scaling up (default: 2)
    SCALE_DOWN_STEP: Workers to remove when scaling down (default: 1)
    SCALE_DECISION_INTERVAL_MS: Minimum time between scaling decisions (default: 1500)
"""

import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional


class ScaleDirection(Enum):
    """Scaling direction."""

    UP = "up"
    DOWN = "down"
    HOLD = "hold"


@dataclass
class EngineState:
    """Current state of the execution engine."""

    current_workers: int
    queue_depth: int
    p95_latency_ms: float
    in_flight_jobs: int
    last_scale_time: Optional[datetime] = None


@dataclass
class ScaleDecision:
    """Scaling decision output."""

    direction: ScaleDirection
    desired_workers: int
    reason: str
    current_workers: int


def make_scale_decision(state: EngineState) -> ScaleDecision:
    """
    Determine desired worker count based on engine state.

    Args:
        state: Current engine state (queue, latency, workers)

    Returns:
        ScaleDecision with desired worker count and reasoning
    """
    # Load config from env
    min_workers = int(os.getenv("MIN_WORKERS", "1"))
    max_workers = int(os.getenv("MAX_WORKERS", "12"))
    target_p95_ms = int(os.getenv("TARGET_P95_LATENCY_MS", "2000"))
    target_queue_depth = int(os.getenv("TARGET_QUEUE_DEPTH", "50"))
    scale_up_step = int(os.getenv("SCALE_UP_STEP", "2"))
    scale_down_step = int(os.getenv("SCALE_DOWN_STEP", "1"))
    scale_interval_ms = int(os.getenv("SCALE_DECISION_INTERVAL_MS", "1500"))

    current = state.current_workers

    # Check if we're in cooldown period
    if state.last_scale_time:
        elapsed = datetime.utcnow() - state.last_scale_time
        cooldown = timedelta(milliseconds=scale_interval_ms)
        if elapsed < cooldown:
            return ScaleDecision(
                direction=ScaleDirection.HOLD,
                desired_workers=current,
                reason=f"Cooldown active ({elapsed.total_seconds():.1f}s < {cooldown.total_seconds():.1f}s)",
                current_workers=current,
            )

    # Scale up conditions
    scale_up_reasons = []

    # 1. Queue depth exceeds target
    if state.queue_depth > target_queue_depth:
        queue_ratio = state.queue_depth / target_queue_depth
        scale_up_reasons.append(f"queue depth {state.queue_depth} > {target_queue_depth} ({queue_ratio:.1f}x)")

    # 2. P95 latency exceeds target
    if state.p95_latency_ms > target_p95_ms:
        latency_ratio = state.p95_latency_ms / target_p95_ms
        scale_up_reasons.append(f"P95 latency {state.p95_latency_ms}ms > {target_p95_ms}ms ({latency_ratio:.1f}x)")

    # 3. All workers busy with queue backlog
    if state.in_flight_jobs >= current and state.queue_depth > 0:
        scale_up_reasons.append(f"all {current} workers busy, {state.queue_depth} queued")

    # Scale up if any condition met
    if scale_up_reasons and current < max_workers:
        desired = min(current + scale_up_step, max_workers)
        return ScaleDecision(
            direction=ScaleDirection.UP,
            desired_workers=desired,
            reason="; ".join(scale_up_reasons),
            current_workers=current,
        )

    # Scale down conditions (all must be true)
    scale_down_ok = True
    scale_down_reasons = []

    # 1. Queue depth well below target
    if state.queue_depth > target_queue_depth * 0.3:  # 30% threshold
        scale_down_ok = False

    # 2. P95 latency well below target
    if state.p95_latency_ms > target_p95_ms * 0.5:  # 50% threshold
        scale_down_ok = False

    # 3. Workers not fully utilized
    utilization = state.in_flight_jobs / current if current > 0 else 0
    if utilization > 0.7:  # 70% threshold
        scale_down_ok = False
    else:
        scale_down_reasons.append(f"utilization {utilization:.1%} < 70%")

    # Scale down if safe
    if scale_down_ok and current > min_workers and scale_down_reasons:
        desired = max(current - scale_down_step, min_workers)
        return ScaleDecision(
            direction=ScaleDirection.DOWN,
            desired_workers=desired,
            reason=f"low load: {'; '.join(scale_down_reasons)}",
            current_workers=current,
        )

    # Hold steady
    return ScaleDecision(
        direction=ScaleDirection.HOLD,
        desired_workers=current,
        reason=f"stable (queue={state.queue_depth}, p95={state.p95_latency_ms}ms, util={state.in_flight_jobs}/{current})",
        current_workers=current,
    )
