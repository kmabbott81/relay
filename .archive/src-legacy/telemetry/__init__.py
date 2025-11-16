"""Telemetry module for observability (noop by default).

Sprint 46: Factory pattern for backend selection.
Sprint 47: OpenTelemetry tracing support.
Sprint 48: Hybrid backend (Prometheus + OpenTelemetry).

Backends:
- noop: No-op (default when TELEMETRY_ENABLED=false)
- prom: Prometheus metrics only (TELEMETRY_BACKEND=prom)
- otel: OpenTelemetry traces only (TELEMETRY_BACKEND=otel)
- hybrid: Prometheus metrics + OpenTelemetry traces (TELEMETRY_BACKEND=hybrid)
"""
from __future__ import annotations

import logging
import os

_LOG = logging.getLogger(__name__)


def init_telemetry() -> None:
    """Initialize telemetry backend based on environment configuration.

    Environment variables:
    - TELEMETRY_ENABLED: Enable/disable telemetry (default: false)
    - TELEMETRY_BACKEND: Backend to use (noop|prom|otel|hybrid, default: noop)

    Safe to call multiple times (idempotent).
    """
    enabled = str(os.getenv("TELEMETRY_ENABLED", "false")).lower() in {"1", "true", "yes"}

    if not enabled:
        _LOG.debug("Telemetry disabled (TELEMETRY_ENABLED=false)")
        return

    backend = os.getenv("TELEMETRY_BACKEND", "noop").lower()

    if backend == "prom":
        from .prom import init_prometheus

        init_prometheus()
        _LOG.info("Telemetry initialized: backend=prometheus")

    elif backend == "otel":
        from .otel import init_opentelemetry

        init_opentelemetry()
        _LOG.info("Telemetry initialized: backend=opentelemetry")

    elif backend == "hybrid":
        # Sprint 48: Hybrid backend (Prometheus + OpenTelemetry)
        from .otel import init_opentelemetry
        from .prom import init_prometheus

        init_prometheus()
        init_opentelemetry()
        _LOG.info("Telemetry initialized: backend=hybrid (prometheus + opentelemetry)")

    elif backend == "noop":
        from .noop import init_noop_if_enabled

        init_noop_if_enabled()

    else:
        _LOG.warning("Unknown telemetry backend '%s', using noop", backend)
        from .noop import init_noop_if_enabled

        init_noop_if_enabled()


# Backwards compatibility: keep old function name
def init_noop_if_enabled() -> None:
    """Deprecated: Use init_telemetry() instead.

    This function is kept for backwards compatibility with Sprint 42 code.
    """
    from .noop import init_noop_if_enabled as _noop_init

    _noop_init()


# Export metrics for direct access
def _get_oauth_events():
    """Get OAuth events counter (lazy access)."""
    from .prom import _oauth_events

    return _oauth_events


# Create a proxy object for oauth_events
class _OAuthEventsProxy:
    def labels(self, provider: str, event: str):
        counter = _get_oauth_events()
        if counter:
            return counter.labels(provider=provider, event=event)
        # Return noop object if not initialized
        return _NoopCounter()


class _NoopCounter:
    def inc(self, amount: int = 1):
        pass


oauth_events = _OAuthEventsProxy()

__all__ = ["init_telemetry", "init_noop_if_enabled", "oauth_events"]
