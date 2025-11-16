"""Prometheus metrics exporter for DJP Workflow.

Sprint 46: Phase 1 (Metrics) implementation.

This module provides Prometheus metrics collection behind the TELEMETRY_ENABLED flag.
All instrumentation is safe-by-default: if the flag is false or prometheus-client
is not installed, all operations become no-ops.

Metrics (SLIs):
- http_request_duration_seconds: HTTP endpoint latency histogram
- http_requests_total: Request count by method/endpoint/status
- queue_job_latency_seconds: Background job processing time
- queue_depth_total: Current queue depth gauge
- external_api_calls_total: External API call counter by service
- external_api_duration_seconds: External API latency histogram
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

_LOG = logging.getLogger(__name__)

# Lazy imports - only load prometheus_client if telemetry is enabled
_PROM_AVAILABLE = False
_METRICS_INITIALIZED = False

# Metric instances (populated on init)
_http_request_duration = None
_http_requests_total = None
_queue_job_latency = None
_queue_depth = None
_external_api_calls = None
_external_api_duration = None
# Sprint 49 Phase B: Action metrics
_action_exec_total = None
_action_latency_seconds = None
_action_error_total = None
# Sprint 53 Phase B: OAuth metrics
_oauth_events = None
# Sprint 54: Gmail Rich Email metrics
_gmail_mime_build_seconds = None
_gmail_attachment_bytes_total = None
_gmail_inline_refs_total = None
_gmail_html_sanitization_changes_total = None
# Sprint 55: Outlook (Microsoft) Rich Email metrics
_outlook_graph_build_seconds = None
_outlook_attachment_bytes_total = None
_outlook_inline_refs_total = None
_outlook_html_sanitization_changes_total = None
# Sprint 54 Phase 4: Structured error tracking
_structured_error_total = None
# Sprint 54 Phase 4: Rollout controller gauge
_rollout_controller_percent = None
# Sprint 55 Week 3: Microsoft upload session metrics
_outlook_upload_session_total = None
_outlook_upload_session_create_seconds = None
_outlook_upload_bytes_total = None
_outlook_upload_chunk_seconds = None
_outlook_draft_created_total = None
_outlook_draft_create_seconds = None
_outlook_draft_sent_total = None
_outlook_draft_send_seconds = None
# Sprint 55 Week 3: AI Orchestrator v0.1 metrics
_ai_planner_seconds = None
_ai_tokens_total = None
_ai_jobs_total = None
_ai_job_latency_seconds = None
_ai_queue_depth = None
_security_decisions_total = None
# Sprint 60 Phase 1: Dual-write migration metrics
_ai_jobs_dual_write_total = None
# Sprint 60 Phase 2.2: Read-routing metrics
_relay_job_read_path_total = None
_relay_job_list_read_path_total = None
_relay_job_list_results_total = None
# Sprint 60 Phase 3: Backfill metrics
_relay_backfill_scanned_total = None
_relay_backfill_migrated_total = None
_relay_backfill_skipped_total = None
_relay_backfill_errors_total = None
_relay_backfill_duration_seconds = None


def _is_enabled() -> bool:
    """Check if telemetry is enabled via environment variable."""
    return str(os.getenv("TELEMETRY_ENABLED", "false")).lower() in {"1", "true", "yes"}


def init_prometheus() -> None:
    """Initialize Prometheus metrics collection if enabled.

    Safe to call multiple times (idempotent). If TELEMETRY_ENABLED=false
    or prometheus-client is not installed, this becomes a no-op.
    """
    global _PROM_AVAILABLE, _METRICS_INITIALIZED
    global _http_request_duration, _http_requests_total
    global _queue_job_latency, _queue_depth
    global _external_api_calls, _external_api_duration
    global _action_exec_total, _action_latency_seconds, _action_error_total
    global _oauth_events
    global _gmail_mime_build_seconds, _gmail_attachment_bytes_total
    global _gmail_inline_refs_total, _gmail_html_sanitization_changes_total
    global _outlook_graph_build_seconds, _outlook_attachment_bytes_total
    global _outlook_inline_refs_total, _outlook_html_sanitization_changes_total
    global _structured_error_total, _rollout_controller_percent
    global _outlook_upload_session_total, _outlook_upload_session_create_seconds
    global _outlook_upload_bytes_total, _outlook_upload_chunk_seconds
    global _outlook_draft_created_total, _outlook_draft_create_seconds
    global _outlook_draft_sent_total, _outlook_draft_send_seconds
    global _ai_planner_seconds, _ai_tokens_total, _ai_jobs_total
    global _ai_job_latency_seconds, _ai_queue_depth, _security_decisions_total
    global _ai_jobs_dual_write_total
    global _relay_job_read_path_total, _relay_job_list_read_path_total, _relay_job_list_results_total
    global _relay_backfill_scanned_total, _relay_backfill_migrated_total, _relay_backfill_skipped_total
    global _relay_backfill_errors_total, _relay_backfill_duration_seconds

    if not _is_enabled():
        _LOG.debug("Telemetry disabled, skipping Prometheus init")
        return

    if _METRICS_INITIALIZED:
        _LOG.debug("Prometheus metrics already initialized")
        return

    try:
        from prometheus_client import Counter, Gauge, Histogram

        _PROM_AVAILABLE = True

        # HTTP metrics
        _http_request_duration = Histogram(
            "http_request_duration_seconds",
            "HTTP request latency in seconds",
            ["method", "endpoint", "status_code"],
            buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
        )

        _http_requests_total = Counter(
            "http_requests_total",
            "Total HTTP requests by method, endpoint, and status code",
            ["method", "endpoint", "status_code"],
        )

        # Queue/worker metrics
        _queue_job_latency = Histogram(
            "queue_job_latency_seconds",
            "Background job processing time in seconds",
            ["job_type"],
            buckets=[0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0],
        )

        _queue_depth = Gauge(
            "queue_depth_total",
            "Current depth of background job queue",
            ["queue_name"],
        )

        # External API metrics
        _external_api_calls = Counter(
            "external_api_calls_total",
            "Total external API calls by service",
            ["service", "operation"],
        )

        _external_api_duration = Histogram(
            "external_api_duration_seconds",
            "External API call latency in seconds",
            ["service", "operation"],
            buckets=[0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0],
        )

        # Sprint 49 Phase B: Action metrics
        _action_exec_total = Counter(
            "action_exec_total",
            "Total action executions by provider, action, and status",
            ["provider", "action", "status"],
        )

        _action_latency_seconds = Histogram(
            "action_latency_seconds",
            "Action execution latency in seconds",
            ["provider", "action"],
            buckets=[0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0],
        )

        _action_error_total = Counter(
            "action_error_total",
            "Total action errors by provider, action, and reason",
            ["provider", "action", "reason"],
        )

        # Sprint 53 Phase B: OAuth metrics
        _oauth_events = Counter(
            "oauth_events_total",
            "OAuth flow events by provider and event type",
            ["provider", "event"],
        )

        # Sprint 54: Gmail Rich Email metrics
        _gmail_mime_build_seconds = Histogram(
            "gmail_mime_build_seconds",
            "Time to build MIME message in seconds",
            buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0],
        )

        _gmail_attachment_bytes_total = Counter(
            "gmail_attachment_bytes_total",
            "Total bytes of attachments processed",
            ["result"],  # accepted | rejected
        )

        _gmail_inline_refs_total = Counter(
            "gmail_inline_refs_total",
            "Inline image CID references",
            ["result"],  # matched | orphan_cid
        )

        _gmail_html_sanitization_changes_total = Counter(
            "gmail_html_sanitization_changes_total",
            "HTML sanitization changes made",
            ["change_type"],  # tag_removed | attr_removed | script_blocked | style_sanitized
        )

        # Sprint 55: Outlook (Microsoft) Rich Email metrics
        _outlook_graph_build_seconds = Histogram(
            "outlook_graph_build_seconds",
            "Time to build Graph API JSON message in seconds",
            buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0],
        )

        _outlook_attachment_bytes_total = Counter(
            "outlook_attachment_bytes_total",
            "Total bytes of attachments processed for Outlook",
            ["result"],  # accepted | rejected
        )

        _outlook_inline_refs_total = Counter(
            "outlook_inline_refs_total",
            "Inline image CID references for Outlook",
            ["result"],  # matched | orphan_cid
        )

        _outlook_html_sanitization_changes_total = Counter(
            "outlook_html_sanitization_changes_total",
            "HTML sanitization changes made for Outlook",
            ["change_type"],  # tag_removed | attr_removed | script_blocked | style_sanitized
        )

        # Sprint 54 Phase 4: Structured error tracking
        _structured_error_total = Counter(
            "structured_error_total",
            "Normalized structured errors emitted by adapters/validators",
            ["provider", "action", "code", "source"],
        )

        # Sprint 54 Phase 4: Rollout controller gauge
        _rollout_controller_percent = Gauge(
            "rollout_controller_percent",
            "Current rollout percentage for a feature",
            ["feature"],
        )

        # Sprint 55 Week 3: Microsoft upload session metrics
        _outlook_upload_session_total = Counter(
            "outlook_upload_session_total",
            "Total Microsoft Graph upload sessions",
            ["result"],  # started | completed | failed | error
        )

        _outlook_upload_session_create_seconds = Histogram(
            "outlook_upload_session_create_seconds",
            "Time to create upload session in seconds",
            buckets=[0.1, 0.25, 0.5, 1.0, 2.5, 5.0],
        )

        _outlook_upload_bytes_total = Counter(
            "outlook_upload_bytes_total",
            "Total bytes uploaded via Microsoft Graph upload sessions",
            ["result"],  # completed | failed
        )

        _outlook_upload_chunk_seconds = Histogram(
            "outlook_upload_chunk_seconds",
            "Microsoft Graph upload chunk duration in seconds",
            buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0],
        )

        _outlook_draft_created_total = Counter(
            "outlook_draft_created_total",
            "Total draft messages created",
            ["result"],  # success | error
        )

        _outlook_draft_create_seconds = Histogram(
            "outlook_draft_create_seconds",
            "Time to create draft message in seconds",
            buckets=[0.1, 0.25, 0.5, 1.0, 2.5, 5.0],
        )

        _outlook_draft_sent_total = Counter(
            "outlook_draft_sent_total",
            "Total draft messages sent",
            ["result"],  # success | error
        )

        _outlook_draft_send_seconds = Histogram(
            "outlook_draft_send_seconds",
            "Time to send draft message in seconds",
            buckets=[0.1, 0.25, 0.5, 1.0, 2.5, 5.0],
        )

        # Sprint 55 Week 3: AI Orchestrator v0.1 metrics
        _ai_planner_seconds = Histogram(
            "ai_planner_seconds",
            "AI planning duration in seconds",
            ["status"],  # ok | error | budget_exceeded
            buckets=[0.5, 1.0, 2.0, 5.0, 10.0, 30.0],
        )

        _ai_tokens_total = Counter(
            "ai_tokens_total",
            "AI token usage",
            ["type"],  # input | output
        )

        _ai_jobs_total = Counter(
            "ai_jobs_total",
            "AI orchestrator job executions",
            ["workspace_id", "status"],  # workspace_id | pending | completed | error
        )

        _ai_job_latency_seconds = Histogram(
            "ai_job_latency_seconds",
            "AI job execution latency in seconds",
            ["workspace_id"],  # workspace_id label
            buckets=[0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0],
        )

        _ai_queue_depth = Gauge(
            "ai_queue_depth",
            "Current AI job queue depth",
            ["workspace_id"],  # workspace_id label
        )

        _security_decisions_total = Counter(
            "security_decisions_total",
            "Security permission decisions",
            ["workspace_id", "result"],  # workspace_id | allowed | denied
        )

        # Sprint 60 Phase 1: Dual-write migration metrics
        _ai_jobs_dual_write_total = Counter(
            "ai_jobs_dual_write_total",
            "AI job dual-write attempts for schema migration",
            ["workspace_id", "result"],  # workspace_id | succeeded | failed
        )

        # Sprint 60 Phase 2.2: Read-routing metrics
        _relay_job_read_path_total = Counter(
            "relay_job_read_path_total",
            "AI job read path distribution (new schema, old schema fallback, or miss)",
            ["workspace_id", "path"],  # workspace_id | new | old | miss
        )

        _relay_job_list_read_path_total = Counter(
            "relay_job_list_read_path_total",
            "AI job list read path distribution (new schema only or mixed with fallback)",
            ["workspace_id", "path"],  # workspace_id | new | mixed
        )

        _relay_job_list_results_total = Counter(
            "relay_job_list_results_total",
            "Total number of job results returned by list operations",
            ["workspace_id"],  # workspace_id
        )

        # Sprint 60 Phase 3: Backfill metrics
        _relay_backfill_scanned_total = Counter(
            "relay_backfill_scanned_total",
            "Total old schema keys scanned during backfill",
            ["workspace_id"],  # workspace_id
        )

        _relay_backfill_migrated_total = Counter(
            "relay_backfill_migrated_total",
            "Total keys successfully migrated to new schema",
            ["workspace_id"],  # workspace_id
        )

        _relay_backfill_skipped_total = Counter(
            "relay_backfill_skipped_total",
            "Total keys skipped during backfill",
            ["workspace_id", "reason"],  # workspace_id | exists | invalid | error
        )

        _relay_backfill_errors_total = Counter(
            "relay_backfill_errors_total",
            "Total migration errors during backfill",
            ["workspace_id"],  # workspace_id
        )

        _relay_backfill_duration_seconds = Histogram(
            "relay_backfill_duration_seconds",
            "Backfill execution duration in seconds",
            buckets=[60, 300, 600, 1800, 3600, 7200, 14400],  # 1m, 5m, 10m, 30m, 1h, 2h, 4h
        )

        _METRICS_INITIALIZED = True
        _LOG.info("Prometheus metrics initialized (port configured via PROM_EXPORT_PORT, default 9090)")

    except ImportError:
        _LOG.warning(
            "prometheus-client not installed; telemetry will be no-op. "
            "Install with: pip install djp-workflow[observability]"
        )
        _PROM_AVAILABLE = False


def record_http_request(method: str, endpoint: str, status_code: int, duration_seconds: float) -> None:
    """Record HTTP request metrics.

    Args:
        method: HTTP method (GET, POST, etc.)
        endpoint: Endpoint path (e.g., /api/workflows)
        status_code: HTTP status code (200, 404, etc.)
        duration_seconds: Request duration in seconds
    """
    if not _PROM_AVAILABLE or not _METRICS_INITIALIZED:
        return

    try:
        _http_request_duration.labels(method=method, endpoint=endpoint, status_code=status_code).observe(
            duration_seconds
        )
        _http_requests_total.labels(method=method, endpoint=endpoint, status_code=status_code).inc()
    except Exception as exc:
        _LOG.warning("Failed to record HTTP request metric: %s", exc)


def record_queue_job(job_type: str, duration_seconds: float) -> None:
    """Record background job metrics.

    Args:
        job_type: Type of job (e.g., workflow_run, batch_publish)
        duration_seconds: Job processing time in seconds
    """
    if not _PROM_AVAILABLE or not _METRICS_INITIALIZED:
        return

    try:
        _queue_job_latency.labels(job_type=job_type).observe(duration_seconds)
    except Exception as exc:
        _LOG.warning("Failed to record queue job metric: %s", exc)


def set_queue_depth(queue_name: str, depth: int) -> None:
    """Set current queue depth gauge.

    Args:
        queue_name: Name of the queue (e.g., batch_runner)
        depth: Current number of jobs in queue
    """
    if not _PROM_AVAILABLE or not _METRICS_INITIALIZED:
        return

    try:
        _queue_depth.labels(queue_name=queue_name).set(depth)
    except Exception as exc:
        _LOG.warning("Failed to set queue depth metric: %s", exc)


def record_external_api_call(service: str, operation: str, duration_seconds: float) -> None:
    """Record external API call metrics.

    Args:
        service: Service name (outlook, teams, slack, etc.)
        operation: Operation name (send_message, fetch_emails, etc.)
        duration_seconds: API call duration in seconds
    """
    if not _PROM_AVAILABLE or not _METRICS_INITIALIZED:
        return

    try:
        _external_api_calls.labels(service=service, operation=operation).inc()
        _external_api_duration.labels(service=service, operation=operation).observe(duration_seconds)
    except Exception as exc:
        _LOG.warning("Failed to record external API metric: %s", exc)


class TimerContext:
    """Context manager for timing operations.

    Example:
        with timer_context("my_operation") as timer:
            # do work
            pass
        print(f"Operation took {timer.elapsed_seconds}s")
    """

    def __init__(self, label: str = "operation"):
        self.label = label
        self.start_time: float | None = None
        self.elapsed_seconds: float = 0.0

    def __enter__(self) -> TimerContext:
        self.start_time = time.perf_counter()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if self.start_time is not None:
            self.elapsed_seconds = time.perf_counter() - self.start_time


def timer_context(label: str = "operation") -> TimerContext:
    """Create a timer context manager.

    Args:
        label: Label for the operation being timed

    Returns:
        TimerContext instance
    """
    return TimerContext(label)


# Sprint 49 Phase B: Action metrics recording


def record_action_execution(provider: str, action: str, status: str, duration_seconds: float) -> None:
    """Record action execution metrics.

    Args:
        provider: Provider name (independent, microsoft, google)
        action: Action ID (e.g., webhook.save)
        status: Execution status (success, failed)
        duration_seconds: Execution duration in seconds
    """
    if not _PROM_AVAILABLE or not _METRICS_INITIALIZED:
        return

    try:
        _action_exec_total.labels(provider=provider, action=action, status=status).inc()
        _action_latency_seconds.labels(provider=provider, action=action).observe(duration_seconds)
    except Exception as exc:
        _LOG.warning("Failed to record action execution metric: %s", exc)


def record_action_error(provider: str, action: str, reason: str) -> None:
    """Record action error metrics.

    Args:
        provider: Provider name (independent, microsoft, google)
        action: Action ID (e.g., webhook.save)
        reason: Error reason (e.g., timeout, invalid_params)
    """
    if not _PROM_AVAILABLE or not _METRICS_INITIALIZED:
        return

    try:
        _action_error_total.labels(provider=provider, action=action, reason=reason).inc()
    except Exception as exc:
        _LOG.warning("Failed to record action error metric: %s", exc)


def generate_metrics_text() -> str:
    """Generate Prometheus metrics in text exposition format.

    Returns:
        Metrics text in Prometheus format, or empty string if disabled
    """
    if not _PROM_AVAILABLE or not _METRICS_INITIALIZED:
        return ""

    try:
        from prometheus_client import REGISTRY, generate_latest

        return generate_latest(REGISTRY).decode("utf-8")
    except Exception as exc:
        _LOG.error("Failed to generate metrics: %s", exc)
        return f"# Error generating metrics: {exc}\n"


def record_structured_error(provider: str, action: str, code: str, source: str) -> None:
    """Record structured error metrics.

    Args:
        provider: Provider name (e.g., "google")
        action: Action name (e.g., "gmail.send")
        code: Error code (e.g., "validation_error_attachment_too_large")
        source: Error source (e.g., "gmail.adapter", "gmail.mime", "gmail.validation")
    """
    if not _PROM_AVAILABLE or not _METRICS_INITIALIZED:
        return

    try:
        _structured_error_total.labels(provider=provider, action=action, code=code, source=source).inc()
    except Exception as exc:
        _LOG.warning("Failed to record structured error metric: %s", exc)


def set_rollout_percentage(feature: str, percentage: float) -> None:
    """Set rollout percentage gauge for a feature.

    Args:
        feature: Feature name (e.g., "google")
        percentage: Rollout percentage (0.0 to 100.0)
    """
    if not _PROM_AVAILABLE or not _METRICS_INITIALIZED:
        return

    try:
        _rollout_controller_percent.labels(feature=feature).set(percentage)
    except Exception as exc:
        _LOG.warning("Failed to set rollout percentage metric: %s", exc)


# Sprint 54: Gmail Rich Email metric exports
# These are exported for direct use in the MIME builder (google_mime.py)
# They are safe to import even if telemetry is disabled (will be None).

gmail_mime_build_seconds = _gmail_mime_build_seconds
gmail_attachment_bytes_total = _gmail_attachment_bytes_total
gmail_inline_refs_total = _gmail_inline_refs_total
gmail_html_sanitization_changes_total = _gmail_html_sanitization_changes_total

# Sprint 55: Outlook (Microsoft) Rich Email metric exports
# These are exported for direct use in the Graph builder (microsoft_graph.py)
# They are safe to import even if telemetry is disabled (will be None).

outlook_graph_build_seconds = _outlook_graph_build_seconds
outlook_attachment_bytes_total = _outlook_attachment_bytes_total
outlook_inline_refs_total = _outlook_inline_refs_total
outlook_html_sanitization_changes_total = _outlook_html_sanitization_changes_total

# Sprint 54 Phase 4: Structured error and rollout exports
structured_error_total = _structured_error_total
rollout_controller_percent = _rollout_controller_percent

# Sprint 55 Week 3: Microsoft upload session metric exports
# These are exported for direct use in the upload session module (microsoft_upload.py)
# They are safe to import even if telemetry is disabled (will be None).

outlook_upload_session_total = _outlook_upload_session_total
outlook_upload_session_create_seconds = _outlook_upload_session_create_seconds
outlook_upload_bytes_total = _outlook_upload_bytes_total
outlook_upload_chunk_seconds = _outlook_upload_chunk_seconds
outlook_draft_created_total = _outlook_draft_created_total
outlook_draft_create_seconds = _outlook_draft_create_seconds
outlook_draft_sent_total = _outlook_draft_sent_total
outlook_draft_send_seconds = _outlook_draft_send_seconds

# Sprint 55 Week 3: AI Orchestrator v0.1 metric exports
ai_planner_seconds = _ai_planner_seconds
ai_tokens_total = _ai_tokens_total
ai_jobs_total = _ai_jobs_total
ai_job_latency_seconds = _ai_job_latency_seconds
ai_queue_depth = _ai_queue_depth
security_decisions_total = _security_decisions_total

# Sprint 60 Phase 1: Dual-write migration metric exports
ai_jobs_dual_write_total = _ai_jobs_dual_write_total

# Sprint 60 Phase 3: Backfill metric exports
backfill_scanned_total = _relay_backfill_scanned_total
backfill_migrated_total = _relay_backfill_migrated_total
backfill_skipped_total = _relay_backfill_skipped_total
backfill_errors_total = _relay_backfill_errors_total
backfill_duration_seconds = _relay_backfill_duration_seconds


# Sprint 55 Week 3: AI Orchestrator v0.1 recording functions


def record_ai_planner(status: str, duration_seconds: float, workspace_id: str = "unknown") -> None:
    """Record AI planner execution metrics.

    Args:
        status: Planning status (ok, error, budget_exceeded)
        duration_seconds: Planning duration in seconds
        workspace_id: Workspace identifier (for S60 isolation)
    """
    if not _PROM_AVAILABLE or not _METRICS_INITIALIZED:
        return

    try:
        _ai_planner_seconds.labels(status=status).observe(duration_seconds)
    except Exception as exc:
        _LOG.warning("Failed to record AI planner metric: %s", exc)


def record_ai_tokens(tokens_input: int, tokens_output: int) -> None:
    """Record AI token usage metrics.

    Args:
        tokens_input: Input tokens consumed
        tokens_output: Output tokens generated
    """
    if not _PROM_AVAILABLE or not _METRICS_INITIALIZED:
        return

    try:
        _ai_tokens_total.labels(type="input").inc(tokens_input)
        _ai_tokens_total.labels(type="output").inc(tokens_output)
    except Exception as exc:
        _LOG.warning("Failed to record AI tokens metric: %s", exc)


def record_ai_job(workspace_id: str, status: str) -> None:
    """Record AI job execution metrics (workspace-scoped).

    Args:
        workspace_id: Workspace identifier
        status: Job status (pending, completed, error)
    """
    if not _PROM_AVAILABLE or not _METRICS_INITIALIZED:
        return

    try:
        _ai_jobs_total.labels(workspace_id=workspace_id, status=status).inc()
    except Exception as exc:
        _LOG.warning("Failed to record AI job metric: %s", exc)


def record_ai_job_latency(workspace_id: str, duration_seconds: float) -> None:
    """Record AI job execution latency (workspace-scoped).

    Args:
        workspace_id: Workspace identifier
        duration_seconds: Job execution duration in seconds
    """
    if not _PROM_AVAILABLE or not _METRICS_INITIALIZED:
        return

    try:
        _ai_job_latency_seconds.labels(workspace_id=workspace_id).observe(duration_seconds)
    except Exception as exc:
        _LOG.warning("Failed to record AI job latency metric: %s", exc)


def set_ai_queue_depth(workspace_id: str, depth: int) -> None:
    """Set AI job queue depth gauge (workspace-scoped).

    Args:
        workspace_id: Workspace identifier
        depth: Current number of jobs in queue for workspace
    """
    if not _PROM_AVAILABLE or not _METRICS_INITIALIZED:
        return

    try:
        _ai_queue_depth.labels(workspace_id=workspace_id).set(depth)
    except Exception as exc:
        _LOG.warning("Failed to set AI queue depth metric: %s", exc)


def record_security_decision(workspace_id: str, result: str) -> None:
    """Record security permission decision (workspace-scoped).

    Args:
        workspace_id: Workspace identifier
        result: Decision result (allowed, denied)
    """
    if not _PROM_AVAILABLE or not _METRICS_INITIALIZED:
        return

    try:
        _security_decisions_total.labels(workspace_id=workspace_id, result=result).inc()
    except Exception as exc:
        _LOG.warning("Failed to record security decision metric: %s", exc)


# Sprint 60 Phase 1: Dual-write migration recording function


def record_dual_write_attempt(workspace_id: str, result: str) -> None:
    """Record dual-write attempt for schema migration (Sprint 60 Phase 1).

    Args:
        workspace_id: Workspace identifier
        result: Dual-write result (succeeded, failed)
    """
    if not _PROM_AVAILABLE or not _METRICS_INITIALIZED:
        return

    try:
        _ai_jobs_dual_write_total.labels(workspace_id=workspace_id, result=result).inc()
    except Exception as exc:
        _LOG.warning("Failed to record dual-write attempt metric: %s", exc)


# Sprint 60 Phase 2.2: Read-routing recording functions


def record_job_read_path(workspace_id: str, path: str) -> None:
    """Record job read path for schema migration tracking (Sprint 60 Phase 2.2).

    Args:
        workspace_id: Workspace identifier
        path: Read path used (new, old, miss)
    """
    if not _PROM_AVAILABLE or not _METRICS_INITIALIZED:
        return

    try:
        _relay_job_read_path_total.labels(workspace_id=workspace_id, path=path).inc()
    except Exception as exc:
        _LOG.warning("Failed to record job read path metric: %s", exc)


def record_job_list_read_path(workspace_id: str, path: str) -> None:
    """Record job list read path for schema migration tracking (Sprint 60 Phase 2.2).

    Args:
        workspace_id: Workspace identifier
        path: Read path used (new, mixed)
    """
    if not _PROM_AVAILABLE or not _METRICS_INITIALIZED:
        return

    try:
        _relay_job_list_read_path_total.labels(workspace_id=workspace_id, path=path).inc()
    except Exception as exc:
        _LOG.warning("Failed to record job list read path metric: %s", exc)


def record_job_list_results(workspace_id: str, count: int) -> None:
    """Record number of job results returned by list operation (Sprint 60 Phase 2.2).

    Args:
        workspace_id: Workspace identifier
        count: Number of jobs returned
    """
    if not _PROM_AVAILABLE or not _METRICS_INITIALIZED:
        return

    try:
        _relay_job_list_results_total.labels(workspace_id=workspace_id).inc(count)
    except Exception as exc:
        _LOG.warning("Failed to record job list results metric: %s", exc)
