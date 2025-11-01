"""Tests for budget enforcer (Sprint 30)."""

import json
import os
from datetime import UTC, datetime

from src.cost.enforcer import (
    emit_governance_event,
    should_deny,
    should_throttle,
)


def test_emit_governance_event(tmp_path):
    """Test governance event emission."""
    events_file = tmp_path / "governance_events.jsonl"
    os.environ["GOVERNANCE_EVENTS_PATH"] = str(events_file)

    emit_governance_event(
        {
            "event": "test_event",
            "tenant": "tenant-1",
            "details": "test details",
        }
    )

    assert events_file.exists()

    with open(events_file) as f:
        line = f.readline()
        event = json.loads(line)

    assert event["event"] == "test_event"
    assert event["tenant"] == "tenant-1"
    assert event["details"] == "test details"
    assert "timestamp" in event


def test_should_deny_under_budget(tmp_path):
    """Test should_deny when under budget."""
    # Create empty cost events file
    cost_events_file = tmp_path / "cost_events.jsonl"
    os.environ["COST_EVENTS_PATH"] = str(cost_events_file)
    os.environ["GOVERNANCE_EVENTS_PATH"] = str(tmp_path / "governance.jsonl")

    cost_events_file.write_text("")

    # Set high budgets
    os.environ["TENANT_BUDGET_DAILY_DEFAULT"] = "100.0"
    os.environ["TENANT_BUDGET_MONTHLY_DEFAULT"] = "2000.0"
    os.environ["GLOBAL_BUDGET_DAILY"] = "500.0"
    os.environ["GLOBAL_BUDGET_MONTHLY"] = "10000.0"

    deny, reason = should_deny("tenant-1")

    assert deny is False
    assert reason is None


def test_should_deny_daily_exceeded(tmp_path):
    """Test should_deny when daily budget exceeded."""
    cost_events_file = tmp_path / "cost_events.jsonl"
    os.environ["COST_EVENTS_PATH"] = str(cost_events_file)
    os.environ["GOVERNANCE_EVENTS_PATH"] = str(tmp_path / "governance.jsonl")

    # Set low daily budget
    os.environ["TENANT_BUDGET_DAILY_DEFAULT"] = "5.0"
    os.environ["TENANT_BUDGET_MONTHLY_DEFAULT"] = "2000.0"
    os.environ["BUDGET_HARD_THRESHOLD"] = "1.0"

    # Add cost events for today totaling $10
    now = datetime.now(UTC).isoformat()

    with open(cost_events_file, "w") as f:
        f.write(json.dumps({"timestamp": now, "tenant": "tenant-1", "cost_estimate": 6.0}) + "\n")
        f.write(json.dumps({"timestamp": now, "tenant": "tenant-1", "cost_estimate": 4.0}) + "\n")

    deny, reason = should_deny("tenant-1", check_global=False)

    assert deny is True
    assert "daily budget exceeded" in reason.lower()


def test_should_deny_monthly_exceeded(tmp_path):
    """Test should_deny when monthly budget exceeded."""
    cost_events_file = tmp_path / "cost_events.jsonl"
    os.environ["COST_EVENTS_PATH"] = str(cost_events_file)
    os.environ["GOVERNANCE_EVENTS_PATH"] = str(tmp_path / "governance.jsonl")

    # Set low monthly budget
    os.environ["TENANT_BUDGET_DAILY_DEFAULT"] = "100.0"
    os.environ["TENANT_BUDGET_MONTHLY_DEFAULT"] = "50.0"
    os.environ["BUDGET_HARD_THRESHOLD"] = "1.0"

    # Add cost events for this month totaling $60
    now = datetime.now(UTC).isoformat()

    with open(cost_events_file, "w") as f:
        for _ in range(6):
            f.write(json.dumps({"timestamp": now, "tenant": "tenant-1", "cost_estimate": 10.0}) + "\n")

    deny, reason = should_deny("tenant-1", check_global=False)

    assert deny is True
    assert "monthly budget exceeded" in reason.lower()


def test_should_deny_global_daily(tmp_path):
    """Test should_deny when global daily budget exceeded."""
    cost_events_file = tmp_path / "cost_events.jsonl"
    os.environ["COST_EVENTS_PATH"] = str(cost_events_file)
    os.environ["GOVERNANCE_EVENTS_PATH"] = str(tmp_path / "governance.jsonl")

    # Set budgets
    os.environ["TENANT_BUDGET_DAILY_DEFAULT"] = "100.0"
    os.environ["TENANT_BUDGET_MONTHLY_DEFAULT"] = "2000.0"
    os.environ["GLOBAL_BUDGET_DAILY"] = "5.0"
    os.environ["GLOBAL_BUDGET_MONTHLY"] = "10000.0"
    os.environ["BUDGET_HARD_THRESHOLD"] = "1.0"

    # Add cost events from multiple tenants today totaling $10
    now = datetime.now(UTC).isoformat()

    with open(cost_events_file, "w") as f:
        f.write(json.dumps({"timestamp": now, "tenant": "tenant-1", "cost_estimate": 3.0}) + "\n")
        f.write(json.dumps({"timestamp": now, "tenant": "tenant-2", "cost_estimate": 3.0}) + "\n")
        f.write(json.dumps({"timestamp": now, "tenant": "tenant-3", "cost_estimate": 4.0}) + "\n")

    deny, reason = should_deny("tenant-1", check_global=True)

    assert deny is True
    assert "global daily budget exceeded" in reason.lower()


