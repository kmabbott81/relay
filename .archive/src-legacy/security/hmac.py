"""HMAC webhook signature verification.

Sprint 57 Step 5: Minimal HMAC implementation for webhook security.
"""
import hashlib
import hmac
import os
from typing import Optional


def compute_signature(body: bytes, secret: str) -> str:
    """Compute HMAC-SHA256 signature for webhook body.

    Args:
        body: Raw request body bytes
        secret: ACTIONS_SIGNING_SECRET from environment

    Returns:
        Hex-encoded HMAC signature
    """
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


def verify_signature(body: bytes, signature: str, secret: str) -> bool:
    """Verify HMAC signature using constant-time comparison.

    Args:
        body: Raw request body bytes
        signature: X-Signature header value
        secret: ACTIONS_SIGNING_SECRET from environment

    Returns:
        True if signature is valid, False otherwise
    """
    expected = compute_signature(body, secret)
    return hmac.compare_digest(expected, signature)


def get_signing_secret() -> Optional[str]:
    """Get ACTIONS_SIGNING_SECRET from environment.

    Returns:
        Secret string if configured, None otherwise
    """
    return os.getenv("ACTIONS_SIGNING_SECRET")
