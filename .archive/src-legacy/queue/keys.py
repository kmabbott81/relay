"""Redis key helpers for AI Orchestrator v0.1.

Sprint 55 Week 3: Standardized Redis key generation.
"""


def ai_job_key(job_id: str) -> str:
    """Get Redis key for AI job data.

    Args:
        job_id: Job identifier

    Returns:
        Redis hash key for job data
    """
    return f"ai:job:{job_id}"


def ai_queue_key() -> str:
    """Get Redis key for AI job queue.

    Returns:
        Redis list key for job queue
    """
    return "ai:queue:pending"


def ai_idempotency_key(client_request_id: str) -> str:
    """Get Redis key for idempotency tracking.

    Args:
        client_request_id: Client-provided request ID

    Returns:
        Redis key for idempotency check
    """
    return f"ai:idempotency:{client_request_id}"
