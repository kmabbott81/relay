"""Tests for cost report CLI (Sprint 30)."""

import json
import os
from datetime import UTC, datetime, timedelta

from scripts.cost_report import print_json_report, print_text_report


def test_print_text_report_empty(tmp_path, capsys):
    """Test text report with no cost events."""
    cost_events_file = tmp_path / "cost_events.jsonl"
    os.environ["COST_EVENTS_PATH"] = str(cost_events_file)
    os.environ["GOVERNANCE_EVENTS_PATH"] = str(tmp_path / "governance.jsonl")

    cost_events_file.write_text("")

    print_text_report(days=30)

    captured = capsys.readouterr()

    assert "Cost Report" in captured.out
    assert "Global Spend:" in captured.out
    assert "$0.00" in captured.out


def test_print_text_report_with_data(tmp_path, capsys):
    """Test text report with cost events."""
    cost_events_file = tmp_path / "cost_events.jsonl"
    os.environ["COST_EVENTS_PATH"] = str(cost_events_file)
    os.environ["GOVERNANCE_EVENTS_PATH"] = str(tmp_path / "governance.jsonl")
    os.environ["TENANT_BUDGET_DAILY_DEFAULT"] = "100.0"
    os.environ["TENANT_BUDGET_MONTHLY_DEFAULT"] = "2000.0"

    now = datetime.now(UTC)

    with open(cost_events_file, "w") as f:
        # Today's events
        today = now.isoformat()
        f.write(json.dumps({"timestamp": today, "tenant": "tenant-1", "cost_estimate": 5.0}) + "\n")
        f.write(json.dumps({"timestamp": today, "tenant": "tenant-2", "cost_estimate": 3.0}) + "\n")

        # This month's events
        last_week = (now - timedelta(days=7)).isoformat()
        f.write(json.dumps({"timestamp": last_week, "tenant": "tenant-1", "cost_estimate": 10.0}) + "\n")
        f.write(json.dumps({"timestamp": last_week, "tenant": "tenant-2", "cost_estimate": 7.0}) + "\n")

    print_text_report(days=30)

    captured = capsys.readouterr()

    assert "Cost Report" in captured.out
    assert "Global Spend:" in captured.out
    assert "Daily:" in captured.out
    assert "Monthly:" in captured.out
    assert "Per-Tenant Spend:" in captured.out
    assert "tenant-1" in captured.out
    assert "tenant-2" in captured.out
    assert "✅" in captured.out  # Budget status icon


def test_print_text_report_filtered_tenant(tmp_path, capsys):
    """Test text report filtered to specific tenant."""
    cost_events_file = tmp_path / "cost_events.jsonl"
    os.environ["COST_EVENTS_PATH"] = str(cost_events_file)
    os.environ["GOVERNANCE_EVENTS_PATH"] = str(tmp_path / "governance.jsonl")
    os.environ["TENANT_BUDGET_DAILY_DEFAULT"] = "100.0"
    os.environ["TENANT_BUDGET_MONTHLY_DEFAULT"] = "2000.0"

    now = datetime.now(UTC).isoformat()

    with open(cost_events_file, "w") as f:
        f.write(json.dumps({"timestamp": now, "tenant": "tenant-1", "cost_estimate": 5.0}) + "\n")
        f.write(json.dumps({"timestamp": now, "tenant": "tenant-2", "cost_estimate": 3.0}) + "\n")

    print_text_report(tenant="tenant-1", days=30)

    captured = capsys.readouterr()

    assert "tenant-1" in captured.out
    assert "tenant-2" not in captured.out


def test_print_text_report_over_budget(tmp_path, capsys):
    """Test text report with over-budget tenant."""
    cost_events_file = tmp_path / "cost_events.jsonl"
    os.environ["COST_EVENTS_PATH"] = str(cost_events_file)
    os.environ["GOVERNANCE_EVENTS_PATH"] = str(tmp_path / "governance.jsonl")
    os.environ["TENANT_BUDGET_DAILY_DEFAULT"] = "5.0"
    os.environ["TENANT_BUDGET_MONTHLY_DEFAULT"] = "100.0"

    now = datetime.now(UTC).isoformat()

    with open(cost_events_file, "w") as f:
        # Tenant over daily budget
        f.write(json.dumps({"timestamp": now, "tenant": "tenant-1", "cost_estimate": 10.0}) + "\n")

    print_text_report(days=30)

    captured = capsys.readouterr()

    assert "🚨" in captured.out  # Over budget icon


