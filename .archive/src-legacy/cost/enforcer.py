"""
Budget Enforcer (Sprint 30)

Checks budgets and emits governance events.
Provides soft (throttle) and hard (deny) enforcement.
"""

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .budgets import get_global_budget, get_team_budget, get_tenant_budget
from .ledger import load_cost_events, window_sum


class BudgetExceededError(Exception):
    """Raised when budget hard limit is exceeded."""

    pass


def get_governance_events_path() -> Path:
    """Get governance events log path."""
    return Path(os.getenv("GOVERNANCE_EVENTS_PATH", "logs/governance_events.jsonl"))


def emit_governance_event(event: dict[str, Any]) -> None:
    """
    Emit governance event to log.

    Args:
        event: Event dictionary
    """
    events_path = get_governance_events_path()
    events_path.parent.mkdir(parents=True, exist_ok=True)

    event["timestamp"] = datetime.now(UTC).isoformat()

    with open(events_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(event) + "\n")


def should_deny(tenant: str, check_global: bool = True, team_id: str | None = None) -> tuple[bool, str | None]:
    """
    Check if execution should be denied due to budget.

    Args:
        tenant: Tenant identifier
        check_global: Also check global budget
        team_id: Optional team identifier (Sprint 34A)

    Returns:
        Tuple of (should_deny, reason)
    """
    hard_threshold = float(os.getenv("BUDGET_HARD_THRESHOLD", "1.0"))

    # Load cost events
    events = load_cost_events()

    # Check team budget first (Sprint 34A)
    if team_id:
        team_daily_spend = window_sum(events, team_id=team_id, days=1)
        team_monthly_spend = window_sum(events, team_id=team_id, days=30)

        team_budget = get_team_budget(team_id)

        if team_daily_spend >= team_budget["daily"] * hard_threshold:
            emit_governance_event(
                {
                    "event": "budget_deny",
                    "tenant": tenant,
                    "team_id": team_id,
                    "reason": "team_daily_budget_exceeded",
                    "daily_spend": team_daily_spend,
                    "daily_budget": team_budget["daily"],
                }
            )
            return True, f"Team daily budget exceeded: ${team_daily_spend:.2f} >= ${team_budget['daily']:.2f}"

        if team_monthly_spend >= team_budget["monthly"] * hard_threshold:
            emit_governance_event(
                {
                    "event": "budget_deny",
                    "tenant": tenant,
                    "team_id": team_id,
                    "reason": "team_monthly_budget_exceeded",
                    "monthly_spend": team_monthly_spend,
                    "monthly_budget": team_budget["monthly"],
                }
            )
            return True, f"Team monthly budget exceeded: ${team_monthly_spend:.2f} >= ${team_budget['monthly']:.2f}"

    # Check tenant budget
    daily_spend = window_sum(events, tenant=tenant, days=1)
    monthly_spend = window_sum(events, tenant=tenant, days=30)

    tenant_budget = get_tenant_budget(tenant)

    if daily_spend >= tenant_budget["daily"] * hard_threshold:
        emit_governance_event(
            {
                "event": "budget_deny",
                "tenant": tenant,
                "reason": "daily_budget_exceeded",
                "daily_spend": daily_spend,
                "daily_budget": tenant_budget["daily"],
            }
        )
        return True, f"Tenant daily budget exceeded: ${daily_spend:.2f} >= ${tenant_budget['daily']:.2f}"

    if monthly_spend >= tenant_budget["monthly"] * hard_threshold:
        emit_governance_event(
            {
                "event": "budget_deny",
                "tenant": tenant,
                "reason": "monthly_budget_exceeded",
                "monthly_spend": monthly_spend,
                "monthly_budget": tenant_budget["monthly"],
            }
        )
        return True, f"Tenant monthly budget exceeded: ${monthly_spend:.2f} >= ${tenant_budget['monthly']:.2f}"

    # Check global budget
    if check_global:
        global_daily = window_sum(events, tenant=None, days=1)
        global_monthly = window_sum(events, tenant=None, days=30)

        global_budget = get_global_budget()

        if global_daily >= global_budget["daily"] * hard_threshold:
            emit_governance_event(
                {
                    "event": "budget_deny",
                    "tenant": tenant,
                    "reason": "global_daily_budget_exceeded",
                    "global_daily_spend": global_daily,
                    "global_daily_budget": global_budget["daily"],
                }
            )
            return True, f"Global daily budget exceeded: ${global_daily:.2f} >= ${global_budget['daily']:.2f}"

        if global_monthly >= global_budget["monthly"] * hard_threshold:
            emit_governance_event(
                {
                    "event": "budget_deny",
                    "tenant": tenant,
                    "reason": "global_monthly_budget_exceeded",
                    "global_monthly_spend": global_monthly,
                    "global_monthly_budget": global_budget["monthly"],
                }
            )
            return True, f"Global monthly budget exceeded: ${global_monthly:.2f} >= ${global_budget['monthly']:.2f}"

    return False, None


