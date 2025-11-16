"""
Budget Configuration (Sprint 30)

Manages per-tenant and global budgets from environment + optional YAML config.
"""

import os
from pathlib import Path
from typing import Any

import yaml


def get_budgets_path() -> Path | None:
    """Get budgets config path if specified."""
    path_str = os.getenv("BUDGETS_PATH")
    return Path(path_str) if path_str else None


def load_budgets_config() -> dict[str, Any]:
    """
    Load budgets from YAML config file.

    Returns:
        Dict with global and per-tenant budgets
    """
    budgets_path = get_budgets_path()

    if not budgets_path or not budgets_path.exists():
        return {}

    try:
        with open(budgets_path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


def get_global_budget() -> dict[str, float]:
    """
    Get global budget limits.

    Returns:
        Dict with daily and monthly limits
    """
    config = load_budgets_config()
    global_config = config.get("global", {})

    return {
        "daily": float(os.getenv("GLOBAL_BUDGET_DAILY", global_config.get("daily", 25.0))),
        "monthly": float(os.getenv("GLOBAL_BUDGET_MONTHLY", global_config.get("monthly", 500.0))),
    }


def get_team_budget(team_id: str) -> dict[str, float]:
    """
    Get budget for specific team (Sprint 34A).

    Args:
        team_id: Team identifier

    Returns:
        Dict with daily and monthly limits
    """
    config = load_budgets_config()
    teams = config.get("teams", {})
    team_config = teams.get(team_id, {})

    # Defaults from env or config
    default_daily = float(os.getenv("TEAM_BUDGET_DAILY_DEFAULT", team_config.get("daily", 10.0)))
    default_monthly = float(os.getenv("TEAM_BUDGET_MONTHLY_DEFAULT", team_config.get("monthly", 200.0)))

    return {
        "daily": team_config.get("daily", default_daily),
        "monthly": team_config.get("monthly", default_monthly),
    }


def get_tenant_budget(tenant: str) -> dict[str, float]:
    """
    Get budget for specific tenant.

    Args:
        tenant: Tenant identifier

    Returns:
        Dict with daily and monthly limits
    """
    config = load_budgets_config()
    tenants = config.get("tenants", {})
    tenant_config = tenants.get(tenant, {})

    # Defaults from env or config
    default_daily = float(os.getenv("TENANT_BUDGET_DAILY_DEFAULT", tenant_config.get("daily", 5.0)))
    default_monthly = float(os.getenv("TENANT_BUDGET_MONTHLY_DEFAULT", tenant_config.get("monthly", 100.0)))

    return {
        "daily": tenant_config.get("daily", default_daily),
        "monthly": tenant_config.get("monthly", default_monthly),
    }


def is_over_team_budget(team_id: str, daily_spend: float, monthly_spend: float) -> dict[str, Any]:
    """
    Check if team is over budget (Sprint 34A).

    Args:
        team_id: Team identifier
        daily_spend: Current daily spend for team
        monthly_spend: Current monthly spend for team

    Returns:
        Dict with daily/monthly flags and amounts
    """
    budget = get_team_budget(team_id)

    return {
        "daily": daily_spend >= budget["daily"],
        "monthly": monthly_spend >= budget["monthly"],
        "daily_amount": daily_spend,
        "monthly_amount": monthly_spend,
        "daily_budget": budget["daily"],
        "monthly_budget": budget["monthly"],
        "daily_remaining": max(0, budget["daily"] - daily_spend),
        "monthly_remaining": max(0, budget["monthly"] - monthly_spend),
    }


def is_over_budget(tenant: str, daily_spend: float, monthly_spend: float) -> dict[str, Any]:
    """
    Check if tenant is over budget.

    Args:
        tenant: Tenant identifier
        daily_spend: Current daily spend
        monthly_spend: Current monthly spend

    Returns:
        Dict with daily/monthly flags and amounts
    """
    budget = get_tenant_budget(tenant)

    return {
        "daily": daily_spend >= budget["daily"],
        "monthly": monthly_spend >= budget["monthly"],
        "daily_amount": daily_spend,
        "monthly_amount": monthly_spend,
        "daily_budget": budget["daily"],
        "monthly_budget": budget["monthly"],
        "daily_remaining": max(0, budget["daily"] - daily_spend),
        "monthly_remaining": max(0, budget["monthly"] - monthly_spend),
    }


def is_over_global(daily_spend: float, monthly_spend: float) -> dict[str, Any]:
    """
    Check if global spend is over budget.

    Args:
        daily_spend: Current global daily spend
        monthly_spend: Current global monthly spend

    Returns:
        Dict with daily/monthly flags and amounts
    """
    budget = get_global_budget()

    return {
        "daily": daily_spend >= budget["daily"],
        "monthly": monthly_spend >= budget["monthly"],
        "daily_amount": daily_spend,
        "monthly_amount": monthly_spend,
        "daily_budget": budget["daily"],
        "monthly_budget": budget["monthly"],
        "daily_remaining": max(0, budget["daily"] - daily_spend),
        "monthly_remaining": max(0, budget["monthly"] - monthly_spend),
    }
