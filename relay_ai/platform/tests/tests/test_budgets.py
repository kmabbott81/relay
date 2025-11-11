"""Tests for budget management (Sprint 30)."""

import os

import yaml

from relay_ai.cost.budgets import get_global_budget, get_tenant_budget, is_over_budget, is_over_global


def test_get_global_budget_from_env():
    """Test loading global budget from env vars."""
    os.environ["GLOBAL_BUDGET_DAILY"] = "50.0"
    os.environ["GLOBAL_BUDGET_MONTHLY"] = "1000.0"

    budget = get_global_budget()

    assert budget["daily"] == 50.0
    assert budget["monthly"] == 1000.0


def test_get_global_budget_defaults():
    """Test default global budget values."""
    os.environ.pop("GLOBAL_BUDGET_DAILY", None)
    os.environ.pop("GLOBAL_BUDGET_MONTHLY", None)

    budget = get_global_budget()

    assert budget["daily"] == 25.0
    assert budget["monthly"] == 500.0


def test_get_tenant_budget_from_env():
    """Test loading tenant budget defaults from env."""
    os.environ["TENANT_BUDGET_DAILY_DEFAULT"] = "5.0"
    os.environ["TENANT_BUDGET_MONTHLY_DEFAULT"] = "100.0"

    budget = get_tenant_budget("tenant-1")

    assert budget["daily"] == 5.0
    assert budget["monthly"] == 100.0


def test_get_tenant_budget_from_yaml(tmp_path):
    """Test loading tenant budget from YAML config."""
    budgets_file = tmp_path / "budgets.yaml"
    os.environ["BUDGETS_PATH"] = str(budgets_file)

    config = {
        "global": {"daily": 100.0, "monthly": 2000.0},
        "tenants": {
            "premium-tenant": {"daily": 20.0, "monthly": 400.0},
            "trial-tenant": {"daily": 1.0, "monthly": 10.0},
        },
    }

    with open(budgets_file, "w") as f:
        yaml.dump(config, f)

    budget = get_tenant_budget("premium-tenant")

    assert budget["daily"] == 20.0
    assert budget["monthly"] == 400.0


def test_get_tenant_budget_yaml_fallback(tmp_path):
    """Test fallback to default when tenant not in YAML."""
    budgets_file = tmp_path / "budgets.yaml"
    os.environ["BUDGETS_PATH"] = str(budgets_file)
    os.environ["TENANT_BUDGET_DAILY_DEFAULT"] = "3.0"
    os.environ["TENANT_BUDGET_MONTHLY_DEFAULT"] = "50.0"

    config = {
        "global": {"daily": 100.0, "monthly": 2000.0},
        "tenants": {
            "premium-tenant": {"daily": 20.0, "monthly": 400.0},
        },
    }

    with open(budgets_file, "w") as f:
        yaml.dump(config, f)

    budget = get_tenant_budget("unknown-tenant")

    assert budget["daily"] == 3.0
    assert budget["monthly"] == 50.0


def test_is_over_budget_under():
    """Test budget check when under budget."""
    os.environ["TENANT_BUDGET_DAILY_DEFAULT"] = "10.0"
    os.environ["TENANT_BUDGET_MONTHLY_DEFAULT"] = "200.0"

    status = is_over_budget("tenant-1", daily_spend=5.0, monthly_spend=100.0)

    assert status["daily"] is False
    assert status["monthly"] is False


def test_is_over_budget_daily():
    """Test budget check when daily exceeded."""
    os.environ["TENANT_BUDGET_DAILY_DEFAULT"] = "10.0"
    os.environ["TENANT_BUDGET_MONTHLY_DEFAULT"] = "200.0"

    status = is_over_budget("tenant-1", daily_spend=15.0, monthly_spend=100.0)

    assert status["daily"] is True
    assert status["monthly"] is False


def test_is_over_budget_monthly():
    """Test budget check when monthly exceeded."""
    os.environ["TENANT_BUDGET_DAILY_DEFAULT"] = "10.0"
    os.environ["TENANT_BUDGET_MONTHLY_DEFAULT"] = "200.0"

    status = is_over_budget("tenant-1", daily_spend=5.0, monthly_spend=250.0)

    assert status["daily"] is False
    assert status["monthly"] is True


def test_is_over_budget_both():
    """Test budget check when both daily and monthly exceeded."""
    os.environ["TENANT_BUDGET_DAILY_DEFAULT"] = "10.0"
    os.environ["TENANT_BUDGET_MONTHLY_DEFAULT"] = "200.0"

    status = is_over_budget("tenant-1", daily_spend=15.0, monthly_spend=250.0)

    assert status["daily"] is True
    assert status["monthly"] is True


def test_is_over_global_under():
    """Test global budget check when under."""
    os.environ["GLOBAL_BUDGET_DAILY"] = "100.0"
    os.environ["GLOBAL_BUDGET_MONTHLY"] = "2000.0"

    status = is_over_global(daily_spend=50.0, monthly_spend=1000.0)

    assert status["daily"] is False
    assert status["monthly"] is False


def test_is_over_global_daily():
    """Test global budget check when daily exceeded."""
    os.environ["GLOBAL_BUDGET_DAILY"] = "100.0"
    os.environ["GLOBAL_BUDGET_MONTHLY"] = "2000.0"

    status = is_over_global(daily_spend=150.0, monthly_spend=1000.0)

    assert status["daily"] is True
    assert status["monthly"] is False


def test_is_over_global_monthly():
    """Test global budget check when monthly exceeded."""
    os.environ["GLOBAL_BUDGET_DAILY"] = "100.0"
    os.environ["GLOBAL_BUDGET_MONTHLY"] = "2000.0"

    status = is_over_global(daily_spend=50.0, monthly_spend=2500.0)

    assert status["daily"] is False
    assert status["monthly"] is True
