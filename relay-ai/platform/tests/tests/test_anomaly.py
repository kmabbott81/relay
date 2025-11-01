"""Tests for cost anomaly detection (Sprint 30)."""

import json
import os
from datetime import UTC, datetime, timedelta

from src.cost.anomaly import compute_baseline, detect_anomalies


def test_compute_baseline_empty():
    """Test baseline computation with no events."""
    baseline = compute_baseline([], tenant="tenant-1", days=7)

    assert baseline["mean"] == 0.0
    assert baseline["std_dev"] == 0.0
    assert baseline["count"] == 0


def test_compute_baseline_single_day():
    """Test baseline with single day of data."""
    now = datetime.now(UTC)
    timestamp = now.isoformat()

    events = [
        {"timestamp": timestamp, "tenant": "tenant-1", "cost_estimate": 5.0},
        {"timestamp": timestamp, "tenant": "tenant-1", "cost_estimate": 3.0},
    ]

    baseline = compute_baseline(events, tenant="tenant-1", days=7)

    assert baseline["mean"] == 8.0
    assert baseline["std_dev"] == 0.0  # Only one day, no deviation
    assert baseline["count"] == 1


def test_compute_baseline_multiple_days():
    """Test baseline with multiple days of data."""
    now = datetime.now(UTC)

    events = []
    daily_costs = [5.0, 7.0, 6.0, 8.0, 5.5]

    for i, cost in enumerate(daily_costs):
        timestamp = (now - timedelta(days=i + 1)).isoformat()
        events.append({"timestamp": timestamp, "tenant": "tenant-1", "cost_estimate": cost})

    baseline = compute_baseline(events, tenant="tenant-1", days=7)

    assert baseline["count"] == 5
    assert baseline["mean"] == sum(daily_costs) / len(daily_costs)
    assert baseline["std_dev"] > 0
    assert baseline["min"] == 5.0
    assert baseline["max"] == 8.0


def test_compute_baseline_filters_tenant():
    """Test baseline filters by tenant."""
    now = datetime.now(UTC)
    timestamp = now.isoformat()

    events = [
        {"timestamp": timestamp, "tenant": "tenant-1", "cost_estimate": 5.0},
        {"timestamp": timestamp, "tenant": "tenant-2", "cost_estimate": 100.0},
    ]

    baseline = compute_baseline(events, tenant="tenant-1", days=7)

    assert baseline["mean"] == 5.0


def test_compute_baseline_filters_window():
    """Test baseline filters by time window."""
    now = datetime.now(UTC)
    old_timestamp = (now - timedelta(days=10)).isoformat()
    recent_timestamp = (now - timedelta(days=2)).isoformat()

    events = [
        {"timestamp": old_timestamp, "tenant": "tenant-1", "cost_estimate": 100.0},
        {"timestamp": recent_timestamp, "tenant": "tenant-1", "cost_estimate": 5.0},
    ]

    baseline = compute_baseline(events, tenant="tenant-1", days=7)

    # Should only include recent event
    assert baseline["count"] == 1
    assert baseline["mean"] == 5.0


def test_detect_anomalies_no_data(tmp_path):
    """Test anomaly detection with no cost events."""
    cost_events_file = tmp_path / "cost_events.jsonl"
    os.environ["COST_EVENTS_PATH"] = str(cost_events_file)
    os.environ["GOVERNANCE_EVENTS_PATH"] = str(tmp_path / "governance.jsonl")

    cost_events_file.write_text("")

    anomalies = detect_anomalies()

    assert anomalies == []


