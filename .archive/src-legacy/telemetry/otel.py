"""OpenTelemetry tracing backend.

Sprint 47: Distributed tracing with OpenTelemetry SDK.

Environment Variables:
- OTEL_SERVICE_NAME: Service name for traces (default: djp-workflow)
- OTEL_EXPORTER: Exporter type (console|otlp, default: console)
- OTEL_ENDPOINT: OTLP endpoint URL (default: http://localhost:4318)
- OTEL_TRACE_SAMPLE: Trace sampling rate 0.0-1.0 (default: 0.1)
"""
from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from opentelemetry.sdk.trace import TracerProvider

_LOG = logging.getLogger(__name__)
_TRACER_PROVIDER: TracerProvider | None = None


def init_opentelemetry() -> None:
    """Initialize OpenTelemetry tracing.

    Sets up tracer provider with configured exporter and sampling.
    Safe to call multiple times (idempotent).
    """
    global _TRACER_PROVIDER

    if _TRACER_PROVIDER is not None:
        _LOG.debug("OpenTelemetry already initialized")
        return

    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

        # Configuration
        service_name = os.getenv("OTEL_SERVICE_NAME", "djp-workflow")
        exporter_type = os.getenv("OTEL_EXPORTER", "console").lower()
        otlp_endpoint = os.getenv("OTEL_ENDPOINT", "http://localhost:4318")
        sample_rate = float(os.getenv("OTEL_TRACE_SAMPLE", "0.1"))

        # Create resource
        resource = Resource.create(
            {
                "service.name": service_name,
                "service.version": "1.0.0",
                "deployment.environment": os.getenv("RAILWAY_ENVIRONMENT", "local"),
            }
        )

        # Create tracer provider with sampling
        from opentelemetry.sdk.trace.sampling import TraceIdRatioBased

        _TRACER_PROVIDER = TracerProvider(
            resource=resource,
            sampler=TraceIdRatioBased(sample_rate),
        )

        # Configure exporter
        if exporter_type == "otlp":
            exporter = OTLPSpanExporter(endpoint=f"{otlp_endpoint}/v1/traces")
            _LOG.info(f"Using OTLP exporter: {otlp_endpoint}")
        else:
            exporter = ConsoleSpanExporter()
            _LOG.info("Using console exporter (logs only)")

        # Add span processor
        _TRACER_PROVIDER.add_span_processor(BatchSpanProcessor(exporter))

        # Set global tracer provider
        trace.set_tracer_provider(_TRACER_PROVIDER)

        _LOG.info(
            f"OpenTelemetry initialized: service={service_name}, "
            f"exporter={exporter_type}, sample_rate={sample_rate}"
        )

    except ImportError as e:
        _LOG.warning(f"OpenTelemetry dependencies not installed: {e}")
    except Exception as e:
        _LOG.error(f"Failed to initialize OpenTelemetry: {e}")


def get_tracer(name: str = __name__):
    """Get a tracer instance.

    Args:
        name: Tracer name (usually __name__)

    Returns:
        Tracer instance or no-op tracer if not initialized
    """
    try:
        from opentelemetry import trace

        return trace.get_tracer(name)
    except ImportError:
        # Return no-op tracer if OpenTelemetry not available
        class NoOpTracer:
            """No-op tracer for when OpenTelemetry is not available."""

            def start_as_current_span(self, name: str, *args, **kwargs):
                """No-op context manager."""
                from contextlib import contextmanager

                @contextmanager
                def _noop():
                    yield None

                return _noop()

        return NoOpTracer()


__all__ = ["init_opentelemetry", "get_tracer"]
