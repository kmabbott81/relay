"""Polling utilities to replace time.sleep() in tests."""
from __future__ import annotations

import time


def wait_until(predicate, timeout: float = 2.0, interval: float = 0.01) -> bool:
    """Wait until predicate returns True or timeout expires.

    Args:
        predicate: Callable that returns bool when condition is met
        timeout: Maximum time to wait in seconds (default: 2.0)
        interval: Polling interval in seconds (default: 0.01)

    Returns:
        bool: True if predicate succeeded, False if timed out
    """
    start = time.perf_counter()
    while time.perf_counter() - start < timeout:
        if predicate():
            return True
        time.sleep(interval)
    return False
