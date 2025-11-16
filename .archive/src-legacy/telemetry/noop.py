from __future__ import annotations

import logging
import os

_LOG = logging.getLogger(__name__)


def init_noop_if_enabled() -> None:
    """Initialize a no-op telemetry hook if TELEMETRY_ENABLED=true.

    This does NOT change runtime behavior; it only emits a single log line
    to prove wiring, and provides a stable seam for future OTel/Prom backends.
    """
    if str(os.getenv("TELEMETRY_ENABLED", "false")).lower() in {"1", "true", "yes"}:
        _LOG.info("telemetry initialized (noop)")
