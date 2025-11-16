"""Retry logic with exponential backoff and jitter."""

import os
import random
from typing import Optional


def compute_backoff_ms(
    attempt: int,
    base_ms: Optional[int] = None,
    cap_ms: Optional[int] = None,
    jitter_pct: Optional[float] = None,
) -> int:
    """Compute backoff delay with exponential growth and jitter.

    Args:
        attempt: Attempt number (0-indexed)
        base_ms: Base delay in milliseconds (default: RETRY_BASE_MS=400)
        cap_ms: Maximum delay cap (default: RETRY_CAP_MS=60000)
        jitter_pct: Jitter percentage 0.0-1.0 (default: RETRY_JITTER_PCT=0.2)

    Returns:
        Delay in milliseconds
    """
    base_ms = base_ms if base_ms is not None else int(os.environ.get("RETRY_BASE_MS", "400"))
    cap_ms = cap_ms if cap_ms is not None else int(os.environ.get("RETRY_CAP_MS", "60000"))
    jitter_pct = jitter_pct if jitter_pct is not None else float(os.environ.get("RETRY_JITTER_PCT", "0.2"))

    # Exponential: base * 2^attempt
    delay = base_ms * (2**attempt)

    # Cap delay
    delay = min(delay, cap_ms)

    # Add jitter: ±jitter_pct
    jitter_range = delay * jitter_pct
    jitter = random.uniform(-jitter_range, jitter_range)
    delay = int(delay + jitter)

    # Ensure positive
    return max(delay, 0)
