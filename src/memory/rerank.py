"""Cross-encoder reranker for memory query results

TASK C: GPU-Accelerated Semantic Reranking

Provides:
- rerank(query, candidates, timeout_ms) → reranked results with circuit breaker
- get_cross_encoder() → lazy-loaded model on GPU
- maybe_rerank(query, candidates) → feature-flagged reranking

Circuit breaker: If reranking exceeds timeout_ms, skip CE and return ANN order (fail-open).
This ensures query latency remains under budget even if GPU is slow.
"""

import asyncio
import logging
import os
import time
from typing import Any

logger = logging.getLogger(__name__)


def _check_cuda() -> bool:
    """Check if CUDA is available without importing torch yet."""
    try:
        import torch

        return torch.cuda.is_available()
    except ImportError:
        return False


# Feature flag: Enable/disable reranking
RERANK_ENABLED = os.getenv("RERANK_ENABLED", "true").lower() == "true"

# Circuit breaker timeout (ms)
RERANK_TIMEOUT_MS = float(os.getenv("RERANK_TIMEOUT_MS", "250"))

# Cross-encoder model (TinyBERT for speed on consumer GPUs)
CROSS_ENCODER_MODEL = os.getenv("CROSS_ENCODER_MODEL", "cross-encoder/ms-marco-TinyBERT-L-2-v2")

# Device (cuda:0 if available, else cpu)
_cuda_available = _check_cuda()
DEVICE = "cuda" if _cuda_available else "cpu"

# Global model instance (lazy-loaded)
_cross_encoder_instance = None


class RerankedResult:
    """Result from reranking: (candidate, score, index)"""

    def __init__(self, candidate: str, score: float, original_index: int):
        self.candidate = candidate
        self.score = score
        self.original_index = original_index

    def __repr__(self):
        return f"RerankedResult({self.candidate[:30]}..., score={self.score:.3f})"


def get_cross_encoder():
    """Lazy-load cross-encoder model on first call.

    Loads ms-marco-TinyBERT-L-2-v2 model on DEVICE (cuda:0 or cpu).
    Subsequent calls return cached instance.

    Returns:
        CrossEncoder model instance

    Raises:
        ImportError: If sentence_transformers not installed
        RuntimeError: If model download fails
    """
    global _cross_encoder_instance

    if _cross_encoder_instance is not None:
        return _cross_encoder_instance

    try:
        from sentence_transformers import CrossEncoder

        logger.info(f"Loading cross-encoder model: {CROSS_ENCODER_MODEL}")
        logger.info(f"Device: {DEVICE}")

        start = time.time()
        model = CrossEncoder(CROSS_ENCODER_MODEL, device=DEVICE)
        elapsed = time.time() - start

        logger.info(f"Model loaded in {elapsed:.2f}s on {DEVICE}")
        _cross_encoder_instance = model
        return model

    except ImportError as e:
        logger.error(f"sentence_transformers not installed: {e}")
        raise ImportError(
            "sentence_transformers required for reranking. " "Install: pip install sentence-transformers"
        ) from e
    except Exception as e:
        logger.error(f"Failed to load cross-encoder model: {e}")
        raise RuntimeError(f"Model loading failed: {e}") from e


