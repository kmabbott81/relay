"""Shared corpus cache for tests to avoid repeated loads."""
from __future__ import annotations

from functools import lru_cache


@lru_cache(maxsize=1)
def load_small_corpus() -> list[str]:
    """Load tiny corpus for speed; sufficient to exercise code paths."""
    return ["alpha", "beta", "gamma", "delta"]


@lru_cache(maxsize=1)
def load_medium_corpus() -> list[str]:
    """Load representative but not huge corpus."""
    base = ["one", "two", "three", "four", "five"]
    return base * 50  # ~250 items, adjust if needed
