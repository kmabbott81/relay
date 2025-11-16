"""
Backoff Policy (Sprint 29)

Exponential backoff with capped delay and jitter for job retries.
"""

import random


def compute_delay(base_ms: int, attempt: int, cap_ms: int, jitter_pct: float) -> int:
    """
    Compute retry delay with exponential backoff, cap, and jitter.

    Args:
        base_ms: Base delay in milliseconds
        attempt: Retry attempt number (0-indexed)
        cap_ms: Maximum delay in milliseconds
        jitter_pct: Jitter percentage (0.0-1.0)

    Returns:
        Delay in milliseconds

    Example:
        >>> compute_delay(500, 0, 60000, 0.2)  # First retry
        ~500-600ms (500 + 0-20% jitter)
        >>> compute_delay(500, 3, 60000, 0.2)  # Fourth retry
        ~4000-4800ms (500 * 2^3 + jitter)
    """
    if attempt < 0:
        attempt = 0

    # Exponential: base * 2^attempt
    delay = base_ms * (2**attempt)

    # Apply cap
    delay = min(delay, cap_ms)

    # Apply jitter: delay * (1 + random(-jitter_pct, +jitter_pct))
    if jitter_pct > 0:
        jitter_factor = 1.0 + random.uniform(-jitter_pct, jitter_pct)
        delay = int(delay * jitter_factor)

    # Ensure non-negative
    return max(0, delay)