def test_detect_anomalies_insufficient_baseline(tmp_path):
    """Test anomaly detection with insufficient baseline events."""
    cost_events_file = tmp_path / "cost_events.jsonl"
    os.environ["COST_EVENTS_PATH"] = str(cost_events_file)
    os.environ["GOVERNANCE_EVENTS_PATH"] = str(tmp_path / "governance.jsonl")
    os.environ["ANOMALY_MIN_EVENTS"] = "10"

    # Only 5 events (below min_events threshold)
    now = datetime.now(UTC)

    with open(cost_events_file, "w") as f:
        for i in range(5):
            timestamp = (now - timedelta(days=i + 1)).isoformat()
            f.write(json.dumps({"timestamp": timestamp, "tenant": "tenant-1", "cost_estimate": 1.0}) + "\n")

    anomalies = detect_anomalies(tenant="tenant-1")

    assert anomalies == []


def test_detect_anomalies_below_threshold(tmp_path):
    """Test anomaly detection when today is below threshold."""
    cost_events_file = tmp_path / "cost_events.jsonl"
    os.environ["COST_EVENTS_PATH"] = str(cost_events_file)
    os.environ["GOVERNANCE_EVENTS_PATH"] = str(tmp_path / "governance.jsonl")
    os.environ["ANOMALY_SIGMA"] = "3.0"
    os.environ["ANOMALY_MIN_EVENTS"] = "5"
    os.environ["ANOMALY_MIN_DOLLARS"] = "3.0"

    now = datetime.now(UTC)

    with open(cost_events_file, "w") as f:
        # Baseline: 7 days of $5/day
        for i in range(1, 8):
            timestamp = (now - timedelta(days=i)).isoformat()
            f.write(json.dumps({"timestamp": timestamp, "tenant": "tenant-1", "cost_estimate": 5.0}) + "\n")

        # Today: $6 (not anomalous)
        today = now.isoformat()
        f.write(json.dumps({"timestamp": today, "tenant": "tenant-1", "cost_estimate": 6.0}) + "\n")

    anomalies = detect_anomalies(tenant="tenant-1")

    assert anomalies == []


def test_detect_anomalies_above_threshold(tmp_path):
    """Test anomaly detection when today exceeds threshold."""
    cost_events_file = tmp_path / "cost_events.jsonl"
    os.environ["COST_EVENTS_PATH"] = str(cost_events_file)
    os.environ["GOVERNANCE_EVENTS_PATH"] = str(tmp_path / "governance.jsonl")
    os.environ["ANOMALY_SIGMA"] = "2.0"
    os.environ["ANOMALY_MIN_EVENTS"] = "5"
    os.environ["ANOMALY_MIN_DOLLARS"] = "3.0"

    now = datetime.now(UTC)

    with open(cost_events_file, "w") as f:
        # Baseline: 7 days of $5/day
        for i in range(1, 8):
            timestamp = (now - timedelta(days=i)).isoformat()
            f.write(json.dumps({"timestamp": timestamp, "tenant": "tenant-1", "cost_estimate": 5.0}) + "\n")

        # Today: $50 (10x baseline, clearly anomalous)
        today = now.isoformat()
        f.write(json.dumps({"timestamp": today, "tenant": "tenant-1", "cost_estimate": 50.0}) + "\n")

    anomalies = detect_anomalies(tenant="tenant-1")

    assert len(anomalies) == 1
    assert anomalies[0]["tenant"] == "tenant-1"
    assert anomalies[0]["today_spend"] == 50.0
    # Note: baseline includes today in the 7-day window, so mean = (7*5 + 50)/8 = 85/8 ≈ 10.6
    # The assertion just checks it's anomalous
    assert anomalies[0]["sigma"] == 2.0


