"""Unit tests for rollout gate.

Sprint 54: Test MinimalGate with mocked Redis.
"""

from relay_ai.rollout.minimal_gate import MinimalGate
from relay_ai.rollout.policy import gmail_policy


class FakeRedis(dict):
    """Fake Redis client for testing (backed by dict)."""

    def get(self, k):
        """Get value from fake Redis."""
        val = super().get(k, None)
        # Redis client returns bytes or None
        if val is None:
            return None
        return val if isinstance(val, bytes) else val.encode()


class TestMinimalGatePercent:
    """Test MinimalGate percentage reading."""

    def test_percent_reads_redis_with_cache(self):
        """Test that percent reads from Redis and caches result."""
        r = FakeRedis(**{"flags:google:rollout_percent": b"10"})
        gate = MinimalGate(r, cache_ttl_sec=3600)

        # First read should hit Redis
        assert gate.percent("google") == 10

        # Second read should hit cache (change Redis value)
        r["flags:google:rollout_percent"] = b"50"
        assert gate.percent("google") == 10  # Still cached

    def test_percent_falls_back_to_env(self, monkeypatch):
        """Test that percent falls back to env var if Redis key missing."""
        r = FakeRedis()  # Empty Redis
        gate = MinimalGate(r)

        # Set env var
        monkeypatch.setenv("FLAGS_GOOGLE_ROLLOUT_PERCENT", "25")

        assert gate.percent("google") == 25

    def test_percent_clamps_to_0_100(self):
        """Test that percent is clamped to 0-100 range."""
        r = FakeRedis(**{"flags:test:rollout_percent": b"150"})
        gate = MinimalGate(r)

        assert gate.percent("test") == 100  # Clamped to 100

        r["flags:test:rollout_percent"] = b"-10"
        gate._cache.clear()  # Clear cache
        assert gate.percent("test") == 0  # Clamped to 0

    def test_percent_handles_invalid_value(self):
        """Test that percent handles non-numeric values gracefully."""
        r = FakeRedis(**{"flags:test:rollout_percent": b"invalid"})
        gate = MinimalGate(r)

        assert gate.percent("test") == 0  # Default to 0 on error


class TestMinimalGateAllow:
    """Test MinimalGate allow decisions."""

    def test_allow_obeys_zero_percent(self, monkeypatch):
        """Test that 0% rollout blocks all requests."""
        r = FakeRedis(**{"flags:google:rollout_percent": b"0"})
        gate = MinimalGate(r)

        # Force randomness to always win (but should still block due to 0%)
        monkeypatch.setattr("random.randint", lambda a, b: 1)

        assert gate.allow("google", {}) is False

    def test_allow_obeys_hundred_percent(self, monkeypatch):
        """Test that 100% rollout allows all requests."""
        r = FakeRedis(**{"flags:google:rollout_percent": b"100"})
        gate = MinimalGate(r)

        # Force randomness to always lose (but should still allow due to 100%)
        monkeypatch.setattr("random.randint", lambda a, b: 100)

        assert gate.allow("google", {}) is True

    def test_allow_respects_context(self):
        """Test that allow() accepts context parameter."""
        r = FakeRedis(**{"flags:google:rollout_percent": b"50"})
        gate = MinimalGate(r)

        context = {"actor_id": "user_123", "workspace_id": "ws_456"}

        # Should not raise exception
        result = gate.allow("google", context)
        assert isinstance(result, bool)


class TestGmailPolicy:
    """Test Gmail rollout policy logic."""

    def test_policy_rollback_on_error_rate_high(self):
        """Test that policy recommends rollback when error rate exceeds 1%."""
        metrics = {
            "error_rate_5m": 0.015,  # 1.5% error rate (bad)
            "latency_p95_5m": 0.3,  # 300ms P95 (good)
            "oauth_refresh_failures_15m": 2,  # 2 failures (good)
        }

        rec = gmail_policy(metrics, current_percent=50)

        assert rec.target_percent == 10  # Reduce to safe level
        assert "error_rate" in rec.reason.lower()

    def test_policy_rollback_on_latency_high(self):
        """Test that policy recommends rollback when P95 latency exceeds 500ms."""
        metrics = {
            "error_rate_5m": 0.005,  # 0.5% error rate (good)
            "latency_p95_5m": 0.8,  # 800ms P95 (bad)
            "oauth_refresh_failures_15m": 2,  # 2 failures (good)
        }

        rec = gmail_policy(metrics, current_percent=50)

        assert rec.target_percent == 10  # Reduce to safe level
        assert "latency" in rec.reason.lower()

    def test_policy_rollback_on_oauth_failures(self):
        """Test that policy recommends rollback when OAuth refresh failures spike."""
        metrics = {
            "error_rate_5m": 0.005,  # 0.5% error rate (good)
            "latency_p95_5m": 0.3,  # 300ms P95 (good)
            "oauth_refresh_failures_15m": 10,  # 10 failures (bad)
        }

        rec = gmail_policy(metrics, current_percent=50)

        assert rec.target_percent == 10  # Reduce to safe level
        assert "OAuth" in rec.reason

    def test_policy_promotes_0_to_10(self):
        """Test that policy promotes from 0% to 10% (initial canary)."""
        metrics = {
            "error_rate_5m": 0.0,
            "latency_p95_5m": 0.2,
            "oauth_refresh_failures_15m": 0,
        }

        rec = gmail_policy(metrics, current_percent=0)

        assert rec.target_percent == 10
        assert "canary" in rec.reason.lower()

    def test_policy_promotes_10_to_50(self):
        """Test that policy promotes from 10% to 50% when healthy."""
        metrics = {
            "error_rate_5m": 0.005,  # 0.5% (good)
            "latency_p95_5m": 0.3,  # 300ms (good)
            "oauth_refresh_failures_15m": 2,  # 2 failures (good)
        }

        rec = gmail_policy(metrics, current_percent=10)

        assert rec.target_percent == 50
        assert "ramp" in rec.reason.lower()

    def test_policy_promotes_50_to_100(self):
        """Test that policy promotes from 50% to 100% (full rollout)."""
        metrics = {
            "error_rate_5m": 0.005,  # 0.5% (good)
            "latency_p95_5m": 0.3,  # 300ms (good)
            "oauth_refresh_failures_15m": 2,  # 2 failures (good)
        }

        rec = gmail_policy(metrics, current_percent=50)

        assert rec.target_percent == 100
        assert "full" in rec.reason.lower()

    def test_policy_holds_at_100(self):
        """Test that policy holds at 100% when stable."""
        metrics = {
            "error_rate_5m": 0.005,  # 0.5% (good)
            "latency_p95_5m": 0.3,  # 300ms (good)
            "oauth_refresh_failures_15m": 2,  # 2 failures (good)
        }

        rec = gmail_policy(metrics, current_percent=100)

        assert rec.target_percent == 100
        assert "hold" in rec.reason.lower()
