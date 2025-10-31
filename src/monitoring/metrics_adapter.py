"""
Metrics adapter for R2 Knowledge API.

Maps R2 calls to R1 metric collectors (record_query_latency, record_index_operation,
record_security_event) with graceful fallback for missing functions.

No behavior changes to R1 collectors; safe no-op if adapter functions unavailable.
"""

import logging
from typing import Optional

try:
    from src.memory.metrics import get_default_collector
except ImportError:
    get_default_collector = None

logger = logging.getLogger(__name__)


def record_api_error(
    error_code: str,
    status_code: int,
    request_id: Optional[str] = None,
) -> None:
    """
    Record API error for observability.

    Maps to R1: record_security_event(kind="api_error", code=error_code, request_id=...)
    """
    if get_default_collector is None:
        logger.debug(f"[{request_id}] Skipping record_api_error: metrics module unavailable")
        return

    try:
        collector = get_default_collector()
        if hasattr(collector, "record_security_event"):
            collector.record_security_event(
                kind="api_error",
                code=error_code,
                details={"status_code": status_code, "request_id": request_id},
            )
        else:
            logger.debug(f"[{request_id}] record_security_event not available in collector")
    except Exception as e:
        logger.debug(f"[{request_id}] Error recording api_error: {e}")


def record_file_upload(
    file_size_bytes: int,
    mime_type: str,
    request_id: Optional[str] = None,
) -> None:
    """
    Record file upload operation.

    Maps to R1: record_index_operation(op="file_upload", details={...})
    """
    if get_default_collector is None:
        logger.debug(f"[{request_id}] Skipping record_file_upload: metrics module unavailable")
        return

    try:
        collector = get_default_collector()
        if hasattr(collector, "record_index_operation"):
            collector.record_index_operation(
                op="file_upload",
                details={"file_size_bytes": file_size_bytes, "mime_type": mime_type},
            )
        else:
            logger.debug(f"[{request_id}] record_index_operation not available for upload")
    except Exception as e:
        logger.debug(f"[{request_id}] Error recording file_upload: {e}")


def record_vector_search(
    query_tokens: int,
    results_count: int,
    latency_ms: float,
    request_id: Optional[str] = None,
) -> None:
    """
    Record vector search operation.

    Maps to R1: record_query_latency(latency_ms=latency_ms, tokens=query_tokens, ...)
    """
    if get_default_collector is None:
        logger.debug(f"[{request_id}] Skipping record_vector_search: metrics module unavailable")
        return

    try:
        collector = get_default_collector()
        if hasattr(collector, "record_query_latency"):
            collector.record_query_latency(
                latency_ms=latency_ms,
                tokens=query_tokens,
                results_returned=results_count,
            )
        else:
            logger.debug(f"[{request_id}] record_query_latency not available")
    except Exception as e:
        logger.debug(f"[{request_id}] Error recording vector_search: {e}")


def record_index_operation(
    operation: str,
    item_count: int = 0,
    request_id: Optional[str] = None,
) -> None:
    """
    Record indexing operation (uploads, embeddings, chunk indexing).

    Maps to R1: record_index_operation(op=operation, ...)
    """
    if get_default_collector is None:
        logger.debug(f"[{request_id}] Skipping record_index_operation: metrics module unavailable")
        return

    try:
        collector = get_default_collector()
        if hasattr(collector, "record_index_operation"):
            collector.record_index_operation(
                op=operation,
                details={"item_count": item_count},
            )
        else:
            logger.debug(f"[{request_id}] record_index_operation not available")
    except Exception as e:
        logger.debug(f"[{request_id}] Error recording index_operation: {e}")


def record_entities_extract(
    entity_count: int,
    extraction_latency_ms: float,
    request_id: Optional[str] = None,
) -> None:
    """
    Record entity extraction operation.

    Maps to R1: record_index_operation(op="entity_extract", ...)
    """
    if get_default_collector is None:
        logger.debug(f"[{request_id}] Skipping record_entities_extract: metrics module unavailable")
        return

    try:
        collector = get_default_collector()
        if hasattr(collector, "record_index_operation"):
            collector.record_index_operation(
                op="entity_extract",
                details={"entity_count": entity_count, "latency_ms": extraction_latency_ms},
            )
        else:
            logger.debug(f"[{request_id}] record_index_operation not available")
    except Exception as e:
        logger.debug(f"[{request_id}] Error recording entities_extract: {e}")


def record_summarize(
    text_tokens: int,
    summary_tokens: int,
    request_id: Optional[str] = None,
) -> None:
    """
    Record text summarization operation.

    Maps to R1: record_index_operation(op="summarize", ...)
    """
    if get_default_collector is None:
        logger.debug(f"[{request_id}] Skipping record_summarize: metrics module unavailable")
        return

    try:
        collector = get_default_collector()
        if hasattr(collector, "record_index_operation"):
            collector.record_index_operation(
                op="summarize",
                details={"text_tokens": text_tokens, "summary_tokens": summary_tokens},
            )
        else:
            logger.debug(f"[{request_id}] record_index_operation not available")
    except Exception as e:
        logger.debug(f"[{request_id}] Error recording summarize: {e}")