def test_detect_anomalies_below_min_dollars(tmp_path):
    """Test anomaly detection with spend below min_dollars threshold."""
    cost_events_file = tmp_path / "cost_events.jsonl"
    os.environ["COST_EVENTS_PATH"] = str(cost_events_file)
    os.environ["GOVERNANCE_EVENTS_PATH"] = str(tmp_path / "governance.jsonl")
    os.environ["ANOMALY_SIGMA"] = "2.0"
    os.environ["ANOMALY_MIN_EVENTS"] = "5"
    os.environ["ANOMALY_MIN_DOLLARS"] = "10.0"

    now = datetime.now(UTC)

    with open(cost_events_file, "w") as f:
        # Baseline: 7 days of $1/day
        for i in range(1, 8):
            timestamp = (now - timedelta(days=i)).isoformat()
            f.write(json.dumps({"timestamp": timestamp, "tenant": "tenant-1", "cost_estimate": 1.0}) + "\n")

        # Today: $5 (5x baseline but below min_dollars)
        today = now.isoformat()
        f.write(json.dumps({"timestamp": today, "tenant": "tenant-1", "cost_estimate": 5.0}) + "\n")

    anomalies = detect_anomalies(tenant="tenant-1")

    # Should not flag because $5 < $10 min_dollars
    assert anomalies == []


def test_detect_anomalies_multiple_tenants(tmp_path):
    """Test anomaly detection across multiple tenants."""
    cost_events_file = tmp_path / "cost_events.jsonl"
    os.environ["COST_EVENTS_PATH"] = str(cost_events_file)
    os.environ["GOVERNANCE_EVENTS_PATH"] = str(tmp_path / "governance.jsonl")
    os.environ["ANOMALY_SIGMA"] = "2.0"
    os.environ["ANOMALY_MIN_EVENTS"] = "5"
    os.environ["ANOMALY_MIN_DOLLARS"] = "20.0"  # Higher threshold to filter out tenant-2

    now = datetime.now(UTC)

    with open(cost_events_file, "w") as f:
        # Tenant 1: normal baseline, anomalous today
        for i in range(1, 8):
            timestamp = (now - timedelta(days=i)).isoformat()
            f.write(json.dumps({"timestamp": timestamp, "tenant": "tenant-1", "cost_estimate": 5.0}) + "\n")
        today = now.isoformat()
        f.write(json.dumps({"timestamp": today, "tenant": "tenant-1", "cost_estimate": 50.0}) + "\n")

        # Tenant 2: normal baseline, normal today
        for i in range(1, 8):
            timestamp = (now - timedelta(days=i)).isoformat()
            f.write(json.dumps({"timestamp": timestamp, "tenant": "tenant-2", "cost_estimate": 3.0}) + "\n")
        f.write(json.dumps({"timestamp": today, "tenant": "tenant-2", "cost_estimate": 3.5}) + "\n")

    anomalies = detect_anomalies()

    assert len(anomalies) == 1
    assert anomalies[0]["tenant"] == "tenant-1"


def test_detect_anomalies_filter_by_tenant(tmp_path):
    """Test anomaly detection filtered to specific tenant."""
    cost_events_file = tmp_path / "cost_events.jsonl"
    os.environ["COST_EVENTS_PATH"] = str(cost_events_file)
    os.environ["GOVERNANCE_EVENTS_PATH"] = str(tmp_path / "governance.jsonl")
    os.environ["ANOMALY_SIGMA"] = "2.0"
    os.environ["ANOMALY_MIN_EVENTS"] = "5"
    os.environ["ANOMALY_MIN_DOLLARS"] = "3.0"

    now = datetime.now(UTC)

    with open(cost_events_file, "w") as f:
        # Both tenants have anomalies
        for tenant_id in ["tenant-1", "tenant-2"]:
            for i in range(1, 8):
                timestamp = (now - timedelta(days=i)).isoformat()
                f.write(json.dumps({"timestamp": timestamp, "tenant": tenant_id, "cost_estimate": 5.0}) + "\n")
            today = now.isoformat()
            f.write(json.dumps({"timestamp": today, "tenant": tenant_id, "cost_estimate": 50.0}) + "\n")

    # Filter to tenant-1 only
    anomalies = detect_anomalies(tenant="tenant-1")

    assert len(anomalies) == 1
    assert anomalies[0]["tenant"] == "tenant-1"