async def rerank(query: str, candidates: list[str], timeout_ms: float = RERANK_TIMEOUT_MS) -> list[RerankedResult]:
    """Rerank candidates using cross-encoder with circuit breaker.

    If reranking exceeds timeout_ms, skip CE and return original ANN order (fail-open).
    This ensures TTFV doesn't exceed budget even if GPU is overloaded.

    Args:
        query: User query string
        candidates: List of candidate passages (typically 24-32 from ANN search)
        timeout_ms: Max time allowed for reranking (default: 250ms)
                   If exceeded, returns ANN order without reranking

    Returns:
        List of RerankedResult sorted by CE score (highest first)
        If timeout exceeded, returns candidates in ANN order

    Example:
        >>> query = "How do I reset my password?"
        >>> candidates = ["Reset password...", "Change password...", "Security..."]
        >>> results = await rerank(query, candidates)
        >>> results[0].candidate  # Best match
        "Reset password..."
    """
    try:
        # Guard: No candidates
        if not candidates:
            return []

        # Guard: Single candidate (no need to rerank)
        if len(candidates) == 1:
            return [RerankedResult(candidates[0], 1.0, 0)]

        # Time the reranking operation
        start = time.time()

        def _rerank_blocking():
            """Blocking reranking call (runs in thread pool)"""
            try:
                model = get_cross_encoder()

                # Create query-candidate pairs
                pairs = [(query, candidate) for candidate in candidates]

                # Score all pairs
                scores = model.predict(pairs)

                return scores

            except Exception as e:
                logger.error(f"Reranking failed: {e}")
                return None

        # Run blocking operation in thread pool to avoid blocking async loop
        loop = asyncio.get_event_loop()
        scores = await asyncio.wait_for(
            loop.run_in_executor(None, _rerank_blocking), timeout=timeout_ms / 1000.0  # Convert ms to seconds
        )

        elapsed_ms = (time.time() - start) * 1000

        if scores is None:
            logger.warning("Reranking returned None, returning ANN order")
            return [RerankedResult(c, 0.0, i) for i, c in enumerate(candidates)]

        # Sort by score (highest first)
        ranked = sorted(
            [RerankedResult(candidate, score, i) for i, (candidate, score) in enumerate(zip(candidates, scores))],
            key=lambda x: x.score,
            reverse=True,
        )

        logger.debug(
            f"Reranked {len(candidates)} candidates in {elapsed_ms:.1f}ms "
            f"(p95 budget: 150ms, timeout: {timeout_ms}ms)"
        )

        return ranked

    except asyncio.TimeoutError:
        # Circuit breaker: Timeout exceeded
        logger.warning(f"Reranking timeout ({timeout_ms}ms) exceeded, " f"returning ANN order (fail-open)")
        return [RerankedResult(c, 0.0, i) for i, c in enumerate(candidates)]

    except Exception as e:
        # Fail-open: Any other error, return ANN order
        logger.error(f"Reranking error: {e}, returning ANN order")
        return [RerankedResult(c, 0.0, i) for i, c in enumerate(candidates)]


async def maybe_rerank(query: str, candidates: list[str]) -> list[str]:
    """Feature-flagged reranking wrapper.

    If RERANK_ENABLED=true: rerank candidates
    If RERANK_ENABLED=false: return ANN order (no-op)

    Args:
        query: User query string
        candidates: List of candidate passages from ANN search

    Returns:
        List of candidate strings, reranked or ANN order

    Example:
        >>> # With RERANK_ENABLED=true
        >>> result = await maybe_rerank("password reset", ["Reset...", "Forgot..."])
        >>> result[0] == "Reset..."  # Reranked
        True

        >>> # With RERANK_ENABLED=false
        >>> result = await maybe_rerank("password reset", ["Reset...", "Forgot..."])
        >>> result[0] == "Reset..."  # Original ANN order
        True
    """
    if not RERANK_ENABLED:
        logger.debug("Reranking disabled (RERANK_ENABLED=false)")
        return candidates

    try:
        ranked_results = await rerank(query, candidates)
        return [result.candidate for result in ranked_results]

    except Exception as e:
        logger.error(f"maybe_rerank failed: {e}, returning ANN order")
        return candidates


def get_rerank_metrics() -> dict[str, Any]:
    """Get reranking metrics for monitoring.

    Returns:
        Dict with:
        - rerank_enabled: bool
        - model_loaded: bool
        - device: str (cuda:0 or cpu)
        - model_name: str
        - timeout_ms: float
    """
    return {
        "rerank_enabled": RERANK_ENABLED,
        "model_loaded": _cross_encoder_instance is not None,
        "device": DEVICE,
        "model_name": CROSS_ENCODER_MODEL,
        "timeout_ms": RERANK_TIMEOUT_MS,
    }
