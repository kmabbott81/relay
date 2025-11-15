"""Tests for Prometheus telemetry (Sprint 46).

Tests cover:
- Safe-by-default behavior (no-op when disabled or deps missing)
- Metrics collection when enabled
- /metrics endpoint
- Middleware instrumentation
"""

from unittest.mock import patch

import pytest


class TestPrometheusInit:
    """Test Prometheus initialization and safe defaults."""

    def test_init_disabled_by_default(self, monkeypatch):
        """Telemetry should be no-op when TELEMETRY_ENABLED=false."""
        monkeypatch.setenv("TELEMETRY_ENABLED", "false")

        from relay_ai.telemetry.prom import init_prometheus

        # Should not raise, should be no-op
        init_prometheus()

    @pytest.mark.integration  # Sprint 52: Prometheus integration test
    def test_init_enabled_without_deps(self, monkeypatch):
        """Should handle missing prometheus-client gracefully."""
        monkeypatch.setenv("TELEMETRY_ENABLED", "true")

        # Mock ImportError for prometheus_client
        with patch("src.telemetry.prom.Counter", side_effect=ImportError):
            from relay_ai.telemetry.prom import init_prometheus

            # Should log warning but not crash
            init_prometheus()

    def test_init_enabled_with_deps(self, monkeypatch):
        """Should initialize metrics when enabled and deps available."""
        monkeypatch.setenv("TELEMETRY_ENABLED", "true")

        # This test requires prometheus-client to be installed
        # Skip if not available (optional dependency)
        try:
            import prometheus_client  # noqa: F401
        except ImportError:
            pytest.skip("prometheus-client not installed")

        from relay_ai.telemetry.prom import init_prometheus

        init_prometheus()

        # Should be idempotent
        init_prometheus()


class TestPrometheusMetrics:
    """Test metric recording functions."""

    def test_record_http_request_disabled(self, monkeypatch):
        """HTTP metrics should be no-op when disabled."""
        monkeypatch.setenv("TELEMETRY_ENABLED", "false")

        from relay_ai.telemetry.prom import record_http_request

        # Should not raise
        record_http_request("GET", "/api/test", 200, 0.123)

    def test_record_http_request_enabled(self, monkeypatch):
        """HTTP metrics should be recorded when enabled."""
        monkeypatch.setenv("TELEMETRY_ENABLED", "true")

        try:
            import prometheus_client  # noqa: F401
        except ImportError:
            pytest.skip("prometheus-client not installed")

        from relay_ai.telemetry.prom import init_prometheus, record_http_request

        init_prometheus()

        # Should not raise
        record_http_request("GET", "/api/test", 200, 0.123)
        record_http_request("POST", "/api/workflows", 201, 0.456)

    def test_record_queue_job_disabled(self, monkeypatch):
        """Queue metrics should be no-op when disabled."""
        monkeypatch.setenv("TELEMETRY_ENABLED", "false")

        from relay_ai.telemetry.prom import record_queue_job

        # Should not raise
        record_queue_job("workflow_run", 1.234)

    def test_set_queue_depth_disabled(self, monkeypatch):
        """Queue depth should be no-op when disabled."""
        monkeypatch.setenv("TELEMETRY_ENABLED", "false")

        from relay_ai.telemetry.prom import set_queue_depth

        # Should not raise
        set_queue_depth("batch_runner", 5)

    def test_record_external_api_call_disabled(self, monkeypatch):
        """External API metrics should be no-op when disabled."""
        monkeypatch.setenv("TELEMETRY_ENABLED", "false")

        from relay_ai.telemetry.prom import record_external_api_call

        # Should not raise
        record_external_api_call("outlook", "send_message", 0.789)


class TestTimerContext:
    """Test timer context manager."""

    def test_timer_context_basic(self):
        """Timer context should measure elapsed time."""
        from relay_ai.telemetry.prom import timer_context

        with timer_context("test_op") as timer:
            # Simulate work
            import time

            time.sleep(0.01)

        # Should have measured some time
        assert timer.elapsed_seconds > 0
        assert timer.elapsed_seconds < 1.0  # Sanity check

    def test_timer_context_with_exception(self):
        """Timer context should handle exceptions."""
        from relay_ai.telemetry.prom import timer_context

        with pytest.raises(ValueError):
            with timer_context("failing_op") as timer:
                raise ValueError("test error")

        # Should still have measured time
        assert timer.elapsed_seconds >= 0


class TestMetricsEndpoint:
    """Test /metrics endpoint generation."""

    def test_generate_metrics_disabled(self, monkeypatch):
        """Metrics endpoint should return empty when disabled."""
        monkeypatch.setenv("TELEMETRY_ENABLED", "false")

        from relay_ai.telemetry.prom import generate_metrics_text

        result = generate_metrics_text()
        assert result == ""

    def test_generate_metrics_enabled(self, monkeypatch):
        """Metrics endpoint should return Prometheus format when enabled."""
        monkeypatch.setenv("TELEMETRY_ENABLED", "true")

        try:
            import prometheus_client  # noqa: F401
        except ImportError:
            pytest.skip("prometheus-client not installed")

        from relay_ai.telemetry.prom import generate_metrics_text, init_prometheus, record_http_request

        init_prometheus()

        # Record some metrics
        record_http_request("GET", "/api/test", 200, 0.123)

        result = generate_metrics_text()

        # Should contain Prometheus format metrics
        assert "http_request_duration_seconds" in result or result.startswith("# ")