def test_should_throttle_under_threshold(tmp_path):
    """Test should_throttle when under soft threshold."""
    cost_events_file = tmp_path / "cost_events.jsonl"
    os.environ["COST_EVENTS_PATH"] = str(cost_events_file)
    os.environ["GOVERNANCE_EVENTS_PATH"] = str(tmp_path / "governance.jsonl")

    cost_events_file.write_text("")

    # Set high budgets
    os.environ["TENANT_BUDGET_DAILY_DEFAULT"] = "100.0"
    os.environ["TENANT_BUDGET_MONTHLY_DEFAULT"] = "2000.0"
    os.environ["BUDGET_SOFT_THRESHOLD"] = "0.8"

    throttle, reason = should_throttle("tenant-1", check_global=False)

    assert throttle is False
    assert reason is None


def test_should_throttle_daily_approaching(tmp_path):
    """Test should_throttle when daily budget approaching."""
    cost_events_file = tmp_path / "cost_events.jsonl"
    os.environ["COST_EVENTS_PATH"] = str(cost_events_file)
    os.environ["GOVERNANCE_EVENTS_PATH"] = str(tmp_path / "governance.jsonl")

    # Set budget and thresholds
    os.environ["TENANT_BUDGET_DAILY_DEFAULT"] = "10.0"
    os.environ["TENANT_BUDGET_MONTHLY_DEFAULT"] = "2000.0"
    os.environ["BUDGET_SOFT_THRESHOLD"] = "0.8"
    os.environ["BUDGET_HARD_THRESHOLD"] = "1.0"

    # Spend $8.5 today (85% of $10 budget, above 80% threshold)
    now = datetime.now(UTC).isoformat()

    with open(cost_events_file, "w") as f:
        f.write(json.dumps({"timestamp": now, "tenant": "tenant-1", "cost_estimate": 8.5}) + "\n")

    throttle, reason = should_throttle("tenant-1", check_global=False)

    assert throttle is True
    assert "approaching daily budget" in reason.lower()


def test_should_throttle_monthly_approaching(tmp_path):
    """Test should_throttle when monthly budget approaching."""
    cost_events_file = tmp_path / "cost_events.jsonl"
    os.environ["COST_EVENTS_PATH"] = str(cost_events_file)
    os.environ["GOVERNANCE_EVENTS_PATH"] = str(tmp_path / "governance.jsonl")

    # Set budget and thresholds
    os.environ["TENANT_BUDGET_DAILY_DEFAULT"] = "500.0"
    os.environ["TENANT_BUDGET_MONTHLY_DEFAULT"] = "100.0"
    os.environ["BUDGET_SOFT_THRESHOLD"] = "0.8"
    os.environ["BUDGET_HARD_THRESHOLD"] = "1.0"

    # Spend $85 this month (85% of $100 monthly, but only 17% of daily)
    now = datetime.now(UTC).isoformat()

    with open(cost_events_file, "w") as f:
        for _ in range(17):
            f.write(json.dumps({"timestamp": now, "tenant": "tenant-1", "cost_estimate": 5.0}) + "\n")

    throttle, reason = should_throttle("tenant-1", check_global=False)

    assert throttle is True
    assert "approaching monthly budget" in reason.lower()


def test_should_throttle_not_when_over_hard(tmp_path):
    """Test should_throttle returns False when over hard threshold."""
    cost_events_file = tmp_path / "cost_events.jsonl"
    os.environ["COST_EVENTS_PATH"] = str(cost_events_file)
    os.environ["GOVERNANCE_EVENTS_PATH"] = str(tmp_path / "governance.jsonl")

    # Set budget and thresholds
    os.environ["TENANT_BUDGET_DAILY_DEFAULT"] = "10.0"
    os.environ["TENANT_BUDGET_MONTHLY_DEFAULT"] = "2000.0"
    os.environ["BUDGET_SOFT_THRESHOLD"] = "0.8"
    os.environ["BUDGET_HARD_THRESHOLD"] = "1.0"

    # Spend $15 today (150% of $10 budget, over hard threshold)
    now = datetime.now(UTC).isoformat()

    with open(cost_events_file, "w") as f:
        f.write(json.dumps({"timestamp": now, "tenant": "tenant-1", "cost_estimate": 15.0}) + "\n")

    throttle, reason = should_throttle("tenant-1", check_global=False)

    # Should not throttle because over hard threshold (should deny instead)
    assert throttle is False
    assert reason is None
