"""
Metrics adapter stub for Relay MVP.

Provides no-op metric recording functions for beta deployment.
In production, these would send metrics to Prometheus/Grafana.
"""

import logging

logger = logging.getLogger(__name__)


def record_api_error(endpoint: str, error_type: str, **kwargs) -> None:
    """Record API error metric (stub implementation)."""
    logger.debug(f"[Metrics Stub] API Error: {endpoint} - {error_type}")


def record_file_upload(user_id: str, file_size: int, **kwargs) -> None:
    """Record file upload metric (stub implementation)."""
    logger.debug(f"[Metrics Stub] File Upload: user={user_id}, size={file_size}")


def record_index_operation(operation: str, duration_ms: float, **kwargs) -> None:
    """Record index operation metric (stub implementation)."""
    logger.debug(f"[Metrics Stub] Index Op: {operation}, duration={duration_ms}ms")


def record_vector_search(query_type: str, result_count: int, **kwargs) -> None:
    """Record vector search metric (stub implementation)."""
    logger.debug(f"[Metrics Stub] Vector Search: {query_type}, results={result_count}")