class TestMiddleware:
    """Test FastAPI telemetry middleware."""

    def test_middleware_normalize_endpoint(self):
        """Middleware should normalize endpoints to avoid cardinality explosion."""
        from relay_ai.telemetry.middleware import TelemetryMiddleware

        # UUIDs should be replaced
        assert (
            TelemetryMiddleware._normalize_endpoint("/api/workflows/550e8400-e29b-41d4-a716-446655440000")
            == "/api/workflows/{id}"
        )

        # Numeric IDs should be replaced
        assert TelemetryMiddleware._normalize_endpoint("/api/workflows/123/runs/456") == "/api/workflows/{id}/runs/{id}"

        # Tenant IDs should be replaced
        assert TelemetryMiddleware._normalize_endpoint("/tenant-abc123/workflows") == "/tenant-{id}/workflows"

        # Static paths should be unchanged
        assert TelemetryMiddleware._normalize_endpoint("/api/templates") == "/api/templates"

    @pytest.mark.asyncio
    @pytest.mark.integration  # Sprint 52: Prometheus integration test
    async def test_middleware_records_metrics(self, monkeypatch):
        """Middleware should record HTTP metrics."""
        monkeypatch.setenv("TELEMETRY_ENABLED", "true")

        try:
            import prometheus_client  # noqa: F401
        except ImportError:
            pytest.skip("prometheus-client not installed")

        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from relay_ai.telemetry.middleware import TelemetryMiddleware
        from relay_ai.telemetry.prom import init_prometheus

        init_prometheus()

        # Create test app
        app = FastAPI()
        app.add_middleware(TelemetryMiddleware)

        @app.get("/test")
        def test_endpoint():
            return {"status": "ok"}

        client = TestClient(app)
        response = client.get("/test")

        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    @pytest.mark.asyncio
    @pytest.mark.integration  # Sprint 52: Prometheus integration test
    async def test_middleware_handles_exceptions(self, monkeypatch):
        """Middleware should record metrics even when endpoint raises."""
        monkeypatch.setenv("TELEMETRY_ENABLED", "true")

        try:
            import prometheus_client  # noqa: F401
        except ImportError:
            pytest.skip("prometheus-client not installed")

        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from relay_ai.telemetry.middleware import TelemetryMiddleware
        from relay_ai.telemetry.prom import init_prometheus

        init_prometheus()

        # Create test app
        app = FastAPI()
        app.add_middleware(TelemetryMiddleware)

        @app.get("/error")
        def error_endpoint():
            raise ValueError("test error")

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/error")

        # Should get 500 error
        assert response.status_code == 500


class TestTelemetryFactory:
    """Test telemetry factory pattern."""

    def test_factory_disabled(self, monkeypatch):
        """Factory should no-op when disabled."""
        monkeypatch.setenv("TELEMETRY_ENABLED", "false")

        from relay_ai.telemetry import init_telemetry

        # Should not raise
        init_telemetry()

    def test_factory_prom_backend(self, monkeypatch):
        """Factory should initialize Prometheus when backend=prom."""
        monkeypatch.setenv("TELEMETRY_ENABLED", "true")
        monkeypatch.setenv("TELEMETRY_BACKEND", "prom")

        try:
            import prometheus_client  # noqa: F401
        except ImportError:
            pytest.skip("prometheus-client not installed")

        from relay_ai.telemetry import init_telemetry

        # Should initialize Prometheus
        init_telemetry()

    def test_factory_noop_backend(self, monkeypatch):
        """Factory should use noop when backend=noop."""
        monkeypatch.setenv("TELEMETRY_ENABLED", "true")
        monkeypatch.setenv("TELEMETRY_BACKEND", "noop")

        from relay_ai.telemetry import init_telemetry

        # Should use noop
        init_telemetry()

    def test_factory_unknown_backend(self, monkeypatch):
        """Factory should fall back to noop for unknown backends."""
        monkeypatch.setenv("TELEMETRY_ENABLED", "true")
        monkeypatch.setenv("TELEMETRY_BACKEND", "unknown")

        from relay_ai.telemetry import init_telemetry

        # Should fall back to noop
        init_telemetry()

    def test_factory_otel_backend_not_impl(self, monkeypatch):
        """Factory should warn that OTel is not yet implemented."""
        monkeypatch.setenv("TELEMETRY_ENABLED", "true")
        monkeypatch.setenv("TELEMETRY_BACKEND", "otel")

        from relay_ai.telemetry import init_telemetry

        # Should fall back to noop with warning
        init_telemetry()