def should_throttle(tenant: str, check_global: bool = True) -> tuple[bool, str | None]:
    """
    Check if execution should be throttled due to approaching budget.

    Args:
        tenant: Tenant identifier
        check_global: Also check global budget

    Returns:
        Tuple of (should_throttle, reason)
    """
    soft_threshold = float(os.getenv("BUDGET_SOFT_THRESHOLD", "0.8"))
    hard_threshold = float(os.getenv("BUDGET_HARD_THRESHOLD", "1.0"))

    # Load cost events
    events = load_cost_events()

    # Check tenant budget
    daily_spend = window_sum(events, tenant=tenant, days=1)
    monthly_spend = window_sum(events, tenant=tenant, days=30)

    tenant_budget = get_tenant_budget(tenant)

    if daily_spend >= tenant_budget["daily"] * soft_threshold and daily_spend < tenant_budget["daily"] * hard_threshold:
        emit_governance_event(
            {
                "event": "budget_throttle",
                "tenant": tenant,
                "reason": "daily_budget_approaching",
                "daily_spend": daily_spend,
                "daily_budget": tenant_budget["daily"],
                "threshold": soft_threshold,
            }
        )
        return True, f"Approaching daily budget: ${daily_spend:.2f} / ${tenant_budget['daily']:.2f}"

    if (
        monthly_spend >= tenant_budget["monthly"] * soft_threshold
        and monthly_spend < tenant_budget["monthly"] * hard_threshold
    ):
        emit_governance_event(
            {
                "event": "budget_throttle",
                "tenant": tenant,
                "reason": "monthly_budget_approaching",
                "monthly_spend": monthly_spend,
                "monthly_budget": tenant_budget["monthly"],
                "threshold": soft_threshold,
            }
        )
        return True, f"Approaching monthly budget: ${monthly_spend:.2f} / ${tenant_budget['monthly']:.2f}"

    # Check global budget
    if check_global:
        global_daily = window_sum(events, tenant=None, days=1)
        global_monthly = window_sum(events, tenant=None, days=30)

        global_budget = get_global_budget()

        if (
            global_daily >= global_budget["daily"] * soft_threshold
            and global_daily < global_budget["daily"] * hard_threshold
        ):
            emit_governance_event(
                {
                    "event": "budget_throttle",
                    "tenant": tenant,
                    "reason": "global_daily_budget_approaching",
                    "global_daily_spend": global_daily,
                    "global_daily_budget": global_budget["daily"],
                    "threshold": soft_threshold,
                }
            )
            return True, f"Approaching global daily budget: ${global_daily:.2f} / ${global_budget['daily']:.2f}"

        if (
            global_monthly >= global_budget["monthly"] * soft_threshold
            and global_monthly < global_budget["monthly"] * hard_threshold
        ):
            emit_governance_event(
                {
                    "event": "budget_throttle",
                    "tenant": tenant,
                    "reason": "global_monthly_budget_approaching",
                    "global_monthly_spend": global_monthly,
                    "global_monthly_budget": global_budget["monthly"],
                    "threshold": soft_threshold,
                }
            )
            return True, f"Approaching global monthly budget: ${global_monthly:.2f} / ${global_budget['monthly']:.2f}"

    return False, None
