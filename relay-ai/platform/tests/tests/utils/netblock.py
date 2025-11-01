from __future__ import annotations

import os
import socket
from contextlib import contextmanager

_ALLOWED = {"127.0.0.1", "localhost", "::1"}


class OutboundBlockedSocket(socket.socket):
    def connect(self, address):
        host, *_ = address if isinstance(address, tuple) else (address,)
        try:
            host_ip = socket.gethostbyname(host) if isinstance(host, str) else host
        except Exception:
            host_ip = host
        if str(host) in _ALLOWED or str(host_ip) in _ALLOWED:
            return super().connect(address)
        raise RuntimeError(f"Outbound network blocked to {address}")


@contextmanager
def block_outbound():
    orig = socket.socket
    socket.socket = OutboundBlockedSocket  # type: ignore
    try:
        yield
    finally:
        socket.socket = orig  # type: ignore


def should_block_by_default() -> bool:
    """Determine if outbound network should be blocked by default.

    On CI, block by default. Locally, allow override with TEST_OFFLINE=false.
    """
    val = os.getenv("TEST_OFFLINE", "").strip().lower()
    if "ci" in (os.getenv("GITHUB_ACTIONS") or "").lower():
        return val not in {"0", "false", "no"}
    return val in {"1", "true", "yes"}