def test_print_text_report_with_anomalies(tmp_path, capsys):
    """Test text report displaying anomalies."""
    cost_events_file = tmp_path / "cost_events.jsonl"
    os.environ["COST_EVENTS_PATH"] = str(cost_events_file)
    os.environ["GOVERNANCE_EVENTS_PATH"] = str(tmp_path / "governance.jsonl")
    os.environ["TENANT_BUDGET_DAILY_DEFAULT"] = "100.0"
    os.environ["TENANT_BUDGET_MONTHLY_DEFAULT"] = "2000.0"
    os.environ["ANOMALY_SIGMA"] = "2.0"
    os.environ["ANOMALY_MIN_EVENTS"] = "5"
    os.environ["ANOMALY_MIN_DOLLARS"] = "3.0"

    now = datetime.now(UTC)

    with open(cost_events_file, "w") as f:
        # Baseline: 7 days of $5/day
        for i in range(1, 8):
            timestamp = (now - timedelta(days=i)).isoformat()
            f.write(json.dumps({"timestamp": timestamp, "tenant": "tenant-1", "cost_estimate": 5.0}) + "\n")

        # Today: $50 (anomalous)
        today = now.isoformat()
        f.write(json.dumps({"timestamp": today, "tenant": "tenant-1", "cost_estimate": 50.0}) + "\n")

    print_text_report(days=30)

    captured = capsys.readouterr()

    assert "Cost Anomalies" in captured.out
    assert "tenant-1" in captured.out
    assert "Baseline:" in captured.out
    assert "Threshold:" in captured.out


def test_print_json_report_empty(tmp_path, capsys):
    """Test JSON report with no cost events."""
    cost_events_file = tmp_path / "cost_events.jsonl"
    os.environ["COST_EVENTS_PATH"] = str(cost_events_file)
    os.environ["GOVERNANCE_EVENTS_PATH"] = str(tmp_path / "governance.jsonl")

    cost_events_file.write_text("")

    print_json_report(days=30)

    captured = capsys.readouterr()
    report = json.loads(captured.out)

    assert report["window_days"] == 30
    assert report["tenant_filter"] is None
    assert report["global"]["daily"] == 0.0
    assert report["global"]["monthly"] == 0.0
    assert report["tenants"] == []
    assert report["anomalies"] == []


def test_print_json_report_with_data(tmp_path, capsys):
    """Test JSON report with cost events."""
    cost_events_file = tmp_path / "cost_events.jsonl"
    os.environ["COST_EVENTS_PATH"] = str(cost_events_file)
    os.environ["GOVERNANCE_EVENTS_PATH"] = str(tmp_path / "governance.jsonl")
    os.environ["TENANT_BUDGET_DAILY_DEFAULT"] = "100.0"
    os.environ["TENANT_BUDGET_MONTHLY_DEFAULT"] = "2000.0"

    now = datetime.now(UTC)

    with open(cost_events_file, "w") as f:
        # Today's events
        today = now.isoformat()
        f.write(json.dumps({"timestamp": today, "tenant": "tenant-1", "cost_estimate": 5.0}) + "\n")
        f.write(json.dumps({"timestamp": today, "tenant": "tenant-2", "cost_estimate": 3.0}) + "\n")

        # This month's events
        last_week = (now - timedelta(days=7)).isoformat()
        f.write(json.dumps({"timestamp": last_week, "tenant": "tenant-1", "cost_estimate": 10.0}) + "\n")

    print_json_report(days=30)

    captured = capsys.readouterr()
    report = json.loads(captured.out)

    assert report["window_days"] == 30
    assert report["global"]["daily"] == 8.0
    assert report["global"]["monthly"] == 18.0
    assert len(report["tenants"]) == 2

    tenant_1 = next(t for t in report["tenants"] if t["tenant"] == "tenant-1")
    assert tenant_1["daily_spend"] == 5.0
    assert tenant_1["monthly_spend"] == 15.0
    assert tenant_1["budget"]["daily"] == 100.0
    assert tenant_1["budget"]["monthly"] == 2000.0
    assert tenant_1["over_budget"]["daily"] is False
    assert tenant_1["over_budget"]["monthly"] is False


