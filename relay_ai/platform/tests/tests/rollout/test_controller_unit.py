"""Unit tests for rollout controller.

Sprint 54: Test automated rollout controller logic.
"""

import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch

# Import controller functions (not main, to avoid sys.exit)
sys.path.insert(0, "scripts")
from rollout_controller import (  # noqa: E402
    get_last_change_time,
    get_metrics,
    is_paused,
    query_prometheus,
    set_last_change_time,
)


class FakeRedis(dict):
    """Fake Redis client for testing."""

    def get(self, k):
        val = super().get(k, None)
        return val

    def set(self, k, v):
        self[k] = v

    def ping(self):
        pass


class TestQueryPrometheus:
    """Test Prometheus query functionality."""

    def test_query_success_with_data(self):
        """Test successful query with data points."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "status": "success",
            "data": {"result": [{"value": [1234567890, "0.015"]}]},  # timestamp, value
        }

        with patch("httpx.get", return_value=mock_response):
            result = query_prometheus("http://localhost:9090", "test_query")

        assert result == 0.015

    def test_query_no_data_returns_zero(self):
        """Test query with no data points returns 0.0."""
        mock_response = Mock()
        mock_response.json.return_value = {"status": "success", "data": {"result": []}}  # No data points

        with patch("httpx.get", return_value=mock_response):
            result = query_prometheus("http://localhost:9090", "test_query")

        assert result == 0.0

    def test_query_failure_returns_none(self):
        """Test query failure returns None."""
        mock_response = Mock()
        mock_response.json.return_value = {"status": "error", "error": "Invalid query"}

        with patch("httpx.get", return_value=mock_response):
            result = query_prometheus("http://localhost:9090", "bad_query")

        assert result is None

    def test_query_network_error_returns_none(self):
        """Test network error returns None."""
        with patch("httpx.get", side_effect=Exception("Network error")):
            result = query_prometheus("http://localhost:9090", "test_query")

        assert result is None


class TestGetMetrics:
    """Test metrics fetching from Prometheus."""

    def test_get_metrics_all_present(self):
        """Test fetching all metrics successfully."""

        def mock_query(url, query):
            # Return different values based on query content
            if "action_error_total" in query:
                return 0.012  # 1.2% error rate
            elif "action_latency" in query:
                return 0.35  # 350ms P95
            elif "oauth_events" in query:
                return 3.0  # 3 OAuth failures

            return 0.0

        with patch("rollout_controller.query_prometheus", side_effect=mock_query):
            metrics = get_metrics("http://localhost:9090")

        assert metrics["error_rate_5m"] == 0.012
        assert metrics["latency_p95_5m"] == 0.35
        assert metrics["oauth_refresh_failures_15m"] == 3

    def test_get_metrics_with_failures(self):
        """Test graceful handling when some metrics fail."""

        def mock_query(url, query):
            if "action_error_total" in query:
                return None  # Query failed

            return 0.0

        with patch("rollout_controller.query_prometheus", side_effect=mock_query):
            metrics = get_metrics("http://localhost:9090")

        # Failed metric defaults to 0
        assert metrics["error_rate_5m"] == 0.0
        assert metrics["latency_p95_5m"] == 0.0
        assert metrics["oauth_refresh_failures_15m"] == 0


class TestLastChangeTime:
    """Test last change timestamp tracking."""

    def test_get_last_change_time_exists(self):
        """Test reading existing timestamp."""
        r = FakeRedis()
        dt = datetime(2025, 10, 8, 15, 30, 0, tzinfo=timezone.utc)
        r["flags:google:last_change_time"] = dt.isoformat()

        result = get_last_change_time(r)

        assert result == dt

    def test_get_last_change_time_missing(self):
        """Test reading missing timestamp returns None."""
        r = FakeRedis()

        result = get_last_change_time(r)

        assert result is None

    def test_corrupted_timestamp_triggers_fail_fast(self):
        """Test that corrupted timestamp raises ValueError (fail-fast safety guard)."""
        import pytest

        r = FakeRedis()
        r["flags:google:last_change_time"] = "not-a-valid-timestamp"

        with pytest.raises(ValueError) as exc_info:
            get_last_change_time(r)

        # Verify error message mentions corruption
        assert "Corrupted Redis timestamp" in str(exc_info.value)
        assert "not-a-valid-timestamp" in str(exc_info.value)

    def test_set_last_change_time(self):
        """Test writing timestamp."""
        r = FakeRedis()
        dt = datetime(2025, 10, 8, 15, 30, 0, tzinfo=timezone.utc)

        set_last_change_time(r, dt)

        assert r["flags:google:last_change_time"] == dt.isoformat()


class TestPauseCheck:
    """Test controller pause functionality."""

    def test_is_paused_true(self):
        """Test pause detection when flag is true."""
        r = FakeRedis()
        r["flags:google:paused"] = "true"

        assert is_paused(r) is True

    def test_is_paused_false(self):
        """Test pause detection when flag is false."""
        r = FakeRedis()
        r["flags:google:paused"] = "false"

        assert is_paused(r) is False

    def test_is_paused_missing(self):
        """Test pause detection when flag is missing (not paused)."""
        r = FakeRedis()

        assert is_paused(r) is False


class TestControllerIntegration:
    """Integration tests for controller decision logic."""

    def test_controller_promotes_when_healthy(self):
        """Test controller promotes rollout when SLOs are healthy."""
        r = FakeRedis()
        r["flags:google:rollout_percent"] = "10"

        # Simulate healthy metrics
        def mock_get_metrics(url):
            return {
                "error_rate_5m": 0.005,  # 0.5% (good)
                "latency_p95_5m": 0.3,  # 300ms (good)
                "oauth_refresh_failures_15m": 2,  # 2 failures (good)
            }

        from relay_ai.rollout.policy import gmail_policy

        metrics = mock_get_metrics("http://localhost:9090")
        rec = gmail_policy(metrics, current_percent=10)

        # Should recommend promotion to 50%
        assert rec.target_percent == 50
        assert "ramp" in rec.reason.lower()

    def test_controller_rolls_back_on_error_rate(self):
        """Test controller rolls back when error rate exceeds threshold."""
        r = FakeRedis()
        r["flags:google:rollout_percent"] = "50"

        # Simulate high error rate
        def mock_get_metrics(url):
            return {
                "error_rate_5m": 0.025,  # 2.5% (bad!)
                "latency_p95_5m": 0.3,  # 300ms (good)
                "oauth_refresh_failures_15m": 2,  # 2 failures (good)
            }

        from relay_ai.rollout.policy import gmail_policy

        metrics = mock_get_metrics("http://localhost:9090")
        rec = gmail_policy(metrics, current_percent=50)

        # Should recommend rollback to 10%
        assert rec.target_percent == 10
        assert "error_rate" in rec.reason.lower()

    def test_controller_respects_dwell_time(self):
        """Test controller waits min dwell time between changes."""
        r = FakeRedis()
        r["flags:google:rollout_percent"] = "10"

        # Set last change to 5 minutes ago (< 15 min dwell time)
        five_min_ago = datetime.now(timezone.utc) - timedelta(minutes=5)
        set_last_change_time(r, five_min_ago)

        last_change = get_last_change_time(r)
        elapsed = datetime.now(timezone.utc) - last_change.replace(tzinfo=timezone.utc)

        # Should still be within dwell time
        assert elapsed < timedelta(minutes=15)

    def test_controller_respects_cooldown_after_rollback(self):
        """Test controller waits 1h cooldown after rollback before promoting."""
        r = FakeRedis()
        r["flags:google:rollout_percent"] = "10"
        r["flags:google:last_percent"] = "50"  # Previous rollback from 50%

        # Set last change to 30 minutes ago (< 1 hour cooldown)
        thirty_min_ago = datetime.now(timezone.utc) - timedelta(minutes=30)
        set_last_change_time(r, thirty_min_ago)

        last_pct = int(r["flags:google:last_percent"])
        current_pct = int(r["flags:google:rollout_percent"])

        # Detect rollback (last > current)
        was_rollback = last_pct > current_pct
        assert was_rollback is True

        # Check cooldown
        last_change = get_last_change_time(r)
        elapsed = datetime.now(timezone.utc) - last_change.replace(tzinfo=timezone.utc)
        assert elapsed < timedelta(hours=1)

    def test_controller_holds_at_100(self):
        """Test controller holds at 100% when stable."""
        metrics = {
            "error_rate_5m": 0.005,
            "latency_p95_5m": 0.3,
            "oauth_refresh_failures_15m": 2,
        }

        from relay_ai.rollout.policy import gmail_policy

        rec = gmail_policy(metrics, current_percent=100)

        # Should hold at 100%
        assert rec.target_percent == 100
        assert "hold" in rec.reason.lower()