def test_print_json_report_filtered_tenant(tmp_path, capsys):
    """Test JSON report filtered to specific tenant."""
    cost_events_file = tmp_path / "cost_events.jsonl"
    os.environ["COST_EVENTS_PATH"] = str(cost_events_file)
    os.environ["GOVERNANCE_EVENTS_PATH"] = str(tmp_path / "governance.jsonl")
    os.environ["TENANT_BUDGET_DAILY_DEFAULT"] = "100.0"
    os.environ["TENANT_BUDGET_MONTHLY_DEFAULT"] = "2000.0"

    now = datetime.now(UTC).isoformat()

    with open(cost_events_file, "w") as f:
        f.write(json.dumps({"timestamp": now, "tenant": "tenant-1", "cost_estimate": 5.0}) + "\n")
        f.write(json.dumps({"timestamp": now, "tenant": "tenant-2", "cost_estimate": 3.0}) + "\n")

    print_json_report(tenant="tenant-1", days=30)

    captured = capsys.readouterr()
    report = json.loads(captured.out)

    assert report["tenant_filter"] == "tenant-1"
    assert len(report["tenants"]) == 1
    assert report["tenants"][0]["tenant"] == "tenant-1"


def test_print_json_report_over_budget(tmp_path, capsys):
    """Test JSON report with over-budget tenant."""
    cost_events_file = tmp_path / "cost_events.jsonl"
    os.environ["COST_EVENTS_PATH"] = str(cost_events_file)
    os.environ["GOVERNANCE_EVENTS_PATH"] = str(tmp_path / "governance.jsonl")
    os.environ["TENANT_BUDGET_DAILY_DEFAULT"] = "5.0"
    os.environ["TENANT_BUDGET_MONTHLY_DEFAULT"] = "100.0"

    now = datetime.now(UTC).isoformat()

    with open(cost_events_file, "w") as f:
        # Tenant over daily budget
        f.write(json.dumps({"timestamp": now, "tenant": "tenant-1", "cost_estimate": 10.0}) + "\n")

    print_json_report(days=30)

    captured = capsys.readouterr()
    report = json.loads(captured.out)

    tenant_1 = report["tenants"][0]
    assert tenant_1["over_budget"]["daily"] is True
    assert tenant_1["over_budget"]["monthly"] is False


def test_print_json_report_with_anomalies(tmp_path, capsys):
    """Test JSON report including anomalies."""
    cost_events_file = tmp_path / "cost_events.jsonl"
    os.environ["COST_EVENTS_PATH"] = str(cost_events_file)
    os.environ["GOVERNANCE_EVENTS_PATH"] = str(tmp_path / "governance.jsonl")
    os.environ["TENANT_BUDGET_DAILY_DEFAULT"] = "100.0"
    os.environ["TENANT_BUDGET_MONTHLY_DEFAULT"] = "2000.0"
    os.environ["ANOMALY_SIGMA"] = "2.0"
    os.environ["ANOMALY_MIN_EVENTS"] = "5"
    os.environ["ANOMALY_MIN_DOLLARS"] = "3.0"

    now = datetime.now(UTC)

    with open(cost_events_file, "w") as f:
        # Baseline: 7 days of $5/day
        for i in range(1, 8):
            timestamp = (now - timedelta(days=i)).isoformat()
            f.write(json.dumps({"timestamp": timestamp, "tenant": "tenant-1", "cost_estimate": 5.0}) + "\n")

        # Today: $50 (anomalous)
        today = now.isoformat()
        f.write(json.dumps({"timestamp": today, "tenant": "tenant-1", "cost_estimate": 50.0}) + "\n")

    print_json_report(days=30)

    captured = capsys.readouterr()
    report = json.loads(captured.out)

    assert len(report["anomalies"]) == 1
    assert report["anomalies"][0]["tenant"] == "tenant-1"
    assert report["anomalies"][0]["today_spend"] == 50.0
    # Note: baseline includes today, so mean won't be exactly 5.0
    assert report["anomalies"][0]["baseline_mean"] > 5.0
